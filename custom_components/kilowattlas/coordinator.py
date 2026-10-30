"""Forward every reading of the shared Energy-dashboard sensors to Kilowattlas.

The source (inverter, meter, battery system) sets the pace. Whenever one of the
shared sensors writes a value, that value is sent: a changed value
(`state_changed`) and an unchanged one written again (`state_reported`) alike,
at whatever rate the sensor delivers. Nothing here samples, thins or
averages; the server computes slot means.

Which sensors are shared, and their sign, comes from the Energy dashboard
(energy_source.py). Values are converted to kW with Home Assistant's own
`PowerConverter` and otherwise sent exactly as the Energy dashboard reads them.

The site owner can switch any channel off on kilowattlas.com. The server then
lists it in the config document's `disabled_channels`, and the coordinator
stops sending it entirely until a newer config removes it again.

Durability comes from Home Assistant's recorder, not from a queue of our own.
The coordinator persists, per channel, the timestamp of the newest reading the
server acknowledged (its cursor). Readings that could not be sent (network
down, server down, Home Assistant restarted) are read back from the recorder's
history after that cursor and sent then. The in-memory queue only holds what
is waiting for the request in flight or the next retry.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from statistics import median
from typing import Any

from aiokilowattlas import (
    DEFAULT_CONFIG,
    KilowattlasAuthError,
    KilowattlasClient,
    KilowattlasError,
    capability_tier,
    is_channel_disabled,
    resolve_config,
    SiteDetails,
)
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import state_changes_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfPower
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import PowerConverter

from .const import (
    SIGNAL_STATUS_UPDATED,
    DOMAIN,
    STATUS_CONNECTED,
    STATUS_RETRYING,
    STATUS_REVOKED,
    STATUS_STARTING,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .energy_source import Channel

_LOGGER = logging.getLogger(__name__)

type KilowattlasConfigEntry = ConfigEntry[KilowattlasCoordinator]

# Rate probe. A passive subscription that measures how often the first shared
# sensor really writes, so the server can tell a donor that CAN deliver 1 s
# data from one that merely said so. Never asks any integration to fetch.
PROBE_WINDOW_SECONDS = 300
PROBE_STARTUP_DELAY_SECONDS = 60  # let HA's boot burst settle first
PROBE_MIN_DELTAS = 3

# In-memory queue bound. Past it the queue is dropped and the readings are
# read back from the recorder once the server is reachable again.
MAX_QUEUE = 20_000

# Rows per request (and per recorder read), kept under the server's own
# max_batch so a catch-up is split across several calls.
MAX_SEND = 500

# How far back the recorder is read. The server accepts raw readings up to
# ten days old, which is also the recorder's default retention.
MAX_REPLAY = timedelta(days=10) - timedelta(hours=1)

# How long a catch-up waits for the recorder to commit what it has queued.
RECORDER_COMMIT_TIMEOUT_SECONDS = 30

# Backoff between failed sends: short enough that a blip costs seconds, long
# enough that a server down for an hour is not probed hundreds of times.
RETRY_BASE_SECONDS = 10
RETRY_MAX_SECONDS = 300

UNAVAILABLE_STATES = {None, "", "unknown", "unavailable"}


def format_ts(ts: datetime) -> str:
    """Server timestamp: UTC, microseconds, Z. Sorts as text."""
    return ts.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_ts(value: str) -> datetime | None:
    """Inverse of format_ts; None for anything unreadable."""
    return dt_util.parse_datetime(value)


def to_kw(value: float, unit: str | None) -> float | None:
    """A power reading in kW, by Home Assistant's PowerConverter.

    None for a missing or unknown unit: the Energy dashboard does not accept
    a power sensor without one either.
    """
    if not unit:
        return None
    try:
        return PowerConverter.convert(value, unit, UnitOfPower.KILO_WATT)
    except HomeAssistantError:
        return None


def to_percent(value: float, unit: str | None) -> float | None:
    """A state of charge must say it is a percentage; anything else is unusable."""
    if unit is not None and unit.strip() == "%":
        return value
    return None


def reading(channel: Channel, state: State) -> float | None:
    """The value to send for a state of `channel`'s sensor, or None if unusable."""
    if state.state in UNAVAILABLE_STATES:
        return None
    try:
        raw = float(state.state)
    except (TypeError, ValueError):
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    value = to_percent(raw, unit) if channel.percent else to_kw(raw, unit)
    return None if value is None else round(value, 3)


