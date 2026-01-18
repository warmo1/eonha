"""Sensor platform for E.ON Next Home Assistant."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    statistics_during_period,
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
from homeassistant.util import dt as dt_util, slugify

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
    
    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        if self._meter_type == "gas":
            return "mdi:fire"
        return "mdi:flash"

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
        
        # 1. Update State to be "Latest Available Day Consumption"
        # Find the latest reading to determine the "latest day"
        latest_end = None
        for record in consumption_list:
             end_dt = datetime.fromisoformat(record["endAt"])
             if latest_end is None or end_dt > latest_end:
                 latest_end = end_dt
        
        if not latest_end:
            return

        # Use the day of the latest reading (local time)
        latest_day_start = latest_end.astimezone(dt_util.DEFAULT_TIME_ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
        
        day_sum = 0.0
        
        for record in consumption_list:
            start_dt = datetime.fromisoformat(record["startAt"])
            # Check if this reading belongs to the latest day
            local_start = start_dt.astimezone(dt_util.DEFAULT_TIME_ZONE)
            if local_start >= latest_day_start:
                day_sum += float(record["value"])

        self._attr_native_value = round(day_sum, 3)
        self._attr_extra_state_attributes = {
            "last_reading_time": latest_end.isoformat(),
            "latest_day_start": latest_day_start.isoformat(),
            "meter_serial": self._serial
        }
        
        # 2. Trigger Statistics Import (Background Task)
        self.hass.async_create_task(self._async_import_historical_stats(consumption_list))
        
        super()._handle_coordinator_update()

    async def _async_import_historical_stats(self, consumption_list: list[dict]):
        """Import historical statistics."""
        if not consumption_list:
            return
            
        # Use target statistic ID if configured, otherwise use stable default
        if self.coordinator.target_statistic_id:
            statistic_id = self.coordinator.target_statistic_id
        else:
            # Format: sensor.eon_next_{serial}_{type}_history
            stat_id_base = f"eon_next_{self._serial}_{self._meter_type}_history"
            statistic_id = f"sensor.{slugify(stat_id_base)}"

        # 1. Aggregate half-hourly data to hourly
        hourly_data = {}
        
        for record in consumption_list:
            start_dt = datetime.fromisoformat(record["startAt"])
            # Ensure timezone awareness. Assuming API returns ISO with offset.
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            
            # Round down to start of hour
            hour_start = start_dt.replace(minute=0, second=0, microsecond=0)
            
            val = float(record["value"])
            
            if hour_start not in hourly_data:
                hourly_data[hour_start] = 0.0
            hourly_data[hour_start] += val

        if not hourly_data:
            return

        sorted_hours = sorted(hourly_data.keys())
        # We need to find the previous sum to continue the chain
        # Query the last statistic
        last_stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            sorted_hours[0] - timedelta(days=365), # Look back far enough
            sorted_hours[0],
            {statistic_id},
            "hour",
            None,
            {"sum"}
        )
        
        running_sum = 0.0
        if statistic_id in last_stats and last_stats[statistic_id]:
             # Get the very last entry
             last_entry = last_stats[statistic_id][-1]
             if "sum" in last_entry:
                 running_sum = last_entry["sum"]
        
        _LOGGER.debug(f"Starting stats import for {statistic_id} with running_sum={running_sum}")

        # 2. Check for existing OUTSIDE the gap? 
        # Actually checking existing statistics for the period we want to insert is good to avoid overwriting or duplicates
        # But for 'sum', we just need to ensure we insert correct cumulative values.
        # If we overwrite existing, we better match.
        # Simplification: Only import hours that don't exist in specific period.
        
        start_time_q = sorted_hours[0]
        end_time_q = sorted_hours[-1] + timedelta(hours=1)

        existing_in_period = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time_q,
            end_time_q,
            {statistic_id},
            "hour",
            None,
            {"sum"}
        )
        
        existing_hours = set()
        if statistic_id in existing_in_period:
             for stat in existing_in_period[statistic_id]:
                 if "start" in stat:
                     dt = datetime.fromtimestamp(stat["start"], tz=timezone.utc)
                     existing_hours.add(dt)

        statistics = []
        for hour_start in sorted_hours:
            val = hourly_data[hour_start]
            running_sum += val # Always increment running sum to track "virtual" total
            
            if hour_start in existing_hours:
                # If it already exists, we skip writing it, BUT we must assume the existing one 
                # matches our calculated running_sum if the history is consistent.
                # If there's a gap or mismatch, this naive approach might drift.
                # Ideally we'd read the existing sum and use that as the base for next.
                # But for now, let's just skip writing.
                continue

            statistics.append(
                StatisticData(
                    start=hour_start,
                    state=running_sum, 
                    sum=running_sum
                )
            )

        if statistics:
            _LOGGER.debug(f"Importing {len(statistics)} statistics for {statistic_id}")
            async_import_statistics(
                self.hass,
                StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=f"{self._attr_name} History", # Give it a name
                    source=DOMAIN,
                    statistic_id=statistic_id,
                    unit_of_measurement=self.native_unit_of_measurement,
                ),
                statistics,
            )

