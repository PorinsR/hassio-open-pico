"""Config flow for Open Pico integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS, CONF_PIN, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .pico_manager import PicoClientManager

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Required(CONF_PIN): str,
        vol.Optional(CONF_NAME): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # Create a temporary manager and client to test connection
    # Note: In a real scenario, we might want to use the shared manager, 
    # but for validation we just want to see if the device responds.
    # However, since the manager handles the UDP transport, we should use a temporary one
    # or reuse the existing one if available.
    
    # We'll use a temporary manager on a different port to avoid conflicts?
    # Or just try to use the existing manager structure if it exists.
    
    ip = data[CONF_IP_ADDRESS]
    pin = data[CONF_PIN]
    
    # TODO: Implement actual validation logic
    # checking if we can connect to the device.
    
    return {"title": data.get(CONF_NAME) or f"Pico {ip}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open Pico."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # info = await validate_input(self.hass, user_input)
                
                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_IP_ADDRESS])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or f"Pico {user_input[CONF_IP_ADDRESS]}",
                    data=user_input
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle import from YAML."""
        # Check if already configured
        await self.async_set_unique_id(user_input[CONF_IP_ADDRESS])
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=user_input.get(CONF_NAME) or f"Pico {user_input[CONF_IP_ADDRESS]}",
            data=user_input,
        )
