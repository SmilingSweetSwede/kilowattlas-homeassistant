"""Forwarding behaviour: every reading, at once, queued only on failure."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from aiokilowattlas import (
    IngestResult,
    KilowattlasAuthError,
    KilowattlasConnectionError,
    RejectedSample,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.kilowattlas.const import DOMAIN
from custom_components.kilowattlas.coordinator import (
    MAX_QUEUE,
    MAX_SEND,
    RETRY_BASE_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
    KilowattlasStore,
    rated_battery_kw,
    to_kw,
    to_percent,
)

from .conftest import BATTERY_SENSOR, GRID_SENSOR, SENSOR, SOC_SENSOR, TOKEN


def _samples(mock_client: MagicMock) -> list[dict]:
    """Every raw sample sent across all ingest calls, in order."""
    out: list[dict] = []
    for call in mock_client.ingest.await_args_list:
        out.extend(call.kwargs.get("samples") or [])
    return out


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1500, "W", 1.5),
        (1.5, "kW", 1.5),
        (0.0015, "MW", 1.5),
        (2, None, 2),
        (1, "kWh", None),
    ],
)
def test_to_kw(value: float, unit: str | None, expected: float | None) -> None:
    assert to_kw(value, unit) == expected


async def test_reading_is_sent_immediately(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A state write is forwarded without any timer delay, normalised to kW."""
    mock_client.ingest.reset_mock()
    hass.states.async_set(SENSOR, "3500", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()

    mock_client.ingest.assert_awaited_once()
    call = mock_client.ingest.await_args
    assert call.args == (TOKEN,)
    (sample,) = call.kwargs["samples"]
    assert sample["power_kw"] == 3.5
    assert sample["ts"].endswith("Z")
    assert len(sample["ts"]) == len("2026-10-14T10:00:00.000000Z")  # microseconds
    assert call.kwargs["donor"] == {"config_version": 1}
    # Production only: the 0.1.0 wire format, no channel declarations.
    assert call.kwargs["channels"] is None
    assert "channel_key" not in sample

    assert hass.states.get("sensor.kilowattlas_shared_production").state == "3.5"
    assert hass.states.get("sensor.kilowattlas_queued_readings").state == "0"


async def test_burst_all_readings_sent_distinct(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Ten sub-second readings all reach the server, each with its own timestamp."""
    mock_client.ingest.reset_mock()
    for i in range(10):
        hass.states.async_set(SENSOR, str(1000 + i), {"unit_of_measurement": "W"})
    await hass.async_block_till_done()

    sent = _samples(mock_client)
    assert [s["power_kw"] for s in sent] == [
        round((1000 + i) / 1000, 3) for i in range(10)
    ]
    assert len({s["ts"] for s in sent}) == 10
    # Natural batching: the first went alone, the rest in follow-up requests.
    assert 1 <= mock_client.ingest.await_count <= 10


async def test_unusable_readings_are_counted_not_sent(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """unknown/unavailable, non-numeric and unknown-unit states are not forwarded."""
    mock_client.ingest.reset_mock()
    hass.states.async_set(SENSOR, "unavailable")
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.kilowattlas_shared_production").state == "unavailable"
    )
    hass.states.async_set(SENSOR, "abc", {"unit_of_measurement": "W"})
    hass.states.async_set(SENSOR, "5", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    mock_client.ingest.assert_not_awaited()
    # The counter entity is disabled by default; read the snapshot instead.
    assert init_integration.runtime_data.data.unusable == 3


async def test_failed_send_queues_and_retries_with_backoff(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Nothing is dropped while the server is down; backoff doubles; recovery drains."""
    mock_client.ingest.reset_mock()
    mock_client.ingest.side_effect = KilowattlasConnectionError("down")

    freezer.tick(timedelta(seconds=1))  # frozen clock: advance so last_updated differs
    hass.states.async_set(SENSOR, "1000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kilowattlas_sharing_status").state == "retrying"
    assert hass.states.get("sensor.kilowattlas_queued_readings").state == "1"
    first_calls = mock_client.ingest.await_count

    # New readings during backoff are queued, not sent (respects the backoff).
    freezer.tick(timedelta(seconds=1))  # frozen clock: advance so last_updated differs
    hass.states.async_set(SENSOR, "1100", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert mock_client.ingest.await_count == first_calls
    assert hass.states.get("sensor.kilowattlas_queued_readings").state == "2"

    # Backoff fires, still down.
    freezer.tick(timedelta(seconds=RETRY_BASE_SECONDS + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.ingest.await_count == first_calls + 1

    # Server back: the retry sends both queued readings in one request.
    mock_client.ingest.side_effect = None
    mock_client.ingest.return_value = IngestResult(accepted=2)
    freezer.tick(timedelta(seconds=RETRY_BASE_SECONDS * 2 + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    last = mock_client.ingest.await_args.kwargs["samples"]
    assert [s["power_kw"] for s in last] == [1.0, 1.1]
    assert hass.states.get("sensor.kilowattlas_sharing_status").state == "connected"
    assert hass.states.get("sensor.kilowattlas_queued_readings").state == "0"
    assert hass.states.get("sensor.kilowattlas_last_sent").state != "unknown"


async def test_queue_is_capped_oldest_dropped(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Past MAX_QUEUE the oldest readings go first."""
    coordinator = init_integration.runtime_data
    mock_client.ingest.side_effect = KilowattlasConnectionError("down")
    coordinator._queue = [{"ts": f"t{i}", "power_kw": 1.0} for i in range(MAX_QUEUE)]
    hass.states.async_set(SENSOR, "999", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert len(coordinator._queue) == MAX_QUEUE
    assert coordinator._queue[0]["ts"] == "t1"
    assert coordinator._queue[-1]["power_kw"] == 0.999


async def test_drain_is_split_in_batches(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A big backlog goes out MAX_SEND rows at a time, back to back."""
    coordinator = init_integration.runtime_data
    mock_client.ingest.reset_mock()
    coordinator._queue = [
        {"ts": f"t{i}", "power_kw": 1.0} for i in range(MAX_SEND * 2 + 5)
    ]
    hass.states.async_set(SENSOR, "1", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    sizes = [len(c.kwargs["samples"]) for c in mock_client.ingest.await_args_list]
    assert sizes == [MAX_SEND, MAX_SEND, 6]
    assert coordinator.queue_length == 0


async def test_rejected_readings_are_surfaced(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Server rejections show on the diagnostic sensor and in the log."""
    mock_client.ingest.return_value = IngestResult(
        accepted=0, rejected=[RejectedSample("t", "exceeds_capacity")]
    )
    hass.states.async_set(SENSOR, "99", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.kilowattlas_rejected_readings_in_last_batch").state
        == "1"
    )
    assert "exceeds_capacity" in caplog.text


async def test_revoked_token_stops_sending_and_starts_reauth(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A 401 mid-stream: status revoked, no retries, reauth flow opened, queue kept."""
    mock_client.ingest.reset_mock()
    mock_client.ingest.side_effect = KilowattlasAuthError("revoked")
    hass.states.async_set(SENSOR, "1", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kilowattlas_sharing_status").state == "revoked"
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
    calls = mock_client.ingest.await_count

    # Further readings are neither sent nor retried.
    hass.states.async_set(SENSOR, "2", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert mock_client.ingest.await_count == calls
    assert init_integration.runtime_data.queue_length == 1


async def test_server_config_applied_only_when_newer(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Config documents are adopted by increasing version and clamped."""
    coordinator = init_integration.runtime_data
    assert coordinator.data.config_version == 1  # from get_site at setup

    mock_client.ingest.return_value = IngestResult(
        accepted=1,
        config={"config_version": 5, "slot_seconds": 300, "max_batch": 10**9},
    )
    hass.states.async_set(SENSOR, "1", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert coordinator.data.config_version == 5
    assert coordinator.data.slot_seconds == 300
    assert coordinator.server_config["max_batch"] == 5000

    mock_client.ingest.return_value = IngestResult(
        accepted=1, config={"config_version": 2, "slot_seconds": 60}
    )
    hass.states.async_set(SENSOR, "2", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert coordinator.data.slot_seconds == 300


async def test_attribute_only_event_not_resent(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """An event that does not advance last_updated is a repeat, not new data."""
    coordinator = init_integration.runtime_data
    mock_client.ingest.reset_mock()
    hass.states.async_set(SENSOR, "1", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    state = hass.states.get(SENSOR)
    coordinator._on_state(
        MagicMock(data={"new_state": state, "old_state": state, "entity_id": SENSOR})
    )
    await hass.async_block_till_done()
    assert len(_samples(mock_client)) == 1


async def test_store_v2_migrates_to_legacy_measurements(
    hass: HomeAssistant, hass_storage: dict
) -> None:
    """Old slot means are carried over to be flushed once."""
    hass_storage[f"{STORAGE_KEY}_x"] = {
        "version": 2,
        "minor_version": 1,
        "key": f"{STORAGE_KEY}_x",
        "data": {
            "pending": {
                "2026-01-01T10:00:00Z": {"power_kw": 2.5, "samples": 30},
                "bad": "not-a-dict",
            }
        },
    }
    store = KilowattlasStore(hass, STORAGE_VERSION, f"{STORAGE_KEY}_x")
    data = await store.async_load()
    assert data["queue"] == []
    assert data["legacy_measurements"] == [
        {
            "ts": "2026-01-01T10:00:00Z",
            "power_kw": 2.5,
            "samples": 30,
            "slot_seconds": 900,
        }
    ]
    assert data["config"]["config_version"] == 0


async def test_queue_survives_restart(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    hass_storage: dict,
) -> None:
    """Unsent readings are persisted on stop and sent on the next start."""
    mock_client.ingest.side_effect = KilowattlasConnectionError("down")
    hass.states.async_set(SENSOR, "1", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    stored = hass_storage[f"{STORAGE_KEY}_{init_integration.entry_id}"]["data"]
    assert len(stored["queue"]) == 1

    mock_client.ingest.reset_mock()
    mock_client.ingest.side_effect = None
    await hass.config_entries.async_setup(init_integration.entry_id)
    await hass.async_block_till_done()
    assert [s["power_kw"] for s in _samples(mock_client)] == [1.0]


async def test_rate_probe_measures_median_interval(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """After the startup delay, a 5-minute probe measures the sensor's real rate."""
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for i in range(7):
        freezer.tick(timedelta(seconds=2))
        hass.states.async_set(SENSOR, str(1 + i), {"unit_of_measurement": "kW"})
        await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=301))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert init_integration.runtime_data.data.measured_sample_interval_seconds == 2.0
    # A restart request while a window is running (the daily one) is ignored.
    coordinator = init_integration.runtime_data
    coordinator._start_probe()
    assert coordinator._probe_running
    seen_before = coordinator._probe_seen
    coordinator._start_probe()
    assert coordinator._probe_seen is seen_before
    donor = mock_client.ingest.await_args.kwargs["donor"]
    assert "sample_capability" not in donor  # last send happened before the probe ended
    hass.states.async_set(SENSOR, "9", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    donor = mock_client.ingest.await_args.kwargs["donor"]
    assert donor["sample_capability"] == "realtime_1s"
    assert donor["measured_sample_interval_seconds"] == 2.0


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [(64, "%", 64), (64, " % ", 64), (64, None, None), (64, "kW", None)],
)
def test_to_percent(value: float, unit: str | None, expected: float | None) -> None:
    assert to_percent(value, unit) == expected


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [
        ({"charge_peak_ac": 5.0, "discharge_peak_ac": 7.5}, 5.0),
        ({"charge_peak_ac": "9", "discharge_peak_ac": 6.25}, 6.25),
        ({"charge_peak_ac": 5.0}, None),
        ({"charge_peak_ac": None, "discharge_peak_ac": 7.5}, None),
        ({"charge_peak_ac": 0, "discharge_peak_ac": 7.5}, None),
        ({}, None),
    ],
)
def test_rated_battery_kw(attrs: dict, expected: float | None) -> None:
    assert rated_battery_kw(attrs) == expected


async def test_multi_channel_readings_are_tagged(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration_full: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Each sensor goes to its own channel; signs follow Kilowattlas' convention."""
    coordinator = init_integration_full.runtime_data
    assert [c.channel_key for c in coordinator.channels] == [
        "",
        "battery",
        "grid",
        "battery_soc",
    ]
    assert coordinator.sensor == SENSOR
    # Rated power picked up from the SoC sensor present at start.
    assert coordinator.data.battery_power_kw == 5.0

    mock_client.ingest.reset_mock()
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(SENSOR, "3210", {"unit_of_measurement": "W"})
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(BATTERY_SENSOR, "-1.5", {"unit_of_measurement": "kW"})
    # Grid sensor reports import as positive: 0.9 kW import = -0.9 kW export.
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(GRID_SENSOR, "900", {"unit_of_measurement": "W"})
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(
        SOC_SENSOR,
        "64",
        {"unit_of_measurement": "%", "charge_peak_ac": 5.0, "discharge_peak_ac": 7.5},
    )
    await hass.async_block_till_done()

    sent = _samples(mock_client)
    by_key = {s.get("channel_key"): s["power_kw"] for s in sent}
    assert by_key == {None: 3.21, "battery": -1.5, "grid": -0.9, "battery_soc": 64.0}
    assert len({s["ts"] for s in sent}) == 4  # one timestamp per sensor write
    assert hass.states.get("sensor.kilowattlas_shared_production").state == "3.21"

    # Every push declares the non-production channels by kind and carries
    # the battery's rated power in the donor report.
    call = mock_client.ingest.await_args
    assert call.kwargs["channels"] == [
        {"channel_key": "battery", "measurement_kind": "battery_power"},
        {"channel_key": "grid", "measurement_kind": "net_export"},
        {"channel_key": "battery_soc", "measurement_kind": "battery_soc"},
    ]
    assert call.kwargs["donor"] == {"config_version": 1, "battery_power_kw": 5.0}


async def test_dedupe_is_per_entity(
    hass: HomeAssistant,
    init_integration_full: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Two sensors written in the same instant are two readings, not one."""
    coordinator = init_integration_full.runtime_data
    mock_client.ingest.reset_mock()
    hass.states.async_set(SENSOR, "1", {"unit_of_measurement": "kW"})
    hass.states.async_set(BATTERY_SENSOR, "2", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert len(_samples(mock_client)) == 2
    # A repeated event for the battery alone is still a repeat.
    state = hass.states.get(BATTERY_SENSOR)
    coordinator._on_state(
        MagicMock(
            data={"new_state": state, "old_state": state, "entity_id": BATTERY_SENSOR}
        )
    )
    await hass.async_block_till_done()
    assert len(_samples(mock_client)) == 2
    # An event for an entity the coordinator does not share is ignored.
    coordinator._on_state(
        MagicMock(data={"new_state": state, "old_state": state, "entity_id": "sensor.x"})
    )
    await hass.async_block_till_done()
    assert len(_samples(mock_client)) == 2


async def test_soc_without_percent_unit_is_unusable(
    hass: HomeAssistant,
    init_integration_full: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """A state of charge is never normalised as a power; wrong unit = unusable."""
    coordinator = init_integration_full.runtime_data
    mock_client.ingest.reset_mock()
    hass.states.async_set(SOC_SENSOR, "64", {"unit_of_measurement": "kW"})
    hass.states.async_set(SOC_SENSOR, "unavailable")
    await hass.async_block_till_done()
    mock_client.ingest.assert_not_awaited()
    assert coordinator.data.unusable == 2
    # The production sensor's availability is untouched by the SoC sensor.
    assert coordinator.data.source_available
    assert hass.states.get("sensor.kilowattlas_shared_production").state == "4.2"


async def test_battery_rating_refreshes_from_attributes(
    hass: HomeAssistant,
    init_integration_full: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """A changed rating on the SoC sensor reaches the next donor report."""
    hass.states.async_set(
        SOC_SENSOR,
        "65",
        {"unit_of_measurement": "%", "charge_peak_ac": 9.0, "discharge_peak_ac": 8.0},
    )
    await hass.async_block_till_done()
    assert mock_client.ingest.await_args.kwargs["donor"]["battery_power_kw"] == 8.0
    # Attributes gone: the last known rating is kept, not blanked.
    hass.states.async_set(SOC_SENSOR, "66", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert "battery_power_kw" not in mock_client.ingest.await_args.kwargs["donor"]
    assert init_integration_full.runtime_data.data.battery_power_kw is None


async def test_rate_probe_classifies_minute_source(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration_full: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """A cloud-polled sensor writing once a minute is batch_15min, not inconclusive.

    Only the production sensor is timed: the battery writing in between must
    not make the site look faster than its production feed is.
    """
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for i in range(4):
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set(BATTERY_SENSOR, str(i), {"unit_of_measurement": "kW"})
        freezer.tick(timedelta(seconds=30))
        hass.states.async_set(SENSOR, str(1 + i), {"unit_of_measurement": "kW"})
        await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert init_integration_full.runtime_data.data.measured_sample_interval_seconds == 60.0
    hass.states.async_set(SENSOR, "9", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    donor = mock_client.ingest.await_args.kwargs["donor"]
    assert donor["sample_capability"] == "batch_15min"
    assert donor["measured_sample_interval_seconds"] == 60.0


async def test_rate_probe_two_deltas_is_inconclusive(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Fewer than three deltas never concludes (a cloudy night must not downgrade)."""
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for i in range(3):
        freezer.tick(timedelta(seconds=90))
        hass.states.async_set(SENSOR, str(1 + i), {"unit_of_measurement": "kW"})
        await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=301))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert init_integration.runtime_data.data.measured_sample_interval_seconds is None
