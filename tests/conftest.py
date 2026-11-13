"""Fixtures for the Kilowattlas tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokilowattlas import DeviceCode, IngestResult, SiteInfo, TokenGrant
from homeassistant.components.energy.data import async_get_manager
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.const import (
    CONF_EXCLUDED,
    CONF_KEY_OVERRIDES,
    CONF_PREFERENCES,
    CONF_SITE_ID,
    CONF_SOURCE,
    CONF_TOKEN,
    DOMAIN,
    SOURCE_ENERGY,
    SOURCE_MANUAL,
)

TOKEN = "kwc_testtoken"
SITE_ID = 42
SOLAR = "sensor.solar_power"
GRID = "sensor.grid_power"
GRID_IMPORT = "sensor.p1_power_import"
GRID_EXPORT = "sensor.p1_power_export"
BATTERY = "sensor.battery_power"
SOC = "sensor.battery_soc"
HOME = "sensor.home_power"
DISHWASHER = "sensor.dishwasher_power"
DISHWASHER_ENERGY = "sensor.dishwasher_energy"

POWER_W = {"unit_of_measurement": "W", "device_class": "power"}
POWER_KW = {"unit_of_measurement": "kW", "device_class": "power"}
PERCENT = {"unit_of_measurement": "%", "device_class": "battery"}

# A home's Energy settings: solar, grid (import positive), a battery with a
# state of charge, a home meter and one device. Energy fields are left out
# where the schema allows; the power fields are what Kilowattlas reads.
ENERGY_PREFS: dict[str, Any] = {
    "energy_sources": [
        {
            "type": "solar",
            "stat_energy_from": "sensor.solar_energy",
            "stat_rate": SOLAR,
            "config_entry_solar_forecast": None,
        },
        {
            "type": "grid",
            "stat_energy_from": "sensor.grid_import_energy",
            "stat_energy_to": "sensor.grid_export_energy",
            "stat_cost": None,
            "entity_energy_price": None,
            "number_energy_price": None,
            "stat_compensation": None,
            "entity_energy_price_export": None,
            "number_energy_price_export": None,
            "cost_adjustment_day": 0.0,
            "power_config": {"stat_rate": GRID},
        },
        {
            "type": "battery",
            "stat_energy_from": "sensor.battery_out_energy",
            "stat_energy_to": "sensor.battery_in_energy",
            "power_config": {"stat_rate": BATTERY},
            "stat_soc": SOC,
            "capacity": 10.0,
        },
    ],
    "device_consumption": [
        {
            "stat_consumption": DISHWASHER_ENERGY,
            "stat_rate": DISHWASHER,
            "name": "Dishwasher",
        }
    ],
}


@pytest.fixture
def mock_recorder_before_hass(async_test_recorder: Any) -> None:
    """Prepare the test recorder before `hass` exists (pytest-homeassistant hook)."""


@pytest.fixture(autouse=True)
def auto_recorder(recorder_mock: Any) -> None:
    """An in-memory recorder; the integration depends on it."""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom_components in every test."""


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Patch the API client wherever the integration constructs one."""
    client = MagicMock()
    client.request_device_code = AsyncMock(
        return_value=DeviceCode(
            device_code="dev-code",
            user_code="ABCD-1234",
            verification_uri="https://kilowattlas.com/link",
            interval=1,
            expires_in=60,
        )
    )
    # A server that creates the installation at approval answers with its id;
    # the tests of the two-phase link set an `activation_required` grant.
    client.poll_token = AsyncMock(return_value=TokenGrant(token=TOKEN, site_id=SITE_ID))
    client.activate = AsyncMock(
        return_value=SiteInfo(site_id=SITE_ID, name="", config={"config_version": 1})
    )
    client.get_site = AsyncMock(
        return_value=SiteInfo(
            site_id=SITE_ID,
            name="Roof",
            capacity_kw=9.5,
            config={"config_version": 1, "slot_seconds": 900},
        )
    )
    client.ingest = AsyncMock(return_value=IngestResult(accepted=1))
    client.revoke = AsyncMock(return_value=None)
    with (
        patch("custom_components.kilowattlas.KilowattlasClient", return_value=client),
        patch(
            "custom_components.kilowattlas.config_flow.KilowattlasClient",
            return_value=client,
        ),
    ):
        yield client


def set_states(hass: HomeAssistant) -> None:
    """Every sensor of ENERGY_PREFS, with a value."""
    hass.states.async_set(SOLAR, "4200", POWER_W)
    hass.states.async_set(GRID, "-0.9", POWER_KW)
    hass.states.async_set(BATTERY, "1.5", POWER_KW)
    hass.states.async_set(SOC, "64", PERCENT)
    hass.states.async_set(HOME, "1.1", POWER_KW)
    hass.states.async_set(DISHWASHER, "1800", POWER_W)


async def save_energy_prefs(hass: HomeAssistant, prefs: dict[str, Any]) -> None:
    """Save Energy settings the way the Energy dashboard does."""
    await async_setup_component(hass, "energy", {})
    manager = await async_get_manager(hass)
    await manager.async_update(prefs)  # type: ignore[arg-type]
    await hass.async_block_till_done()


def energy_entry(**options: Any) -> MockConfigEntry:
    """A linked installation sharing from the Energy settings."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kilowattlas",
        unique_id=str(SITE_ID),
        version=2,
        data={CONF_TOKEN: TOKEN, CONF_SITE_ID: SITE_ID},
        options={
            CONF_SOURCE: SOURCE_ENERGY,
            CONF_PREFERENCES: {},
            CONF_KEY_OVERRIDES: {},
            CONF_EXCLUDED: [],
            **options,
        },
        entry_id="entry1",
    )


def manual_entry(prefs: dict[str, Any], **options: Any) -> MockConfigEntry:
    """A linked installation sharing sensors entered in the options."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kilowattlas",
        unique_id=str(SITE_ID),
        version=2,
        data={CONF_TOKEN: TOKEN, CONF_SITE_ID: SITE_ID},
        options={
            CONF_SOURCE: SOURCE_MANUAL,
            CONF_PREFERENCES: prefs,
            CONF_KEY_OVERRIDES: {},
            CONF_EXCLUDED: [],
            **options,
        },
        entry_id="entry_manual",
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """Add and set up an entry."""
    await async_setup_component(hass, "homeassistant", {})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_client: MagicMock
) -> AsyncGenerator[MockConfigEntry]:
    """Linked, sharing the full ENERGY_PREFS home."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    yield await setup_entry(hass, energy_entry())
