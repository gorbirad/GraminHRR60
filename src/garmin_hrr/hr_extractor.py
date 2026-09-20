"""Wyciąganie próbek tętna (czas + wartość) z różnych źródeł danych.

Obsługiwane źródła:
- odpowiedź `get_activity_details()` z Garmin Connect (API, bez plików),
- odpowiedź `get_heart_rates(date)` z Garmin Connect - ciągły pomiar tętna
  z nadgarstka dla całego dnia, niezależny od konkretnej aktywności (używany
  jako fallback, gdy w samej aktywności brakuje próbek 60s po jej końcu),
- pliki TCX (Garmin i inne zegarki eksportujące ten format),
- pliki FIT (Garmin, Polar, Wahoo, ...),
- pliki GPX (rzadziej zawierają tętno, ale bywa w rozszerzeniach `gpxtpx:hr`).

Każda funkcja zwraca listę `HRSample` posortowaną rosnąco po czasie - to jest
wspólny format wejściowy dla `hrr_calculator.compute_hrr60`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class HRSample:
    time: datetime
    hr: int


def _parse_iso_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def from_garmin_activity_details(details: dict[str, Any]) -> list[HRSample]:
    """Wyciąga próbki tętna z odpowiedzi `Garmin.get_activity_details()`.

    Struktura odpowiedzi Garmina zawiera `activityDetailMetrics` (lista próbek)
    oraz `metricDescriptors` (mapowanie nazwa metryki -> indeks w `metrics`).
    Szukamy metryki `directHeartRate` (lub `heartRate`) oraz `directTimestamp`.
    """
    descriptors = details.get("metricDescriptors", [])
    metrics = details.get("activityDetailMetrics", [])

    hr_index = None
    time_index = None
    for descriptor in descriptors:
        key = descriptor.get("key")
        index = descriptor.get("metricsIndex")
        if key in ("directHeartRate", "heartRate"):
            hr_index = index
        elif key in ("directTimestamp", "sumElapsedDuration"):
            if key == "directTimestamp":
                time_index = index

    if hr_index is None or time_index is None:
        return []

    samples: list[HRSample] = []
    for row in metrics:
        values = row.get("metrics", [])
        if len(values) <= max(hr_index, time_index):
            continue
        hr_value = values[hr_index]
        time_value = values[time_index]
        if hr_value is None or time_value is None:
            continue
        # `directTimestamp` bywa epoch w milisekundach.
        time_point = datetime.fromtimestamp(time_value / 1000.0, tz=timezone.utc)
        samples.append(HRSample(time=time_point, hr=int(hr_value)))

    samples.sort(key=lambda s: s.time)
    return samples


def from_garmin_daily_heart_rate(daily_hr: dict[str, Any]) -> list[HRSample]:
    """Parsuje odpowiedź `Garmin.get_heart_rates(date)`.

    To jest ciągły pomiar tętna z nadgarstka dla całego dnia, niezależny od
    konkretnej aktywności - urządzenie kontynuuje go również po zakończeniu
    nagrywania treningu. Używany jako fallback w `sync.py`, gdy sama aktywność
    nie zawiera 60 sekund próbek po punkcie odniesienia (co jest regułą, a nie
    wyjątkiem: ostatnia próbka nagrania z definicji nie ma "przyszłych" próbek
    w tym samym nagraniu).

    Uwaga: częstotliwość próbkowania w ciągłym pomiarze bywa rzadsza (Garmin
    zwykle próbkuje co ok. 2 minuty poza aktywnością), więc wynik HRR60 oparty
    o te dane jest interpolowany z mniejszą dokładnością niż w trakcie samej
    aktywności.
    """
    values = daily_hr.get("heartRateValues") or []

    samples: list[HRSample] = []
    for entry in values:
        if not entry or len(entry) < 2:
            continue
        timestamp_ms, hr_value = entry[0], entry[1]
        if timestamp_ms is None or hr_value is None:
            continue
        samples.append(
            HRSample(
                time=datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc),
                hr=int(hr_value),
            )
        )

    samples.sort(key=lambda s: s.time)
    return samples


def from_tcx(tcx_content: str | bytes) -> list[HRSample]:
    """Parsuje plik TCX i zwraca próbki tętna ze wszystkich Trackpointów."""
    import xmltodict

    if isinstance(tcx_content, bytes):
        tcx_content = tcx_content.decode("utf-8")

    data = xmltodict.parse(tcx_content)
    activities = data["TrainingCenterDatabase"]["Activities"]["Activity"]
    if isinstance(activities, list):
        activity = activities[0]
    else:
        activity = activities

    laps = activity.get("Lap", [])
    if not isinstance(laps, list):
        laps = [laps]

    samples: list[HRSample] = []
    for lap in laps:
        track = lap.get("Track")
        if track is None:
            continue
        tracks = track if isinstance(track, list) else [track]
        for trk in tracks:
            trackpoints = trk.get("Trackpoint", [])
            if not isinstance(trackpoints, list):
                trackpoints = [trackpoints]
            for tp in trackpoints:
                hr_field = tp.get("HeartRateBpm")
                time_field = tp.get("Time")
                if hr_field is None or time_field is None:
                    continue
                hr_value = hr_field.get("Value") if isinstance(hr_field, dict) else hr_field
                samples.append(
                    HRSample(time=_parse_iso_time(time_field), hr=int(hr_value))
                )

    samples.sort(key=lambda s: s.time)
    return samples


def from_fit(fit_content: bytes) -> list[HRSample]:
    """Parsuje plik FIT (Garmin, Polar, Wahoo, ...) i zwraca próbki tętna."""
    import io

    from fitparse import FitFile

    fit_file = FitFile(io.BytesIO(fit_content))

    samples: list[HRSample] = []
    for record in fit_file.get_messages("record"):
        hr_value = record.get_value("heart_rate")
        time_value = record.get_value("timestamp")
        if hr_value is None or time_value is None:
            continue
        time_point = time_value
        if time_point.tzinfo is None:
            time_point = time_point.replace(tzinfo=timezone.utc)
        samples.append(HRSample(time=time_point, hr=int(hr_value)))

    samples.sort(key=lambda s: s.time)
    return samples


def from_gpx(gpx_content: str | bytes) -> list[HRSample]:
    """Parsuje plik GPX i zwraca próbki tętna z rozszerzenia `gpxtpx:hr` (jeśli obecne)."""
    import gpxpy

    if isinstance(gpx_content, bytes):
        gpx_content = gpx_content.decode("utf-8")

    gpx = gpxpy.parse(gpx_content)

    samples: list[HRSample] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                hr_value = _extract_hr_extension(point.extensions)
                if hr_value is None or point.time is None:
                    continue
                samples.append(HRSample(time=point.time, hr=hr_value))

    samples.sort(key=lambda s: s.time)
    return samples


def _extract_hr_extension(extensions: Iterable[Any]) -> int | None:
    for ext in extensions:
        # gpxpy zwraca elementy ElementTree; tag zawiera namespace, np. "{...}TrackPointExtension"
        for child in ext.iter():
            tag = child.tag.split("}")[-1].lower()
            if tag == "hr" and child.text:
                return int(child.text)
    return None
