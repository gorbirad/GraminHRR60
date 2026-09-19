"""FastAPI - proste REST API do przeglądania wyników HRR60."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .config import get_settings
from .storage import Storage

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
def sync_activities() -> dict:
    """Placeholder do ręcznego wywołania synchronizacji z Garmin Connect.

    Docelowa implementacja: zalogować się przez GarminClient, pobrać nowe
    aktywności, policzyć HRR60 (hrr_calculator) i zapisać (storage) - patrz
    PLAN.md, etap 6/7.
    """
    return {"status": "not_implemented_yet"}
