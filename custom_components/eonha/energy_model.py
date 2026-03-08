"""Pure helpers for tariff-aware energy calculations."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any


OFFPEAK_START = time(hour=0, minute=0)
OFFPEAK_END = time(hour=7, minute=0)


def _parse_record_start(record: dict[str, Any]) -> datetime:
    """Return an aware UTC datetime for a consumption record start."""
    start_dt = datetime.fromisoformat(record["startAt"])
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    return start_dt.astimezone(timezone.utc)


def is_offpeak(local_dt: datetime) -> bool:
    """Return True when a local datetime falls in the configured off-peak window."""
    local_time = local_dt.timetz().replace(tzinfo=None)
    return OFFPEAK_START <= local_time < OFFPEAK_END


def summarize_consumption(
    consumption_list: list[dict[str, Any]],
    local_tz,
) -> dict[str, Any] | None:
    """Summarize consumption for latest-day and cumulative tariff totals."""
    if not consumption_list:
        return None

    latest_end = None
    total_kwh = 0.0
    peak_kwh = 0.0
    offpeak_kwh = 0.0

    for record in consumption_list:
        start_dt_utc = _parse_record_start(record)
        end_dt = datetime.fromisoformat(record["endAt"])
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        end_dt = end_dt.astimezone(timezone.utc)

        if latest_end is None or end_dt > latest_end:
            latest_end = end_dt

        value = float(record["value"])
        total_kwh += value

        if is_offpeak(start_dt_utc.astimezone(local_tz)):
            offpeak_kwh += value
        else:
            peak_kwh += value

    if latest_end is None:
        return None

    latest_day_start = latest_end.astimezone(local_tz).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    latest_day_kwh = 0.0
    for record in consumption_list:
        start_dt_utc = _parse_record_start(record)
        if start_dt_utc.astimezone(local_tz) >= latest_day_start:
            latest_day_kwh += float(record["value"])

    return {
        "latest_end": latest_end,
        "latest_day_start": latest_day_start,
        "latest_day_kwh": latest_day_kwh,
        "total_kwh": total_kwh,
        "peak_kwh": peak_kwh,
        "offpeak_kwh": offpeak_kwh,
    }


def bucket_consumption_by_hour(
    consumption_list: list[dict[str, Any]],
    local_tz,
) -> list[dict[str, Any]]:
    """Aggregate half-hourly readings into hourly UTC buckets with tariff splits."""
    if not consumption_list:
        return []

    hourly: dict[datetime, dict[str, float]] = {}

    for record in consumption_list:
        start_dt_utc = _parse_record_start(record)
        hour_start_utc = start_dt_utc.replace(minute=0, second=0, microsecond=0)
        value = float(record["value"])

        if hour_start_utc not in hourly:
            hourly[hour_start_utc] = {
                "total": 0.0,
                "peak": 0.0,
                "offpeak": 0.0,
            }

        hourly[hour_start_utc]["total"] += value
        if is_offpeak(start_dt_utc.astimezone(local_tz)):
            hourly[hour_start_utc]["offpeak"] += value
        else:
            hourly[hour_start_utc]["peak"] += value

    start_hour = min(hourly)
    end_hour = max(hourly)

    rows: list[dict[str, Any]] = []
    current_hour = start_hour
    while current_hour <= end_hour:
        values = hourly.get(
            current_hour,
            {"total": 0.0, "peak": 0.0, "offpeak": 0.0},
        )
        rows.append(
            {
                "start": current_hour,
                "total": values["total"],
                "peak": values["peak"],
                "offpeak": values["offpeak"],
            }
        )
        current_hour += timedelta(hours=1)

    return rows
