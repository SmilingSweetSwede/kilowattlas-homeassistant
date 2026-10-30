"""Tests for diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import DISHWASHER, GRID, TOKEN


async def test_diagnostics(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The token is redacted; the Energy mapping is visible."""
    diag = await async_get_config_entry_diagnostics(hass, init_integration)
    assert diag["entry"]["token"] == "**REDACTED**"
    assert TOKEN not in str(diag)
    assert diag["options"]["source"] == "energy"
    assert diag["state"]["status"] == "connected"
    assert diag["server_config"]["slot_seconds"] == 900
    channels = {c["key"]: c for c in diag["channels"]}
    assert channels["grid"] == {
        "key": "grid",
        "kind": "grid_power",
        "entity_id": GRID,
        "name": None,
        "percent": False,
    }
    assert channels["device_sensor.dishwasher_energy"]["entity_id"] == DISHWASHER
    assert diag["cursors"] == {}
    assert diag["replay_windows"] == {}
    assert diag["queue_length"] == 0
