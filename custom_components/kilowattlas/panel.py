"""The status page in the sidebar: shows that this home is connected.

The Energy dashboard is generated and takes no cards from integrations, so the
status has a page of its own until Home Assistant offers a place for it.
Custom integration only (installed from the Marketplace): scripts/sync_to_core.sh
strips this module and its frontend, because core integrations do not ship
frontend code.

The status is plain data from one websocket command, so anything else that may
show it later (a card in another dashboard, a place in the Energy dashboard)
reads the same thing.
"""

from __future__ import annotations

from hashlib import sha256
import logging
from pathlib import Path
from typing import Any

from aiokilowattlas import (
    KilowattlasConflictError,
    KilowattlasError,
    KilowattlasRejectedError,
)
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    CONF_EXCLUDED,
    CONF_KNOWN,
    DOMAIN,
    MAP_BASE_URL,
    SIGNAL_STATUS_UPDATED,
)
from .energy_source import excluded_keys
from .sensor import map_url

PANEL_PATH = DOMAIN
PANEL_ELEMENT = "kilowattlas-panel"
PANEL_ICON = "kilowattlas:logo"
STATIC_URL = "/kilowattlas_static"
SCRIPT = "kilowattlas-panel.js"
FRONTEND_DIR = Path(__file__).parent / "frontend"
DATA_PANEL_URL = f"{DOMAIN}_panel_url"
STATUS_NOT_LOADED = "not_loaded"
# Readings arrive in bursts: the first change goes out at once, the rest at most
# this often.
PUSH_COOLDOWN_SECONDS = 1

ERR_UNAVAILABLE = "unavailable"
# What the status page may change: the same fields as Edit my plant on the map.
DETAIL_FIELDS = frozenset(
    {
        "name",
        "capacity_kw",
        "install_year",
        "panel_make",
        "inverter_make",
        "panel_count",
        "roof_tilt_deg",
        "roof_direction",
        "roof_azimuth_deg",
        "battery_kwh",
        "mount_type",
    }
)

_LOGGER = logging.getLogger(__name__)


