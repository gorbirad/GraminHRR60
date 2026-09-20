"""Klient Garmin Connect - logowanie i pobieranie aktywności/tętna.

Oparty o bibliotekę `garminconnect` (https://github.com/cyberjunky/python-garminconnect),
która wewnętrznie korzysta z `garth` do obsługi logowania (w tym MFA) i zarządzania
tokenami OAuth1/OAuth2. Token sesji jest zapisywany na dysku (GARMIN_TOKEN_STORE),
dzięki czemu logowanie hasłem jest potrzebne tylko raz.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from garminconnect import Garmin

from .config import Settings, get_settings


class GarminClient:
    """Cienki wrapper na bibliotekę `garminconnect` dla naszych potrzeb."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        email: str | None = None,
        password: str | None = None,
    ) -> None:
        """`email`/`password` pozwalają nadpisać dane logowania z `.env`/zmiennych
        środowiskowych jednorazowo (np. gdy użytkownik wpisze je ręcznie w
        dashboardzie zamiast trzymać je jako sekret na serwerze) - patrz
        `scripts/dashboard.py`."""
        base_settings = settings or get_settings()
        if email or password:
            base_settings = replace(
                base_settings,
                garmin_email=email or base_settings.garmin_email,
                garmin_password=password or base_settings.garmin_password,
            )
        self.settings = base_settings
        self._api: Garmin | None = None

    def login(self) -> None:
        """Loguje się do Garmin Connect, korzystając z zapisanego tokenu jeśli istnieje."""
        token_store = self.settings.garmin_token_store
        token_store.mkdir(parents=True, exist_ok=True)

        api = Garmin(
            email=self.settings.garmin_email,
            password=self.settings.garmin_password,
            return_on_mfa=True,
        )

        try:
            # Najpierw próba użycia zapisanej sesji (bez ponownego logowania hasłem).
            api.login(str(token_store))
        except Exception:
            # Brak/nieważny token - pełne logowanie hasłem (może wymagać MFA - patrz
            # dokumentacja garminconnect co do obsługi kodu 2FA w konsoli).
            api.login()
            api.garth.dump(str(token_store))

        self._api = api

    @property
    def api(self) -> Garmin:
        if self._api is None:
            raise RuntimeError("Wywołaj najpierw GarminClient.login().")
        return self._api

    def list_activities(self, start: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        """Zwraca listę ostatnich aktywności (najnowsze pierwsze)."""
        return self.api.get_activities(start, limit)

    def list_activities_by_date(
        self, start_date: str, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        """Zwraca wszystkie aktywności między `start_date` a `end_date` (format YYYY-MM-DD).

        `end_date=None` oznacza "do dziś" (tak działa to w samej bibliotece
        `garminconnect`). Wynik jest automatycznie paginowany przez bibliotekę,
        więc może obejmować dowolną liczbę aktywności w podanym zakresie dat.
        """
        return self.api.get_activities_by_date(start_date, end_date)

    def get_activity_details(self, activity_id: int | str) -> dict[str, Any]:
        """Zwraca szczegóły aktywności zawierające m.in. próbki tętna w czasie."""
        return self.api.get_activity_details(activity_id)

    def get_activity_summary(self, activity_id: int | str) -> dict[str, Any]:
        """Zwraca podsumowanie aktywności (m.in. `activityType` - do filtrowania biegów)."""
        return self.api.get_activity(activity_id)

    def get_activity_splits(self, activity_id: int | str) -> dict[str, Any]:
        """Zwraca podział aktywności na okrążenia/interwały (laps)."""
        return self.api.get_activity_splits(activity_id)

    def get_activity_typed_splits(self, activity_id: int | str) -> dict[str, Any]:
        """Zwraca 'typed splits' - podział na interwały z dodatkowym typem
        (np. aktywny/odpoczynek), jeśli Garmin go udostępnia dla danej aktywności.
        """
        return self.api.get_activity_typed_splits(activity_id)

    def get_daily_heart_rates(self, date_str: str) -> dict[str, Any]:
        """Zwraca ciągły pomiar tętna (nadgarstkowy) dla całego dnia `date_str` (YYYY-MM-DD).

        Używane jako fallback do wyliczenia HRR60, gdy w samej aktywności brakuje
        próbek 60s po punkcie odniesienia (patrz `sync.py`).
        """
        return self.api.get_heart_rates(date_str)

    def download_activity_file(
        self, activity_id: int | str, dl_fmt: str = "TCX"
    ) -> bytes:
        """Pobiera oryginalny plik aktywności (TCX/GPX/FIT) - przydatne jako backup/fallback."""
        return self.api.download_activity(activity_id, dl_fmt=dl_fmt)

    def save_activity_file(
        self, activity_id: int | str, destination_dir: Path, dl_fmt: str = "TCX"
    ) -> Path:
        """Pobiera i zapisuje plik aktywności na dysku, zwraca ścieżkę zapisanego pliku."""
        destination_dir.mkdir(parents=True, exist_ok=True)
        extension = dl_fmt.lower()
        file_path = destination_dir / f"{activity_id}.{extension}"
        file_path.write_bytes(self.download_activity_file(activity_id, dl_fmt=dl_fmt))
        return file_path
