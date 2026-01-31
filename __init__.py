"""Open Pico integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform, CONF_IP_ADDRESS, CONF_PIN, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import MainCoordinator
from .pico_manager import PicoClientManager


_LOGGER = logging.getLogger(__name__)

# The list of supported platforms
PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
]

# Define the device schema
DEVICE_SCHEMA = vol.Schema({
    vol.Required("ip"): cv.string,
    vol.Required("pin"): cv.string,
    vol.Optional("name"): cv.string,  # Optional friendly name
})

# Define your YAML configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Required("devices"): vol.All(cv.ensure_list, [DEVICE_SCHEMA]),
            vol.Optional("local_port", default=40069): cv.port,
            vol.Optional("verbose", default=False): cv.boolean,
        })
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Open Pico integration from YAML configuration."""
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN not in config:
        return True

    domain_config = config[DOMAIN]
    devices = domain_config.get("devices", [])
    local_port = domain_config.get("local_port", 40069)
    verbose = domain_config.get("verbose", False)
    
    # Store global config (port, verbose) to be used by async_setup_entry
    hass.data[DOMAIN]["local_port"] = local_port
    hass.data[DOMAIN]["verbose"] = verbose

    for device_config in devices:
        entry_data = {
            CONF_IP_ADDRESS: device_config["ip"],
            CONF_PIN: device_config["pin"],
            CONF_NAME: device_config.get("name")
        }
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=entry_data
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open Pico from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Check if manager exists, if not create it
    if "manager" not in hass.data[DOMAIN]:
        local_port = hass.data[DOMAIN].get("local_port", 40069)
        verbose = hass.data[DOMAIN].get("verbose", False)
        
        manager = PicoClientManager(local_port=local_port, verbose=verbose)
        try:
            await manager.initialize()
            hass.data[DOMAIN]["manager"] = manager
            _LOGGER.info("Shared transport initialized on port %d", local_port)
        except Exception as err:
            _LOGGER.error("Failed to initialize shared transport: %s", err, exc_info=True)
            return False
            
    manager: PicoClientManager = hass.data[DOMAIN]["manager"]
    
    pico_ip = entry.data[CONF_IP_ADDRESS]
    pin = entry.data[CONF_PIN]
    device_name = entry.data.get(CONF_NAME) or f"Pico {pico_ip}"
    
    device_id = f"pico_{pico_ip.replace('.', '_')}"
    
    # Create client
    client = manager.create_client(
        ip=pico_ip,
        pin=pin,
        device_id=device_id,
        timeout=15,
        retry_attempts=3,
        retry_delay=2.0
    )
    
    # Connect
    try:
        await client.connect()
    except Exception as err:
        _LOGGER.error("Failed to connect to device %s: %s", device_name, err)
        # We don't return False here to allow retries by coordinator, 
        # but client needs to be connected for initial fetch?
        # Coordinator handles reconnection.
        # But if we fail here, maybe we should raise ConfigEntryNotReady?
        from homeassistant.exceptions import ConfigEntryNotReady
        raise ConfigEntryNotReady(f"Failed to connect to device: {err}") from err
        
    coordinator = MainCoordinator(hass, client, device_name)
    
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
         _LOGGER.error("Failed initial refresh for %s: %s", device_name, err)
         await client.disconnect()
         raise # This triggers ConfigEntryNotReady
         
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        
        # If no more entries, shutdown manager
        if not hass.config_entries.async_entries(DOMAIN):
             if "manager" in hass.data[DOMAIN]:
                 try:
                     await hass.data[DOMAIN]["manager"].shutdown()
                 except Exception as err:
                     _LOGGER.error("Error shutting down manager: %s", err)
                 hass.data[DOMAIN].pop("manager")
                 
    return unload_ok
