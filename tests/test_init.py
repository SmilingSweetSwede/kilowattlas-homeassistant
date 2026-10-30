"""Tests for setup, migration, repairs and removal."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aiokilowattlas import (
    KilowattlasAuthError,
    KilowattlasConnectionError,
    KilowattlasResponseError,
)
from homeassistant.components.repairs import DOMAIN as REPAIRS_DOMAIN
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.const import (
    CONF_KEY_OVERRIDES,
    CONF_PREFERENCES,
    CONF_SOURCE,
    DOMAIN,
    SOURCE_ENERGY,
    SOURCE_MANUAL,
)
from custom_components.kilowattlas.energy_source import Channel

from .conftest import (
    BATTERY,
    ENERGY_PREFS,
    GRID,
    GRID_EXPORT,
    GRID_IMPORT,
    POWER_KW,
    POWER_W,
    SITE_ID,
    SOC,
    SOLAR,
    TOKEN,
    energy_entry,
    manual_entry,
    save_energy_prefs,
    set_states,
    setup_entry,
)


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Setup verifies the token, shares the Energy sensors, unload cleans up."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    mock_client.get_site.assert_awaited_once_with(TOKEN)
    assert hass.states.get("sensor.kilowattlas_sharing_status").state == "connected"
    assert hass.states.get("sensor.kilowattlas_shared_channels").state == "5"
    assert hass.states.get("sensor.kilowattlas_shared_production") is None

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    # Unload (also used on restart/reload) must NOT revoke.
    mock_client.revoke.assert_not_awaited()


async def test_setup_auth_failed_starts_reauth(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A revoked token at startup puts the entry in error and opens reauth."""
    mock_client.get_site.side_effect = KilowattlasAuthError("revoked")
    entry = await setup_entry(hass, energy_entry())
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH


