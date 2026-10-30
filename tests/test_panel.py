"""The status page: what it shows, and that it comes and goes with the entries."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokilowattlas import (
    KilowattlasConflictError,
    KilowattlasConnectionError,
    KilowattlasRejectedError,
    SiteDetails,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_component,
)

from custom_components.kilowattlas.const import CONF_EXCLUDED, STATUS_CONNECTED
from custom_components.kilowattlas.panel import (
    DATA_PANEL_URL,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_PATH,
    async_remove_panel,
    async_setup_panel,
    async_status,
    ws_get_details,
    ws_save_details,
    ws_set_shared,
    ws_status,
    ws_subscribe_status,
)

from .conftest import (
    ENERGY_PREFS,
    GRID,
    POWER_KW,
    POWER_W,
    SOLAR,
    TOKEN,
    energy_entry,
    save_energy_prefs,
    set_states,
    setup_entry,
)


def _frontend(hass: HomeAssistant) -> Any:
    mock_component(hass, "frontend")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    return patch.multiple(
        "custom_components.kilowattlas.panel",
        frontend=MagicMock(DATA_PANELS="frontend_panels"),
        panel_custom=MagicMock(async_register_panel=AsyncMock()),
    )


async def test_no_panel_without_a_frontend(hass: HomeAssistant) -> None:
    """A headless install still shares; there is just nothing to show."""
    await async_setup_panel(hass)
    assert DATA_PANEL_URL not in hass.data


async def test_panel_is_added_once(hass: HomeAssistant) -> None:
    """The script path can only be registered once per process."""
    with _frontend(hass):
        from custom_components.kilowattlas import panel

        await async_setup_panel(hass)
        hass.data["frontend_panels"] = {PANEL_PATH: object()}
        await async_setup_panel(hass)

        hass.http.async_register_static_paths.assert_awaited_once()
        panel.panel_custom.async_register_panel.assert_awaited_once()
        kwargs = panel.panel_custom.async_register_panel.await_args.kwargs
        assert kwargs["webcomponent_name"] == PANEL_ELEMENT
        assert kwargs["sidebar_icon"] == PANEL_ICON
        assert kwargs["require_admin"] is True
        assert "kilowattlas-panel.js?v=" in hass.data[DATA_PANEL_URL]


async def test_panel_removed_with_the_last_entry(hass: HomeAssistant) -> None:
    """A second installation keeps the page."""
    with _frontend(hass):
        from custom_components.kilowattlas import panel

        await async_setup_panel(hass)
        entry = MockConfigEntry(domain="kilowattlas")
        entry.add_to_hass(hass)
        async_remove_panel(hass)
        panel.frontend.async_remove_panel.assert_not_called()

        # Removing the entry takes the page with it.
        await hass.config_entries.async_remove(entry.entry_id)
        panel.frontend.async_remove_panel.assert_called_once()
        panel.frontend.remove_extra_js_url.assert_called_once()


async def test_status_of_a_running_installation(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """What the page shows is the coordinator's own state."""
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()

    [status] = await async_status(hass)
    assert status["status"] == STATUS_CONNECTED
    assert status["shared_channels"] == 5
    assert status["last_sent"] is not None
    assert status["queued"] == 0
    assert "lat=" in status["map_url"]
    assert status["community_url"].endswith("/energigemenskap")


