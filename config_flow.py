"""Config flow for Open Pico integration."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class OpenPicoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open Pico."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="Open Pico", data=user_input)

        return self.async_show_form(step_id="user")

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle import from YAML."""
        # We handle YAML setup in async_setup, so we don't necessarily need to create an entry here
        # But if HA insists on import, we can create one.
        return self.async_create_entry(title="Open Pico (YAML)", data=user_input)
