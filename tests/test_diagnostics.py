"""Tests for diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SENSOR, TOKEN


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
