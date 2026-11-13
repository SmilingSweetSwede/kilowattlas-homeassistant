"""Tests for the Kilowattlas config and options flows."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokilowattlas import (
    AuthorizationExpired,
    AuthorizationPending,
    KilowattlasAuthError,
    KilowattlasConnectionError,
    KilowattlasRejectedError,
    TokenGrant,
)
from homeassistant import config_entries
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.data_entry_flow import (
    EVENT_DATA_ENTRY_FLOW_PROGRESSED,
    FlowResultType,
    InvalidData,
)

from custom_components.kilowattlas.config_flow import (
    DATA_PENDING_GRANT,
    NUDGE_INTERVAL,
    PENDING_GRANT_TTL,
    manual_suggested,
)
from custom_components.kilowattlas.const import (
    CONF_EXCLUDED,
    CONF_KEY_OVERRIDES,
    CONF_KNOWN,
    CONF_PREFERENCES,
    CONF_SHARE_NEW,
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


# A server that creates the installation when the setup is finished.
PENDING = TokenGrant(token=TOKEN, activation_required=True)

ALL_KEYS = ["", "battery", "battery_soc", "device_sensor.dishwasher_energy", "grid"]


async def _start(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _choose(hass: HomeAssistant, choice: dict | None = None) -> dict:
    """With Energy settings: choose what to share (everything unless given)."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], choice or {"share_all": True}
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
        "verification_uri": (
            "https://kilowattlas.com/link?user_code=ABCD-1234&from=home-assistant"
        ),
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


# --- step 1: what to share -----------------------------------------------------


async def test_share_everything(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Choose all -> link -> the installation and the entry, by themselves."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    mock_client.poll_token.side_effect = [AuthorizationPending, PENDING]
    result = await _start(hass)
    assert result["step_id"] == "user"
    # Nothing is chosen for the user: neither "all" nor any sensor.
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    assert defaults == {"share_all": False, "share": []}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"share_all": True}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    # Approved on the website, and nothing exists there yet.
    mock_client.activate.assert_not_awaited()

    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kilowattlas"
    mock_client.activate.assert_awaited_once_with(TOKEN)
    assert result["data"] == {CONF_TOKEN: TOKEN, CONF_SITE_ID: SITE_ID}
    assert result["options"] == {
        CONF_SOURCE: SOURCE_ENERGY,
        CONF_PREFERENCES: {},
        CONF_KEY_OVERRIDES: {},
        CONF_EXCLUDED: [],
        CONF_SHARE_NEW: True,
        CONF_KNOWN: ALL_KEYS,
    }
    assert result["result"].unique_id == str(SITE_ID)
    assert DATA_PENDING_GRANT not in hass.data

    # HA's home position was volunteered, with a provisional capability, and
    # the installation asked to be created at the end of the setup.
    call = mock_client.request_device_code.await_args
    assert call.args == (hass.config.latitude, hass.config.longitude)
    assert call.kwargs["capability"]["sample_interval_seconds"] == 10
    assert call.kwargs["activation"] is True


async def test_share_chosen_sensors(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Sensor by sensor: only the ticked ones, and none that come later."""
    mock_client.poll_token.side_effect = [PENDING]
    result = await _choose(hass, {"share_all": False, "share": ["", "grid"]})
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_EXCLUDED] == [
        "battery",
        "battery_soc",
        "device_sensor.dishwasher_energy",
    ]
    assert result["options"][CONF_SHARE_NEW] is False
    assert result["options"][CONF_KNOWN] == ALL_KEYS
    await hass.async_block_till_done()
    entry = result["result"]
    assert [c.key for c in entry.runtime_data.channels] == ["", "grid"]


async def test_nothing_chosen(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Neither "all" nor a sensor: no link is started."""
    result = await _choose(hass, {"share_all": False, "share": []})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "nothing_chosen"}
    mock_client.request_device_code.assert_not_awaited()


