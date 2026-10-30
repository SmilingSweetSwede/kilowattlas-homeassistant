"""The Kilowattlas integration: share what the Energy dashboard measures."""

from __future__ import annotations

import logging
from typing import Any

from aiokilowattlas import (
    KIND_BATTERY_POWER,
    KIND_BATTERY_SOC,
    KIND_EV_CHARGER_POWER,
    KIND_HEAT_PUMP_POWER,
    KilowattlasAuthError,
    KilowattlasClient,
    KilowattlasConnectionError,
    KilowattlasError,
)
from homeassistant.components.energy.data import async_get_manager
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_EXCLUDED,
    CONF_KEY_OVERRIDES,
    CONF_PREFERENCES,
    CONF_SITE_ID,
    CONF_SOURCE,
    CONF_TOKEN,
    DOMAIN,
    ISSUE_NO_CHANNELS,
    ISSUE_USE_ENERGY,
    LEGACY_BATTERY_CHARGE_POSITIVE,
    LEGACY_BATTERY_POWER_SENSOR,
    LEGACY_BATTERY_SOC_SENSOR,
    LEGACY_CHANNEL_EV_CHARGER,
    LEGACY_CHANNEL_HEAT_PUMP,
    LEGACY_CONSUMPTION_SENSOR,
    LEGACY_EV_CHARGER_SENSOR,
    LEGACY_GRID_IMPORT_POSITIVE,
    LEGACY_GRID_POWER_SENSOR,
    LEGACY_HEAT_PUMP_SENSOR,
    LEGACY_KEYS,
    LEGACY_POWER_SENSOR,
    SOURCE_ENERGY,
    SOURCE_MANUAL,
)
from .coordinator import KilowattlasConfigEntry, KilowattlasCoordinator
from .energy_source import (
    Channel,
    async_energy_preferences,
    battery_capacity_kwh,
    power_transforms,
    resolve_channels,
    resolve_manual_preferences,
    transform_unique_id,
)
from .panel import async_remove_panel, async_setup_panel  # hacs-only

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

# hass.data key: the one Energy-settings listener of this process. The Energy
# manager offers no way to unregister a listener, so it is registered once
# and fans out to whichever entries are loaded.
DATA_ENERGY_LISTENER = f"{DOMAIN}_energy_listener"


