"""Testy jednostkowe dla wybranych, czysto logicznych fragmentów sync.py
(filtrowanie typów aktywności, fallback ciągłego pomiaru tętna) - bez
faktycznego logowania do Garmina.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from garmin_hrr.hr_extractor import HRSample
from garmin_hrr.hrr_calculator import HRRCalculationError
from garmin_hrr.sync import _compute_hrr60_with_fallback, _is_running_activity


@pytest.mark.parametrize(
    "type_key,expected",
    [
        ("running", True),
        ("track_running", True),
        ("trail_running", True),
        ("treadmill_running", True),
        ("walking", False),
        ("cycling", False),
        (None, False),
    ],
)
def test_is_running_activity(type_key, expected):
    activity = {"activityType": {"typeKey": type_key}} if type_key else {}
    assert _is_running_activity(activity) is expected


def test_is_running_activity_handles_missing_activity_type_key():
    assert _is_running_activity({"activityType": None}) is False


class _FakeClientNoExtraData:
    """Symuluje brak dodatkowych danych o ciągłym pomiarze tętna (puste dni)."""

    def get_daily_heart_rates(self, date_str):
        return {"heartRateValues": []}


def test_compute_hrr60_with_fallback_raises_when_no_continuous_data_available():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # Tylko 3 sekundy danych - reference_index domyślnie = ostatnia próbka.
    samples = [
        HRSample(time=start, hr=160),
        HRSample(time=start + timedelta(seconds=1), hr=150),
        HRSample(time=start + timedelta(seconds=2), hr=140),
    ]

    with pytest.raises(HRRCalculationError):
        _compute_hrr60_with_fallback(
            _FakeClientNoExtraData(), samples, "2024-01-01 00:00:00", reference_index=2
        )


def test_compute_hrr60_with_fallback_succeeds_without_needing_fallback():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    samples = [
        HRSample(time=start + timedelta(seconds=i), hr=160 - i) for i in range(90)
    ]

    result = _compute_hrr60_with_fallback(
        _FakeClientNoExtraData(), samples, "2024-01-01 00:00:00", reference_index=0
    )

    assert result.hr_at_t0 == 160
    assert result.hrr60 == pytest.approx(60.0)
