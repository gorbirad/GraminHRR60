"""Wyliczanie HRR60 (Heart Rate Recovery 60s) z listy próbek tętna.

HRR60 = tętno w punkcie odniesienia t0 (koniec głównej sesji treningu)
minus tętno w chwili t0 + 60 sekund (interpolowane liniowo między dwiema
najbliższymi próbkami, jeśli próbkowanie nie trafia dokładnie w t0+60s).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .hr_extractor import HRSample


@dataclass(frozen=True)
class HRRResult:
    t0: datetime
    hr_at_t0: int
    t1: datetime
    hr_at_t1: float
    hrr60: float


class HRRCalculationError(ValueError):
    """Zgłaszane, gdy nie da się wyliczyć HRR60 (za mało danych / brak punktu t1)."""


def _interpolate_hr(samples: list[HRSample], target_time) -> float:
    """Zwraca tętno w `target_time`, interpolując liniowo między najbliższymi próbkami.

    Zakłada, że `samples` jest posortowane rosnąco po czasie.
    """
    if target_time <= samples[0].time:
        return float(samples[0].hr)
    if target_time >= samples[-1].time:
        return float(samples[-1].hr)

    for left, right in zip(samples, samples[1:]):
        if left.time <= target_time <= right.time:
            span = (right.time - left.time).total_seconds()
            if span == 0:
                return float(left.hr)
            fraction = (target_time - left.time).total_seconds() / span
            return left.hr + fraction * (right.hr - left.hr)

    raise HRRCalculationError("Nie znaleziono próbek otaczających target_time.")


def compute_hrr60(
    samples: list[HRSample],
    reference_index: int | None = None,
) -> HRRResult:
    """Liczy HRR60 dla podanych próbek tętna.

    Args:
        samples: próbki tętna (posortowane lub nie - zostaną posortowane).
        reference_index: indeks próbki traktowanej jako koniec głównej sesji
            (t0). Domyślnie `None` = ostatnia próbka (wariant A z PLAN.md:
            "koniec całej aktywności"). Można podać inny indeks, np. koniec
            konkretnego lapa (wariant B) lub ręcznie wskazaną minutę (wariant C).

    Raises:
        HRRCalculationError: gdy brak wystarczających danych (mniej niż 2
            próbki, albo brak próbek sięgających t0 + 60s).
    """
    if len(samples) < 2:
        raise HRRCalculationError("Potrzeba co najmniej 2 próbek tętna.")

    ordered = sorted(samples, key=lambda s: s.time)

    ref_idx = len(ordered) - 1 if reference_index is None else reference_index
    if not (0 <= ref_idx < len(ordered)):
        raise HRRCalculationError(f"reference_index={reference_index} poza zakresem danych.")

    reference = ordered[ref_idx]
    t0 = reference.time
    t1 = t0 + timedelta(seconds=60)

    if t1 > ordered[-1].time:
        raise HRRCalculationError(
            "Brak danych o tętnie sięgających 60 sekund po punkcie odniesienia "
            "(aktywność mogła zakończyć się wcześniej niż t0+60s)."
        )

    hr_at_t1 = _interpolate_hr(ordered, t1)

    return HRRResult(
        t0=t0,
        hr_at_t0=reference.hr,
        t1=t1,
        hr_at_t1=hr_at_t1,
        hrr60=reference.hr - hr_at_t1,
    )
