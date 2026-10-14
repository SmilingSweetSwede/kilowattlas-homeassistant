"""Fixtures for the Kilowattlas tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokilowattlas import DeviceCode, IngestResult, SiteInfo, TokenGrant
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.const import (
    CONF_POWER_SENSOR,
    CONF_SITE_ID,
    CONF_TOKEN,
    DOMAIN,
)

TOKEN = "kwc_testtoken"
SITE_ID = 42
SENSOR = "sensor.solar_power"


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
    client.poll_token = AsyncMock(return_value=TokenGrant(token=TOKEN, site_id=SITE_ID))
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


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A linked installation."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kilowattlas",
        unique_id=str(SITE_ID),
        data={CONF_TOKEN: TOKEN, CONF_SITE_ID: SITE_ID, CONF_POWER_SENSOR: SENSOR},
        entry_id="entry1",
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> AsyncGenerator[MockConfigEntry]:
    """Set the integration up with a fake 4.2 kW solar sensor present."""
    await async_setup_component(hass, "homeassistant", {})
    hass.states.async_set(
        SENSOR, "4200", {"unit_of_measurement": "W", "device_class": "power"}
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    yield mock_config_entry
