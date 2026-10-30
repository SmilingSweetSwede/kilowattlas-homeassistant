"""Tests for the sensor platform."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas import const
from custom_components.kilowattlas.const import CONF_PREFERENCES, DOMAIN

from .conftest import BATTERY, POWER_KW, manual_entry, setup_entry


async def test_entities_and_device(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Status entities are grouped under one service device with a map link."""
    status = hass.states.get("sensor.kilowattlas_sharing_status")
    assert status.state == "connected"
    assert status.attributes["options"] == [
        "starting",
        "connected",
        "retrying",
        "revoked",
    ]
    assert hass.states.get("sensor.kilowattlas_shared_channels").state == "5"

    registry = er.async_get(hass)
    # Disabled by default: the noisy diagnostics.
    for entity_id in (
        "sensor.kilowattlas_unusable_readings",
        "sensor.kilowattlas_measured_sensor_interval",
    ):
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert hass.states.get(entity_id) is None

    (device,) = dr.async_entries_for_config_entry(
        dr.async_get(hass), init_integration.entry_id
    )
    assert device.identifiers == {(DOMAIN, init_integration.entry_id)}
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.configuration_url.startswith("https://kilowattlas.com/?lat=")


def test_map_base_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """KILOWATTLAS_MAP_BASE points the Visit link elsewhere; blank means default."""
    try:
        monkeypatch.setenv("KILOWATTLAS_MAP_BASE", " http://localhost:3500/ ")
        assert importlib.reload(const).MAP_BASE_URL == "http://localhost:3500"
        monkeypatch.setenv("KILOWATTLAS_MAP_BASE", "  ")
        assert importlib.reload(const).MAP_BASE_URL == "https://kilowattlas.com"
    finally:
        monkeypatch.delenv("KILOWATTLAS_MAP_BASE", raising=False)
        importlib.reload(const)
    assert const.MAP_BASE_URL == "https://kilowattlas.com"


async def test_transform_sensor_follows_the_options(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Energy's transform sensor exists while the options need it, not after."""
    prefs = {
        "energy_sources": [
            {"type": "battery", "power_config": {"stat_rate_inverted": BATTERY}}
        ],
        "device_consumption": [],
    }
    hass.states.async_set(BATTERY, "2", POWER_KW)  # charging, in its own sign
    entry = await setup_entry(hass, manual_entry(prefs))
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, "entry_manual_battery_0_power"
    )
    assert entity_id == "sensor.kilowattlas_battery_power_inverted"
    assert hass.states.get(entity_id).state == "-2.0"

    plain = {
        "energy_sources": [{"type": "battery", "power_config": {"stat_rate": BATTERY}}],
        "device_consumption": [],
    }
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_PREFERENCES: plain}
    )
    await hass.async_block_till_done()
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "entry_manual_battery_0_power")
        is None
    )
    assert [c.entity_id for c in entry.runtime_data.channels] == [BATTERY]
