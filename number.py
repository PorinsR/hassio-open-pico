"""Number platform for Open Pico integration."""
import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Number platform from a config entry."""
    coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities([
        PicoFanSpeedNumber(coordinator, 0),
    ])


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Set up the Number platform from YAML."""
    _LOGGER.debug("Setting up number platform")

    # Get all coordinators from hass.data
    coordinators = hass.data[DOMAIN]["coordinators"]

    # Create number entities for each coordinator/device
    numbers = [
        PicoFanSpeedNumber(coordinator, idx)
        for idx, coordinator in enumerate(coordinators)
    ]
    
    _LOGGER.debug(f"Adding {len(numbers)} number entities")
    async_add_entities(numbers)


class PicoFanSpeedNumber(BaseEntity, NumberEntity):
    """Representation of a Pico Fan Speed Number."""

    _attr_translation_key = "fan_speed"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the number."""
        super().__init__(coordinator, device_index)

        # Set unique_id based on IP address
        self._attr_unique_id = f"{DOMAIN}_fan_speed_{coordinator.pico_ip.replace('.', '_')}"
        self._attr_name = "Fan Speed"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Only available if the device supports fan speed control
        available = (
            super().available and
            self.coordinator.supports_fan_speed
        )
        return available

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.coordinator.data:
            return None

        return float(self.coordinator.fan_speed)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        
        # Check if current mode supports fan speed control
        if not self.coordinator.supports_fan_speed:
            current_mode = self.coordinator.data.operating.mode.name if self.coordinator.data else "Unknown"
            raise HomeAssistantError(
                f"Current mode '{current_mode}' does not support fan speed control"
            )

        try:
            await self.coordinator.async_set_fan_speed(int(value))
        except Exception as err:
            _LOGGER.error("Failed to set fan speed: %s", err)
            raise HomeAssistantError(f"Failed to set fan speed: {err}") from err
