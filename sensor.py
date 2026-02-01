"""Sensor platform for Open Pico integration."""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, PERCENTAGE, CONCENTRATION_PARTS_PER_MILLION, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Set up the Sensor platform from YAML."""

    # Get all coordinators from hass.data
    coordinators = hass.data[DOMAIN]["coordinators"]

    # Create sensor entities for each coordinator/device
    sensors = []
    for idx, coordinator in enumerate(coordinators):
        sensors.extend([
            PicoTemperatureSensor(coordinator, idx),
            PicoHumiditySensor(coordinator, idx),
            PicoAirQualitySensor(coordinator, idx),
            PicoTVOCSensor(coordinator, idx),
            PicoCO2Sensor(coordinator, idx),
        ])

    async_add_entities(sensors)


class PicoTemperatureSensor(BaseEntity, SensorEntity):
    """Representation of a Pico Temperature Sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_temperature_{coordinator.pico_ip.replace('.', '_')}"
        self._attr_name = "Temperature"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.sensors.temperature


class PicoHumiditySensor(BaseEntity, SensorEntity):
    """Representation of a Pico Humidity Sensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_humidity_{coordinator.pico_ip.replace('.', '_')}"
        self._attr_name = "Humidity"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.sensors.humidity


class PicoAirQualitySensor(BaseEntity, SensorEntity):
    """Representation of a Pico Air Quality Sensor."""

    _attr_translation_key = "air_quality"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_air_quality_{coordinator.pico_ip.replace('.', '_')}"
        self._attr_name = "Air Quality"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.sensors.air_quality


class PicoTVOCSensor(BaseEntity, SensorEntity):
    """Representation of a Pico TVOC Sensor."""

    _attr_device_class = SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_tvoc_{coordinator.pico_ip.replace('.', '_')}"
        self._attr_name = "TVOC"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.sensors.tvoc


class PicoCO2Sensor(BaseEntity, SensorEntity):
    """Representation of a Pico CO2 Sensor."""

    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_co2_{coordinator.pico_ip.replace('.', '_')}"
        self._attr_name = "CO2"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.sensors.eco2
