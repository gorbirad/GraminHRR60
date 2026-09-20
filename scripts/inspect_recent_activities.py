"""Skrypt diagnostyczny (batch): pokazuje krótkie podsumowanie struktury lapów
dla N ostatnich aktywności z Garmin Connect (dowolnego typu).

Dla każdej aktywności wypisuje:
- typ aktywności (`activityType.typeKey`),
- liczbę lapów,
- sekwencję `intensityType` lapów (albo "brak intensityType" jeśli auto-lapy
  bez struktury interwałowej),
- czas (elapsed od startu treningu) końca ostatniego lapa `ACTIVE`, jeśli
  istnieje - to jest kandydat na "koniec głównej sesji treningu" wg
  PLAN.md sekcja 3a.

Nie liczy HRR60 ani nic nie zapisuje do bazy - to czysto diagnostyczny
przegląd, żeby zweryfikować hipotezę na większej próbce danych przed zmianą
właściwej logiki w `sync.py`.

Użycie (z katalogu głównego repo, po aktywacji .venv):

    python scripts\\inspect_recent_activities.py --limit 20
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from garmin_hrr.garmin_client import GarminClient  # noqa: E402


def _parse_gmt(value: str) -> datetime:
    return datetime.strptime(value.split(".")[0], "%Y-%m-%dT%H:%M:%S")


def _summarize_laps(splits: dict) -> tuple[int, list[str], str | None]:
    """Zwraca (liczba_lapów, lista_intensityType, elapsed_koniec_ostatniego_ACTIVE)."""
    laps = splits.get("lapDTOs", [])
    if not laps:
        return 0, [], None

    activity_start = _parse_gmt(laps[0]["startTimeGMT"])
    intensity_sequence = [lap.get("intensityType", "?") for lap in laps]

    last_active_end_elapsed = None
    for lap in laps:
        if lap.get("intensityType") == "ACTIVE":
            start = _parse_gmt(lap["startTimeGMT"])
            end = start + timedelta(seconds=lap.get("duration", 0))
            elapsed = end - activity_start
            last_active_end_elapsed = str(elapsed)

    return len(laps), intensity_sequence, last_active_end_elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=20, help="Ile ostatnich aktywności sprawdzić."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Włącz logi diagnostyczne (DEBUG)."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    client = GarminClient()
    client.login()

    activities = client.list_activities(0, args.limit)
    print(f"Pobrano {len(activities)} aktywności.\n")

    header = (
        f"{'id':<13} {'typeKey':<16} {'start lokalny':<20} "
        f"{'#lapów':>6}  {'koniec ost. ACTIVE':<12}  intensityType lapów"
    )
    print(header)
    print("-" * len(header))

    for activity in activities:
        activity_id = activity.get("activityId")
        type_key = (activity.get("activityType") or {}).get("typeKey", "?")
        start_local = activity.get("startTimeLocal", "?")

        try:
            splits = client.get_activity_splits(activity_id)
            lap_count, sequence, last_active_end = _summarize_laps(splits)
        except Exception as exc:  # noqa: BLE001
            print(f"{activity_id!s:<13} {type_key:<16} {start_local:<20}  BŁĄD: {exc}")
            continue

        seq_str = ",".join(sequence) if sequence else "(brak lapów)"
        last_active_str = last_active_end or "-"
        print(
            f"{activity_id!s:<13} {type_key:<16} {start_local:<20} "
            f"{lap_count:>6}  {last_active_str:<12}  {seq_str}"
        )

    print()
    print(
        "Uwaga: kolumna 'koniec ost. ACTIVE' to czas (elapsed od startu treningu) "
        "końca ostatniego lapa oznaczonego intensityType=ACTIVE - to kandydat na "
        "punkt odniesienia t0. '-' oznacza brak takiego lapa (np. prosty bieg bez "
        "struktury interwałowej albo aktywność niebiegowa)."
    )


if __name__ == "__main__":
    main()