@dataclass(frozen=True, slots=True)
class KilowattlasData:
    """Snapshot the entities render."""

    status: str
    last_push: datetime | None
    pending_count: int
    catching_up: bool
    last_accepted: int
    last_rejected: int
    unusable: int
    measured_sample_interval_seconds: float | None
    slot_seconds: int
    raw_sample_interval_seconds: int
    config_version: int
    shared_channels: int


class KilowattlasStore(Store[dict[str, Any]]):
    """Store that upgrades older buffers in place."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Upgrade an older buffer to v4.

        v1/v2 slot means are still valid measurements and v3 queued readings
        are still valid samples; both are carried over and sent once rather
        than discarded, so a donor upgrading mid-outage keeps their data.
        """
        old_data = old_data or {}
        if old_major_version >= STORAGE_VERSION:
            return old_data
        if old_major_version == 3:
            return {
                "config": old_data.get("config"),
                "cursors": {},
                "replay": {},
                "carried_queue": old_data.get("queue") or [],
                "legacy_measurements": old_data.get("legacy_measurements") or [],
                "measured_sample_interval_seconds": old_data.get(
                    "measured_sample_interval_seconds"
                ),
            }
        legacy: list[dict[str, Any]] = []
        pending = old_data.get("pending", old_data)
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
            "cursors": {},
            "replay": {},
            "carried_queue": [],
            "legacy_measurements": legacy,
            "measured_sample_interval_seconds": None,
        }


