"""The Kilowattlas integration: share rooftop solar production with Kilowattlas."""

from __future__ import annotations

import logging

from aiokilowattlas import (
    KilowattlasAuthError,
    KilowattlasClient,
    KilowattlasConnectionError,
    KilowattlasError,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_POWER_SENSOR, CONF_SITE_ID, CONF_TOKEN
from .coordinator import KilowattlasConfigEntry, KilowattlasCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: KilowattlasConfigEntry) -> bool:
    """Set up Kilowattlas from a config entry."""
    client = KilowattlasClient(async_get_clientsession(hass))
    token: str = entry.data[CONF_TOKEN]

    # Verify the link before anything else: a revoked token is a reauth, an
    # unreachable API is a retry. Neither should produce a half-set-up entry.
    try:
        site = await client.get_site(token)
    except KilowattlasAuthError as err:
        raise ConfigEntryAuthFailed("Kilowattlas rejected the sharing token") from err
    except KilowattlasConnectionError as err:
        raise ConfigEntryNotReady("Cannot reach Kilowattlas") from err
    except KilowattlasError as err:
        raise ConfigEntryNotReady(f"Unexpected answer from Kilowattlas: {err}") from err

    coordinator = KilowattlasCoordinator(
        hass,
        entry,
        client,
        token,
        site_id=int(entry.data.get(CONF_SITE_ID) or site.site_id),
        sensor=entry.data[CONF_POWER_SENSOR],
        initial_config=site.config,
    )
    await coordinator.async_start()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> bool:
    """Unload a config entry. Also runs on reload and restart, so never revoke here."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> None:
    """Revoke the sharing token when the user removes the integration.

    Best effort: a failure (for example being offline) must not block removal,
    so it is logged and the token stays valid until the installation is deleted
    on the website.
    """
    token = entry.data.get(CONF_TOKEN)
    if not token:
        return
    client = KilowattlasClient(async_get_clientsession(hass))
    try:
        await client.revoke(token)
    except KilowattlasError as err:
        _LOGGER.warning(
            "Could not revoke the sharing token on removal; delete the installation "
            "on the website to stop sharing: %s",
            err,
        )
