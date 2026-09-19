"""FastAPI - proste REST API do przeglądania wyników HRR60."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .config import get_settings
from .storage import Storage
from .sync import sync_recent_activities

app = FastAPI(title="Garmin HRR60 Tracker")

_settings = get_settings()
_storage = Storage(_settings.database_path)


@app.get("/activities")
def list_activities() -> list[dict]:
    """Zwraca wszystkie zapisane wyniki HRR60."""
    return _storage.list_activities()


@app.get("/activities/{activity_id}/hrr60")
def get_activity_hrr60(activity_id: str) -> dict:
    """Zwraca wynik HRR60 dla konkretnej aktywności."""
    activity = _storage.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono aktywności.")
    return activity


@app.post("/sync")
def sync_activities(limit: int = 5) -> dict:
    """Loguje się do Garmin Connect, pobiera `limit` ostatnich aktywności i liczy HRR60.

    Zwraca listę wyników (status "ok"/"skipped_no_hr_data"/"error") dla każdej
    sprawdzonej aktywności.
    """
    outcomes = sync_recent_activities(limit=limit)
    return {
        "checked": len(outcomes),
        "results": [
            {
                "activity_id": o.activity_id,
                "activity_name": o.activity_name,
                "start_time": o.start_time,
                "status": o.status,
                "message": o.message,
                "hrr60": o.result.hrr60 if o.result else None,
            }
            for o in outcomes
        ],
    }
