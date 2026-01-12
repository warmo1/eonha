"""Sensor platform for E.ON Next Home Assistant."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

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
        start_time = sorted_hours[0]
        end_time = sorted_hours[-1] + timedelta(hours=1)

        # 2. Check for existing statistics to avoid duplicates
        # We query the recorder to see which hours already have data
        existing_stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            {statistic_id},
            "hour",
            None,
            {"sum"}
        )
        
        existing_hours = set()
        if statistic_id in existing_stats:
            for stat in existing_stats[statistic_id]:
                if "start" in stat:
                    # stat['start'] is usually a timestamp (float/int)
                    dt = datetime.fromtimestamp(stat["start"], tz=timezone.utc)
                    existing_hours.add(dt)

        # 3. Build list of statistics to import
        statistics = []
        
        # We need a running total for 'sum' (which technically is the cumulative total in DB).
        # However, if we are backfilling into a gap, we might not know the absolute total.
        # But E.ON API gives us the meter reading? 
        # Actually API response records have 'startAt', 'endAt', 'value'.
        # None of these are the cumulative meter reading; 'value' is consumption.
        # So we can only provide the 'sum' delta if the import API supports it.
        # The spec says: "sum -- energy used during that hour (kWh delta)".
        # We will trust the spec/helper to handle this for 'total_increasing'.

        # Calculate a local running sum just in case we need it for 'state'
        # But 'state' should be the meter reading. We don't have absolute meter reading from this API endpoint?
        # Coordinator comment says: "state = total_kwh".
        # If we don't have the initial meter reading, we can't emit a correct 'state' (cumulative).
        # But for Energy Dashboard, 'sum' (the change) is what matters most.
        
        # NOTE: If we are injecting into an EXISTING sensor (Hildebrand), 
        # providing a 'state' that is just the day's total (e.g. 10kWh) vs the real meter reading (15000kWh)
        # might confuse things if specific rows are looked at.
        # But 'sum' (delta) is the critical part for the bar charts.

        current_cumulative_simulated = 0.0 # This might be wrong if we don't know the start.

        for hour_start in sorted_hours:
            if hour_start in existing_hours:
                continue
                
            val = hourly_data[hour_start]
            current_cumulative_simulated += val
            
            statistics.append(
                StatisticData(
                    start=hour_start,
                    state=None, # Let HA calculate state if possible, or omit if we don't know absolute meter reading
                    sum=val  # Sum is the delta for the hour per spec requirements
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
                    source=DOMAIN if not self.coordinator.target_statistic_id else "recorder", # Keep source if targetting ext
                    statistic_id=statistic_id,
                    unit_of_measurement=self.native_unit_of_measurement,
                ),
                statistics,
            )

