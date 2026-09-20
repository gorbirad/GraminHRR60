"""Wyznaczanie punktu odniesienia t0 ("koniec głównej sesji treningu").

t0 NIE jest zwykle końcem całego nagrania - jest końcem ostatniego faktycznego
interwału biegowego (np. przed schładzaniem). Reguła poniżej została w pełni
zweryfikowana empirycznie na kilkunastu prawdziwych aktywnościach - patrz
PLAN.md, sekcje 3a-3d, po pełen opis i przykłady.

Kolejność prób (od najbardziej wiarygodnej):
1. `GarminClient.get_activity_typed_splits()` - segmenty z prawdziwym typem
   (`INTERVAL_WARMUP/ACTIVE/RECOVERY/COOLDOWN`). Jeśli istnieje co najmniej
   jeden segment `INTERVAL_ACTIVE`, t0 = `endTimeGMT` ostatniego z nich.
2. Fallback: `GarminClient.get_activity_splits()` (surowe lapy `lapDTOs`).
   Używane, gdy typed splits nie zawierają żadnego `INTERVAL_ACTIVE` (np.
   wyścig z auto-lapami PacePro - patrz PLAN.md 3d). t0 = koniec ostatniego
   lapa z `intensityType` w {"ACTIVE", "INTERVAL"}.
3. Jeśli oba zawiodą (brak lapów w ogóle - proste, niestrukturyzowane
   nagranie), zwracamy `None` - wywołujący powinien wtedy użyć własnego
   fallbacku (typowo: koniec całego nagrania / ostatnia próbka tętna).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Wartości `intensityType` z surowych `lapDTOs`, które traktujemy jako "główny
# wysiłek" w fallbacku 3. poziomu. "INTERVAL" bywa jedyną wartością obecną dla
# WSZYSTKICH lapów strukturyzowanego treningu (patrz PLAN.md 3c) - nie da się
# wtedy odróżnić rozgrzewki od właściwego wysiłku, dlatego ten fallback jest
# celowo używany tylko wtedy, gdy typed splits nie dają żadnej odpowiedzi.
_MAIN_EFFORT_INTENSITY_TYPES = {"ACTIVE", "INTERVAL"}


def _parse_garmin_gmt(value: str) -> datetime:
    """Parsuje znacznik czasu Garmina, np. '2026-09-18T13:41:03.0' (zawsze GMT/UTC)."""
    return datetime.strptime(value.split(".")[0], "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc
    )


def find_last_active_end_from_typed_splits(
    typed_splits: dict[str, Any]
) -> datetime | None:
    """Zwraca t0 na podstawie `get_activity_typed_splits()`.

    Bierze pod uwagę wyłącznie segmenty typu `INTERVAL_ACTIVE` - równoległe
    segmentacje typu `RWD_RUN`/`RWD_WALK`/`PACE_PRO_SPLIT` są ignorowane (nie
    opisują struktury WARMUP/ACTIVE/RECOVERY/COOLDOWN treningu).

    Zwraca `None`, jeśli nie ma żadnego segmentu `INTERVAL_ACTIVE` (np. wyścig
    z auto-lapami PacePro, patrz PLAN.md sekcja 3d).
    """
    active_segments = [
        s
        for s in typed_splits.get("splits", [])
        if s.get("type") == "INTERVAL_ACTIVE"
        and s.get("startTimeGMT")
        and s.get("endTimeGMT")
    ]
    if not active_segments:
        return None

    active_segments.sort(key=lambda s: s["startTimeGMT"])
    return _parse_garmin_gmt(active_segments[-1]["endTimeGMT"])


def find_last_main_effort_end_from_raw_laps(splits: dict[str, Any]) -> datetime | None:
    """Fallback: wyznacza t0 z surowych `lapDTOs` (`get_activity_splits()`).

    Używany tylko wtedy, gdy `get_activity_typed_splits()` nie zwrócił żadnego
    segmentu `INTERVAL_ACTIVE`. t0 = koniec ostatniego lapa z `intensityType`
    w {"ACTIVE", "INTERVAL"}.
    """
    candidates = [
        lap
        for lap in splits.get("lapDTOs", [])
        if lap.get("intensityType") in _MAIN_EFFORT_INTENSITY_TYPES
        and lap.get("startTimeGMT")
        and lap.get("duration") is not None
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda lap: lap["startTimeGMT"])
    last = candidates[-1]
    start = _parse_garmin_gmt(last["startTimeGMT"])
    return start + timedelta(seconds=last["duration"])


def determine_main_session_end(client, activity_id: int | str) -> datetime | None:
    """Wyznacza t0 (koniec głównej sesji treningu) wg reguły z PLAN.md 3d.

    Args:
        client: `GarminClient` (już zalogowany).
        activity_id: identyfikator aktywności Garmina.

    Returns:
        Znacznik czasu (UTC) końca ostatniego faktycznego interwału biegowego,
        albo `None`, jeśli nie udało się go wyznaczyć z dostępnych danych o
        lapach - wywołujący powinien wtedy użyć własnego fallbacku (typowo:
        koniec całego nagrania).
    """
    try:
        typed_splits = client.get_activity_typed_splits(activity_id)
    except Exception:
        logger.exception(
            "get_activity_typed_splits nie powiodło się dla aktywności %s.", activity_id
        )
        typed_splits = None

    if typed_splits is not None:
        t0 = find_last_active_end_from_typed_splits(typed_splits)
        if t0 is not None:
            return t0

    try:
        splits = client.get_activity_splits(activity_id)
    except Exception:
        logger.exception(
            "get_activity_splits nie powiodło się dla aktywności %s.", activity_id
        )
        return None

    return find_last_main_effort_end_from_raw_laps(splits)