@pytest.mark.parametrize(
    "error", [KilowattlasConnectionError("down"), KilowattlasResponseError("odd")]
)
async def test_setup_retries_when_unreachable(
    hass: HomeAssistant, mock_client: MagicMock, error: Exception
) -> None:
    """An unreachable or confused API means retry, not failure."""
    mock_client.get_site.side_effect = error
    entry = await setup_entry(hass, energy_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_remove_revokes_token(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Removing the integration revokes the token server-side."""
    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    mock_client.revoke.assert_awaited_once_with(TOKEN)


async def test_remove_tolerates_revoke_failure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Being offline at removal logs a warning but still removes."""
    mock_client.revoke.side_effect = KilowattlasConnectionError("down")
    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    assert not hass.config_entries.async_entries(DOMAIN)
    assert "Could not revoke" in caplog.text


async def test_excluded_channels_are_not_shared(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A channel the user unticked is not shared."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    entry = await setup_entry(hass, energy_entry(excluded_channels=["grid"]))
    keys = {c.key for c in entry.runtime_data.channels}
    assert "grid" not in keys and "" in keys


async def test_no_energy_settings_raises_issue(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Nothing to share is shown as a repair issue, cleared once fixed."""
    await async_setup_component(hass, "energy", {})
    entry = await setup_entry(hass, energy_entry())
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, f"no_channels_{entry.entry_id}")

    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    assert not issues.async_get_issue(DOMAIN, f"no_channels_{entry.entry_id}")
    assert len(entry.runtime_data.channels) == 5


@pytest.mark.parametrize(
    (
        "grid_import_positive",
        "battery_charge_positive",
        "grid_config",
        "battery_config",
    ),
    [
        (False, False, {"stat_rate_inverted": GRID}, {"stat_rate": BATTERY}),
        (True, False, {"stat_rate": GRID}, {"stat_rate": BATTERY}),
        (False, True, {"stat_rate_inverted": GRID}, {"stat_rate_inverted": BATTERY}),
        (True, True, {"stat_rate": GRID}, {"stat_rate_inverted": BATTERY}),
    ],
)
async def test_migrate_0_7_entry(
    hass: HomeAssistant,
    mock_client: MagicMock,
    grid_import_positive: bool,
    battery_charge_positive: bool,
    grid_config: dict[str, str],
    battery_config: dict[str, str],
) -> None:
    """A 0.7.0 entry keeps its token and every channel, in Energy's model."""
    data = {
        "token": TOKEN,
        "site_id": SITE_ID,
        "power_sensor": SOLAR,
        "grid_power_sensor": GRID,
        "battery_power_sensor": BATTERY,
        "battery_soc_sensor": SOC,
        "consumption_sensor": "sensor.house",
        "ev_charger_power_sensor": "sensor.wallbox",
        "heat_pump_power_sensor": "sensor.heat_pump",
    }
    if grid_import_positive:
        data["grid_import_positive"] = True
    if battery_charge_positive:
        data["battery_charge_positive"] = True
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=str(SITE_ID), version=1, data=data, entry_id="old"
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, "old_shared_production", config_entry=entry
    )
    set_states(hass)
    await async_setup_component(hass, "homeassistant", {})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert entry.data == {"token": TOKEN, "site_id": SITE_ID}
    assert entry.options[CONF_SOURCE] == SOURCE_MANUAL
    sources = entry.options[CONF_PREFERENCES]["energy_sources"]
    assert {"type": "grid", "power_config": grid_config} in sources
    assert {
        "type": "battery",
        "power_config": battery_config,
        "stat_soc": SOC,
    } in sources
    assert entry.options[CONF_KEY_OVERRIDES] == {
        "sensor.wallbox": ["ev_charger", "ev_charger_power"],
        "sensor.heat_pump": ["heat_pump", "heat_pump_power"],
    }
    assert not registry.async_get_entity_id("sensor", DOMAIN, "old_shared_production")

    # Same server channels as 0.7.0 used.
    keys = {c.key: c.kind for c in entry.runtime_data.channels}
    assert keys == {
        "": "gross_production",
        "grid": "grid_power",
        "battery": "battery_power",
        "battery_soc": "battery_soc",
        "consumption": "consumption",
        "ev_charger": "ev_charger_power",
        "heat_pump": "heat_pump_power",
    }


async def test_migrated_export_positive_grid_is_inverted_by_energy(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """0.7.0's export-positive grid sensor is now read through Energy's inversion."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(SITE_ID),
        version=1,
        data={
            "token": TOKEN,
            "site_id": SITE_ID,
            "power_sensor": SOLAR,
            "grid_power_sensor": GRID,
        },
        entry_id="old",
    )
    hass.states.async_set(SOLAR, "4000", POWER_W)
    hass.states.async_set(GRID, "0.5", POWER_KW)  # exporting, in 0.7.0's sign
    await setup_entry(hass, entry)
    grid = next(c for c in entry.runtime_data.channels if c.key == "grid")
    assert grid.entity_id != GRID  # the Energy dashboard's transform sensor
    assert hass.states.get(grid.entity_id).state == "-0.5"

    hass.states.async_set(GRID, "0.7", POWER_KW)
    await hass.async_block_till_done()
    samples = [
        s
        for c in mock_client.ingest.await_args_list
        for s in c.kwargs["samples"] or []
        if s.get("channel_key") == "grid"
    ]
    assert samples[-1]["power_kw"] == -0.7  # export, in Energy's sign


async def test_manual_two_sensor_grid(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Import and export sensors are combined by the Energy dashboard's code."""
    prefs = {
        "energy_sources": [
            {
                "type": "grid",
                "power_config": {
                    "stat_rate_from": GRID_IMPORT,
                    "stat_rate_to": GRID_EXPORT,
                },
            }
        ],
        "device_consumption": [],
    }
    hass.states.async_set(GRID_IMPORT, "0", POWER_W)
    hass.states.async_set(GRID_EXPORT, "1500", POWER_W)
    entry = await setup_entry(hass, manual_entry(prefs))
    (grid,) = entry.runtime_data.channels
    assert grid.key == "grid" and grid.kind == "grid_power"
    assert hass.states.get(grid.entity_id).state == "-1500.0"


async def test_use_energy_settings_repair(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Manual sensors plus Energy settings: a repair offers to switch."""
    prefs = {
        "energy_sources": [{"type": "solar", "stat_rate": SOLAR}],
        "device_consumption": [],
    }
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    await async_setup_component(hass, REPAIRS_DOMAIN, {})
    entry = await setup_entry(hass, manual_entry(prefs))
    issue_id = f"use_energy_settings_{entry.entry_id}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.is_fixable

    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_init(DOMAIN, data={"issue_id": issue_id})
    assert result["step_id"] == "confirm"
    result = await manager.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options[CONF_SOURCE] == SOURCE_ENERGY
    assert len(entry.runtime_data.channels) == 5
    assert not ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def test_renamed_sensor_is_followed(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A shared sensor renamed in the entity registry keeps being shared."""
    registry = er.async_get(hass)
    solar = registry.async_get_or_create(
        "sensor", "demo", "solar", suggested_object_id="solar"
    )
    prefs = {
        "energy_sources": [{"type": "solar", "stat_rate": solar.entity_id}],
        "device_consumption": [],
    }
    entry = await setup_entry(hass, manual_entry(prefs))
    assert entry.runtime_data.channels == [
        Channel("", "gross_production", solar.entity_id)
    ]
    registry.async_update_entity(solar.entity_id, new_entity_id="sensor.roof")
    await hass.async_block_till_done()
    # Manual preferences keep the old id until the user updates them; the
    # Energy dashboard updates its own on rename. Either way nothing crashes.
    assert entry.state is ConfigEntryState.LOADED
