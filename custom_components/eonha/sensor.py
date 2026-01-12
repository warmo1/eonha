"""Sensor platform for E.ON Next Home Assistant."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import EonNextDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the E.ON Next sensors."""
    coordinator: EonNextDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for meter_data in coordinator.data["meters"]:
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
        # Revert to old ID to preserve entity availability for users upgrading from v1.0
        self._attr_unique_id = f"eon_next_{self._serial}_{self._meter_type}_latest"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Find the updated data for this meter
        current_data = next(
            (m for m in self.coordinator.data["meters"] if m["info"]["serial"] == self._serial), 
            None
        )
        if not current_data or not current_data["consumption"]:
            return

        self.meter_data = current_data
        consumption_list = current_data["consumption"]
        
        # 1. Update State to be "Today's Consumption"
        # Calculate sum of readings that started today (local time)
        now = dt_util.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        today_sum = 0.0
        latest_end = None
        
        for record in consumption_list:
            # Parse ISO string
            start_dt = datetime.fromisoformat(record["startAt"])
            end_dt = datetime.fromisoformat(record["endAt"])
            val = float(record["value"])
            
            # Simple check if it's today
            if start_dt.astimezone(now.tzinfo) >= today_start:
                today_sum += val
                
            latest_end = end_dt

        self._attr_native_value = round(today_sum, 3)
        self._attr_extra_state_attributes = {
            "last_reading_time": latest_end.isoformat() if latest_end else None,
            "meter_serial": self._serial
        }
        
        # 2. Trigger Statistics Import (Background Task)
        self.hass.async_create_task(self._async_import_historical_stats(consumption_list))
        
        super()._handle_coordinator_update()

    async def _async_import_historical_stats(self, consumption_list: list[dict]):
        """Import historical statistics."""
        if not self.entity_id:
            return

        statistic_id = self.entity_id
        
        # Get the last known statistic sum to continue the running total
        last_stats = await get_last_statistics(self.hass, 1, statistic_id, True, {"sum"})
        
        current_sum = 0.0
        last_stats_time = None
        
        if statistic_id in last_stats and last_stats[statistic_id]:
            stat = last_stats[statistic_id][0]
            current_sum = stat["sum"] or 0.0
            last_stats_time = datetime.fromtimestamp(stat["start"], tz=timezone.utc)

        statistics = []
        
        for record in consumption_list:
            start_dt = datetime.fromisoformat(record["startAt"])
            val = float(record["value"])
            
            # Only import if newer than last statistic
            if last_stats_time and start_dt <= last_stats_time:
                continue

            current_sum += val
            
            statistics.append(
                StatisticData(
                    start=start_dt,
                    state=val,
                    sum=current_sum
                )
            )

        if statistics:
            _LOGGER.debug(f"Importing {len(statistics)} statistics for {statistic_id}")
            async_import_statistics(
                self.hass,
                StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=self.name,
                    source=DOMAIN,
                    statistic_id=statistic_id,
                    unit_of_measurement=self.native_unit_of_measurement,
                ),
                statistics,
            )

