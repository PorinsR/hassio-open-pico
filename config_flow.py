"""Config flow for Open Pico integration."""
from __future__ import annotations

import logging
import asyncio
import ipaddress
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS, CONF_PIN, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .pico_manager import PicoClientManager
from .open_pico_local_api.shared_transport_manager import SharedTransportManager

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
    ip = data[CONF_IP_ADDRESS]
    pin = data[CONF_PIN]
    user_name = data.get(CONF_NAME)

    # Normalize IP
    try:
        ip_obj = ipaddress.ip_address(ip)
        normalized_ip = str(ip_obj)
    except ValueError:
        normalized_ip = ip

    # 1. Initialize or get shared manager
    # We need to access the manager to create a client.
    # Since this might be the first setup, we need to ensure it's initialized.
    
    # Check if manager already exists in hass.data
    manager = None
    if DOMAIN in hass.data and "manager" in hass.data[DOMAIN]:
        manager = hass.data[DOMAIN]["manager"]
    else:
        # If not, create a temporary one or initialize the global one?
        # Ideally we initialize the global one.
        # But we need config for port/verbose which might not be set if not via YAML.
        # Default to 40069.
        manager = PicoClientManager(local_port=40069)
        await manager.initialize()
        # We don't store it in hass.data yet, or maybe we should?
        # If we don't store it, we must shutdown it if validation fails to release port?
        # Actually SharedTransportManager is a singleton pattern in the lib, 
        # so initializing it here affects the global state.
    
    device_id = f"pico_{normalized_ip.replace('.', '_')}"
    
    # 2. Create a client
    client = manager.create_client(
        ip=normalized_ip,
        pin=pin,
        device_id=device_id,
        timeout=5,
        retry_attempts=2
    )
    
    try:
        # 3. Connect and fetch status
        await client.connect()
        status = await client.get_status(retry=True)
        
        # 4. Extract name from device
        device_name_from_packet = status.device_info.name
        
        # If user didn't provide a name, use the one from the device
        final_name = user_name or device_name_from_packet or f"Pico {normalized_ip}"
        
        return {"title": final_name, "device_name": device_name_from_packet}
        
    except Exception as e:
        _LOGGER.error(f"Failed to validate connection to {normalized_ip}: {e}")
        raise CannotConnect from e
    finally:
        # If we created a temporary client, disconnect it
        await client.disconnect()
        # If we initialized the manager just for this check and didn't store it, 
        # we might want to shut it down IF no other devices are using it.
        # But SharedTransportManager is a singleton, so shutting it down affects everyone.
        # Safe to leave it running if we are adding a device.


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
                # Normalize IP
                try:
                    ip_obj = ipaddress.ip_address(user_input[CONF_IP_ADDRESS])
                    user_input[CONF_IP_ADDRESS] = str(ip_obj)
                except ValueError:
                    pass # Keep original if invalid (validation might catch it later)

                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_IP_ADDRESS])
                self._abort_if_unique_id_configured()

                # Validate connection and get name
                info = await validate_input(self.hass, user_input)
                
                # If name was found on device and user didn't provide one, store it
                if not user_input.get(CONF_NAME) and info.get("device_name"):
                    user_input[CONF_NAME] = info["device_name"]

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle import from YAML."""
        # Normalize IP (YAML import should already be normalized by async_setup, but just in case)
        try:
            ip_obj = ipaddress.ip_address(user_input[CONF_IP_ADDRESS])
            user_input[CONF_IP_ADDRESS] = str(ip_obj)
        except ValueError:
            pass

        # Check if already configured
        await self.async_set_unique_id(user_input[CONF_IP_ADDRESS])
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=user_input.get(CONF_NAME) or f"Pico {user_input[CONF_IP_ADDRESS]}",
            data=user_input,
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
