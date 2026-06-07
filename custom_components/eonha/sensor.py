"""Sensor platform for E.ON Next Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_import_statistics,
    statistics_during_period,
)

try:
    from homeassistant.components.recorder.models import StatisticMeanType
    from homeassistant.const import UnitClass

    _STATS_API_V2 = True
except ImportError:
    _STATS_API_V2 = False

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
from .energy_model import bucket_consumption_by_hour, summarize_consumption

_LOGGER = logging.getLogger(__name__)


def _build_statistic_id(serial: str, meter_type: str, kind: str) -> str:
    """Build an external statistic ID for the Energy dashboard.

    External statistics MUST be in the form '<domain>:<object_id>'.
    'sensor.xxx' style IDs are reserved for recorder-backed entity
    statistics and are rejected by async_add_external_statistics.
    """
    return f"{DOMAIN}:{slugify(f'eon_next_{serial}_{meter_type}_{kind}')}"


def _build_metadata(name: str, statistic_id: str, source: str) -> StatisticMetaData:
    """Build statistics metadata compatible with old and new HA versions."""
    if _STATS_API_V2:
        return StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=name,
            source=source,
            statistic_id=statistic_id,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            unit_class=UnitClass.ENERGY,
            mean_type=StatisticMeanType.NONE,
        )

    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source=source,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the E.ON Next sensors."""
    coordinator: EonNextDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for meter_data in coordinator.data["meters"]:
        meter_type = meter_data["info"]["type"]
        entities.append(EonNextLatestDaySensor(coordinator, meter_data))
        entities.append(EonNextCumulativeSensor(coordinator, meter_data, "total"))

        if meter_type == "electricity":
            entities.append(EonNextCumulativeSensor(coordinator, meter_data, "peak"))
            entities.append(EonNextCumulativeSensor(coordinator, meter_data, "offpeak"))

    async_add_entities(entities)


class EonNextBaseSensor(CoordinatorEntity, SensorEntity):
    """Shared base for E.ON Next sensors."""

    def __init__(self, coordinator: EonNextDataUpdateCoordinator, meter_data: dict) -> None:
        """Initialize the shared meter metadata."""
        super().__init__(coordinator)
        self.meter_data = meter_data
        self._serial = meter_data["info"]["serial"]
        self._meter_type = meter_data["info"]["type"]
        self._meter_id = meter_data["info"]["id"]
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        if self._meter_type == "gas":
            return "mdi:fire"
        return "mdi:flash"

    def _find_current_data(self) -> dict | None:
        """Find the current coordinator payload for this meter."""
        return next(
            (
                meter
                for meter in self.coordinator.data["meters"]
                if meter["info"]["serial"] == self._serial
            ),
            None,
        )


