"""Tests for the Kilowattlas config flow."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokilowattlas import (
    AuthorizationExpired,
    AuthorizationPending,
    KilowattlasConnectionError,
    TokenGrant,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kilowattlas.const import (
    CONF_CONSENT,
    CONF_POWER_SENSOR,
    CONF_SITE_ID,
    CONF_TOKEN,
    DOMAIN,
)

from .conftest import SENSOR, SITE_ID, TOKEN

pytestmark = pytest.mark.usefixtures("mock_client")

_real_sleep = asyncio.sleep


@pytest.fixture(autouse=True)
def fast_sleep() -> Generator[AsyncMock]:
    """Make the poll loop yield to the event loop without really waiting."""

    async def _sleep(_seconds: float) -> None:
        await _real_sleep(0)

    with patch(
        "custom_components.kilowattlas.config_flow.asyncio.sleep",
        new=AsyncMock(side_effect=_sleep),
    ) as mocked:
        yield mocked


async def _consent(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONSENT: True}
    )


async def _finish_progress(hass: HomeAssistant, result: dict) -> dict:
    """Let the background approval task run, then advance the flow.

    When the approval resolves before the first poll ever yields (an instant
    mock), the flow already moved on and there is no progress screen to wait
    for; that is a valid outcome and is returned as is.
    """
    if result["type"] is not FlowResultType.SHOW_PROGRESS:
        return result
    assert result["step_id"] == "link"
    assert result["progress_action"] == "wait_for_approval"
    assert result["description_placeholders"] == {
        "user_code": "ABCD-1234",
        "verification_uri": "https://kilowattlas.com/link?user_code=ABCD-1234",
    }
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(result["flow_id"])


async def test_full_flow(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Consent -> code shown with progress -> approved -> sensor -> entry."""
    mock_client.poll_token.side_effect = [
        AuthorizationPending,
        TokenGrant(token=TOKEN, site_id=SITE_ID),
    ]
    result = await _consent(hass)
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER_SENSOR: SENSOR}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kilowattlas"
    assert result["data"] == {
        CONF_TOKEN: TOKEN,
        CONF_SITE_ID: SITE_ID,
        CONF_POWER_SENSOR: SENSOR,
    }
    assert result["result"].unique_id == str(SITE_ID)

    # HA's home position was volunteered, with a provisional capability.
    call = mock_client.request_device_code.await_args
    assert call.args == (hass.config.latitude, hass.config.longitude)
    assert call.kwargs["capability"]["sample_interval_seconds"] == 10
    mock_client.poll_token.assert_awaited_with("dev-code")


async def test_consent_required(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Unticked consent stays on the form and contacts nothing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONSENT: False}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "consent_required"}
    mock_client.request_device_code.assert_not_awaited()


async def test_cannot_connect_requesting_code(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """The API being down when asking for a code aborts cleanly."""
    mock_client.request_device_code.side_effect = KilowattlasConnectionError("down")
    result = await _consent(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_pending_then_approved(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Pending answers keep polling; approval continues the flow."""
    mock_client.poll_token.side_effect = [
        AuthorizationPending,
        AuthorizationPending,
        TokenGrant(token=TOKEN, site_id=SITE_ID),
    ]
    result = await _consent(hass)
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor"
    assert mock_client.poll_token.await_count == 3


async def test_expired(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """An expired code aborts with its own reason."""
    mock_client.poll_token.side_effect = AuthorizationExpired
    result = await _consent(hass)
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "expired"


async def test_deadline_passes(
    hass: HomeAssistant, mock_client: MagicMock, fast_sleep: AsyncMock
) -> None:
    """Never approved within the code's lifetime counts as expired."""
    mock_client.request_device_code.return_value = (
        mock_client.request_device_code.return_value.__class__(
            device_code="dev-code",
            user_code="ABCD-1234",
            verification_uri="https://kilowattlas.com/link",
            interval=1000,  # clamped to 30
            expires_in=1,  # clamped to 30 -> one poll, then give up
        )
    )
    mock_client.poll_token.side_effect = AuthorizationPending
    result = await _consent(hass)
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "expired"
    assert mock_client.poll_token.await_count == 1
    # The poll interval was clamped to the ceiling (HA itself also sleeps(0)).
    assert [c.args[0] for c in fast_sleep.await_args_list if c.args[0]] == [30]


async def test_poll_connection_error(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A network failure while polling aborts with cannot_connect."""
    mock_client.poll_token.side_effect = KilowattlasConnectionError("down")
    result = await _consent(hass)
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Linking the same site twice is refused."""
    mock_config_entry.add_to_hass(hass)
    result = await _consent(hass)
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Reauth approves a new link and updates token + site id in place."""
    mock_config_entry.add_to_hass(hass)
    mock_client.poll_token.return_value = TokenGrant(token="kwc_new", site_id=SITE_ID)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_TOKEN] == "kwc_new"
    assert mock_config_entry.data[CONF_POWER_SENSOR] == SENSOR


async def test_reauth_wrong_site(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Approving a different installation during reauth is refused."""
    mock_config_entry.add_to_hass(hass)
    mock_client.poll_token.return_value = TokenGrant(token="kwc_other", site_id=99)
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert mock_config_entry.data[CONF_TOKEN] == TOKEN


async def test_reconfigure(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfigure swaps the sensor without re-linking."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER_SENSOR: "sensor.other"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_POWER_SENSOR] == "sensor.other"
    assert mock_config_entry.data[CONF_TOKEN] == TOKEN