def _script_hash() -> str:
    digest = sha256()
    for path in sorted(FRONTEND_DIR.glob("*.js")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Add the page and its script; once per Home Assistant process."""
    # Without a frontend (a headless install) there is nothing to show it in.
    if "frontend" not in hass.config.components:
        return

    url = hass.data.get(DATA_PANEL_URL)
    if url is None:
        # Named after its content, so a browser never keeps an old copy.
        version = await hass.async_add_executor_job(_script_hash)
        url = f"{STATIC_URL}/{SCRIPT}?v={version}"
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), True)
            ]
        )
        websocket_api.async_register_command(hass, ws_status)
        websocket_api.async_register_command(hass, ws_subscribe_status)
        websocket_api.async_register_command(hass, ws_set_shared)
        websocket_api.async_register_command(hass, ws_get_details)
        websocket_api.async_register_command(hass, ws_save_details)
        hass.data[DATA_PANEL_URL] = url

    if PANEL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        return
    # Loaded on every page: the sidebar needs the icon before the page opens.
    frontend.add_extra_js_url(hass, url)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="Kilowattlas",
        sidebar_icon=PANEL_ICON,
        module_url=url,
        require_admin=True,
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the page with the last installation."""
    url = hass.data.get(DATA_PANEL_URL)
    if url is None or hass.config_entries.async_entries(DOMAIN):
        return
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
    frontend.remove_extra_js_url(hass, url)


async def _async_channel_rows(
    hass: HomeAssistant, entry: ConfigEntry, loaded: bool
) -> list[dict[str, Any]]:
    """Every channel of the installation: what it reads, and if and what it sent."""
    coordinator = entry.runtime_data if loaded else None
    available = await _async_available(hass, entry)
    excluded = excluded_keys(entry.options, available)
    last_sent = coordinator.last_sent if coordinator else {}
    rows = []
    for channel in available:
        state = hass.states.get(channel.entity_id)
        last = last_sent.get(channel.key) or {}
        rows.append(
            {
                "key": channel.key,
                "kind": channel.kind,
                "name": channel.name,
                "sensor": state.name if state else channel.entity_id,
                "percent": channel.percent,
                "shared": channel.key not in excluded,
                "off_on_web": bool(coordinator and coordinator.channel_disabled(channel.key)),
                "last_value": last.get("power_kw"),
                "last_sent": last.get("ts"),
            }
        )
    return rows


async def async_status(hass: HomeAssistant) -> list[dict[str, Any]]:
    """The sharing status of every installation, as plain data."""
    out: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        loaded = entry.state is ConfigEntryState.LOADED
        data = entry.runtime_data.data if loaded else None
        out.append(
            {
                "entry_id": entry.entry_id,
                "status": data.status if data else STATUS_NOT_LOADED,
                "shared_channels": data.shared_channels if data else 0,
                "last_sent": (
                    data.last_push.isoformat() if data and data.last_push else None
                ),
                "queued": data.pending_count if data else 0,
                "catching_up": data.catching_up if data else False,
                "rejected": data.last_rejected if data else 0,
                "map_url": map_url(hass),
                "community_url": f"{MAP_BASE_URL}/energigemenskap",
                "channels": await _async_channel_rows(hass, entry, loaded),
            }
        )
    return out


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "kilowattlas/status"})
@websocket_api.async_response
async def ws_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Answer with the sharing status."""
    connection.send_result(msg["id"], {"entries": await async_status(hass)})


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "kilowattlas/subscribe_status"})
@websocket_api.async_response
async def ws_subscribe_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the sharing status now and whenever it changes."""

    async def _send() -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"entries": await async_status(hass)})
        )

    debouncer = Debouncer(
        hass,
        _LOGGER,
        cooldown=PUSH_COOLDOWN_SECONDS,
        immediate=True,
        function=_send,
        background=True,
    )
    unsubscribe = async_dispatcher_connect(
        hass, SIGNAL_STATUS_UPDATED, debouncer.async_schedule_call
    )

    @callback
    def _unsubscribe() -> None:
        unsubscribe()
        debouncer.async_cancel()

    connection.subscriptions[msg["id"]] = _unsubscribe
    connection.send_result(msg["id"])
    await _send()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "kilowattlas/set_shared",
        "entry_id": str,
        "channel_key": str,
        "shared": bool,
    }
)
@websocket_api.async_response
async def ws_set_shared(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Tick or untick a channel: the same option as the integration's Configure.

    The update listener reloads the entry. An unticked channel is no longer sent;
    ticked again it starts with its next reading, so nothing measured while it
    was unticked ever leaves Home Assistant.
    """
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown entry")
        return
    keys = {c.key for c in await _async_available(hass, entry)}
    key = msg["channel_key"]
    if key not in keys:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown channel")
        return
    excluded = set(entry.options.get(CONF_EXCLUDED) or ())
    if msg["shared"]:
        excluded.discard(key)
    else:
        excluded.add(key)
    # Either way the user has now decided on this sensor.
    known = set(entry.options.get(CONF_KNOWN) or ()) | {key}
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_EXCLUDED: sorted(excluded),
            CONF_KNOWN: sorted(known),
        },
    )
    connection.send_result(msg["id"])


def _loaded_entry(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> ConfigEntry | None:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown entry")
        return None
    if entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], ERR_UNAVAILABLE, "Not running")
        return None
    return entry


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "kilowattlas/get_details", "entry_id": str})
@websocket_api.async_response
async def ws_get_details(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Read the installation's description from Kilowattlas. Nothing is kept here."""
    if (entry := _loaded_entry(hass, connection, msg)) is None:
        return
    try:
        site = await entry.runtime_data.async_get_site_details()
    except KilowattlasError as err:
        connection.send_error(msg["id"], ERR_UNAVAILABLE, str(err))
        return
    connection.send_result(
        msg["id"], {"details": site.details, "revision": site.revision}
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "kilowattlas/save_details",
        "entry_id": str,
        "revision": str,
        "details": dict,
    }
)
@websocket_api.async_response
async def ws_save_details(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Save the description to Kilowattlas, the same fields as on the map.

    Changed elsewhere since it was read: nothing is saved, and the answer says so
    with the current values. A refused value comes back with the server's code.
    """
    if (entry := _loaded_entry(hass, connection, msg)) is None:
        return
    details = {k: v for k, v in msg["details"].items() if k in DETAIL_FIELDS}
    try:
        site = await entry.runtime_data.async_save_site_details(
            details, msg["revision"]
        )
    except KilowattlasConflictError as err:
        connection.send_result(
            msg["id"],
            {"conflict": True, "details": err.current, "revision": err.revision},
        )
    except KilowattlasRejectedError as err:
        connection.send_result(msg["id"], {"rejected": err.code})
    except KilowattlasError as err:
        connection.send_error(msg["id"], ERR_UNAVAILABLE, str(err))
    else:
        connection.send_result(
            msg["id"], {"details": site.details, "revision": site.revision}
        )


async def _async_available(hass: HomeAssistant, entry: ConfigEntry) -> list[Any]:
    from . import async_available_channels  # noqa: PLC0415 (imports this module)

    return await async_available_channels(hass, entry)
