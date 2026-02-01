"""Open Pico integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
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
    Platform.NUMBER,
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

    # Check if domain is in config
    if DOMAIN not in config:
        return True

    # Get your domain's configuration from configuration.yaml
    domain_config = config[DOMAIN]
    devices = domain_config.get("devices", [])
    
    # Store global config options (like port) for use during entry setup
    hass.data[DOMAIN]["yaml_config"] = domain_config

    # Trigger import flow for each device
    for device_config in devices:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data={
                    CONF_IP_ADDRESS: device_config["ip"],
                    CONF_PIN: device_config["pin"],
                    CONF_NAME: device_config.get("name"),
                },
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open Pico from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize Manager (Singleton) if not already initialized
    if "manager" not in hass.data[DOMAIN]:
        # Check if we have YAML config for port overrides
        yaml_config = hass.data[DOMAIN].get("yaml_config", {})
        local_port = yaml_config.get("local_port", 40069)
        verbose = yaml_config.get("verbose", False)
        
        manager = PicoClientManager(local_port=local_port, verbose=verbose)
        try:
            await manager.initialize()
            hass.data[DOMAIN]["manager"] = manager
            _LOGGER.info("Shared transport initialized on port %d", local_port)
        except Exception as err:
            _LOGGER.error("Failed to initialize shared transport: %s", err, exc_info=True)
            return False
    else:
        manager = hass.data[DOMAIN]["manager"]

    # Get device config from entry
    ip = entry.data[CONF_IP_ADDRESS]
    pin = entry.data[CONF_PIN]
    name = entry.data.get(CONF_NAME, f"Pico {ip}")

    # Create Client
    device_id = f"pico_{ip.replace('.', '_')}"
    client = manager.create_client(
        ip=ip,
        pin=pin,
        device_id=device_id,
        timeout=15,
        retry_attempts=3,
        retry_delay=2.0
    )

    try:
        await client.connect()
        _LOGGER.debug("Connected to device '%s' at %s", name, ip)
    except Exception as err:
        _LOGGER.error("Failed to connect to device '%s': %s", name, err)
        # We proceed even if connection fails initially, allowing retries

    # Create Coordinator
    coordinator = MainCoordinator(hass, client, name)

    # Perform initial data load
    try:
        # We use async_config_entry_first_refresh which handles ConfigEntryNotReady
        # if the device is not reachable.
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Initial refresh failed for device '%s' (%s): %s", name, ip, err)
        # We let the setup finish so the entity is created (as unavailable)
        # or raises ConfigEntryNotReady if strictly required. 
        # Using async_config_entry_first_refresh usually raises ConfigEntryNotReady 
        # on failure, which retries setup later. 
        raise

    # Store coordinator in hass.data mapped by entry_id
    if "entries" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["entries"] = {}
    
    hass.data[DOMAIN]["entries"][entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Remove coordinator
        if "entries" in hass.data[DOMAIN] and entry.entry_id in hass.data[DOMAIN]["entries"]:
            coordinator = hass.data[DOMAIN]["entries"].pop(entry.entry_id)
            try:
                await coordinator.async_shutdown()
            except Exception as err:
                _LOGGER.error("Error shutting down coordinator: %s", err)

        # If no more entries are active, shutdown the shared manager
        if "entries" in hass.data[DOMAIN] and not hass.data[DOMAIN]["entries"]:
            manager = hass.data[DOMAIN].get("manager")
            if manager:
                try:
                    await manager.shutdown()
                    _LOGGER.info("Shared transport manager shut down successfully")
                except Exception as err:
                    _LOGGER.error("Error shutting down manager: %s", err)
                hass.data[DOMAIN].pop("manager")

    return unload_ok
