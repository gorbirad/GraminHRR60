"""Skrypt diagnostyczny: pokazuje interwały (lapy) i typ aktywności dla
wskazanego ID aktywności z Garmin Connect.

Zamiast zrzucać surowy (i łatwo obcinany w terminalu) JSON, skrypt:
- zapisuje PEŁNE, nieobcięte odpowiedzi API do plików `data/raw/<id>_*.json`
  (do ew. dalszej analizy pól, których nie widać w podsumowaniu),
- wypisuje na ekranie czytelne, obliczone podsumowanie każdego lapa: indeks,
  typ intensywności, czas startu/końca WZGLĘDNY (mm:ss od startu treningu)
  oraz w GMT, czas trwania w sekundach,
- wypisuje pola związane z typem wydarzenia (np. "czy to wyścig"), jeśli
  Garmin je udostępnia w podsumowaniu aktywności (`get_activity`).

Używane do zbadania prawdziwego kształtu odpowiedzi `get_activity` i
`get_activity_splits`, zanim napiszemy właściwą logikę wykrywania "końca
ostatniego interwału biegowego" (patrz PLAN.md).

Użycie (z katalogu głównego repo, po aktywacji .venv):

    python scripts\\inspect_activity.py 24408599358
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from garmin_hrr.garmin_client import GarminClient  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def _save_raw(activity_id: str, name: str, data) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{activity_id}_{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _parse_gmt(value: str) -> datetime:
    # Format Garmina: "2026-09-18T13:41:03.0" (bez strefy, traktujemy jako GMT).
    return datetime.strptime(value.split(".")[0], "%Y-%m-%dT%H:%M:%S")


def _format_elapsed(delta: timedelta) -> str:
    total_seconds = delta.total_seconds()
    minutes, seconds = divmod(total_seconds, 60)
    return f"{int(minutes)}:{seconds:05.2f}"


def _print_event_fields(summary: dict) -> None:
    """Wypisuje wszystkie pola z podsumowania aktywności, których nazwa
    sugeruje typ wydarzenia (np. wyścig) - żeby sprawdzić, czy da się to
    wykryć automatycznie z API zamiast zgadywać po nazwie treningu.
    """
    interesting_keys = [
        key
        for key in summary.keys()
        if "event" in key.lower() or "race" in key.lower() or "workout" in key.lower()
    ]
    if not interesting_keys:
        print("(brak pól zawierających 'event'/'race'/'workout' w podsumowaniu)")
        return
    for key in interesting_keys:
        print(f"  {key} = {summary.get(key)!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("activity_id", help="ID aktywności Garmin (np. 24408599358)")
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

    summary = client.get_activity_summary(args.activity_id)
    activity_type = summary.get("activityTypeDTO") or summary.get("activityType") or {}
    _save_raw(args.activity_id, "summary", summary)

    print("=" * 70)
    print(f"Aktywność {args.activity_id}")
    print("=" * 70)
    print(f"activityType.typeKey = {activity_type.get('typeKey')}")
    print("Pola dot. typu wydarzenia (wyścig/trening/itp.):")
    _print_event_fields(summary)
    print()

    try:
        splits = client.get_activity_splits(args.activity_id)
        raw_path = _save_raw(args.activity_id, "splits", splits)
        print(f"(pełny JSON zapisany w {raw_path})")
    except Exception as exc:  # noqa: BLE001
        print(f"get_activity_splits nie powiodło się: {exc}\n")
        return

    laps = splits.get("lapDTOs", [])
    print(f"Liczba lapów: {len(laps)}")
    print("-" * 70)
    print(
        f"{'#':>3} {'intensityType':<12} {'start (mm:ss)':<14} {'koniec (mm:ss)':<14} "
        f"{'start GMT':<20} {'czas[s]':>8}"
    )
    print("-" * 70)
    if laps:
        activity_start = _parse_gmt(laps[0]["startTimeGMT"])
    for lap in laps:
        lap_index = lap.get("lapIndex")
        intensity = lap.get("intensityType", "?")
        start_raw = lap.get("startTimeGMT")
        duration = lap.get("duration")
        if start_raw is None or duration is None:
            print(f"{lap_index!s:>3} {intensity:<12} (brak startTimeGMT/duration)")
            continue
        start = _parse_gmt(start_raw)
        end = start + timedelta(seconds=duration)
        start_elapsed = _format_elapsed(start - activity_start)
        end_elapsed = _format_elapsed(end - activity_start)
        print(
            f"{lap_index!s:>3} {intensity:<12} {start_elapsed:<14} {end_elapsed:<14} "
            f"{start.isoformat():<20} {duration:>8.1f}"
        )
    print("-" * 70)
    print("Uwaga: 'mm:ss' to czas WZGLĘDNY liczony od startu treningu (pierwszy lap).")
    print()

    _print_typed_splits_analysis(client, args.activity_id)


def _print_typed_splits_analysis(client: GarminClient, activity_id: str) -> None:
    """Pobiera get_activity_typed_splits, filtruje segmenty INTERVAL_* i
    wyznacza t0 = koniec ostatniego segmentu INTERVAL_ACTIVE.

    Wypisuje dwa "zegary" dla każdego segmentu:
    - suma skumulowana pola `duration` (czas aktywny/ruchu, bez pauz) -
      to właśnie ten "zegar" pokazuje aplikacja Garmin Connect w tabeli
      interwałów, zweryfikowane empirycznie na kilku aktywnościach,
    - rzeczywisty czas zegarowy (na podstawie endTimeGMT) - to jest realny
      znacznik czasu potrzebny do wyszukania/interpolacji próbki tętna.
    """
    try:
        typed = client.get_activity_typed_splits(activity_id)
    except Exception as exc:  # noqa: BLE001
        print(f"get_activity_typed_splits nie powiodło się: {exc}\n")
        return

    raw_path = _save_raw(activity_id, "typed_splits", typed)
    print(f"(pełny JSON zapisany w {raw_path})")

    interval_splits = [s for s in typed.get("splits", []) if str(s.get("type", "")).startswith("INTERVAL_")]
    interval_splits.sort(key=lambda s: s["startTimeGMT"])

    if not interval_splits:
        print("Brak segmentów INTERVAL_* w get_activity_typed_splits (np. aktywność jednolapowa).")
        return

    activity_start = _parse_gmt(interval_splits[0]["startTimeGMT"])

    print()
    print("=" * 90)
    print("Segmenty INTERVAL_* (z get_activity_typed_splits) - właściwa struktura treningu")
    print("=" * 90)
    print(
        f"{'#':>3} {'type':<20} {'skum. koniec (mm:ss)':<22} {'koniec GMT (realny)':<22} {'czas[s]':>8}"
    )
    print("-" * 90)

    cumulative = 0.0
    last_active_end_gmt: datetime | None = None
    last_active_end_cumulative: str | None = None
    for i, seg in enumerate(interval_splits, 1):
        duration = seg.get("duration", 0.0)
        cumulative += duration
        end_gmt = _parse_gmt(seg["endTimeGMT"])
        seg_type = seg.get("type", "?")
        marker = "  <-- ostatni ACTIVE?" if seg_type == "INTERVAL_ACTIVE" else ""
        print(
            f"{i:>3} {seg_type:<20} {_format_elapsed(timedelta(seconds=cumulative)):<22} "
            f"{end_gmt.isoformat():<22} {duration:>8.1f}{marker}"
        )
        if seg_type == "INTERVAL_ACTIVE":
            last_active_end_gmt = end_gmt
            last_active_end_cumulative = _format_elapsed(timedelta(seconds=cumulative))

    print("-" * 90)
    if last_active_end_gmt is not None:
        print(
            f">>> t0 (koniec ostatniego INTERVAL_ACTIVE): {last_active_end_gmt.isoformat()} GMT"
            f"  (etykieta UI ~ {last_active_end_cumulative})"
        )
    else:
        print(
            ">>> Brak segmentu INTERVAL_ACTIVE - prawdopodobnie wyścig/pojedynczy wysiłek "
            "bez rozgrzewki/schładzania. t0 = koniec ostatniego segmentu (koniec nagrania)."
        )
        print(f">>> t0 (koniec ostatniego segmentu): {_parse_gmt(interval_splits[-1]['endTimeGMT']).isoformat()} GMT")
    print(
        "Uwaga: 'skum. koniec (mm:ss)' to suma pola 'duration' (czas aktywny, bez pauz) - "
        "to ta wartość odpowiada etykietom czasu widocznym w aplikacji Garmin Connect."
    )
    print()


if __name__ == "__main__":
    main()
