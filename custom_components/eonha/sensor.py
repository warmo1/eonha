"""Sensor platform for E.ON Next Home Assistant."""
from __future__ import annotations

from typing import Any
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EonNextDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the E.ON Next sensors."""
    coordinator: EonNextDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for meter_data in coordinator.data["meters"]:
        # Create a sensor for latest reading
        entities.append(EonNextConsumptionSensor(coordinator, meter_data))

    async_add_entities(entities)


class EonNextConsumptionSensor(CoordinatorEntity, SensorEntity):
    """Representation of an E.ON Next Consumption Sensor."""

    def __init__(self, coordinator: EonNextDataUpdateCoordinator, meter_data: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter_data = meter_data
        self._serial = meter_data["info"]["serial"]
        self._meter_type = meter_data["info"]["type"]
        self._meter_id = meter_data["info"]["id"]
        
        self._attr_name = f"E.ON Next {self._meter_type.capitalize()} ({self._serial})"
        self._attr_unique_id = f"eon_next_{self._serial}_{self._meter_type}_latest"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        if self._meter_type == "electricity":
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        else:
             self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR # Gas usually converted to kWh by API? 
             # API returns "value". Gas is often m3 or ft3 but utility bills in kWh. 
             # E.ON Next API "value" is typically kWh for both.
             
    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        # Find the updated data for this meter in the coordinator
        current_data = next(
            (m for m in self.coordinator.data["meters"] if m["info"]["serial"] == self._serial), 
            None
        )
        if current_data and current_data["latest_reading"]:
            return float(current_data["latest_reading"]["value"])
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        current_data = next(
            (m for m in self.coordinator.data["meters"] if m["info"]["serial"] == self._serial), 
            None
        )
        attrs = {
            "meter_serial": self._serial,
            "meter_type": self._meter_type,
            "meter_id": self._meter_id
        }
        if current_data and current_data["latest_reading"]:
            attrs["reading_start"] = current_data["latest_reading"]["startAt"]
            attrs["reading_end"] = current_data["latest_reading"]["endAt"]
        return attrs