class KilowattlasCoordinator(DataUpdateCoordinator[KilowattlasData]):
    """Forwards sensor readings immediately; catches up from the recorder."""

    config_entry: KilowattlasConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: KilowattlasConfigEntry,
        client: KilowattlasClient,
        token: str,
        *,
        site_id: int,
        channels: list[Channel],
        battery_capacity_kwh: float | None = None,
        initial_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialise. Push-based, so no update interval."""
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self._client = client
        self._token = token
        self.site_id = site_id
        self.channels: list[Channel] = []
        self._by_entity: dict[str, Channel] = {}
        self._by_key: dict[str, Channel] = {}
        self._set_channels(channels)
        self._battery_capacity_kwh = battery_capacity_kwh
        self._store = KilowattlasStore(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}"
        )

        self._queue: list[dict[str, Any]] = []
        self._legacy: list[dict[str, Any]] = []
        # Newest acknowledged reading per channel key, as format_ts text.
        self._cursors: dict[str, str] = {}
        # Newest acknowledged value per channel key, for the status page.
        self._last_sent: dict[str, dict[str, Any]] = {}
        # Recorder windows still to send per channel key: [after, before),
        # both format_ts text.
        self._replay: dict[str, list[str]] = {}
        self._config = resolve_config(DEFAULT_CONFIG, initial_config)

        self._unsub_state: CALLBACK_TYPE | None = None
        self._unsub_report: CALLBACK_TYPE | None = None
        self._unsub_retry: CALLBACK_TYPE | None = None
        self._unsub_probe: CALLBACK_TYPE | None = None
        self._unsub_probe_daily: CALLBACK_TYPE | None = None

        self._sending = False
        self._stopping = False
        self._retry_delay = RETRY_BASE_SECONDS
        self._unavailable_logged = False

        self._status = STATUS_STARTING
        self._last_push: datetime | None = None
        self._last_accepted = 0
        self._last_rejected = 0
        self._unusable = 0
        self._measured_interval: float | None = None
        self._probe_running = False
        self._probe_seen: list[datetime] = []
        # Per entity: the newest reading taken, so one write is never sent twice.
        self._last_ts: dict[str, datetime] = {}

    def _set_channels(self, channels: list[Channel]) -> None:
        self.channels = list(channels)
        self._by_entity = {c.entity_id: c for c in channels}
        self._by_key = {c.key: c for c in channels}

    # --- read-only views ------------------------------------------------------

    @property
    def server_config(self) -> dict[str, Any]:
        """The server-directed policy currently in effect."""
        return dict(self._config)

    @property
    def cursors(self) -> dict[str, str]:
        """Newest acknowledged reading per channel key."""
        return dict(self._cursors)

    async def async_get_site_details(self) -> SiteDetails:
        """The owner's description of the installation, as last saved anywhere."""
        return await self._client.get_site_details(self._token)

    async def async_save_site_details(
        self, details: dict[str, Any], revision: str
    ) -> SiteDetails:
        """Save the description; refused if it changed elsewhere since `revision`."""
        return await self._client.update_site_details(self._token, details, revision)

    @property
    def last_sent(self) -> dict[str, dict[str, Any]]:
        """Newest acknowledged value and its time per channel key."""
        return {k: dict(v) for k, v in self._last_sent.items()}

    def channel_disabled(self, channel_key: str) -> bool:
        """Whether the owner switched this channel off on kilowattlas.com."""
        return self._disabled(channel_key)

    @property
    def replay_windows(self) -> dict[str, list[str]]:
        """Recorder windows still to be sent per channel key."""
        return {k: list(v) for k, v in self._replay.items()}

    def _disabled(self, channel_key: str) -> bool:
        """Whether the owner switched this channel off on kilowattlas.com."""
        return is_channel_disabled(self._config, channel_key)

    @property
    def _active(self) -> list[Channel]:
        return [c for c in self.channels if not self._disabled(c.key)]

    @property
    def _channel_decls(self) -> list[dict[str, Any]]:
        """What the server is told about channels it may not have yet.

        Sent with every push (a few bytes); the server applies the kind only
        on creation. A channel the owner switched off is not declared either.
        """
        decls: list[dict[str, Any]] = []
        for c in self._active:
            if not c.key:
                continue  # the default channel needs no declaration
            decl: dict[str, Any] = {"channel_key": c.key, "measurement_kind": c.kind}
            if c.name:
                decl["name"] = c.name
            decls.append(decl)
        return decls

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
            last_push=self._last_push,
            pending_count=len(self._queue) + len(self._legacy),
            catching_up=bool(self._replay),
            last_accepted=self._last_accepted,
            last_rejected=self._last_rejected,
            unusable=self._unusable,
            measured_sample_interval_seconds=self._measured_interval,
            slot_seconds=int(self._config["slot_seconds"]),
            raw_sample_interval_seconds=int(
                self._config.get("raw_sample_interval_seconds", 10)
            ),
            config_version=int(self._config["config_version"]),
            shared_channels=len(self._active),
        )

    @callback
    def _publish(self) -> None:
        self.async_set_updated_data(self._snapshot())
        async_dispatcher_send(self.hass, SIGNAL_STATUS_UPDATED)

    # --- lifecycle ------------------------------------------------------------

    async def async_start(self) -> None:
        """Load the cursors, subscribe to the sensors and catch up."""
        stored = await self._store.async_load() or {}
        stored_cfg = stored.get("config")
        if isinstance(stored_cfg, dict) and int(
            stored_cfg.get("config_version", 0)
        ) > int(self._config["config_version"]):
            self._config = resolve_config(self._config, stored_cfg)
        # A channel gone from the settings while stopped loses its cursor, as in
        # async_update_channels: if it returns, it starts with its next reading.
        self._cursors = {
            str(k): str(v)
            for k, v in (stored.get("cursors") or {}).items()
            if k in self._by_key
        }
        self._replay = {
            str(k): [str(v[0]), str(v[1])]
            for k, v in (stored.get("replay") or {}).items()
            if k in self._by_key and isinstance(v, list) and len(v) == 2
        }
        self._last_sent = {
            str(k): v
            for k, v in (stored.get("last_sent") or {}).items()
            if k in self._by_key and isinstance(v, dict)
        }
        self._queue = [
            q for q in stored.get("carried_queue") or [] if isinstance(q, dict)
        ]
        self._legacy = [
            m for m in stored.get("legacy_measurements") or [] if isinstance(m, dict)
        ]
        self._measured_interval = stored.get("measured_sample_interval_seconds")
        self._forget_disabled()
        self._log_disabled_change(frozenset())

        started = dt_util.utcnow()
        self._subscribe(started)
        # What happened while Home Assistant was stopped, or while the server
        # could not be reached before that, is in the recorder.
        for channel in self._active:
            if cursor := self._cursors.get(channel.key):
                self._extend_replay(channel.key, cursor, format_ts(started))

        self._unsub_probe = async_call_later(
            self.hass, PROBE_STARTUP_DELAY_SECONDS, self._start_probe
        )
        self._unsub_probe_daily = async_track_time_change(
            self.hass, self._start_probe, hour=12, minute=0, second=0
        )

        self._status = STATUS_CONNECTED
        self._publish()
        if self._queue or self._legacy or self._replay:
            self._schedule_send()

    @callback
    def _subscribe(self, now: datetime) -> None:
        """Track every active channel's sensor from `now` on."""
        self._unsubscribe()
        entities = [c.entity_id for c in self._active]
        for entity_id in entities:
            # The value at subscription time predates it: it was sent before,
            # or comes from the recorder. Only newer writes are taken live.
            self._last_ts[entity_id] = now
        if not entities:
            return
        # Event-driven, not polled: a timer can only observe at the rate it
        # ticks. Subscribing delivers every value the sources write.
        self._unsub_state = async_track_state_change_event(
            self.hass, entities, self._on_state
        )
        self._unsub_report = async_track_state_report_event(
            self.hass, entities, self._on_report
        )

    @callback
    def _unsubscribe(self) -> None:
        for unsub in (self._unsub_state, self._unsub_report):
            if unsub:
                unsub()
        self._unsub_state = self._unsub_report = None

    async def async_update_channels(
        self, channels: list[Channel], battery_capacity_kwh: float | None
    ) -> None:
        """Follow a change of the Energy settings without a reload.

        A new channel starts with its next reading; a removed one stops. What
        is already queued is still sent: it was measured while it was shared.
        """
        before = {c.key for c in self.channels}
        self._set_channels(channels)
        self._battery_capacity_kwh = battery_capacity_kwh
        for key in before - set(self._by_key):
            self._cursors.pop(key, None)
            self._last_sent.pop(key, None)
            self._replay.pop(key, None)
        if self._status != STATUS_REVOKED:
            self._subscribe(dt_util.utcnow())
        await self._save()
        self._publish()

    async def async_stop(self) -> None:
        """Unsubscribe, make one last send attempt and persist the cursors."""
        self._stopping = True
        self._unsubscribe()
        for unsub in (self._unsub_retry, self._unsub_probe, self._unsub_probe_daily):
            if unsub:
                unsub()
        self._unsub_retry = self._unsub_probe = self._unsub_probe_daily = None
        if (
            (self._queue or self._legacy)
            and not self._sending
            and self._status != STATUS_REVOKED
        ):
            # A failure is handled inside; the recorder keeps the readings.
            await self._send_batch()
        # What could not be sent is in the recorder: catch up from there.
        self._spill_queue()
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "config": self._config,
                "cursors": self._cursors,
                "last_sent": self._last_sent,
                "replay": self._replay,
                "carried_queue": [],
                "legacy_measurements": self._legacy,
                "measured_sample_interval_seconds": self._measured_interval,
            }
        )

    # --- capture --------------------------------------------------------------

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        """A sensor wrote a new value (or new attributes)."""
        state = event.data["new_state"]
        self._take(
            event.data["entity_id"], state, state.last_updated if state else None
        )

    @callback
    def _on_report(self, event: Event[EventStateReportedData]) -> None:
        """A sensor wrote the same value again: a real reading all the same."""
        self._take(
            event.data["entity_id"],
            event.data["new_state"],
            event.data["last_reported"],
        )

    @callback
    def _take(self, entity_id: str, state: State | None, ts: datetime | None) -> None:
        """Queue one reading and send it right away."""
        channel = self._by_entity.get(entity_id)
        if (
            channel is None
            or self._disabled(channel.key)
            or state is None
            or ts is None
        ):
            return
        if self._probe_running and channel is self._active[0]:
            self._probe_seen.append(ts)
        value = reading(channel, state)
        if value is None:
            # Unavailable, not a number, or a unit that cannot be interpreted:
            # counted, never guessed at.
            self._unusable += 1
            self._publish()
            return
        last = self._last_ts.get(entity_id)
        if last is not None and ts <= last:
            return
        self._last_ts[entity_id] = ts
        self._enqueue(self._sample(channel, ts, value))
        self._schedule_send()
        self._publish()

    @staticmethod
    def _sample(channel: Channel, ts: datetime, value: float) -> dict[str, Any]:
        sample: dict[str, Any] = {"ts": format_ts(ts), "power_kw": value}
        if channel.key:
            sample["channel_key"] = channel.key
        return sample

    def _enqueue(self, sample: dict[str, Any]) -> None:
        self._queue.append(sample)
        if len(self._queue) > MAX_QUEUE:
            _LOGGER.info(
                "%d readings waiting; the rest will be sent from the recorder",
                len(self._queue),
            )
            self._spill_queue()

    def _spill_queue(self) -> None:
        """Drop the in-memory queue; a recorder window covers it instead.

        The window spans exactly the dropped readings of each channel. It may
        include readings the server already has (live ones sent while older
        ones waited); a resent reading carries no weight in the server's
        time-weighted mean, so that costs bandwidth, never accuracy.
        """
        one = timedelta(microseconds=1)
        for sample in self._queue:
            key = sample.get("channel_key") or ""
            ts = parse_ts(sample["ts"])
            if ts is None or key not in self._by_key:
                continue
            self._extend_replay(key, format_ts(ts - one), format_ts(ts + one))
        self._queue = []

    def _extend_replay(self, key: str, after: str, before: str) -> None:
        oldest = format_ts(dt_util.utcnow() - MAX_REPLAY)
        after = max(after, oldest)
        if after >= before:
            return
        if window := self._replay.get(key):
            self._replay[key] = [min(window[0], after), max(window[1], before)]
        else:
            self._replay[key] = [after, before]

    @callback
    def _schedule_send(self) -> None:
        """Send now, unless a send is in flight or a backoff is pending.

        In-flight: the running send re-checks the queue when it finishes, so
        readings that arrived meanwhile go out in the very next request. Backoff
        pending: the retry timer will send everything queued.
        """
        if (
            self._sending
            or self._unsub_retry
            or self._stopping
            or self._status == STATUS_REVOKED
        ):
            return
        self.config_entry.async_create_background_task(
            self.hass, self._send(), f"{DOMAIN}_send", eager_start=True
        )

    # --- catch up from the recorder ---------------------------------------------

    async def _load_replay(self) -> None:
        """Move the next chunk of recorder history into the queue."""
        # The recorder commits every few seconds. A window read before that
        # would come back short and be dropped, losing those readings for good.
        try:
            async with asyncio.timeout(RECORDER_COMMIT_TIMEOUT_SECONDS):
                await get_instance(self.hass).async_block_till_done()
        except TimeoutError:
            _LOGGER.debug("Recorder has not committed; catching up later")
            self._schedule_retry()
            return
        for key in list(self._replay):
            channel = self._by_key.get(key)
            if channel is None or self._disabled(key):
                del self._replay[key]
                continue
            after, before = self._replay[key]
            start, end = parse_ts(after), parse_ts(before)
            if start is None or end is None:
                del self._replay[key]
                continue
            history = await get_instance(self.hass).async_add_executor_job(
                partial(
                    state_changes_during_period,
                    self.hass,
                    start,
                    end,
                    channel.entity_id,
                    descending=False,
                    limit=MAX_SEND,
                    include_start_time_state=False,
                )
            )
            states = history.get(channel.entity_id, [])
            samples = []
            for state in states:
                value = reading(channel, state)
                if value is not None:
                    samples.append(self._sample(channel, state.last_updated, value))
            if len(states) < MAX_SEND:
                del self._replay[key]
            else:
                self._replay[key] = [format_ts(states[-1].last_updated), before]
            if samples:
                # At most MAX_SEND, ahead of the live readings. Never spills:
                # the window for what follows is still in self._replay.
                self._queue = samples + self._queue
                return

    # --- send -----------------------------------------------------------------

    async def _send(self) -> None:
        """Send what is queued, then whatever the recorder still owes."""
        if self._sending:
            return
        self._sending = True
        try:
            while self._status != STATUS_REVOKED:
                if not (self._queue or self._legacy) and self._replay:
                    await self._load_replay()
                if not (self._queue or self._legacy):
                    break
                if not await self._send_batch():
                    break
        finally:
            self._sending = False
            self._publish()

    async def _send_batch(self) -> bool:
        """Push one batch. Only what was acknowledged leaves the queue."""
        batch = self._queue[:MAX_SEND]
        legacy = self._legacy[:MAX_SEND] or None
        try:
            result = await self._client.ingest(
                self._token,
                samples=batch or None,
                measurements=legacy,
                donor=self._donor_report(),
                channels=self._channel_decls or None,
            )
        except KilowattlasAuthError:
            # The token was revoked on the server. Retrying cannot help; the
            # user has to approve a new link. The recorder keeps the readings.
            self._status = STATUS_REVOKED
            self._unsubscribe()
            self._spill_queue()
            await self._save()
            self.config_entry.async_start_reauth(self.hass)
            return False
        except KilowattlasError as err:
            self._status = STATUS_RETRYING
            if not self._unavailable_logged:
                _LOGGER.info("Cannot send to Kilowattlas, readings are queued: %s", err)
                self._unavailable_logged = True
            else:
                _LOGGER.debug("Send failed (%s); %d queued", err, len(self._queue))
            self._schedule_retry()
            return False

        # Slice by count, never clear: readings that arrived DURING the
        # request are at the tail and must survive.
        del self._queue[: len(batch)]
        if legacy:
            del self._legacy[: len(legacy)]
        for sample in batch:
            key = sample.get("channel_key") or ""
            if key in self._by_key and sample["ts"] > self._cursors.get(key, ""):
                self._cursors[key] = sample["ts"]
                self._last_sent[key] = {
                    "ts": sample["ts"],
                    "power_kw": sample["power_kw"],
                }

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
        return True

    @callback
    def _schedule_retry(self) -> None:
        if self._unsub_retry or self._stopping:
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
        if self._battery_capacity_kwh is not None:
            report["battery_capacity_kwh"] = self._battery_capacity_kwh
        return report

    # --- rate probe -----------------------------------------------------------

    @callback
    def _start_probe(self, _now: datetime | None = None) -> None:
        """Measure how often the first shared sensor actually writes."""
        if self._probe_running or not self._active:
            return  # the daily restart must not cut a running window short
        if self._unsub_probe:
            self._unsub_probe()
            self._unsub_probe = None
        self._probe_running = True
        self._probe_seen = []

        @callback
        def _finish(_now: datetime) -> None:
            self._unsub_probe = None
            self._probe_running = False
            self._finish_probe()

        self._unsub_probe = async_call_later(self.hass, PROBE_WINDOW_SECONDS, _finish)

    @callback
    def _finish_probe(self) -> None:
        """Conclude the probe, or leave the previous rate alone.

        An inconclusive probe must never be read as "this sensor is slow": one
        quiet night would permanently downgrade a fast donor.
        """
        deltas = [
            (b - a).total_seconds()
            for a, b in zip(self._probe_seen, self._probe_seen[1:], strict=False)
            if (b - a).total_seconds() > 0
        ]
        if len(deltas) < PROBE_MIN_DELTAS:
            _LOGGER.debug("Rate probe inconclusive (%d deltas)", len(deltas))
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
        before = self._disabled_set()
        self._config = resolve_config(self._config, incoming)
        if self._log_disabled_change(before):
            self._forget_disabled()
            if self._status != STATUS_REVOKED:
                # Resubscribe: a re-enabled channel resumes with its NEXT
                # reading, exactly as after a restart.
                self._subscribe(dt_util.utcnow())
        _LOGGER.debug(
            "Applied server config v%d (slot %d s, target sample %d s)",
            self._config["config_version"],
            self._config["slot_seconds"],
            self._config.get("raw_sample_interval_seconds", 10),
        )

    def _disabled_set(self) -> frozenset[str]:
        return frozenset(self._config.get("disabled_channels") or ())

    def _log_disabled_change(self, before: frozenset[str]) -> bool:
        """Log once per change of the owner's switched-off set. True if changed."""
        after = self._disabled_set()
        if after == before:
            return False
        if stopped := sorted(after - before):
            _LOGGER.info(
                "Kilowattlas stopped sharing channel(s) %s as set on kilowattlas.com",
                ", ".join(stopped),
            )
        if resumed := sorted(before - after):
            _LOGGER.info(
                "Kilowattlas resumed sharing channel(s) %s as set on kilowattlas.com",
                ", ".join(resumed),
            )
        return True

    def _forget_disabled(self) -> None:
        """Drop everything of switched-off channels: queue, cursor, catch-up.

        Without its cursor a channel switched back on starts afresh and never
        sends what was measured while it was off.
        """
        before = len(self._queue) + len(self._legacy)
        self._queue = [
            q for q in self._queue if not self._disabled(q.get("channel_key") or "")
        ]
        # Slot means inherited from before 0.5.0 are production.
        if self._disabled(""):
            self._legacy = []
        for key in list(self._cursors) + list(self._replay):
            if self._disabled(key):
                self._cursors.pop(key, None)
                self._replay.pop(key, None)
        if dropped := before - len(self._queue) - len(self._legacy):
            _LOGGER.debug("Dropped %d queued reading(s) of disabled channels", dropped)
