"""Testy jednostkowe dla hrr_calculator - nie wymagają logowania do Garmina."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from garmin_hrr.hr_extractor import HRSample
from garmin_hrr.hrr_calculator import HRRCalculationError, compute_hrr60


def _samples_every_second(start: datetime, hr_values: list[int]) -> list[HRSample]:
    return [
        HRSample(time=start + timedelta(seconds=i), hr=hr)
        for i, hr in enumerate(hr_values)
    ]


def test_compute_hrr60_raises_when_reference_is_last_sample_and_no_data_after():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    hr_values = [160 - i for i in range(91)]  # t=0 -> 160, t=90 -> 70
    samples = _samples_every_second(start, hr_values)

    # domyślnie t0 = ostatnia próbka (t=90s); nie ma danych do t0+60s -> błąd
    with pytest.raises(HRRCalculationError):
        compute_hrr60(samples)


def test_compute_hrr60_with_explicit_reference_index():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    hr_values = [160 - i for i in range(91)]  # spadek 1 bpm/s przez 90s
    samples = _samples_every_second(start, hr_values)

    # referencja na t=0 (indeks 0), t1 = t0+60s -> hr powinno wynosić 160-60=100
    result = compute_hrr60(samples, reference_index=0)

    assert result.hr_at_t0 == 160
    assert result.hr_at_t1 == pytest.approx(100.0)
    assert result.hrr60 == pytest.approx(60.0)


def test_compute_hrr60_interpolates_between_samples():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # próbki co 10 sekund zamiast co 1s - wymusza interpolację
    samples = [
        HRSample(time=start, hr=150),
        HRSample(time=start + timedelta(seconds=60), hr=150),
        HRSample(time=start + timedelta(seconds=70), hr=100),
    ]

    result = compute_hrr60(samples, reference_index=0)

    assert result.hr_at_t0 == 150
    assert result.hr_at_t1 == pytest.approx(150.0)
    assert result.hrr60 == pytest.approx(0.0)


def test_compute_hrr60_raises_when_not_enough_future_data():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    samples = _samples_every_second(start, [160, 150, 140])  # tylko 3 sekundy danych

    with pytest.raises(HRRCalculationError):
        compute_hrr60(samples)  # t0 = ostatnia próbka, brak danych do t0+60s


def test_compute_hrr60_raises_with_too_few_samples():
    with pytest.raises(HRRCalculationError):
        compute_hrr60([HRSample(time=datetime.now(timezone.utc), hr=150)])
