"""Logika synchronizacji: pobranie aktywności z Garmina i wyliczenie HRR60.

Ten moduł łączy ze sobą GarminClient, hr_extractor, hrr_calculator i storage
w jeden przepływ, który można wywołać zarówno z CLI (scripts/sync_last_activity.py),
jak i z API (POST /sync).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .garmin_client import GarminClient
from .hr_extractor import HRSample, from_garmin_activity_details, from_tcx
from .hrr_calculator import HRRCalculationError, HRRResult, compute_hrr60
from .storage import ActivityRecord, Storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncOutcome:
    activity_id: str
    activity_name: str | None
    start_time: str | None
    status: str  # "ok" | "skipped_no_hr_data" | "error"
    result: HRRResult | None = None
    message: str | None = None


def _get_hr_samples(client: GarminClient, activity_id: int | str) -> list[HRSample]:
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


def sync_activity(
    client: GarminClient, storage: Storage, activity: dict
) -> SyncOutcome:
    """Przetwarza pojedynczą aktywność zwróconą przez `GarminClient.list_activities()`."""
    activity_id = str(activity.get("activityId"))
    activity_name = activity.get("activityName")
    start_time = activity.get("startTimeLocal") or activity.get("startTimeGMT")

    try:
        samples = _get_hr_samples(client, activity_id)
    except Exception as exc:  # noqa: BLE001 - chcemy zalogować i kontynuować z kolejną aktywnością
        logger.exception("Błąd podczas pobierania danych tętna dla %s", activity_id)
        return SyncOutcome(
            activity_id=activity_id,
            activity_name=activity_name,
            start_time=start_time,
            status="error",
            message=str(exc),
        )

    if not samples:
        return SyncOutcome(
            activity_id=activity_id,
            activity_name=activity_name,
            start_time=start_time,
            status="skipped_no_hr_data",
            message="Aktywność nie zawiera żadnych próbek tętna.",
        )

    try:
        result = compute_hrr60(samples)
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


def sync_recent_activities(limit: int = 5) -> list[SyncOutcome]:
    """Loguje się do Garmina, pobiera `limit` ostatnich aktywności i liczy dla nich HRR60."""
    client = GarminClient()
    client.login()

    from .config import get_settings

    storage = Storage(get_settings().database_path)

    activities = client.list_activities(0, limit)

    outcomes = []
    for activity in activities:
        outcomes.append(sync_activity(client, storage, activity))
    return outcomes
