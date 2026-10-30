"""Config flow for Kilowattlas.

Device-linking wizard:
  1. `user`     - explain what is shared and ask for consent.
  2. `link`     - show a code and a link; wait (with a progress indicator, not
                  a blocked dialog) until the user approves it on the website.
  3. `channels` - list the power sensors of the user's Energy settings and let
                  the user leave any of them out. Without Energy settings,
                  `energy_missing` offers to check again after setting them up,
                  or to enter the same fields here (`manual`).

Re-authentication reuses step 2. The options flow reopens step 3.

The `manual` form asks for exactly what the Energy dashboard's power settings
ask for (homeassistant.components.energy.data): a sensor per source, and for
the grid and a battery the choice between one sensor, one inverted sensor, or
two sensors (`power_config`), validated with the Energy dashboard's own
`POWER_CONFIG_SCHEMA`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from aiokilowattlas import (
    DEFAULT_CONFIG,
    AuthorizationExpired,
    AuthorizationPending,
    DeviceCode,
    KilowattlasClient,
    KilowattlasError,
    TokenGrant,
    capability_tier,
)
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
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
from .energy_source import (
    Channel,
    async_energy_preferences,
    resolve_channels,
    validate_power_config,
)

_LOGGER = logging.getLogger(__name__)

# The server supplies both timings; clamp them so a hostile or buggy server can
# neither make us poll in a tight loop nor wait forever.
MIN_POLL_INTERVAL = 3
MAX_POLL_INTERVAL = 30
MIN_DEADLINE = 30
MAX_DEADLINE = 900

CONF_SHARE = "share"

# --- the manual form: the Energy dashboard's power fields --------------------

_POWER = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
_POWERS = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power", multiple=True)
)
_SOC = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="battery")
)
# The three ways the Energy dashboard reads grid and battery power.
MODE_SINGLE = "single"
MODE_INVERTED = "inverted"
MODE_TWO = "two"
_MODE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[MODE_SINGLE, MODE_INVERTED, MODE_TWO],
        translation_key="power_mode",
        mode=selector.SelectSelectorMode.LIST,
    )
)

SECTION_GRID = "grid"
SECTION_SOLAR = "solar"
SECTION_BATTERY = "battery"
SECTION_HOME = "home"
SECTION_DEVICES = "devices"

F_GRID_MODE = "grid_mode"
F_GRID = "grid_power"
F_GRID_TO = "grid_power_to"
F_SOLAR = "solar_power"
F_BATTERY_MODE = "battery_mode"
F_BATTERY = "battery_power"
F_BATTERY_TO = "battery_power_to"
F_BATTERY_SOC = "battery_soc"
F_BATTERY_CAPACITY = "battery_capacity"
F_HOME = "home_power"
F_DEVICES = "device_power"


def manual_schema(expanded: frozenset[str] = frozenset()) -> vol.Schema:
    """The manual form; sections are collapsed unless named in `expanded`."""
    fields: dict[str, dict[vol.Marker, Any]] = {
        SECTION_GRID: {
            vol.Optional(F_GRID_MODE, default=MODE_SINGLE): _MODE,
            vol.Optional(F_GRID): _POWER,
            vol.Optional(F_GRID_TO): _POWER,
        },
        SECTION_SOLAR: {vol.Optional(F_SOLAR): _POWER},
        SECTION_BATTERY: {
            vol.Optional(F_BATTERY_MODE, default=MODE_SINGLE): _MODE,
            vol.Optional(F_BATTERY): _POWER,
            vol.Optional(F_BATTERY_TO): _POWER,
            vol.Optional(F_BATTERY_SOC): _SOC,
            vol.Optional(F_BATTERY_CAPACITY): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=1000,
                    step=0.1,
                    unit_of_measurement="kWh",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        },
        SECTION_HOME: {vol.Optional(F_HOME): _POWER},
        SECTION_DEVICES: {vol.Optional(F_DEVICES): _POWERS},
    }
    return vol.Schema(
        {
            vol.Required(name): section(
                vol.Schema(f), {"collapsed": name not in expanded}
            )
            for name, f in fields.items()
        }
    )


def _power_config(
    mode: str, first: str | None, second: str | None
) -> dict[str, str] | None:
    """The Energy dashboard's power_config for one of the three modes."""
    if not first:
        return None
    if mode == MODE_INVERTED:
        return {"stat_rate_inverted": first}
    if mode == MODE_TWO:
        # Two positive sensors; Energy computes first - second:
        # grid: from the grid - to the grid; battery: discharge - charge.
        # A missing second sensor is left out, so the Energy schema's
        # "both or neither" rule reports it.
        config = {"stat_rate_from": first}
        if second:
            config["stat_rate_to"] = second
        return config
    return {"stat_rate": first}


