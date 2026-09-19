"""Wczytywanie konfiguracji i sekretów z pliku .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Katalog główny projektu (dwa poziomy wyżej niż ten plik: src/garmin_hrr/config.py -> repo root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    garmin_email: str
    garmin_password: str
    garmin_token_store: Path
    database_path: Path
    discord_bot_token: str | None
    discord_channel_id: str | None


def get_settings() -> Settings:
    """Zwraca ustawienia wczytane ze zmiennych środowiskowych (.env)."""

    def _resolve(path_str: str) -> Path:
        path = Path(path_str)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    return Settings(
        garmin_email=os.environ.get("GARMIN_EMAIL", ""),
        garmin_password=os.environ.get("GARMIN_PASSWORD", ""),
        garmin_token_store=_resolve(os.environ.get("GARMIN_TOKEN_STORE", "./data/.garth_session")),
        database_path=_resolve(os.environ.get("DATABASE_PATH", "./data/hrr.db")),
        discord_bot_token=os.environ.get("DISCORD_BOT_TOKEN") or None,
        discord_channel_id=os.environ.get("DISCORD_CHANNEL_ID") or None,
    )
