"""Logika synchronizacji: pobranie aktywności z Garmina i wyliczenie HRR60.

Ten moduł łączy ze sobą GarminClient, hr_extractor, hrr_calculator i storage
w jeden przepływ, który można wywołać zarówno z CLI (scripts/sync_last_activity.py),
jak i z API (POST /sync).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from .garmin_client import GarminClient
from .hr_extractor import (
    HRSample,
    from_garmin_activity_details,
    from_garmin_daily_heart_rate,
    from_tcx,
)
from .hrr_calculator import HRRCalculationError, HRRResult, compute_hrr60
from .intervals import determine_main_session_end
from .storage import ActivityRecord, Storage

logger = logging.getLogger(__name__)

# Typy aktywności (`activityType.typeKey`), dla których liczymy HRR60 - patrz
# PLAN.md sekcja 3b. `running` i `track_running` zostały potwierdzone na
# prawdziwych danych; `trail_running`/`treadmill_running` to standardowe
# wartości Garmina, jeszcze niepotwierdzone empirycznie w tym koncie.
RUNNING_ACTIVITY_TYPES = {
    "running",
    "trail_running",
    "track_running",
    "treadmill_running",
}


@dataclass(frozen=True)
class SyncOutcome:
    activity_id: str
    activity_name: str | None
    start_time: str | None
    status: str  # "ok" | "skipped_not_running" | "skipped_no_hr_data" | "error"
    result: HRRResult | None = None
    message: str | None = None


def _is_running_activity(activity: dict) -> bool:
    """Sprawdza, czy aktywność należy do biegowej rodziny typów (patrz PLAN.md 3b)."""
    type_key = (activity.get("activityType") or {}).get("typeKey")
    return type_key in RUNNING_ACTIVITY_TYPES


def _get_activity_hr_samples(client: GarminClient, activity_id: int | str) -> list[HRSample]:
    """Próbuje wyciągnąć próbki tętna z API, a jeśli się nie uda - z pliku TCX."""
    details = client.get_activity_details(activity_id)
    samples = from_garmin_activity_details(details)
    if samples:
        return samples

    logger.info(
        "Brak tętna w get_activity_details dla %s, próbuję pliku TCX jako fallback.",
        activity_id,
    )
    tcx_content = client.download_activity_file(activity_id, dl_fmt="TCX")
    return from_tcx(tcx_content)


def _extend_with_continuous_heart_rate(
    client: GarminClient, activity_samples: list[HRSample], start_time_local: str | None
) -> list[HRSample]:
    """Dokleja ciągły (nadgarstkowy) pomiar tętna z całego dnia do próbek z aktywności.

    Ostatnia próbka nagrania aktywności z definicji nie ma "przyszłych" próbek
    w tym samym pliku/nagraniu - dlatego samo `get_activity_details`/TCX praktycznie
    nigdy nie wystarczy do policzenia HRR60 z domyślnym punktem odniesienia (koniec
    aktywności). Garmin kontynuuje jednak pomiar tętna również po zakończeniu
    rejestrowania treningu, więc dociągamy te dane z `get_heart_rates(date)`.

    Zwraca listę próbek: oryginalne próbki z aktywności + próbki ciągłe, które
    wystąpiły ściśle po ostatniej próbce z aktywności (żeby nie podmieniać
    dokładniejszych danych z aktywności rzadszym pomiarem ciągłym).
    """
    if not activity_samples or not start_time_local:
        return activity_samples

    last_activity_time = activity_samples[-1].time
    try:
        base_date = datetime.strptime(start_time_local[:10], "%Y-%m-%d")
    except ValueError:
        logger.warning("Nie udało się sparsować daty aktywności z '%s'.", start_time_local)
        return activity_samples

    daily_samples: list[HRSample] = []
    # Sprawdzamy dzień startu treningu oraz kolejny dzień (na wypadek treningu
    # kończącego się tuż po północy).
    for offset_days in (0, 1):
        cdate = (base_date + timedelta(days=offset_days)).strftime("%Y-%m-%d")
        try:
            daily_hr = client.get_daily_heart_rates(cdate)
        except Exception:
            logger.exception("Nie udało się pobrać ciągłych danych tętna dla %s.", cdate)
            continue
        daily_samples.extend(from_garmin_daily_heart_rate(daily_hr))

    extra_samples = sorted(
        (s for s in daily_samples if s.time > last_activity_time),
        key=lambda s: s.time,
    )
    if not extra_samples:
        return activity_samples

    logger.info(
        "Dociągnięto %d próbek ciągłego pomiaru tętna po zakończeniu aktywności.",
        len(extra_samples),
    )
    return activity_samples + extra_samples


def _compute_hrr60_with_fallback(
    client: GarminClient,
    activity_samples: list[HRSample],
    start_time: str | None,
    **reference_kwargs,
) -> HRRResult:
    """Liczy HRR60, a jeśli w samej aktywności brakuje 60s danych po t0 (co jest
    NORMALNE dla wyścigów i prostych nagrań bez struktury interwałowej - patrz
    PLAN.md 3d, punkt 5), dogrywa ciągły pomiar tętna z całego dnia i próbuje
    ponownie z tym samym punktem odniesienia."""
    try:
        return compute_hrr60(activity_samples, **reference_kwargs)
    except HRRCalculationError:
        extended_samples = _extend_with_continuous_heart_rate(
            client, activity_samples, start_time
        )
        return compute_hrr60(extended_samples, **reference_kwargs)


def sync_activity(
    client: GarminClient, storage: Storage, activity: dict
) -> SyncOutcome:
    """Przetwarza pojedynczą aktywność zwróconą przez `GarminClient.list_activities()`."""
    activity_id = str(activity.get("activityId"))
    activity_name = activity.get("activityName")
    start_time = activity.get("startTimeLocal") or activity.get("startTimeGMT")

    if not _is_running_activity(activity):
        type_key = (activity.get("activityType") or {}).get("typeKey")
        return SyncOutcome(
            activity_id=activity_id,
            activity_name=activity_name,
            start_time=start_time,
            status="skipped_not_running",
            message=(
                f"Pomijam aktywność typu '{type_key}' - liczymy HRR60 tylko dla "
                "biegów (patrz PLAN.md sekcja 3b)."
            ),
        )

    try:
        activity_samples = _get_activity_hr_samples(client, activity_id)
    except Exception as exc:  # noqa: BLE001 - chcemy zalogować i kontynuować z kolejną aktywnością
        logger.exception("Błąd podczas pobierania danych tętna dla %s", activity_id)
        return SyncOutcome(
            activity_id=activity_id,
            activity_name=activity_name,
            start_time=start_time,
            status="error",
            message=str(exc),
        )

    if not activity_samples:
        return SyncOutcome(
            activity_id=activity_id,
            activity_name=activity_name,
            start_time=start_time,
            status="skipped_no_hr_data",
            message="Aktywność nie zawiera żadnych próbek tętna.",
        )

    # Punkt odniesienia (t0) = koniec ostatniego faktycznego interwału biegowego
    # (koniec głównej sesji treningu), wyznaczony wg reguły z PLAN.md 3d. Jeśli
    # nie da się go wyznaczyć z danych o lapach (proste nagranie bez struktury),
    # spadamy do historycznego zachowania: t0 = ostatnia próbka nagrania.
    try:
        reference_time = determine_main_session_end(client, activity_id)
    except Exception:
        logger.exception(
            "Nie udało się wyznaczyć końca głównej sesji dla %s - użyję końca nagrania.",
            activity_id,
        )
        reference_time = None

    reference_kwargs = (
        {"reference_time": reference_time}
        if reference_time is not None
        else {"reference_index": len(activity_samples) - 1}
    )

    try:
        result = _compute_hrr60_with_fallback(
            client, activity_samples, start_time, **reference_kwargs
        )
    except HRRCalculationError as exc:
        return SyncOutcome(
            activity_id=activity_id,
            activity_name=activity_name,
            start_time=start_time,
            status="skipped_no_hr_data",
            message=str(exc),
        )

    storage.save_result(
        ActivityRecord(
            activity_id=activity_id,
            source="garmin",
            activity_name=activity_name,
            start_time=start_time,
            result=result,
        )
    )

    return SyncOutcome(
        activity_id=activity_id,
        activity_name=activity_name,
        start_time=start_time,
        status="ok",
        result=result,
    )


def sync_recent_activities(
    limit: int = 5,
    *,
    garmin_email: str | None = None,
    garmin_password: str | None = None,
) -> list[SyncOutcome]:
    """Loguje się do Garmina, pobiera `limit` ostatnich aktywności i liczy dla nich HRR60.

    `garmin_email`/`garmin_password` pozwalają jednorazowo nadpisać dane logowania
    z `.env` (np. formularz logowania w dashboardzie zamiast sekretu na serwerze).
    """
    client = GarminClient(email=garmin_email, password=garmin_password)
    client.login()

    from .config import get_settings

    storage = Storage(get_settings().database_path)

    activities = client.list_activities(0, limit)

    outcomes = []
    for activity in activities:
        outcomes.append(sync_activity(client, storage, activity))
    return outcomes


def sync_activities_by_date(
    start_date: str,
    end_date: str | None = None,
    *,
    garmin_email: str | None = None,
    garmin_password: str | None = None,
) -> list[SyncOutcome]:
    """Loguje się do Garmina, pobiera WSZYSTKIE aktywności z zakresu dat
    `start_date`..`end_date` (format YYYY-MM-DD, `end_date=None` = do dziś)
    i liczy dla nich HRR60. Przydatne np. do sprawdzenia całego miesiąca
    naraz, zamiast podawać `limit` "na oko".

    `garmin_email`/`garmin_password` pozwalają jednorazowo nadpisać dane logowania
    z `.env` (np. formularz logowania w dashboardzie zamiast sekretu na serwerze).
    """
    client = GarminClient(email=garmin_email, password=garmin_password)
    client.login()

    from .config import get_settings

    storage = Storage(get_settings().database_path)

    activities = client.list_activities_by_date(start_date, end_date)

    outcomes = []
    for activity in activities:
        outcomes.append(sync_activity(client, storage, activity))
    return outcomes
