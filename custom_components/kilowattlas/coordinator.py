"""Capture every reading of a power sensor and forward it to Kilowattlas at once.

The source (inverter or meter) sets the pace. Whenever its Home Assistant sensor
writes a value, that value is sent, at whatever rate the sensor delivers:
several times a second, once a second, once a minute. Nothing here samples,
thins or averages. The server stages raw readings and computes slot means.

What the coordinator adds is durability. A reading that cannot be sent (network
down, server down) waits in a persisted queue and goes out on the next
successful connection, with capped exponential backoff in between. There is no
timer that holds readings back: the queue exists only for readings that could
not be sent the moment they arrived.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median
from typing import Any

from aiokilowattlas import (
    DEFAULT_CONFIG,
    KilowattlasAuthError,
    KilowattlasClient,
    KilowattlasError,
    capability_tier,
    resolve_config,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    STATUS_CONNECTED,
    STATUS_RETRYING,
    STATUS_REVOKED,
    STATUS_STARTING,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

type KilowattlasConfigEntry = ConfigEntry[KilowattlasCoordinator]

# Rate probe. A passive subscription that measures how often the sensor really
# updates, so the server can tell a donor that CAN deliver 1 s data from one
# that merely said so. Never asks any integration to fetch.
PROBE_WINDOW_SECONDS = 300
PROBE_STARTUP_DELAY_SECONDS = 60  # let HA's boot burst settle first
PROBE_MIN_DELTAS = 5

# Retry queue bounds. Roughly an hour at a few readings per second; past that the
# OLDEST are dropped, since the server cannot use samples older than its
# retention window anyway.
MAX_QUEUE = 20_000

# Rows per request, kept under the server's own max_batch so a drain after an
# outage is split across several calls rather than rejected wholesale.
MAX_SEND = 500

# Backoff between failed sends: short enough that a blip costs seconds, long
# enough that a server down for an hour is not probed hundreds of times.
RETRY_BASE_SECONDS = 10
RETRY_MAX_SECONDS = 300

UNAVAILABLE_STATES = {None, "", "unknown", "unavailable"}


@dataclass(frozen=True, slots=True)
class KilowattlasData:
    """Snapshot the entities render."""

    status: str
    current_kw: float | None
    source_available: bool
    last_push: datetime | None
    pending_count: int
    last_accepted: int
    last_rejected: int
    unusable: int
    measured_sample_interval_seconds: float | None
    slot_seconds: int
    raw_sample_interval_seconds: int
    config_version: int


class KilowattlasStore(Store[dict[str, Any]]):
    """Store that upgrades older buffers in place."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Upgrade a v1/v2 buffer (slot means) to the v3 raw-sample queue.

        Slot means are still valid measurements and the server still accepts
        that shape, so they are carried into a separate list and flushed once
        rather than discarded: a donor upgrading mid-outage keeps their data.
        """
        if old_major_version >= STORAGE_VERSION:
            return old_data
        legacy: list[dict[str, Any]] = []
        pending = (old_data or {}).get("pending", old_data or {})
        for ts, entry in pending.items():
            if not isinstance(entry, dict):
                continue
            legacy.append(
                {
                    "ts": ts,
                    "power_kw": entry.get("power_kw"),
                    "samples": entry.get("samples", 0),
                    "slot_seconds": entry.get(
                        "slot_seconds", DEFAULT_CONFIG["slot_seconds"]
                    ),
                }
            )
        if legacy:
            _LOGGER.info(
                "Buffer migrated to v%d: %d pre-aggregated slot(s) will be sent once",
                STORAGE_VERSION,
                len(legacy),
            )
        return {
            "config": resolve_config(DEFAULT_CONFIG, None),
            "queue": [],
            "legacy_measurements": legacy,
            "measured_sample_interval_seconds": None,
        }


def to_kw(value: float, unit: str | None) -> float | None:
    """Normalise a power reading to kW. None for a unit we cannot interpret."""
    if unit is None:
        return value  # a sensor without a unit is assumed to report kW
    match unit.strip().lower():
        case "kw":
            return value
        case "w":
            return value / 1000.0
        case "mw":
            return value * 1000.0
    return None


class KilowattlasCoordinator(DataUpdateCoordinator[KilowattlasData]):
    """Forwards sensor readings to Kilowattlas immediately; queues only on failure."""

    config_entry: KilowattlasConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: KilowattlasConfigEntry,
        client: KilowattlasClient,
        token: str,
        *,
        site_id: int,
        sensor: str,
        initial_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialise. Push-based, so no update interval."""
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self._client = client
        self._token = token
        self.site_id = site_id
        self.sensor = sensor
        self._store = KilowattlasStore(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}"
        )

        self._queue: list[dict[str, Any]] = []
        self._legacy: list[dict[str, Any]] = []
        self._config = resolve_config(DEFAULT_CONFIG, initial_config)

        self._unsub_state: CALLBACK_TYPE | None = None
        self._unsub_retry: CALLBACK_TYPE | None = None
        self._unsub_probe: CALLBACK_TYPE | None = None
        self._unsub_probe_daily: CALLBACK_TYPE | None = None

        self._sending = False
        self._retry_delay = RETRY_BASE_SECONDS
        self._unavailable_logged = False

        self._status = STATUS_STARTING
        self._last_push: datetime | None = None
        self._last_accepted = 0
        self._last_rejected = 0
        self._current_kw: float | None = None
        self._source_available = False
        self._unusable = 0
        self._measured_interval: float | None = None
        self._probe_running = False
        self._probe_seen: list[datetime] = []
        self._probe_values: list[float] = []
        # HA fires a state event on attribute-only changes too; this is what
        # keeps the same reading from being forwarded twice.
        self._last_ts: datetime | None = None

    # --- read-only views ------------------------------------------------------

    @property
    def server_config(self) -> dict[str, Any]:
        """The server-directed policy currently in effect."""
        return dict(self._config)

    @property
    def queue_length(self) -> int:
        """Readings captured but not yet acknowledged."""
        return len(self._queue)

    @property
    def legacy_queue_length(self) -> int:
        """Slot means inherited from an older version, not yet sent."""
        return len(self._legacy)

    def _snapshot(self) -> KilowattlasData:
        return KilowattlasData(
            status=self._status,
            current_kw=self._current_kw,
            source_available=self._source_available,
            last_push=self._last_push,
            pending_count=len(self._queue) + len(self._legacy),
            last_accepted=self._last_accepted,
            last_rejected=self._last_rejected,
            unusable=self._unusable,
            measured_sample_interval_seconds=self._measured_interval,
            slot_seconds=int(self._config["slot_seconds"]),
            raw_sample_interval_seconds=int(
                self._config.get("raw_sample_interval_seconds", 10)
            ),
            config_version=int(self._config["config_version"]),
        )

    @callback
    def _publish(self) -> None:
        self.async_set_updated_data(self._snapshot())

    # --- lifecycle ------------------------------------------------------------

    async def async_start(self) -> None:
        """Load the queue, subscribe to the sensor and flush anything left over."""
        stored = await self._store.async_load() or {}
        # A config fetched live at setup is newer than, or equal to, the stored
        # one; resolve_config keeps whichever has the higher version.
        stored_cfg = stored.get("config")
        if isinstance(stored_cfg, dict) and int(
            stored_cfg.get("config_version", 0)
        ) > int(self._config["config_version"]):
            self._config = resolve_config(self._config, stored_cfg)
        self._queue = [q for q in stored.get("queue", []) if isinstance(q, dict)]
        self._legacy = [
            m for m in stored.get("legacy_measurements", []) if isinstance(m, dict)
        ]
        self._measured_interval = stored.get("measured_sample_interval_seconds")

        # Show the sensor's current value right away, but do not send it: it
        # predates this start and the next write will arrive on its own.
        current = self.hass.states.get(self.sensor)
        self._source_available = (
            current is not None and current.state not in UNAVAILABLE_STATES
        )
        if current is not None and self._source_available:
            try:
                kw = to_kw(
                    float(current.state), current.attributes.get("unit_of_measurement")
                )
            except (TypeError, ValueError):
                kw = None
            if kw is not None:
                self._current_kw = round(kw, 3)
            self._last_ts = current.last_updated

        # Event-driven, not polled: a timer can only observe at the rate it
        # ticks. Subscribing delivers every value the source writes.
        self._unsub_state = async_track_state_change_event(
            self.hass, [self.sensor], self._on_state
        )
        self._unsub_probe = async_call_later(
            self.hass, PROBE_STARTUP_DELAY_SECONDS, self._start_probe
        )
        self._unsub_probe_daily = async_track_time_change(
            self.hass, self._start_probe, hour=12, minute=0, second=0
        )

        self._status = STATUS_CONNECTED
        self._publish()

        if self._queue or self._legacy:
            self._schedule_send()

    async def async_stop(self) -> None:
        """Unsubscribe, make one last send attempt and persist the queue."""
        for unsub in (
            self._unsub_state,
            self._unsub_retry,
            self._unsub_probe,
            self._unsub_probe_daily,
        ):
            if unsub:
                unsub()
        self._unsub_state = self._unsub_retry = None
        self._unsub_probe = self._unsub_probe_daily = None
        if (self._queue or self._legacy) and self._status != STATUS_REVOKED:
            try:
                await self._send()
            except (
                KilowattlasError
            ):  # a shutdown flush that fails just waits for next start
                _LOGGER.debug("Final send failed; readings stay queued")
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "config": self._config,
                "queue": self._queue,
                "legacy_measurements": self._legacy,
                "measured_sample_interval_seconds": self._measured_interval,
            }
        )

    # --- capture --------------------------------------------------------------

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        """Queue a reading and send it right away."""
        state = event.data["new_state"]
        if state is None or state.state in UNAVAILABLE_STATES:
            self._source_available = False
            self._unusable += 1
            self._publish()
            return
        self._source_available = True
        try:
            raw = float(state.state)
        except (TypeError, ValueError):
            self._unusable += 1
            self._publish()
            return
        kw = to_kw(raw, state.attributes.get("unit_of_measurement"))
        if kw is None:
            # An unrecognised unit is not a glitch: the sensor cannot be
            # interpreted at all. Counted, not guessed at.
            self._unusable += 1
            self._publish()
            return

        # last_updated advances on every write by the source integration, even
        # when the value did not change: a steady 4.2 kW for a minute is many
        # real readings, not one.
        ts = state.last_updated
        if self._last_ts is not None and ts <= self._last_ts:
            return
        self._last_ts = ts

        self._current_kw = round(kw, 3)
        self._queue.append(
            {
                # Microseconds: two readings in the same millisecond stay two
                # rows in order, and the server measures received - ts latency.
                "ts": ts.astimezone(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
                "power_kw": round(kw, 3),
            }
        )
        if len(self._queue) > MAX_QUEUE:
            dropped = len(self._queue) - MAX_QUEUE
            del self._queue[:dropped]
            _LOGGER.warning("Queue full; dropped %d oldest reading(s)", dropped)

        self._schedule_send()
        self._publish()

    @callback
    def _schedule_send(self) -> None:
        """Send now, unless a send is in flight or a backoff is pending.

        In-flight: the running send re-checks the queue when it finishes, so
        readings that arrived meanwhile go out in the very next request. Backoff
        pending: the retry timer will send everything queued.
        """
        if self._sending or self._unsub_retry or self._status == STATUS_REVOKED:
            return
        self.config_entry.async_create_background_task(
            self.hass, self._send(), f"{DOMAIN}_send", eager_start=True
        )

    # --- send -----------------------------------------------------------------

    async def _send(self) -> None:
        """Push queued readings. Only what was sent leaves the queue."""
        if self._sending or not (self._queue or self._legacy):
            return
        self._sending = True
        try:
            batch = self._queue[:MAX_SEND]
            legacy = self._legacy[:MAX_SEND] or None
            result = await self._client.ingest(
                self._token,
                samples=batch or None,
                measurements=legacy,
                donor=self._donor_report(),
            )
            # Slice by count, never clear: readings that arrived DURING the
            # request are at the tail and must survive.
            del self._queue[: len(batch)]
            if legacy:
                del self._legacy[: len(legacy)]

            self._last_accepted = result.accepted
            self._last_rejected = len(result.rejected)
            if result.rejected:
                # Permanently invalid, so resending is pointless, but a silent
                # rejection is indistinguishable from healthy operation.
                reasons = sorted({r.reason for r in result.rejected})
                _LOGGER.warning(
                    "Server rejected %d reading(s): %s",
                    len(result.rejected),
                    ", ".join(reasons),
                )
            self._apply_config(result.config)
            self._last_push = dt_util.utcnow()
            self._status = STATUS_CONNECTED
            self._retry_delay = RETRY_BASE_SECONDS
            if self._unavailable_logged:
                _LOGGER.info("Connection to Kilowattlas restored")
                self._unavailable_logged = False
            await self._save()
        except KilowattlasAuthError:
            # The token was revoked on the server. Retrying cannot help; the
            # user has to approve a new link. Keep the queue for after reauth.
            self._status = STATUS_REVOKED
            if self._unsub_state:
                self._unsub_state()
                self._unsub_state = None
            await self._save()
            self.config_entry.async_start_reauth(self.hass)
        except KilowattlasError as err:
            self._status = STATUS_RETRYING
            if not self._unavailable_logged:
                _LOGGER.info("Cannot send to Kilowattlas, readings are queued: %s", err)
                self._unavailable_logged = True
            else:
                _LOGGER.debug("Send failed (%s); %d queued", err, len(self._queue))
            await self._save()
            self._schedule_retry()
        finally:
            self._sending = False
            self._publish()

        # Readings that arrived while the request was in flight go out now.
        if self._status == STATUS_CONNECTED and (self._queue or self._legacy):
            self._schedule_send()

    @callback
    def _schedule_retry(self) -> None:
        if self._unsub_retry:
            return

        @callback
        def _fire(_now: datetime) -> None:
            self._unsub_retry = None
            self._schedule_send()

        self._unsub_retry = async_call_later(self.hass, self._retry_delay, _fire)
        self._retry_delay = min(self._retry_delay * 2, RETRY_MAX_SECONDS)

    def _donor_report(self) -> dict[str, Any]:
        report: dict[str, Any] = {"config_version": self._config["config_version"]}
        if self._measured_interval is not None:
            report["measured_sample_interval_seconds"] = self._measured_interval
            report["sample_capability"] = capability_tier(self._measured_interval)
        return report

    # --- rate probe -----------------------------------------------------------

    @callback
    def _start_probe(self, _now: datetime | None = None) -> None:
        """Measure how often the sensor actually updates."""
        if self._probe_running:
            return  # the daily restart must not cut a running window short
        if self._unsub_probe:
            self._unsub_probe()
            self._unsub_probe = None
        self._probe_running = True
        self._probe_seen = []
        self._probe_values = []
        unsub_events = async_track_state_change_event(
            self.hass, [self.sensor], self._on_probe_event
        )

        @callback
        def _finish(_now: datetime) -> None:
            unsub_events()
            self._unsub_probe = None
            self._probe_running = False
            self._finish_probe()

        self._unsub_probe = async_call_later(self.hass, PROBE_WINDOW_SECONDS, _finish)

    @callback
    def _on_probe_event(self, event: Event[EventStateChangedData]) -> None:
        state = event.data["new_state"]
        if state is None or state.state in UNAVAILABLE_STATES:
            return
        if not self._probe_seen or state.last_updated != self._probe_seen[-1]:
            self._probe_seen.append(state.last_updated)
        try:
            self._probe_values.append(float(state.state))
        except (TypeError, ValueError):
            pass

    @callback
    def _finish_probe(self) -> None:
        """Conclude the probe, or leave the previous rate alone.

        An inconclusive probe must never be read as "this sensor is slow": one
        cloudy night would permanently downgrade a fast donor.
        """
        deltas = [
            (b - a).total_seconds()
            for a, b in zip(self._probe_seen, self._probe_seen[1:], strict=False)
            if (b - a).total_seconds() > 0
        ]
        if len(deltas) < PROBE_MIN_DELTAS:
            _LOGGER.debug("Rate probe inconclusive (%d deltas)", len(deltas))
            return
        if self._probe_values and not any(v != 0 for v in self._probe_values):
            _LOGGER.debug("Rate probe saw only zeros (inverter asleep); not concluding")
            return
        # Median, not mean: one restart-induced gap must not skew it.
        self._measured_interval = round(median(deltas), 3)
        _LOGGER.debug("Measured sensor rate: %.3f s", self._measured_interval)
        self._publish()

    # --- config ---------------------------------------------------------------

    def _apply_config(self, incoming: dict[str, Any] | None) -> None:
        """Adopt a server config document if it is newer than the one held."""
        if not isinstance(incoming, dict):
            return
        try:
            incoming_version = int(incoming.get("config_version", 0))
        except (TypeError, ValueError):
            return
        if incoming_version <= int(self._config["config_version"]):
            return
        self._config = resolve_config(self._config, incoming)
        _LOGGER.debug(
            "Applied server config v%d (slot %d s, target sample %d s)",
            self._config["config_version"],
            self._config["slot_seconds"],
            self._config.get("raw_sample_interval_seconds", 10),
        )
