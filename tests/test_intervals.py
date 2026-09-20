"""Testy jednostkowe dla intervals.determine_main_session_end i pomocniczych
funkcji - pokrywają wszystkie przypadki empirycznie zweryfikowane w PLAN.md
(sekcje 3c/3d) na prawdziwych aktywnościach Garmina.
"""
from __future__ import annotations

from datetime import datetime, timezone

from garmin_hrr.intervals import (
    determine_main_session_end,
    find_last_active_end_from_typed_splits,
    find_last_main_effort_end_from_raw_laps,
)


def _typed_split(type_: str, start: str, end: str) -> dict:
    return {"type": type_, "startTimeGMT": start, "endTimeGMT": end}


def _lap(intensity_type: str | None, start: str, duration: float) -> dict:
    return {"intensityType": intensity_type, "startTimeGMT": start, "duration": duration}


class _FakeClient:
    """Podstawia GarminClient - zwraca zadane z góry odpowiedzi typed/raw splits."""

    def __init__(self, typed_splits=None, splits=None, raise_on="none"):
        self._typed_splits = typed_splits
        self._splits = splits
        self._raise_on = raise_on

    def get_activity_typed_splits(self, activity_id):
        if self._raise_on in ("typed", "both"):
            raise RuntimeError("boom (typed)")
        return self._typed_splits

    def get_activity_splits(self, activity_id):
        if self._raise_on in ("raw", "both"):
            raise RuntimeError("boom (raw)")
        return self._splits


def test_find_last_active_end_from_typed_splits_picks_last_active_segment():
    typed_splits = {
        "splits": [
            _typed_split("INTERVAL_WARMUP", "2026-09-18T13:41:03.0", "2026-09-18T13:51:03.0"),
            _typed_split("INTERVAL_ACTIVE", "2026-09-18T13:51:02.0", "2026-09-18T13:52:02.0"),
            _typed_split("INTERVAL_RECOVERY", "2026-09-18T13:52:02.0", "2026-09-18T13:53:02.0"),
            _typed_split("INTERVAL_ACTIVE", "2026-09-18T13:53:02.0", "2026-09-18T13:54:02.0"),
            _typed_split("INTERVAL_COOLDOWN", "2026-09-18T13:54:02.0", "2026-09-18T13:59:02.0"),
            # Równoległa segmentacja run/walk - musi być ignorowana.
            _typed_split("RWD_RUN", "2026-09-18T13:41:03.0", "2026-09-18T13:59:02.0"),
        ]
    }

    t0 = find_last_active_end_from_typed_splits(typed_splits)

    assert t0 == datetime(2026, 9, 18, 13, 54, 2, tzinfo=timezone.utc)


def test_find_last_active_end_from_typed_splits_returns_none_without_active():
    # Wyścig z auto-lapami PacePro: brak jakichkolwiek segmentów INTERVAL_*.
    typed_splits = {
        "splits": [
            _typed_split("RWD_RUN", "2026-09-18T13:41:03.0", "2026-09-18T14:59:02.0"),
            _typed_split("PACE_PRO_SPLIT", "2026-09-18T13:41:03.0", "2026-09-18T13:51:03.0"),
        ]
    }

    assert find_last_active_end_from_typed_splits(typed_splits) is None


def test_find_last_main_effort_end_from_raw_laps_uses_active_and_interval():
    splits = {
        "lapDTOs": [
            _lap("WARMUP", "2026-09-17T14:04:43.0", 600.0),
            _lap("ACTIVE", "2026-09-17T14:14:43.0", 120.0),
            _lap("INTERVAL", "2026-09-17T14:16:43.0", 150.0),
            _lap("COOLDOWN", "2026-09-17T14:19:13.0", 300.0),
        ]
    }

    t0 = find_last_main_effort_end_from_raw_laps(splits)

    # Ostatni lap "główny wysiłek" to INTERVAL zaczynający się 14:16:43 + 150s.
    assert t0 == datetime(2026, 9, 17, 14, 19, 13, tzinfo=timezone.utc)


def test_find_last_main_effort_end_from_raw_laps_returns_none_without_candidates():
    splits = {"lapDTOs": [_lap("WARMUP", "2026-09-17T14:04:43.0", 600.0)]}

    assert find_last_main_effort_end_from_raw_laps(splits) is None


def test_determine_main_session_end_prefers_typed_splits():
    typed_splits = {
        "splits": [
            _typed_split("INTERVAL_ACTIVE", "2026-09-18T13:51:02.0", "2026-09-18T13:52:02.0"),
        ]
    }
    client = _FakeClient(typed_splits=typed_splits, splits={"lapDTOs": []})

    t0 = determine_main_session_end(client, "123")

    assert t0 == datetime(2026, 9, 18, 13, 52, 2, tzinfo=timezone.utc)


def test_determine_main_session_end_falls_back_to_raw_laps():
    # Brak segmentów INTERVAL_* w typed splits (np. wyścig z PacePro) -> fallback.
    typed_splits = {"splits": [_typed_split("RWD_RUN", "2026-09-18T13:41:03.0", "2026-09-18T14:00:00.0")]}
    splits = {"lapDTOs": [_lap("ACTIVE", "2026-09-18T13:41:03.0", 600.0)]}
    client = _FakeClient(typed_splits=typed_splits, splits=splits)

    t0 = determine_main_session_end(client, "123")

    assert t0 == datetime(2026, 9, 18, 13, 51, 3, tzinfo=timezone.utc)


def test_determine_main_session_end_returns_none_when_nothing_usable():
    client = _FakeClient(typed_splits={"splits": []}, splits={"lapDTOs": []})

    assert determine_main_session_end(client, "123") is None


def test_determine_main_session_end_handles_api_errors_gracefully():
    # Oba wywołania API rzucają wyjątek - funkcja nie powinna propagować błędu.
    client = _FakeClient(raise_on="both")

    assert determine_main_session_end(client, "123") is None


def test_determine_main_session_end_falls_back_to_raw_laps_when_typed_splits_errors():
    splits = {"lapDTOs": [_lap("ACTIVE", "2026-09-18T13:41:03.0", 600.0)]}
    client = _FakeClient(splits=splits, raise_on="typed")

    t0 = determine_main_session_end(client, "123")

    assert t0 == datetime(2026, 9, 18, 13, 51, 3, tzinfo=timezone.utc)
