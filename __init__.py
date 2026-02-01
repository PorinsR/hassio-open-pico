"""Open Pico integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.typing import ConfigType
from homeassistant import config_entries

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

    # Check if domain is in config
    if DOMAIN not in config:
        return True

    # Get your domain's configuration from configuration.yaml
    domain_config = config[DOMAIN]
    
    # Store config in hass.data for use by async_setup_entry
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["config"] = domain_config

    # Trigger import flow if no entry exists
    # This ensures that even if loaded via YAML, we create a Config Entry
    if not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=domain_config
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open Pico from a config entry."""
    _LOGGER.debug("Setting up Open Pico from config entry")

    # Get config from entry data (if imported) or hass.data (fallback)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinators"] = []
    
    domain_config = entry.data
    if not domain_config and "config" in hass.data[DOMAIN]:
        domain_config = hass.data[DOMAIN]["config"]
        
    if not domain_config:
        _LOGGER.error("No configuration found for Open Pico")
        return False

    devices = domain_config.get("devices", [])
    local_port = domain_config.get("local_port", 40069)
    verbose = domain_config.get("verbose", False)

    _LOGGER.info("Setting up %s with %d device(s)", DOMAIN, len(devices))

    # Create shared PicoClient manager
    # Check if a manager already exists in hass.data from a previous load
    if DOMAIN in hass.data and "manager" in hass.data[DOMAIN]:
        manager = hass.data[DOMAIN]["manager"]
        _LOGGER.debug("Reusing existing PicoClientManager")
    else:
        manager = PicoClientManager(local_port=local_port, verbose=verbose)
        try:
            await manager.initialize()
            hass.data[DOMAIN]["manager"] = manager
            _LOGGER.info("Shared transport initialized on port %d", local_port)
        except Exception as err:
            _LOGGER.error("Failed to initialize shared transport: %s", err, exc_info=True)
            return False

    # Create clients and coordinators for each device
    successful_devices = 0
    for idx, device_config in enumerate(devices):
        pico_ip = device_config.get("ip")
        pin = device_config.get("pin")
        device_name = device_config.get("name", f"Pico Device {idx + 1}")

        _LOGGER.debug("Setting up device '%s': ip=%s", device_name, pico_ip)

        try:
            # Create client with shared socket
            device_id = f"pico_{pico_ip.replace('.', '_')}"
            client = manager.create_client(
                ip=pico_ip,
                pin=pin,
                device_id=device_id,
                timeout=15,
                retry_attempts=3,
                retry_delay=2.0
            )

            # Connect to device
            await client.connect()
            _LOGGER.debug("Connected to device '%s' at %s", device_name, pico_ip)

            # Initialize the coordinator for this device
            coordinator = MainCoordinator(hass, client, device_name)

            # Perform initial data load with timeout
            try:
                async with asyncio.timeout(30):
                    await coordinator.async_refresh()

                    # Check if refresh encountered an error
                    if not coordinator.last_update_success:
                        raise Exception(
                            f"Initial refresh failed: {coordinator.last_exception}"
                        )

            except asyncio.TimeoutError:
                _LOGGER.error(
                    "Timeout during initial refresh for device '%s' (%s). "
                    "Check if device is reachable and PIN is correct.",
                    device_name, pico_ip
                )
                await client.disconnect()
                continue
            except Exception as err:
                _LOGGER.error(
                    "Initial refresh failed for device '%s' (%s): %s",
                    device_name, pico_ip, err
                )
                await client.disconnect()
                continue

            # Check if we got data
            if not coordinator.data:
                _LOGGER.error("Failed to fetch initial data from device '%s' (%s)", device_name, pico_ip)
                await client.disconnect()
                continue

            # Store coordinator in our list
            hass.data[DOMAIN]["coordinators"].append(coordinator)
            successful_devices += 1

            _LOGGER.info(
                "Successfully set up device '%s' (%s): Mode=%s, Temp=%.1f°C, Humidity=%.1f%%",
                device_name,
                pico_ip,
                coordinator.data.operating.mode.name,
                coordinator.data.sensors.temperature,
                coordinator.data.sensors.humidity
            )

        except Exception as err:
            _LOGGER.error(
                "Error setting up device '%s' (%s): %s",
                device_name, pico_ip, err, exc_info=True
            )
            continue

    # Check if we have at least one successful coordinator
    if successful_devices == 0:
        _LOGGER.error("No devices were successfully set up")
        await manager.shutdown()
        return False

    _LOGGER.info(
        "Successfully set up %s with %d/%d device(s)",
        DOMAIN, successful_devices, len(devices)
    )

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry | None = None) -> bool:
    """Unload the integration."""
    _LOGGER.info("Unloading %s integration", DOMAIN)

    # Unload platforms
    if entry:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Shutdown coordinators
    if DOMAIN in hass.data and "coordinators" in hass.data[DOMAIN]:
        for coordinator in hass.data[DOMAIN]["coordinators"]:
            try:
                await coordinator.async_shutdown()
            except Exception as err:
                _LOGGER.error("Error shutting down coordinator: %s", err)

    # Shutdown the shared manager
    if DOMAIN in hass.data and "manager" in hass.data[DOMAIN]:
        try:
            await hass.data[DOMAIN]["manager"].shutdown()
            _LOGGER.info("Shared transport manager shut down successfully")
        except Exception as err:
            _LOGGER.error("Error shutting down manager: %s", err)

    # Clean up hass.data
    if DOMAIN in hass.data:
        hass.data.pop(DOMAIN)
    _LOGGER.info("Successfully unloaded %s", DOMAIN)
    return True
