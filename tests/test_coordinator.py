"""Forwarding: every reading at once; caught up from the recorder on failure."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
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
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.kilowattlas.const import DOMAIN, STORAGE_KEY
from custom_components.kilowattlas.coordinator import (
    MAX_SEND,
    PROBE_WINDOW_SECONDS,
    RETRY_BASE_SECONDS,
    SAVE_DELAY_SECONDS,
    to_kw,
)

from .conftest import (
    BATTERY,
    DISHWASHER,
    ENERGY_PREFS,
    GRID,
    POWER_KW,
    POWER_W,
    SOC,
    SOLAR,
    energy_entry,
    save_energy_prefs,
    set_states,
    setup_entry,
)


def sent(mock_client: MagicMock) -> list[dict[str, Any]]:
    """Every sample sent so far, in order."""
    out: list[dict[str, Any]] = []
    for call in mock_client.ingest.await_args_list:
        out.extend(call.kwargs.get("samples") or [])
    return out


def values(mock_client: MagicMock, key: str = "") -> list[float]:
    """The values sent on one channel."""
    return [s["power_kw"] for s in sent(mock_client) if s.get("channel_key", "") == key]


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (4200, "W", 4.2),
        (4.2, "kW", 4.2),
        (0.0042, "MW", 4.2),
        (4200000, "mW", 4.2),  # milliwatt, not megawatt
        (1, "GW", 1_000_000),
        (1, None, None),
        (1, "kWh", None),
    ],
)
def test_to_kw_uses_power_converter(
    value: float, unit: str | None, expected: float | None
) -> None:
    """Home Assistant's PowerConverter, so mW and MW are no longer confused."""
    result = to_kw(value, unit)
    assert result == pytest.approx(expected) if expected is not None else result is None