async def _async_preferences(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> dict[str, Any] | None:
    """The Energy-shaped preferences this installation reads."""
    options = entry.options
    if options.get(CONF_SOURCE, SOURCE_ENERGY) == SOURCE_MANUAL:
        registry = er.async_get(hass)
        return resolve_manual_preferences(
            options.get(CONF_PREFERENCES),
            lambda t: registry.async_get_entity_id(
                "sensor", DOMAIN, transform_unique_id(entry.entry_id, t)
            ),
        )
    return await async_energy_preferences(hass)


async def async_available_channels(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> list[Channel]:
    """Every channel that could be shared, ticked or not."""
    return resolve_channels(
        await _async_preferences(hass, entry), entry.options.get(CONF_KEY_OVERRIDES)
    )


async def async_resolve(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> tuple[list[Channel], float | None]:
    """The channels to share and the battery capacity."""
    prefs = await _async_preferences(hass, entry)
    excluded = set(entry.options.get(CONF_EXCLUDED) or ())
    channels = [
        c
        for c in resolve_channels(prefs, entry.options.get(CONF_KEY_OVERRIDES))
        if c.key not in excluded
    ]
    # A battery's size says it exists: unticked, it stays home with its readings.
    shares_battery = any(
        c.kind in (KIND_BATTERY_POWER, KIND_BATTERY_SOC) for c in channels
    )
    return channels, battery_capacity_kwh(prefs) if shares_battery else None


async def _async_update_issues(
    hass: HomeAssistant, entry: KilowattlasConfigEntry, channels: list[Channel]
) -> None:
    """Raise or clear the repair issues that depend on what is shared."""
    issue_no_channels = f"{ISSUE_NO_CHANNELS}_{entry.entry_id}"
    if channels:
        ir.async_delete_issue(hass, DOMAIN, issue_no_channels)
    else:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_no_channels,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_NO_CHANNELS,
        )

    issue_use_energy = f"{ISSUE_USE_ENERGY}_{entry.entry_id}"
    if entry.options.get(CONF_SOURCE) == SOURCE_MANUAL and resolve_channels(
        await async_energy_preferences(hass)
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_use_energy,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_USE_ENERGY,
            data={"entry_id": entry.entry_id},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_use_energy)


async def async_refresh_channels(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> None:
    """Re-read what is shared and hand it to the running coordinator."""
    channels, capacity = await async_resolve(hass, entry)
    await entry.runtime_data.async_update_channels(channels, capacity)
    await _async_update_issues(hass, entry, channels)


async def _async_ensure_energy_listener(hass: HomeAssistant) -> None:
    """Follow changes of the Energy settings, once per process."""
    if hass.data.get(DATA_ENERGY_LISTENER):
        return
    hass.data[DATA_ENERGY_LISTENER] = True

    async def _on_energy_update() -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await async_refresh_channels(hass, entry)

    (await async_get_manager(hass)).async_listen_updates(_on_energy_update)


async def async_setup_entry(hass: HomeAssistant, entry: KilowattlasConfigEntry) -> bool:
    """Set up Kilowattlas from a config entry."""
    await async_setup_panel(hass)  # hacs-only
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

    channels, capacity = await async_resolve(hass, entry)
    coordinator = KilowattlasCoordinator(
        hass,
        entry,
        client,
        token,
        site_id=int(entry.data.get(CONF_SITE_ID) or site.site_id),
        channels=channels,
        battery_capacity_kwh=capacity,
        initial_config=site.config,
    )
    await coordinator.async_start()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Transform sensors of manual preferences are registered only now.
    if entry.options.get(CONF_SOURCE) == SOURCE_MANUAL and power_transforms(
        entry.options.get(CONF_PREFERENCES)
    ):
        await async_refresh_channels(hass, entry)
    else:
        await _async_update_issues(hass, entry, channels)

    await _async_ensure_energy_listener(hass)

    @callback
    def _on_registry_update(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        # A renamed sensor, including a transform sensor the Energy dashboard
        # renamed, changes which entity a channel reads.
        if event.data["action"] != "update" or "old_entity_id" not in event.data:
            return
        shared = {c.entity_id for c in entry.runtime_data.channels}
        reg_entry = er.async_get(hass).async_get(event.data["entity_id"])
        if event.data["old_entity_id"] in shared or (
            reg_entry is not None and reg_entry.platform in ("energy", DOMAIN)
        ):
            entry.async_create_background_task(
                hass, async_refresh_channels(hass, entry), f"{DOMAIN}_refresh"
            )

    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _on_registry_update)
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> None:
    """What is shared changed in the options: start over with it."""
    await hass.config_entries.async_reload(entry.entry_id)


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
    for issue in (ISSUE_NO_CHANNELS, ISSUE_USE_ENERGY):
        ir.async_delete_issue(hass, DOMAIN, f"{issue}_{entry.entry_id}")
    async_remove_panel(hass)  # hacs-only
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


def preferences_from_legacy(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Energy-dashboard-shaped preferences for a pre-1.0.0 entry.

    Every sensor keeps its server channel: the first solar, grid and battery
    sources and the home source map onto the keys 0.7.0 used, and the two
    fixed load sensors keep theirs through key overrides. Sign flags become
    the Energy dashboard's own `power_config`: 0.7.0 counted grid export and
    battery discharge as positive, the Energy dashboard counts grid import and
    battery discharge as positive.
    """
    sources: list[dict[str, Any]] = []
    if solar := data.get(LEGACY_POWER_SENSOR):
        sources.append({"type": "solar", "stat_rate": solar})
    if grid := data.get(LEGACY_GRID_POWER_SENSOR):
        # The checkbox said "my sensor shows import as positive", which is
        # exactly the Energy dashboard's convention.
        key = (
            "stat_rate"
            if data.get(LEGACY_GRID_IMPORT_POSITIVE)
            else "stat_rate_inverted"
        )
        sources.append({"type": "grid", "power_config": {key: grid}})
    battery: dict[str, Any] = {}
    if power := data.get(LEGACY_BATTERY_POWER_SENSOR):
        key = (
            "stat_rate_inverted"
            if data.get(LEGACY_BATTERY_CHARGE_POSITIVE)
            else "stat_rate"
        )
        battery["power_config"] = {key: power}
    if soc := data.get(LEGACY_BATTERY_SOC_SENSOR):
        battery["stat_soc"] = soc
    if battery:
        sources.append({"type": "battery", **battery})
    if home := data.get(LEGACY_CONSUMPTION_SENSOR):
        sources.append({"type": "home", "stat_rate": home})

    devices: list[dict[str, Any]] = []
    overrides: dict[str, list[str]] = {}
    for conf, name, key, kind in (
        (
            LEGACY_EV_CHARGER_SENSOR,
            "EV charger",
            LEGACY_CHANNEL_EV_CHARGER,
            KIND_EV_CHARGER_POWER,
        ),
        (
            LEGACY_HEAT_PUMP_SENSOR,
            "Heat pump",
            LEGACY_CHANNEL_HEAT_PUMP,
            KIND_HEAT_PUMP_POWER,
        ),
    ):
        if entity_id := data.get(conf):
            devices.append({"stat_rate": entity_id, "name": name})
            overrides[entity_id] = [key, kind]
    return {"energy_sources": sources, "device_consumption": devices}, overrides


async def async_migrate_entry(
    hass: HomeAssistant, entry: KilowattlasConfigEntry
) -> bool:
    """Migrate a pre-1.0.0 entry (own sensor picker) onto the Energy model.

    The token and site are kept as they are. The chosen sensors become manual
    Energy-shaped preferences on the same server channels, so no channel and
    no history is lost; a repair issue then offers to switch to the Energy
    settings when they cover the home.
    """
    if entry.version > 2:
        return False
    if entry.version == 1:
        prefs, overrides = preferences_from_legacy(dict(entry.data))
        data = {k: v for k, v in entry.data.items() if k not in LEGACY_KEYS}
        options = {
            CONF_SOURCE: SOURCE_MANUAL,
            CONF_PREFERENCES: prefs,
            CONF_KEY_OVERRIDES: overrides,
            CONF_EXCLUDED: [],
        }
        # The production mirror entity is gone in 1.0.0: the solar sensor
        # itself shows the same value.
        registry = er.async_get(hass)
        if entity_id := registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_shared_production"
        ):
            registry.async_remove(entity_id)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=2
        )
        _LOGGER.info("Migrated Kilowattlas entry to the Energy-dashboard model")
    return True
