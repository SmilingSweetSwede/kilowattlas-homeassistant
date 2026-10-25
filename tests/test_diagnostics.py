"""Tests for diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import BATTERY_SENSOR, SENSOR, TOKEN


async def test_diagnostics_redacts_token(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    diag = await async_get_config_entry_diagnostics(hass, init_integration)
    assert diag["entry"]["token"] == "**REDACTED**"
    assert diag["entry"]["power_sensor"] == SENSOR
    assert TOKEN not in str(diag)
    assert diag["state"]["status"] == "connected"
    assert diag["server_config"]["slot_seconds"] == 900
    assert diag["queue_length"] == 0
    assert diag["channels"] == [
        {
            "entity_id": SENSOR,
            "channel_key": "",
            "kind": "gross_production",
            "invert": False,
            "percent": False,
        }
    ]
    assert diag["state"]["battery_power_kw"] is None


async def test_diagnostics_lists_every_channel(
    hass: HomeAssistant, init_integration_full: MockConfigEntry
) -> None:
    diag = await async_get_config_entry_diagnostics(hass, init_integration_full)
    assert TOKEN not in str(diag)
    keys = [(c["channel_key"], c["kind"], c["invert"]) for c in diag["channels"]]
    assert keys == [
        ("", "gross_production", False),
        ("battery", "battery_power", False),
        ("grid", "net_export", True),
        ("battery_soc", "battery_soc", False),
    ]
    assert diag["channels"][1]["entity_id"] == BATTERY_SENSOR
    assert diag["state"]["battery_power_kw"] == 5.0
