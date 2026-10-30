"""Tests for the Kilowattlas config and options flows."""

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

from custom_components.kilowattlas.config_flow import manual_suggested
from custom_components.kilowattlas.const import (
    CONF_CONSENT,
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

from .conftest import (
    BATTERY,
    DISHWASHER,
    ENERGY_PREFS,
    GRID_EXPORT,
    GRID_IMPORT,
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


def _manual(
    grid: dict | None = None,
    solar: dict | None = None,
    battery: dict | None = None,
    home: dict | None = None,
    devices: dict | None = None,
) -> dict:
    """A manual form answer, shaped like the frontend sends it."""
    return {
        "grid": grid or {},
        "solar": solar or {},
        "battery": battery or {},
        "home": home or {},
        "devices": devices or {},
    }


async def test_full_flow_from_energy_settings(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Consent -> link -> the Energy sensors, all ticked -> entry."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    mock_client.poll_token.side_effect = [
        AuthorizationPending,
        TokenGrant(token=TOKEN, site_id=SITE_ID),
    ]
    result = await _consent(hass)
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channels"
    share = next(iter(result["data_schema"].schema))
    assert share.default() == [
        "",
        "grid",
        "battery",
        "battery_soc",
        "device_sensor.dishwasher_energy",
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"share": ["", "grid", "device_sensor.dishwasher_energy"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kilowattlas"
    assert result["data"] == {CONF_TOKEN: TOKEN, CONF_SITE_ID: SITE_ID}
    assert result["options"] == {
        CONF_SOURCE: SOURCE_ENERGY,
        CONF_PREFERENCES: {},
        CONF_KEY_OVERRIDES: {},
        CONF_EXCLUDED: ["battery", "battery_soc"],
    }
    assert result["result"].unique_id == str(SITE_ID)

    # HA's home position was volunteered, with a provisional capability.
    call = mock_client.request_device_code.await_args
    assert call.args == (hass.config.latitude, hass.config.longitude)
    assert call.kwargs["capability"]["sample_interval_seconds"] == 10


async def test_energy_missing_then_set_up(hass: HomeAssistant) -> None:
    """Without Energy settings: set them up, check again, continue."""
    result = await _finish_progress(hass, await _consent(hass))
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "energy_missing"
    assert result["menu_options"] == ["channels", "manual"]

    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "channels"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channels"


async def test_manual_sensors(hass: HomeAssistant) -> None:
    """The Energy dashboard's power fields, entered here instead."""
    set_states(hass)
    hass.states.async_set(GRID_IMPORT, "0", {"unit_of_measurement": "W"})
    hass.states.async_set(GRID_EXPORT, "0", {"unit_of_measurement": "W"})
    result = await _finish_progress(hass, await _consent(hass))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["step_id"] == "manual"

    # Two-sensor grid with one sensor missing: Energy's schema refuses it.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _manual(grid={"grid_mode": "two", "grid_power": GRID_IMPORT})
    )
    assert result["errors"] == {"grid": "invalid_power_config"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _manual()
    )
    assert result["errors"] == {"base": "nothing_to_share"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual(
            grid={
                "grid_mode": "two",
                "grid_power": GRID_IMPORT,
                "grid_power_to": GRID_EXPORT,
            },
            solar={"solar_power": SOLAR},
            battery={
                "battery_mode": "inverted",
                "battery_power": BATTERY,
                "battery_soc": SOC,
                "battery_capacity": 9.6,
            },
            devices={"device_power": [DISHWASHER]},
        ),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SOURCE] == SOURCE_MANUAL
    assert result["options"][CONF_PREFERENCES] == {
        "energy_sources": [
            {
                "type": "grid",
                "power_config": {
                    "stat_rate_from": GRID_IMPORT,
                    "stat_rate_to": GRID_EXPORT,
                },
            },
            {"type": "solar", "stat_rate": SOLAR},
            {
                "type": "battery",
                "power_config": {"stat_rate_inverted": BATTERY},
                "stat_soc": SOC,
                "capacity": 9.6,
            },
        ],
        "device_consumption": [{"stat_rate": DISHWASHER, "name": "dishwasher power"}],
    }


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
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "energy_missing"
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


async def test_already_configured(hass: HomeAssistant) -> None:
    """Linking the same site twice is refused."""
    energy_entry().add_to_hass(hass)
    result = await _consent(hass)
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Reauth approves a new link and updates token + site id in place."""
    mock_config_entry = energy_entry()
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
    assert mock_config_entry.options[CONF_SOURCE] == SOURCE_ENERGY


async def test_reauth_wrong_site(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Approving a different installation during reauth is refused."""
    mock_config_entry = energy_entry()
    mock_config_entry.add_to_hass(hass)
    mock_client.poll_token.return_value = TokenGrant(token="kwc_other", site_id=99)
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert mock_config_entry.data[CONF_TOKEN] == TOKEN


async def test_options_choose_energy_channels(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """The options reopen the channel list, remembering what was left out."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    entry = await setup_entry(hass, energy_entry(excluded_channels=["grid"]))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "channels"}
    )
    share = next(iter(result["data_schema"].schema))
    assert "grid" not in share.default()
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"share": ["grid"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_EXCLUDED] == [
        "",
        "battery",
        "battery_soc",
        "device_sensor.dishwasher_energy",
    ]
    assert [c.key for c in entry.runtime_data.channels] == ["grid"]


async def test_options_manual_keeps_overrides(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Editing manual sensors keeps the pre-1.0.0 channel keys."""
    prefs = {
        "energy_sources": [{"type": "solar", "stat_rate": SOLAR}],
        "device_consumption": [{"stat_rate": DISHWASHER, "name": "EV"}],
    }
    set_states(hass)
    entry = await setup_entry(
        hass,
        manual_entry(
            prefs, key_overrides={DISHWASHER: ["ev_charger", "ev_charger_power"]}
        ),
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    # No Energy settings: straight to the manual form, prefilled.
    assert result["step_id"] == "manual"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _manual(solar={"solar_power": SOLAR}, devices={"device_power": [DISHWASHER]}),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    keys = {c.key: c.kind for c in entry.runtime_data.channels}
    assert keys == {"": "gross_production", "ev_charger": "ev_charger_power"}


def test_manual_form_is_prefilled_from_preferences() -> None:
    """Stored preferences show up again in the form."""
    prefs = {
        "energy_sources": [
            {"type": "grid", "power_config": {"stat_rate_inverted": "sensor.g"}},
            {
                "type": "battery",
                "power_config": {
                    "stat_rate_from": "sensor.o",
                    "stat_rate_to": "sensor.i",
                },
                "stat_soc": "sensor.s",
                "capacity": 5.0,
            },
            {"type": "solar", "stat_rate": "sensor.p"},
            {"type": "home", "stat_rate": "sensor.h"},
        ],
        "device_consumption": [{"stat_rate": "sensor.d"}],
    }
    assert manual_suggested(prefs) == {
        "grid": {"grid_mode": "inverted", "grid_power": "sensor.g"},
        "solar": {"solar_power": "sensor.p"},
        "battery": {
            "battery_mode": "two",
            "battery_power": "sensor.o",
            "battery_power_to": "sensor.i",
            "battery_soc": "sensor.s",
            "battery_capacity": 5.0,
        },
        "home": {"home_power": "sensor.h"},
        "devices": {"device_power": ["sensor.d"]},
    }