async def test_status_lists_every_channel_with_its_last_value(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Sensor, value sent and when, per channel; not sent yet is empty."""
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()

    [status] = await async_status(hass)
    by_key = {c["key"]: c for c in status["channels"]}
    assert len(by_key) == 5
    solar = by_key[""]
    assert solar["last_value"] == 5.0
    assert solar["last_sent"] is not None
    assert solar["shared"] is True
    assert solar["sensor"]
    assert by_key["grid"]["last_value"] is None


async def test_unticked_channel_is_listed_and_not_sent(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Ticking off from the page stops the channel but keeps it on the page."""
    set_states(hass)
    await save_energy_prefs(hass, ENERGY_PREFS)
    entry = await setup_entry(hass, energy_entry())

    connection = MagicMock()
    connection.user.is_admin = True
    ws_set_shared(
        hass,
        connection,
        {
            "id": 1,
            "type": "kilowattlas/set_shared",
            "entry_id": entry.entry_id,
            "channel_key": "grid",
            "shared": False,
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    connection.send_result.assert_called_once_with(1)
    assert entry.options[CONF_EXCLUDED] == ["grid"]

    mock_client.ingest.reset_mock()
    hass.states.async_set(GRID, "2.5", POWER_KW)
    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    sent = [
        s.get("channel_key")
        for c in mock_client.ingest.await_args_list
        for s in c.kwargs["samples"] or []
    ]
    assert "grid" not in sent

    [status] = await async_status(hass)
    grid = next(c for c in status["channels"] if c["key"] == "grid")
    assert grid["shared"] is False
    assert grid["last_value"] is None


async def test_set_shared_refuses_what_does_not_exist(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """An unknown channel or entry changes nothing."""
    connection = MagicMock()
    connection.user.is_admin = True
    base = {"type": "kilowattlas/set_shared", "shared": False}
    ws_set_shared(
        hass,
        connection,
        {**base, "id": 1, "entry_id": init_integration.entry_id, "channel_key": "nope"},
    )
    ws_set_shared(
        hass, connection, {**base, "id": 2, "entry_id": "nope", "channel_key": "grid"}
    )
    await hass.async_block_till_done()
    assert connection.send_error.call_count == 2
    assert init_integration.options[CONF_EXCLUDED] == []


async def test_status_of_an_installation_not_running(hass: HomeAssistant) -> None:
    """An entry that could not start is shown, not hidden."""
    MockConfigEntry(domain="kilowattlas").add_to_hass(hass)
    assert (await async_status(hass))[0]["status"] == "not_loaded"


async def test_status_command_is_for_admins(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Administrators get the status; anyone else is refused."""
    connection = MagicMock()
    connection.user.is_admin = True
    ws_status(hass, connection, {"id": 1, "type": "kilowattlas/status"})
    await hass.async_block_till_done()
    result = connection.send_result.call_args.args[1]
    assert len(result["entries"]) == 1

    connection = MagicMock()
    connection.user.is_admin = False
    with pytest.raises(Unauthorized):
        ws_status(hass, connection, {"id": 2, "type": "kilowattlas/status"})
    with pytest.raises(Unauthorized):
        ws_set_shared(
            hass,
            connection,
            {
                "id": 3,
                "type": "kilowattlas/set_shared",
                "entry_id": init_integration.entry_id,
                "channel_key": "grid",
                "shared": False,
            },
        )
    connection.send_result.assert_not_called()


async def test_subscription_pushes_when_a_reading_is_sent(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The page hears of a reading when it is acknowledged, without asking."""
    connection = MagicMock()
    connection.user.is_admin = True
    connection.subscriptions = {}
    ws_subscribe_status(hass, connection, {"id": 7, "type": "kilowattlas/subscribe_status"})
    await hass.async_block_till_done()
    connection.send_result.assert_called_once_with(7)
    assert connection.send_message.call_count == 1

    hass.states.async_set(SOLAR, "5000", POWER_W)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done(wait_background_tasks=True)

    latest = connection.send_message.call_args.args[0]["event"]["entries"][0]
    solar = next(c for c in latest["channels"] if c["key"] == "")
    assert solar["last_value"] == 5.0

    # Unsubscribed, nothing more is sent.
    connection.subscriptions[7]()
    count = connection.send_message.call_count
    hass.states.async_set(SOLAR, "6000", POWER_W)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=4))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert connection.send_message.call_count == count


def _admin() -> MagicMock:
    connection = MagicMock()
    connection.user.is_admin = True
    return connection


async def test_details_are_read_from_kilowattlas(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Nothing is kept locally: what the map saved is what the page reads."""
    mock_client.get_site_details = AsyncMock(
        return_value=SiteDetails({"install_year": 2021}, "rev1")
    )
    connection = _admin()
    ws_get_details(
        hass,
        connection,
        {"id": 1, "type": "x", "entry_id": init_integration.entry_id},
    )
    await hass.async_block_till_done()
    connection.send_result.assert_called_once_with(
        1, {"details": {"install_year": 2021}, "revision": "rev1"}
    )


async def test_save_details_sends_only_known_fields(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Saved with the revision it was based on; other keys never leave."""
    mock_client.update_site_details = AsyncMock(
        return_value=SiteDetails({"roof_tilt_deg": 27}, "rev2")
    )
    connection = _admin()
    ws_save_details(
        hass,
        connection,
        {
            "id": 2,
            "type": "x",
            "entry_id": init_integration.entry_id,
            "revision": "rev1",
            "details": {"roof_tilt_deg": 27, "bio": "not this"},
        },
    )
    await hass.async_block_till_done()
    mock_client.update_site_details.assert_awaited_once_with(
        TOKEN, {"roof_tilt_deg": 27}, "rev1"
    )
    connection.send_result.assert_called_once_with(
        2, {"details": {"roof_tilt_deg": 27}, "revision": "rev2"}
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            KilowattlasConflictError({"install_year": 2022}, "new"),
            {"conflict": True, "details": {"install_year": 2022}, "revision": "new"},
        ),
        (KilowattlasRejectedError("value_out_of_range"), {"rejected": "value_out_of_range"}),
    ],
)
async def test_save_details_conflict_and_rejection(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
    expected: dict[str, Any],
) -> None:
    """Both are answers the page shows, not failures."""
    mock_client.update_site_details = AsyncMock(side_effect=error)
    connection = _admin()
    ws_save_details(
        hass,
        connection,
        {
            "id": 3,
            "type": "x",
            "entry_id": init_integration.entry_id,
            "revision": "old",
            "details": {},
        },
    )
    await hass.async_block_till_done()
    connection.send_result.assert_called_once_with(3, expected)


async def test_details_unavailable_and_unknown(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Unreachable, stopped or unknown: an error, and nothing changes."""
    mock_client.get_site_details = AsyncMock(side_effect=KilowattlasConnectionError("x"))
    mock_client.update_site_details = AsyncMock(
        side_effect=KilowattlasConnectionError("x")
    )
    connection = _admin()
    base = {"type": "x", "entry_id": init_integration.entry_id}
    ws_get_details(hass, connection, {**base, "id": 1})
    ws_save_details(hass, connection, {**base, "id": 2, "revision": "r", "details": {}})
    ws_get_details(hass, connection, {"type": "x", "id": 3, "entry_id": "nope"})
    stopped = MockConfigEntry(domain="kilowattlas")
    stopped.add_to_hass(hass)
    ws_get_details(hass, connection, {"type": "x", "id": 4, "entry_id": stopped.entry_id})
    await hass.async_block_till_done()
    assert connection.send_error.call_count == 4
