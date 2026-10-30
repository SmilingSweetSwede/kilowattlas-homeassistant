"""Diagnostics support for Kilowattlas."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import KilowattlasConfigEntry

TO_REDACT = {CONF_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    `channels` is how each shared Energy-dashboard field maps onto a server
    channel; `options` says whether they come from the Energy settings or
    from this integration's own (Energy-shaped) preferences.
    """
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "state": asdict(coordinator.data),
        "channels": [asdict(channel) for channel in coordinator.channels],
        "server_config": coordinator.server_config,
        "cursors": coordinator.cursors,
        "replay_windows": coordinator.replay_windows,
        "queue_length": coordinator.queue_length,
        "legacy_queue_length": coordinator.legacy_queue_length,
    }
