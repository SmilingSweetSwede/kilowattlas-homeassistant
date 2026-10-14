"""Config flow for Kilowattlas.

Device-linking wizard:
  1. `user`   - explain what is shared and ask for consent.
  2. `link`   - show a code and a link; wait (with a progress indicator, not a
                blocked dialog) until the user approves it on the website.
  3. `sensor` - choose the power sensor to share.

Re-authentication reuses step 2; reconfiguration reuses step 3.
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
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CONSENT, CONF_POWER_SENSOR, CONF_SITE_ID, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

# The server supplies both timings; clamp them so a hostile or buggy server can
# neither make us poll in a tight loop nor wait forever.
MIN_POLL_INTERVAL = 3
MAX_POLL_INTERVAL = 30
MIN_DEADLINE = 30
MAX_DEADLINE = 900

SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="power")
        )
    }
)


class KilowattlasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the linking wizard."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._client: KilowattlasClient | None = None
        self._device: DeviceCode | None = None
        self._grant: TokenGrant | None = None
        self._link_task: asyncio.Task[TokenGrant | None] | None = None
        self._link_error: str | None = None

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
            except KilowattlasError:
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
        return await self.async_step_sensor()

    # --- step 3: sensor ---------------------------------------------------------

    async def async_step_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the power sensor to share."""
        if user_input is not None:
            assert self._grant is not None  # noqa: S101
            return self.async_create_entry(
                title="Kilowattlas",
                data={
                    CONF_TOKEN: self._grant.token,
                    CONF_SITE_ID: self._grant.site_id,
                    CONF_POWER_SENSOR: user_input[CONF_POWER_SENSOR],
                },
            )
        return self.async_show_form(step_id="sensor", data_schema=SENSOR_SCHEMA)

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

    # --- reconfigure --------------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the shared power sensor without re-linking."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry, data_updates={CONF_POWER_SENSOR: user_input[CONF_POWER_SENSOR]}
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                SENSOR_SCHEMA, {CONF_POWER_SENSOR: entry.data.get(CONF_POWER_SENSOR)}
            ),
        )