def manual_preferences(
    hass: HomeAssistant, user_input: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Energy-dashboard-shaped preferences from the manual form, and errors."""
    grid = user_input.get(SECTION_GRID) or {}
    solar = user_input.get(SECTION_SOLAR) or {}
    battery = user_input.get(SECTION_BATTERY) or {}
    home = user_input.get(SECTION_HOME) or {}
    devices = user_input.get(SECTION_DEVICES) or {}
    errors: dict[str, str] = {}
    sources: list[dict[str, Any]] = []

    def checked(name: str, config: dict[str, str] | None) -> dict[str, str] | None:
        if config is None:
            return None
        try:
            return validate_power_config(config)
        except Exception:  # noqa: BLE001 - voluptuous or probatio, per HA version
            errors[name] = "invalid_power_config"
            return None

    if config := checked(
        SECTION_GRID,
        _power_config(
            grid.get(F_GRID_MODE, MODE_SINGLE), grid.get(F_GRID), grid.get(F_GRID_TO)
        ),
    ):
        sources.append({"type": "grid", "power_config": config})
    if solar.get(F_SOLAR):
        sources.append({"type": "solar", "stat_rate": solar[F_SOLAR]})
    battery_source: dict[str, Any] = {}
    if config := checked(
        SECTION_BATTERY,
        _power_config(
            battery.get(F_BATTERY_MODE, MODE_SINGLE),
            battery.get(F_BATTERY),
            battery.get(F_BATTERY_TO),
        ),
    ):
        battery_source["power_config"] = config
    if battery.get(F_BATTERY_SOC):
        battery_source["stat_soc"] = battery[F_BATTERY_SOC]
    if battery_source:
        if battery.get(F_BATTERY_CAPACITY):
            battery_source["capacity"] = float(battery[F_BATTERY_CAPACITY])
        sources.append({"type": "battery", **battery_source})
    if home.get(F_HOME):
        sources.append({"type": "home", "stat_rate": home[F_HOME]})
    device_list = []
    for entity_id in devices.get(F_DEVICES) or []:
        state = hass.states.get(entity_id)
        device_list.append(
            {"stat_rate": entity_id, "name": state.name if state else entity_id}
        )
    prefs = {"energy_sources": sources, "device_consumption": device_list}
    if not errors and not resolve_channels(prefs):
        errors["base"] = "nothing_to_share"
    return prefs, errors


def manual_suggested(prefs: Mapping[str, Any] | None) -> dict[str, Any]:
    """The manual form prefilled from stored preferences."""
    out: dict[str, Any] = {
        name: {}
        for name in (
            SECTION_GRID,
            SECTION_SOLAR,
            SECTION_BATTERY,
            SECTION_HOME,
            SECTION_DEVICES,
        )
    }

    def mode_fields(
        config: Mapping[str, str], mode_key: str, first: str, second: str
    ) -> dict[str, Any]:
        if "stat_rate_inverted" in config:
            return {mode_key: MODE_INVERTED, first: config["stat_rate_inverted"]}
        if "stat_rate_from" in config:
            return {
                mode_key: MODE_TWO,
                first: config["stat_rate_from"],
                second: config.get("stat_rate_to"),
            }
        return {mode_key: MODE_SINGLE, first: config.get("stat_rate")}

    for source in (prefs or {}).get("energy_sources") or []:
        match source.get("type"):
            case "grid" if not out[SECTION_GRID]:
                out[SECTION_GRID] = mode_fields(
                    source.get("power_config") or {}, F_GRID_MODE, F_GRID, F_GRID_TO
                )
            case "solar" if not out[SECTION_SOLAR]:
                out[SECTION_SOLAR] = {F_SOLAR: source.get("stat_rate")}
            case "battery" if not out[SECTION_BATTERY]:
                fields = mode_fields(
                    source.get("power_config") or {},
                    F_BATTERY_MODE,
                    F_BATTERY,
                    F_BATTERY_TO,
                )
                fields[F_BATTERY_SOC] = source.get("stat_soc")
                fields[F_BATTERY_CAPACITY] = source.get("capacity")
                out[SECTION_BATTERY] = fields
            case "home" if not out[SECTION_HOME]:
                out[SECTION_HOME] = {F_HOME: source.get("stat_rate")}
    devices = [
        d.get("stat_rate") for d in (prefs or {}).get("device_consumption") or []
    ]
    if devices:
        out[SECTION_DEVICES] = {F_DEVICES: devices}
    return {
        name: {k: v for k, v in fields.items() if v is not None}
        for name, fields in out.items()
    }


# --- the channels step ------------------------------------------------------

KIND_LABELS = {
    "en": {
        "gross_production": "Solar",
        "grid_power": "Grid",
        "battery_power": "Battery",
        "battery_soc": "Battery state of charge",
        "consumption": "Home",
        "device_power": "Device",
        "ev_charger_power": "EV charger",
        "heat_pump_power": "Heat pump",
    },
    "sv": {
        "gross_production": "Sol",
        "grid_power": "Elnät",
        "battery_power": "Batteri",
        "battery_soc": "Batteriets laddnivå",
        "consumption": "Hemmet",
        "device_power": "Enhet",
        "ev_charger_power": "Laddbox",
        "heat_pump_power": "Värmepump",
    },
}


def channel_options(
    hass: HomeAssistant, channels: list[Channel]
) -> list[selector.SelectOptionDict]:
    """One checkbox per channel: what it is and which sensor it reads."""
    labels = KIND_LABELS.get(hass.config.language.split("-")[0], KIND_LABELS["en"])
    options: list[selector.SelectOptionDict] = []
    for channel in channels:
        state = hass.states.get(channel.entity_id)
        sensor = state.name if state else channel.entity_id
        what = channel.name or labels.get(channel.kind, channel.kind)
        options.append(
            selector.SelectOptionDict(value=channel.key, label=f"{what}: {sensor}")
        )
    return options


def channels_schema(
    hass: HomeAssistant, channels: list[Channel], excluded: set[str]
) -> vol.Schema:
    """Every channel found, ticked unless the user left it out before."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SHARE, default=[c.key for c in channels if c.key not in excluded]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=channel_options(hass, channels),
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def energy_options(
    channels: list[Channel],
    shared: list[str],
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Entry options for sharing from the Energy settings."""
    previous = previous or {}
    return {
        CONF_SOURCE: SOURCE_ENERGY,
        CONF_PREFERENCES: previous.get(CONF_PREFERENCES) or {},
        CONF_KEY_OVERRIDES: previous.get(CONF_KEY_OVERRIDES) or {},
        CONF_EXCLUDED: sorted(c.key for c in channels if c.key not in set(shared)),
    }


def manual_options(
    prefs: dict[str, Any], previous: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Entry options for sharing manually entered sensors."""
    previous = previous or {}
    return {
        CONF_SOURCE: SOURCE_MANUAL,
        CONF_PREFERENCES: prefs,
        CONF_KEY_OVERRIDES: previous.get(CONF_KEY_OVERRIDES) or {},
        CONF_EXCLUDED: [],
    }


class KilowattlasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the linking wizard."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialise flow state."""
        self._client: KilowattlasClient | None = None
        self._device: DeviceCode | None = None
        self._grant: TokenGrant | None = None
        self._link_task: asyncio.Task[TokenGrant | None] | None = None
        self._link_error: str | None = None
        self._channels: list[Channel] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KilowattlasOptionsFlow:
        """What is shared can be changed at any time."""
        return KilowattlasOptionsFlow()

    # --- step 1: consent --------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain what is shared and ask for consent."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CONSENT):
                errors["base"] = "consent_required"
            else:
                return await self.async_step_link()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_CONSENT, default=False): selector.BooleanSelector()}
            ),
            errors=errors,
        )

    # --- step 2: link -----------------------------------------------------------

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request a device code, then wait for approval without blocking."""
        if self._link_task is None:
            self._client = KilowattlasClient(async_get_clientsession(self.hass))
            try:
                self._device = await self._client.request_device_code(
                    # HA's own position is volunteered so the web form can
                    # prefill where the installation is (consented in step 1).
                    self.hass.config.latitude,
                    self.hass.config.longitude,
                    capability={
                        "sample_capability": capability_tier(
                            DEFAULT_CONFIG["max_sample_interval_seconds"]
                        ),
                        "sample_interval_seconds": DEFAULT_CONFIG[
                            "max_sample_interval_seconds"
                        ],
                    },
                )
            except KilowattlasError as err:
                _LOGGER.debug(
                    "Requesting a device code from %s failed: %s",
                    self._client.base_url,
                    err,
                )
                return self.async_abort(reason="cannot_connect")
            self._link_task = self.hass.async_create_task(self._wait_for_approval())

        if not self._link_task.done():
            return self.async_show_progress(
                step_id="link",
                progress_action="wait_for_approval",
                progress_task=self._link_task,
                description_placeholders=self._placeholders(),
            )

        # The task reference is kept on purpose: the flow manager re-invokes
        # this step when the task finishes, and the frontend may do so once
        # more. Neither must start a second linking round.
        self._grant = self._link_task.result()
        if self._grant is None:
            return self.async_show_progress_done(next_step_id="link_failed")
        return self.async_show_progress_done(next_step_id="linked")

    def _placeholders(self) -> dict[str, str]:
        assert self._device is not None  # noqa: S101 - set before every caller
        return {
            "user_code": self._device.user_code,
            "verification_uri": self._device.verification_uri_complete,
        }

    async def _wait_for_approval(self) -> TokenGrant | None:
        """Poll until the code is approved, expired or the deadline passes.

        Runs as a background task behind the progress indicator. Returns None
        on failure and records why in `_link_error`.
        """
        assert self._client is not None and self._device is not None  # noqa: S101
        interval = min(max(self._device.interval, MIN_POLL_INTERVAL), MAX_POLL_INTERVAL)
        deadline = min(max(self._device.expires_in, MIN_DEADLINE), MAX_DEADLINE)
        waited = 0
        while waited < deadline:
            try:
                return await self._client.poll_token(self._device.device_code)
            except AuthorizationPending:
                await asyncio.sleep(interval)
                waited += interval
            except AuthorizationExpired:
                self._link_error = "expired"
                return None
            except KilowattlasError as err:
                _LOGGER.debug("Polling for approval failed: %s", err)
                self._link_error = "cannot_connect"
                return None
        # The code is only valid for `expires_in`; past it, it is as good as expired.
        self._link_error = "expired"
        return None

    async def async_step_link_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Abort after a failed link (progress flows cannot abort directly)."""
        return self.async_abort(reason=self._link_error or "cannot_connect")

    async def async_step_linked(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Approved: fix the unique id, then finish per flow source."""
        assert self._grant is not None  # noqa: S101
        await self.async_set_unique_id(str(self._grant.site_id))
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="unique_id_mismatch")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates={
                    CONF_TOKEN: self._grant.token,
                    CONF_SITE_ID: self._grant.site_id,
                },
            )
        self._abort_if_unique_id_configured()
        return await self.async_step_channels()

    # --- step 3: what to share ----------------------------------------------------

    def _create(self, options: dict[str, Any]) -> ConfigFlowResult:
        assert self._grant is not None  # noqa: S101
        return self.async_create_entry(
            title="Kilowattlas",
            data={CONF_TOKEN: self._grant.token, CONF_SITE_ID: self._grant.site_id},
            options=options,
        )

    async def async_step_channels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what the Energy settings hold; the user may leave some out."""
        if user_input is not None:
            return self._create(
                energy_options(self._channels, user_input.get(CONF_SHARE) or [])
            )
        self._channels = resolve_channels(await async_energy_preferences(self.hass))
        if not self._channels:
            return await self.async_step_energy_missing()
        return self.async_show_form(
            step_id="channels",
            data_schema=channels_schema(self.hass, self._channels, set()),
        )

    async def async_step_energy_missing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """No Energy settings yet: check again once set up, or enter them here."""
        return self.async_show_menu(
            step_id="energy_missing", menu_options=["channels", "manual"]
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter the Energy dashboard's power fields here instead."""
        errors: dict[str, str] = {}
        if user_input is not None:
            prefs, errors = manual_preferences(self.hass, user_input)
            if not errors:
                return self._create(manual_options(prefs))
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                manual_schema(frozenset({SECTION_GRID, SECTION_SOLAR})),
                user_input or {},
            ),
            errors=errors,
        )

    # --- reauth -------------------------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The server rejected the token: approve a new link."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm before starting a new device link."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_link()


