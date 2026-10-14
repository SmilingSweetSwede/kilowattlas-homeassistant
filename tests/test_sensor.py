"""Tests for the sensor platform."""

from __future__ import annotations

from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.const import DOMAIN

from .conftest import SENSOR


async def test_entities_and_device(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Entities are grouped under one service device with a map link."""
    prod = hass.states.get("sensor.kilowattlas_shared_production")
    assert prod is not None
    assert prod.state == "4.2"  # 4200 W at setup
    assert prod.attributes[ATTR_UNIT_OF_MEASUREMENT] == "kW"
    assert prod.attributes[ATTR_DEVICE_CLASS] == "power"

    status = hass.states.get("sensor.kilowattlas_sharing_status")
    assert status.state == "connected"
    assert status.attributes["options"] == [
        "starting",
        "connected",
        "retrying",
        "revoked",
    ]

    registry = er.async_get(hass)
    entry = registry.async_get("sensor.kilowattlas_shared_production")
    assert entry.unique_id == f"{init_integration.entry_id}_shared_production"
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

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, init_integration.entry_id)}
    )
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.configuration_url.startswith("https://kilowattlas.com/?lat=")


async def test_production_unavailable_when_source_is(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The production sensor mirrors the source's availability."""
    hass.states.async_set(SENSOR, "unavailable")
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.kilowattlas_shared_production").state == "unavailable"
    )
    # Diagnostics stay available.
    assert hass.states.get("sensor.kilowattlas_sharing_status").state == "connected"

    hass.states.async_set(SENSOR, "2.5", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kilowattlas_shared_production").state == "2.5"
