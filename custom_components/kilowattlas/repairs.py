"""Repairs for Kilowattlas."""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_SOURCE, ISSUE_USE_ENERGY, SOURCE_ENERGY


class UseEnergySettingsFlow(ConfirmRepairFlow):
    """Switch an entry from its own sensor list to the Energy settings.

    Key overrides and excluded channels are kept, so every channel continues
    on the server with its history.
    """

    def __init__(self, entry_id: str) -> None:
        """Remember which entry to switch."""
        super().__init__()
        self._entry_id = entry_id

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Switch once the user confirms."""
        if user_input is not None:
            if entry := self.hass.config_entries.async_get_entry(self._entry_id):
                self.hass.config_entries.async_update_entry(
                    entry, options={**entry.options, CONF_SOURCE: SOURCE_ENERGY}
                )
            return self.async_create_entry(data={})
        return await super().async_step_confirm(user_input)


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow for a fixable issue."""
    if issue_id.startswith(ISSUE_USE_ENERGY) and data and "entry_id" in data:
        return UseEnergySettingsFlow(str(data["entry_id"]))
    return ConfirmRepairFlow()