class KilowattlasOptionsFlow(OptionsFlow):
    """Change what is shared without re-linking."""

    def __init__(self) -> None:
        """Initialise flow state."""
        self._channels: list[Channel] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Share from the Energy settings, or enter sensors here."""
        self._channels = resolve_channels(
            await async_energy_preferences(self.hass),
            self.config_entry.options.get(CONF_KEY_OVERRIDES),
        )
        if not self._channels:
            return await self.async_step_manual()
        return self.async_show_menu(step_id="init", menu_options=["channels", "manual"])

    async def async_step_channels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which power sensors of the Energy settings to share."""
        options = self.config_entry.options
        if user_input is not None:
            return self.async_create_entry(
                data=energy_options(
                    self._channels, user_input.get(CONF_SHARE) or [], options
                )
            )
        excluded = (
            set(options.get(CONF_EXCLUDED) or ())
            if options.get(CONF_SOURCE) == SOURCE_ENERGY
            else set()
        )
        return self.async_show_form(
            step_id="channels",
            data_schema=channels_schema(self.hass, self._channels, excluded),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter the Energy dashboard's power fields here."""
        options = self.config_entry.options
        errors: dict[str, str] = {}
        if user_input is not None:
            prefs, errors = manual_preferences(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=manual_options(prefs, options))
        suggested = user_input or (
            manual_suggested(options.get(CONF_PREFERENCES))
            if options.get(CONF_SOURCE) == SOURCE_MANUAL
            else {}
        )
        expanded = frozenset(
            name for name, fields in suggested.items() if fields
        ) or frozenset({SECTION_GRID, SECTION_SOLAR})
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                manual_schema(expanded), suggested
            ),
            errors=errors,
        )