class EonNextLatestDaySensor(EonNextBaseSensor):
    """Sensor showing the latest fully/partially available day total."""

    def __init__(self, coordinator: EonNextDataUpdateCoordinator, meter_data: dict) -> None:
        """Initialize the latest-day sensor."""
        super().__init__(coordinator, meter_data)
        self._attr_name = f"E.ON Next {self._meter_type.capitalize()} ({self._serial})"
        self._attr_unique_id = f"eon_next_{self._serial}_{self._meter_type}_latest"
        # TOTAL with last_reset: the value resets each day, so HA must know
        # the reset point or long-term statistics for this entity are junk.
        self._attr_state_class = SensorStateClass.TOTAL
        self._update_from_meter_data(meter_data)

    async def async_added_to_hass(self) -> None:
        """Kick off a statistics import as soon as the entity is loaded.

        The coordinator's first refresh happens before entities exist and
        register their update listeners, so without this the first import
        would only run on the NEXT hourly refresh (up to 60 min after a
        restart).
        """
        await super().async_added_to_hass()
        consumption_list = self.meter_data.get("consumption") or []
        if consumption_list:
            self.hass.async_create_task(
                self._async_import_historical_stats(consumption_list)
            )

    def _update_from_meter_data(self, meter_data: dict) -> None:
        """Calculate the latest-day total from the current consumption list."""
        summary = summarize_consumption(
            meter_data.get("consumption") or [],
            dt_util.DEFAULT_TIME_ZONE,
        )
        if summary is None:
            return

        self._attr_native_value = round(summary["latest_day_kwh"], 3)
        self._attr_last_reset = summary["latest_day_start"]
        self._attr_extra_state_attributes = {
            "last_reading_time": summary["latest_end"].isoformat(),
            "latest_day_start": summary["latest_day_start"].isoformat(),
            "meter_serial": self._serial,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh state from coordinator data and schedule backfill imports."""
        current_data = self._find_current_data()
        if current_data:
            self.meter_data = current_data
            self._update_from_meter_data(current_data)

            consumption_list = current_data.get("consumption") or []
            if consumption_list:
                self.hass.async_create_task(
                    self._async_import_historical_stats(consumption_list)
                )

        super()._handle_coordinator_update()

    async def _async_import_stat_series(
        self,
        statistic_id: str,
        statistic_name: str,
        hourly_rows: list[dict],
        field_name: str,
    ) -> None:
        """Import a cumulative hourly statistic series.

        External IDs ('eonha:xxx') go through async_add_external_statistics.
        Entity IDs ('sensor.xxx', only used for target_statistic_id) go
        through async_import_statistics with source 'recorder'.
        Existing rows in the window are overwritten, which also picks up
        late revisions from E.ON.
        """
        if not hourly_rows:
            return

        is_external = ":" in statistic_id
        source = statistic_id.split(":")[0] if is_external else "recorder"

        first_start = hourly_rows[0]["start"]
        stats_manager = get_instance(self.hass)

        # Find the running sum immediately before our import window so the
        # cumulative series continues instead of restarting at zero.
        last_stats = await stats_manager.async_add_executor_job(
            statistics_during_period,
            self.hass,
            first_start - timedelta(days=365),
            first_start,
            {statistic_id},
            "hour",
            None,
            {"sum"},
        )

        running_sum = 0.0
        if statistic_id in last_stats and last_stats[statistic_id]:
            running_sum = float(last_stats[statistic_id][-1].get("sum") or 0.0)

        statistics: list[StatisticData] = []
        for row in hourly_rows:
            running_sum += float(row[field_name])
            statistics.append(
                StatisticData(
                    start=row["start"],
                    state=running_sum,
                    sum=running_sum,
                )
            )

        _LOGGER.debug(
            "Importing %d %s statistics for %s",
            len(statistics),
            field_name,
            statistic_id,
        )

        metadata = _build_metadata(statistic_name, statistic_id, source)
        if is_external:
            async_add_external_statistics(self.hass, metadata, statistics)
        else:
            async_import_statistics(self.hass, metadata, statistics)

    async def _async_import_historical_stats(self, consumption_list: list[dict]) -> None:
        """Import long-term statistics for total and tariff-aware energy usage."""
        try:
            hourly_rows = bucket_consumption_by_hour(
                consumption_list, dt_util.DEFAULT_TIME_ZONE
            )
            if not hourly_rows:
                return

            await self._async_import_stat_series(
                _build_statistic_id(self._serial, self._meter_type, "total"),
                f"E.ON Next {self._meter_type.capitalize()} Total ({self._serial})",
                hourly_rows,
                "total",
            )

            # Optional: also push into an existing recorder-backed entity
            # statistic chosen by the user (must be a real sensor entity).
            target_id = self.coordinator.target_statistic_id
            if target_id:
                if self.hass.states.get(target_id) is not None:
                    await self._async_import_stat_series(
                        target_id,
                        f"E.ON Next {self._meter_type.capitalize()} Total ({self._serial})",
                        hourly_rows,
                        "total",
                    )
                else:
                    _LOGGER.warning(
                        "target_statistic_id %s is not an existing entity; skipping",
                        target_id,
                    )

            if self._meter_type != "electricity":
                return

            await self._async_import_stat_series(
                _build_statistic_id(self._serial, self._meter_type, "peak"),
                f"E.ON Next Electricity Peak ({self._serial})",
                hourly_rows,
                "peak",
            )
            await self._async_import_stat_series(
                _build_statistic_id(self._serial, self._meter_type, "offpeak"),
                f"E.ON Next Electricity Off Peak ({self._serial})",
                hourly_rows,
                "offpeak",
            )
        except Exception:
            _LOGGER.exception(
                "Failed to import E.ON Next statistics for meter %s", self._serial
            )


class EonNextCumulativeSensor(EonNextBaseSensor):
    """Cumulative total/peak/off-peak sensors (informational).

    NOTE: the Energy dashboard should use the imported 'eonha:*'
    statistics, not these entities. E.ON data arrives 3-5 days late, so
    live entity statistics would land in the wrong hours, and the value
    here only covers the fetched window (it shrinks after a restart).
    TOTAL + last_reset keeps recorder statistics coherent.
    """

    def __init__(
        self,
        coordinator: EonNextDataUpdateCoordinator,
        meter_data: dict,
        kind: str,
    ) -> None:
        """Initialize a cumulative sensor."""
        super().__init__(coordinator, meter_data)
        self._kind = kind
        self._attr_state_class = SensorStateClass.TOTAL

        kind_name = {
            "total": "Total",
            "peak": "Peak",
            "offpeak": "Off Peak",
        }[kind]

        self._attr_name = f"E.ON Next {self._meter_type.capitalize()} {kind_name} ({self._serial})"
        self._attr_unique_id = f"eon_next_{self._serial}_{self._meter_type}_{kind}"
        self._update_from_meter_data(meter_data)

    def _update_from_meter_data(self, meter_data: dict) -> None:
        """Set the cumulative state value for the current tariff bucket."""
        summary = summarize_consumption(
            meter_data.get("consumption") or [],
            dt_util.DEFAULT_TIME_ZONE,
        )
        if summary is None:
            return

        key = {
            "total": "total_kwh",
            "peak": "peak_kwh",
            "offpeak": "offpeak_kwh",
        }[self._kind]

        self._attr_native_value = round(summary[key], 3)
        self._attr_last_reset = summary["earliest_start"]
        self._attr_extra_state_attributes = {
            "last_reading_time": summary["latest_end"].isoformat(),
            "meter_serial": self._serial,
            "tariff_bucket": self._kind,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh state from coordinator data."""
        current_data = self._find_current_data()
        if current_data:
            self.meter_data = current_data
            self._update_from_meter_data(current_data)

        super()._handle_coordinator_update()