async def test_only_energy_dashboard_sensors_can_be_chosen(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A sensor that is not in the Energy settings is not an option."""
    with pytest.raises(InvalidData):
        await _choose(hass, {"share": ["device_sensor.not_in_energy"]})
    mock_client.request_device_code.assert_not_awaited()


async def test_sensor_added_later_follows_the_choice(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """After a selection a new Energy sensor waits; after "all" it is shared."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    # Chosen one by one when only solar and grid existed.
    entry = await setup_entry(
        hass, energy_entry(share_new=False, known_channels=["", "grid"])
    )
    assert [c.key for c in entry.runtime_data.channels] == ["", "grid"]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.config_entries.async_remove(entry.entry_id)

    entry = energy_entry(share_new=True, known_channels=["", "grid"])
    entry = await setup_entry(hass, entry)
    assert sorted(c.key for c in entry.runtime_data.channels) == ALL_KEYS


async def test_energy_missing_then_set_up(hass: HomeAssistant) -> None:
    """Without Energy settings the flow waits for them, then offers them."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "energy_missing"

    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_manual_sensors(hass: HomeAssistant) -> None:
    """The Energy dashboard's power fields, entered here instead."""
    set_states(hass)
    hass.states.async_set(GRID_IMPORT, "0", {"unit_of_measurement": "W"})
    hass.states.async_set(GRID_EXPORT, "0", {"unit_of_measurement": "W"})
    result = await _start(hass)
    assert result["step_id"] == "energy_missing"
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
    # Everything is chosen: the link is next, and the setup ends by itself.
    result = await _finish_progress(hass, result)
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



# --- step 2: link --------------------------------------------------------------


async def test_cannot_connect_requesting_code(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """The API being down when asking for a code aborts cleanly."""
    mock_client.request_device_code.side_effect = KilowattlasConnectionError("down")
    result = await _choose(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_pending_then_approved(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Pending answers keep polling; approval finishes the setup."""
    mock_client.poll_token.side_effect = [
        AuthorizationPending,
        AuthorizationPending,
        PENDING,
    ]
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_client.poll_token.await_count == 3


async def test_server_that_creates_at_approval(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """An older server answers with the installation: nothing left to create."""
    mock_client.poll_token.side_effect = [
        AuthorizationPending,
        TokenGrant(token=TOKEN, site_id=SITE_ID),
    ]
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_TOKEN: TOKEN, CONF_SITE_ID: SITE_ID}
    mock_client.activate.assert_not_awaited()


async def test_expired(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """An expired code aborts with its own reason."""
    mock_client.poll_token.side_effect = AuthorizationExpired
    result = await _finish_progress(hass, await _choose(hass))
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
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "expired"
    assert mock_client.poll_token.await_count == 1
    # The poll interval was clamped to the ceiling (HA itself also sleeps(0)).
    # The signal to the dialog has a rhythm of its own.
    assert [
        c.args[0]
        for c in fast_sleep.await_args_list
        if c.args[0] not in (0, NUDGE_INTERVAL)
    ] == [30]


async def test_poll_connection_error(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """An API that stays unreachable for the code's lifetime ends the wait."""
    mock_client.poll_token.side_effect = KilowattlasConnectionError("down")
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
    assert mock_client.poll_token.await_count > 1


async def test_poll_survives_a_failed_request(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """One failed or hanging poll does not end the linking."""
    mock_client.poll_token.side_effect = [
        KilowattlasConnectionError("down"),
        TimeoutError,
        PENDING,
    ]
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_client.poll_token.await_count == 3


async def test_already_configured(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """The same installation twice is refused."""
    energy_entry().add_to_hass(hass)
    mock_client.poll_token.side_effect = [AuthorizationPending, PENDING]
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # Nothing is left for a later setup to continue.
    assert DATA_PENDING_GRANT not in hass.data


# --- an approved link is not stranded --------------------------------------------


async def _approved_but_unseen(hass: HomeAssistant, mock_client: MagicMock) -> dict:
    """Approved on the website while the dialog was not listening."""
    mock_client.poll_token.side_effect = [AuthorizationPending, PENDING]
    result = await _choose(hass)
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    return result


async def test_approval_is_signalled_until_the_dialog_reacts(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A dialog that missed the one "approved" event still finishes the setup.

    The frontend closes its connection in a hidden tab and never asks again by
    itself, so the event is repeated until the dialog fetches the next step.
    """
    events: list[Event] = []

    @callback
    def _seen(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_DATA_ENTRY_FLOW_PROGRESSED, _seen)
    result = await _approved_but_unseen(hass, mock_client)
    for _ in range(20):
        await _real_sleep(0)
    assert len(events) > 1
    assert {e.data["flow_id"] for e in events} == {result["flow_id"]}

    # The dialog reacts: it fetches the flow, and the signal stops.
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    events.clear()
    for _ in range(20):
        await _real_sleep(0)
    assert events == []


async def test_closed_dialog_creates_nothing(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Closing the dialog after the approval: no signal, no installation."""
    events: list[Event] = []

    @callback
    def _seen(event: Event) -> None:
        events.append(event)

    result = await _approved_but_unseen(hass, mock_client)
    hass.config_entries.flow.async_abort(result["flow_id"])
    hass.bus.async_listen(EVENT_DATA_ENTRY_FLOW_PROGRESSED, _seen)
    for _ in range(20):
        await _real_sleep(0)
    assert events == []
    mock_client.activate.assert_not_awaited()
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_new_setup_uses_an_approved_link(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """The approved link survives a lost dialog: no new code is needed.

    The server hands the token out once. Starting over would ask for a new
    code and waste the approval.
    """
    first = await _approved_but_unseen(hass, mock_client)
    hass.config_entries.flow.async_abort(first["flow_id"])

    # What to share is asked again, then the setup finishes without a link.
    result = await _start(hass)
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"share": ["grid"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_client.request_device_code.await_count == 1
    assert mock_client.poll_token.await_count == 2
    mock_client.activate.assert_awaited_once_with(TOKEN)
    assert result["data"] == {CONF_TOKEN: TOKEN, CONF_SITE_ID: SITE_ID}
    assert result["options"][CONF_SHARE_NEW] is False
    assert DATA_PENDING_GRANT not in hass.data


async def test_new_setup_next_to_the_first_dialog(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A second setup takes the approved link over from the first; one entry."""
    first = await _approved_but_unseen(hass, mock_client)
    second = await _start(hass)
    second = await hass.config_entries.flow.async_configure(
        second["flow_id"], {"share_all": True}
    )
    assert second["type"] is FlowResultType.CREATE_ENTRY

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    # The setup that got the approval ended when the second one took it over:
    # it does not wait, and signal, until the next restart.
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_approved_link_is_forgotten_after_a_while(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """An approved link that nobody finished is not picked up much later."""
    first = await _approved_but_unseen(hass, mock_client)
    hass.config_entries.flow.async_abort(first["flow_id"])
    grant, approved_at, flow_id = hass.data[DATA_PENDING_GRANT]
    hass.data[DATA_PENDING_GRANT] = (
        grant,
        approved_at - PENDING_GRANT_TTL - 1,
        flow_id,
    )

    mock_client.poll_token.side_effect = AuthorizationPending
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"share_all": True}
    )
    # A new code: the old approval is not used.
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert mock_client.request_device_code.await_count == 2
    assert DATA_PENDING_GRANT not in hass.data
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_reauth_leaves_nothing_to_continue(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A new token from reauth belongs to its entry, not to a later setup."""
    mock_config_entry = energy_entry()
    mock_config_entry.add_to_hass(hass)
    mock_client.poll_token.return_value = TokenGrant(token="kwc_new", site_id=SITE_ID)
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _finish_progress(hass, result)
    assert DATA_PENDING_GRANT not in hass.data
    # The reauth reloads the entry; let that finish before the test ends.
    await hass.async_block_till_done()


# --- step 3: the installation is created at the end, or not at all --------------


async def test_unreachable_at_the_end_can_be_tried_again(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """No answer from Kilowattlas: a form that says so, nothing set up."""
    mock_client.poll_token.side_effect = [AuthorizationPending, PENDING]
    mock_client.activate.side_effect = KilowattlasConnectionError("down")
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "finish"
    assert result["errors"] == {"base": "cannot_finish"}
    assert hass.config_entries.async_entries(DOMAIN) == []

    mock_client.activate.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == str(SITE_ID)
    assert result["options"][CONF_SHARE_NEW] is True


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (AuthorizationExpired(), "link_lost"),
        (KilowattlasAuthError("token rejected"), "link_lost"),
        (KilowattlasRejectedError("plant_already_linked"), "activation_refused"),
    ],
)
async def test_end_that_cannot_succeed_says_so(
    hass: HomeAssistant, mock_client: MagicMock, error: Exception, reason: str
) -> None:
    """The approval ran out or was refused: a clear end, nothing left behind."""
    mock_client.poll_token.side_effect = [AuthorizationPending, PENDING]
    mock_client.activate.side_effect = error
    result = await _finish_progress(hass, await _choose(hass))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert hass.config_entries.async_entries(DOMAIN) == []
    # The next setup starts from the beginning, with a new code.
    assert DATA_PENDING_GRANT not in hass.data


# --- reauth and options ---------------------------------------------------------


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



async def test_dialog_asking_twice_creates_one_installation(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Two fetches of the step after the approval do not both create it."""
    result = await _approved_but_unseen(hass, mock_client)
    release = asyncio.Event()

    async def _slow_activate(_token: str) -> object:
        await release.wait()
        return mock_client.activate.return_value

    mock_client.activate.side_effect = _slow_activate
    first = hass.async_create_task(
        hass.config_entries.flow.async_configure(result["flow_id"])
    )
    second = hass.async_create_task(
        hass.config_entries.flow.async_configure(result["flow_id"])
    )
    for _ in range(5):
        await _real_sleep(0)
    assert mock_client.activate.await_count == 1
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert results[0]["type"] is FlowResultType.CREATE_ENTRY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
