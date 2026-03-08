"""Unit tests for tariff-aware energy helpers."""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "eonha"
    / "energy_model.py"
)
SPEC = importlib.util.spec_from_file_location("eonha_energy_model", MODULE_PATH)
ENERGY_MODEL = importlib.util.module_from_spec(SPEC)
assert SPEC is not None
assert SPEC.loader is not None
SPEC.loader.exec_module(ENERGY_MODEL)

bucket_consumption_by_hour = ENERGY_MODEL.bucket_consumption_by_hour
is_offpeak = ENERGY_MODEL.is_offpeak
summarize_consumption = ENERGY_MODEL.summarize_consumption


LONDON = ZoneInfo("Europe/London")


def test_is_offpeak_respects_boundary() -> None:
    """00:00-06:59 is off-peak and 07:00 is peak."""
    assert is_offpeak(datetime(2026, 3, 8, 0, 0, tzinfo=LONDON)) is True
    assert is_offpeak(datetime(2026, 3, 8, 6, 59, tzinfo=LONDON)) is True
    assert is_offpeak(datetime(2026, 3, 8, 7, 0, tzinfo=LONDON)) is False


def test_bucket_consumption_by_hour_splits_peak_and_offpeak() -> None:
    """Half-hour readings should aggregate into hourly tariff buckets."""
    rows = bucket_consumption_by_hour(
        [
            {
                "startAt": "2026-03-08T06:00:00+00:00",
                "endAt": "2026-03-08T06:30:00+00:00",
                "value": "1.0",
            },
            {
                "startAt": "2026-03-08T06:30:00+00:00",
                "endAt": "2026-03-08T07:00:00+00:00",
                "value": "2.0",
            },
            {
                "startAt": "2026-03-08T07:00:00+00:00",
                "endAt": "2026-03-08T07:30:00+00:00",
                "value": "3.0",
            },
            {
                "startAt": "2026-03-08T07:30:00+00:00",
                "endAt": "2026-03-08T08:00:00+00:00",
                "value": "4.0",
            },
        ],
        LONDON,
    )

    assert len(rows) == 2
    assert rows[0]["total"] == 3.0
    assert rows[0]["offpeak"] == 3.0
    assert rows[0]["peak"] == 0.0
    assert rows[1]["total"] == 7.0
    assert rows[1]["offpeak"] == 0.0
    assert rows[1]["peak"] == 7.0


def test_summarize_consumption_returns_latest_day_and_totals() -> None:
    """Summary should include latest-day, total, peak and off-peak kWh."""
    summary = summarize_consumption(
        [
            {
                "startAt": "2026-03-07T23:30:00+00:00",
                "endAt": "2026-03-08T00:00:00+00:00",
                "value": "1.5",
            },
            {
                "startAt": "2026-03-08T00:00:00+00:00",
                "endAt": "2026-03-08T00:30:00+00:00",
                "value": "2.0",
            },
            {
                "startAt": "2026-03-08T07:00:00+00:00",
                "endAt": "2026-03-08T07:30:00+00:00",
                "value": "3.0",
            },
        ],
        LONDON,
    )

    assert summary is not None
    assert round(summary["total_kwh"], 3) == 6.5
    assert round(summary["offpeak_kwh"], 3) == 2.0
    assert round(summary["peak_kwh"], 3) == 4.5
    assert round(summary["latest_day_kwh"], 3) == 5.0
