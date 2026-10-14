"""Tests for setup, unload and removal."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aiokilowattlas import (
    KilowattlasAuthError,
    KilowattlasConnectionError,
    KilowattlasResponseError,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.const import DOMAIN

from .conftest import TOKEN


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Setup verifies the token, creates entities, and unload cleans up."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    mock_client.get_site.assert_awaited_once_with(TOKEN)
    assert hass.states.get("sensor.kilowattlas_shared_production") is not None
    assert hass.states.get("sensor.kilowattlas_sharing_status").state == "connected"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    # Unload (also used on restart/reload) must NOT revoke.
    mock_client.revoke.assert_not_awaited()


async def test_setup_auth_failed_starts_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A revoked token at startup puts the entry in error and opens reauth."""
    mock_client.get_site.side_effect = KilowattlasAuthError("revoked")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH


@pytest.mark.parametrize(
    "error", [KilowattlasConnectionError("down"), KilowattlasResponseError("odd")]
)
async def test_setup_retries_when_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
) -> None:
    """An unreachable or confused API means retry, not failure."""
    mock_client.get_site.side_effect = error
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


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
