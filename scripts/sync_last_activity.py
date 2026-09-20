"""Skrypt do szybkiego, ręcznego testu: pobiera ostatnie aktywności z Garmin Connect
i wylicza dla nich HRR60, wypisując wynik na ekranie.

Użycie (z katalogu głównego repo, po aktywacji .venv):

    python scripts\\sync_last_activity.py                 # sprawdza 1 ostatnią aktywność
    python scripts\\sync_last_activity.py --limit 5        # sprawdza 5 ostatnich aktywności
    python scripts\\sync_last_activity.py --this-month     # wszystkie aktywności od 1. dnia bieżącego miesiąca do dziś
    python scripts\\sync_last_activity.py --start-date 2026-09-01 --end-date 2026-09-30

Wymaga uzupełnionego pliku .env (GARMIN_EMAIL, GARMIN_PASSWORD).
Przy pierwszym uruchomieniu może poprosić o kod MFA w konsoli, jeśli masz
włączone dwuskładnikowe logowanie w Garmin Connect.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

# Pozwala uruchomić skrypt bezpośrednio (`python scripts/sync_last_activity.py`)
# bez konieczności instalowania pakietu / ustawiania PYTHONPATH ręcznie.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from garmin_hrr.sync import sync_activities_by_date, sync_recent_activities  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Ile ostatnich aktywności sprawdzić (domyślnie 1 = tylko ostatni trening). "
        "Ignorowane, jeśli podano --start-date/--this-month.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Sprawdź aktywności od tej daty (format YYYY-MM-DD) zamiast wg --limit.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Data końcowa zakresu (format YYYY-MM-DD, domyślnie: dziś). "
        "Używane tylko razem z --start-date/--this-month.",
    )
    parser.add_argument(
        "--this-month",
        action="store_true",
        help="Skrót: sprawdź wszystkie aktywności od 1. dnia bieżącego miesiąca do dziś.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Włącz logi diagnostyczne (DEBUG)."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.this_month:
        today = date.today()
        args.start_date = today.replace(day=1).isoformat()

    if args.start_date:
        print(
            f"Logowanie do Garmin Connect i pobieranie aktywności od {args.start_date} "
            f"do {args.end_date or 'dziś'}..."
        )
        outcomes = sync_activities_by_date(args.start_date, args.end_date)
    else:
        print(f"Logowanie do Garmin Connect i pobieranie {args.limit} ostatnich aktywności...")
        outcomes = sync_recent_activities(limit=args.limit)

    if not outcomes:
        print("Brak aktywności do przetworzenia (konto puste, limit=0 albo pusty zakres dat).")
        return

    for outcome in outcomes:
        print("-" * 60)
        print(f"Aktywność: {outcome.activity_name} (id={outcome.activity_id})")
        print(f"Start: {outcome.start_time}")
        print(f"Status: {outcome.status}")

        if outcome.status == "ok" and outcome.result is not None:
            r = outcome.result
            print(f"  t0  (koniec sesji): {r.t0.isoformat()}  HR={r.hr_at_t0}")
            print(f"  t0+60s:              {r.t1.isoformat()}  HR={r.hr_at_t1:.1f}")
            print(f"  HRR60 = {r.hrr60:.1f} bpm")
        elif outcome.message:
            print(f"  Info: {outcome.message}")

    ok_results = [o for o in outcomes if o.status == "ok" and o.result is not None]
    print("-" * 60)
    print(f"Sprawdzono {len(outcomes)} aktywności, policzono HRR60 dla {len(ok_results)}.")
    if ok_results:
        avg_hrr60 = sum(o.result.hrr60 for o in ok_results) / len(ok_results)
        print(f"Średnie HRR60: {avg_hrr60:.1f} bpm")
    print("Wyniki ze statusem 'ok' zostały zapisane w bazie (data/hrr.db).")
    print("Sprawdź je też przez API: GET /activities (po uruchomieniu uvicorn).")


if __name__ == "__main__":
    main()