async def test_every_channel_sent_in_energy_sign(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Each Energy field is sent as its own channel, sign untouched."""
    hass.states.async_set(SOLAR, "5000", POWER_W)
    hass.states.async_set(GRID, "1.2", POWER_KW)  # importing
    hass.states.async_set(BATTERY, "-2", POWER_KW)  # charging
    hass.states.async_set(SOC, "65", {"unit_of_measurement": "%"})
    hass.states.async_set(DISHWASHER, "2000", POWER_W)
    await hass.async_block_till_done()

    assert values(mock_client, "") == [5.0]
    assert values(mock_client, "grid") == [1.2]
    assert values(mock_client, "battery") == [-2.0]
    assert values(mock_client, "battery_soc") == [65.0]
    assert values(mock_client, "device_sensor.dishwasher_energy") == [2.0]

    call = mock_client.ingest.await_args_list[-1].kwargs
    assert {"channel_key": "grid", "measurement_kind": "grid_power"} in call["channels"]
    assert {
        "channel_key": "device_sensor.dishwasher_energy",
        "measurement_kind": "device_power",
        "name": "Dishwasher",
    } in call["channels"]
    assert call["donor"]["battery_capacity_kwh"] == 10.0


async def test_unticked_battery_does_not_report_its_size(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A battery's size says it exists: unticked, it is not sent either."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    await setup_entry(hass, energy_entry(excluded_channels=["battery", "battery_soc"]))
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()

    call = mock_client.ingest.await_args_list[-1].kwargs
    assert "battery_capacity_kwh" not in (call.get("donor") or {})


async def test_unchanged_value_is_a_reading(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sensor writing the same value again (state_reported) is sent too."""
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    samples = [s for s in sent(mock_client) if "channel_key" not in s]
    assert [s["power_kw"] for s in samples] == [5.0, 5.0]
    assert samples[0]["ts"] < samples[1]["ts"]


async def test_values_present_at_start_are_not_sent(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The value already there at start predates sharing."""
    await hass.async_block_till_done()
    mock_client.ingest.assert_not_awaited()


@pytest.mark.parametrize(
    ("state", "attributes"),
    [
        ("unavailable", POWER_W),
        ("abc", POWER_W),
        ("5", {}),  # no unit: the Energy dashboard would not accept it either
        ("5", {"unit_of_measurement": "kWh"}),
    ],
)
async def test_unusable_readings_are_counted_not_sent(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    state: str,
    attributes: dict[str, str],
) -> None:
    """Nothing is guessed at."""
    hass.states.async_set(SOLAR, state, attributes)
    await hass.async_block_till_done()
    assert sent(mock_client) == []
    assert init_integration.runtime_data.data.unusable == 1


async def test_soc_must_be_percent(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A state of charge without % is not a state of charge."""
    hass.states.async_set(SOC, "50", POWER_KW)
    await hass.async_block_till_done()
    assert values(mock_client, "battery_soc") == []


async def test_failure_retries_with_backoff(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed send keeps the reading and tries again later."""
    mock_client.ingest.side_effect = KilowattlasConnectionError("down")
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    coordinator = init_integration.runtime_data
    assert coordinator.data.status == "retrying"
    assert coordinator.queue_length == 1

    mock_client.ingest.side_effect = None
    freezer.tick(timedelta(seconds=RETRY_BASE_SECONDS + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.data.status == "connected"
    assert coordinator.queue_length == 0
    assert coordinator.cursors[""] == sent(mock_client)[-1]["ts"]


async def test_rejections_are_logged(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rejected reading is not resent, but it is never silent."""
    mock_client.ingest.return_value = IngestResult(
        accepted=0, rejected=[RejectedSample(ts="t", reason="negative_power")]
    )
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    assert "negative_power" in caplog.text
    assert init_integration.runtime_data.data.last_rejected == 1


async def test_revoked_token_starts_reauth(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Revoked on the server: stop, and ask for a new link."""
    mock_client.ingest.side_effect = KilowattlasAuthError("revoked")
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    assert init_integration.runtime_data.data.status == "revoked"
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    # Nothing more is taken in.
    mock_client.ingest.reset_mock()
    hass.states.async_set(SOLAR, "6000", POWER_W)
    await hass.async_block_till_done()
    mock_client.ingest.assert_not_awaited()


async def test_disabled_channel_stops_and_forgets(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Switched off on the web: not sent, not declared, cursor forgotten."""
    hass.states.async_set(GRID, "1.0", POWER_KW)
    await hass.async_block_till_done()
    coordinator = init_integration.runtime_data
    assert "grid" in coordinator.cursors

    mock_client.ingest.return_value = IngestResult(
        accepted=1, config={"config_version": 2, "disabled_channels": ["grid"]}
    )
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    assert "grid" not in coordinator.cursors

    mock_client.ingest.reset_mock()
    hass.states.async_set(GRID, "2.0", POWER_KW)
    hass.states.async_set(SOLAR, "5100", POWER_W)
    await hass.async_block_till_done()
    assert values(mock_client, "grid") == []
    decls = mock_client.ingest.await_args_list[-1].kwargs["channels"]
    assert all(d["channel_key"] != "grid" for d in decls)


async def test_energy_settings_change_is_followed(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A sensor removed from the Energy dashboard stops being shared."""
    prefs = {**ENERGY_PREFS, "device_consumption": []}
    await save_energy_prefs(hass, prefs)
    coordinator = init_integration.runtime_data
    assert DISHWASHER not in {c.entity_id for c in coordinator.channels}
    hass.states.async_set(DISHWASHER, "2500", POWER_W)
    await hass.async_block_till_done()
    assert values(mock_client, "device_sensor.dishwasher_energy") == []


async def test_catch_up_from_recorder_after_restart(
    hass: HomeAssistant,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """What could not be sent before a restart comes from the recorder."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    entry = await setup_entry(hass, energy_entry())

    freezer.tick(timedelta(seconds=5))
    hass.states.async_set(SOLAR, "1000", POWER_W)
    await hass.async_block_till_done()
    assert values(mock_client) == [1.0]

    # The server goes away; three readings cannot be sent.
    mock_client.ingest.side_effect = KilowattlasConnectionError("down")
    for watts in ("2000", "3000", "4000"):
        freezer.tick(timedelta(seconds=5))
        hass.states.async_set(SOLAR, watts, POWER_W)
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Home Assistant is back with the server reachable.
    mock_client.ingest.side_effect = None
    mock_client.ingest.reset_mock()
    freezer.tick(timedelta(seconds=5))
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert values(mock_client) == [2.0, 3.0, 4.0]
    assert not entry.runtime_data.replay_windows


async def test_channel_absent_at_start_never_replays_its_gap(
    hass: HomeAssistant,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sensor removed while stopped: what it measured unshared stays home."""
    key = "device_sensor.dishwasher_energy"
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    entry = await setup_entry(hass, energy_entry())

    freezer.tick(timedelta(seconds=5))
    hass.states.async_set(DISHWASHER, "1000", POWER_W)
    await hass.async_block_till_done()
    assert values(mock_client, key) == [1.0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    await save_energy_prefs(hass, {**ENERGY_PREFS, "device_consumption": []})
    freezer.tick(timedelta(seconds=5))
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert key not in entry.runtime_data.cursors

    freezer.tick(timedelta(seconds=5))
    hass.states.async_set(DISHWASHER, "2500", POWER_W)
    await async_wait_recording_done(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    await save_energy_prefs(hass, ENERGY_PREFS)
    mock_client.ingest.reset_mock()
    freezer.tick(timedelta(seconds=5))
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert values(mock_client, key) == []


async def test_long_outage_spills_to_recorder(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past the in-memory bound, readings wait in the recorder instead."""
    monkeypatch.setattr("custom_components.kilowattlas.coordinator.MAX_QUEUE", 2)
    coordinator = init_integration.runtime_data
    mock_client.ingest.side_effect = KilowattlasConnectionError("down")
    for watts in ("1000", "2000", "3000"):
        freezer.tick(timedelta(seconds=1))  # well inside the first backoff
        hass.states.async_set(SOLAR, watts, POWER_W)
        await hass.async_block_till_done()
    assert coordinator.queue_length == 0
    assert "" in coordinator.replay_windows

    # No waiting for the recorder here: the catch-up must do that itself, or
    # it reads a short history and loses what was not committed yet.
    mock_client.ingest.side_effect = None
    mock_client.ingest.reset_mock()
    freezer.tick(timedelta(seconds=RETRY_BASE_SECONDS * 4))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert values(mock_client) == [1.0, 2.0, 3.0]
    assert not coordinator.replay_windows


async def test_v3_queue_is_carried_over(
    hass: HomeAssistant, mock_client: MagicMock, hass_storage: dict[str, Any]
) -> None:
    """Readings queued by 0.7.0 are sent once after the upgrade."""
    hass_storage[f"{STORAGE_KEY}_entry1"] = {
        "version": 3,
        "minor_version": 1,
        "key": f"{STORAGE_KEY}_entry1",
        "data": {
            "config": {"config_version": 1},
            "queue": [{"ts": "2026-10-29T10:00:00.000000Z", "power_kw": 3.3}],
            "legacy_measurements": [],
            "measured_sample_interval_seconds": 5.0,
        },
    }
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    entry = await setup_entry(hass, energy_entry())
    assert values(mock_client) == [3.3]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    stored = await Store(hass, 4, f"{STORAGE_KEY}_entry1").async_load()
    assert stored["carried_queue"] == []
    assert stored["measured_sample_interval_seconds"] == 5.0


async def test_cursors_are_written_in_batches_not_per_reading(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """An acknowledged batch schedules one write; a run of them shares it."""
    key = f"{STORAGE_KEY}_{init_integration.entry_id}"

    def on_disk() -> dict[str, Any]:
        return (hass_storage.get(key) or {}).get("data", {}).get("last_sent", {})

    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    assert values(mock_client, "") == [5.0]
    assert "" not in on_disk()

    # A second batch well inside the delay rides on the same pending write.
    freezer.tick(timedelta(seconds=SAVE_DELAY_SECONDS / 2))
    async_fire_time_changed(hass)
    hass.states.async_set(SOLAR, "6000", POWER_W)
    await hass.async_block_till_done()
    assert values(mock_client, "") == [5.0, 6.0]
    assert "" not in on_disk()

    # The write lands one delay after the first batch, with the latest cursor.
    freezer.tick(timedelta(seconds=SAVE_DELAY_SECONDS / 2 + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert on_disk()[""]["power_kw"] == 6.0


async def _run_probe(
    hass: HomeAssistant,
    coordinator: Any,
    freezer: FrozenDateTimeFactory,
    gaps: list[int],
) -> None:
    """Run one probe window with the first sensor writing after these gaps."""
    coordinator._start_probe()
    watts = 1000
    for gap in gaps:
        freezer.tick(timedelta(seconds=gap))
        watts += 1
        hass.states.async_set(SOLAR, str(watts), POWER_W)
        await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=PROBE_WINDOW_SECONDS))
    # Well past the window, whatever the loop's own clock has seen.
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PROBE_WINDOW_SECONDS + 1)
    )
    await hass.async_block_till_done()


async def test_rate_probe_takes_the_median(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """One long gap, as after a restart, does not skew the measured rate."""
    coordinator = init_integration.runtime_data
    await _run_probe(hass, coordinator, freezer, [5, 5, 5, 5, 200])
    assert coordinator.data.measured_sample_interval_seconds == 5.0


async def test_inconclusive_rate_probe_keeps_the_previous_rate(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A quiet window is not read as a slow sensor."""
    coordinator = init_integration.runtime_data
    await _run_probe(hass, coordinator, freezer, [5, 5, 5, 5])
    assert coordinator.data.measured_sample_interval_seconds == 5.0
    await _run_probe(hass, coordinator, freezer, [30])
    assert coordinator.data.measured_sample_interval_seconds == 5.0


async def test_rate_probe_restart_does_not_cut_a_running_window(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The daily restart leaves readings already seen in the window."""
    coordinator = init_integration.runtime_data
    coordinator._start_probe()
    watts = 1000
    for _ in range(3):
        freezer.tick(timedelta(seconds=7))
        watts += 1
        hass.states.async_set(SOLAR, str(watts), POWER_W)
        await hass.async_block_till_done()
    coordinator._start_probe()
    await _run_probe(hass, coordinator, freezer, [7, 7])
    assert coordinator.data.measured_sample_interval_seconds == 7.0


async def test_batches_are_bounded(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """No request carries more than MAX_SEND readings."""
    mock_client.ingest.side_effect = KilowattlasConnectionError("down")
    for i in range(MAX_SEND + 10):
        freezer.tick(timedelta(milliseconds=10))
        hass.states.async_set(SOLAR, str(1000 + i), POWER_W)
    await hass.async_block_till_done()
    mock_client.ingest.side_effect = None
    mock_client.ingest.reset_mock()
    freezer.tick(timedelta(seconds=RETRY_BASE_SECONDS + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    sizes = [len(c.kwargs["samples"]) for c in mock_client.ingest.await_args_list]
    assert sizes == [MAX_SEND, 10]
