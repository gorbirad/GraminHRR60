# Garmin HRR60 Tracker

Automatyczne pobieranie treningów z Garmin Connect i wyliczanie **HRR60**
(Heart Rate Recovery 60s) - spadku tętna 60 sekund po zakończeniu głównej
sesji treningowej.

Pełny plan projektu: [PLAN.md](./PLAN.md).


## Struktura projektu

```
Garmin/
├── PLAN.md                      # plan projektu i architektura
├── requirements.txt             # zależności Pythona
├── pyproject.toml               # konfiguracja pakietu + pytest
├── .env.example                 # szablon zmiennych środowiskowych (bez sekretów)
├── .env                         # TWOJE prawdziwe dane logowania (gitignored!)
├── .gitignore
├── src/garmin_hrr/
│   ├── config.py                # wczytywanie ustawień z .env
│   ├── garmin_client.py         # logowanie + pobieranie z Garmin Connect
│   ├── hr_extractor.py          # próbki tętna z API/TCX/FIT/GPX (różne zegarki)
│   ├── hrr_calculator.py        # logika HRR60 (z interpolacją)
│   ├── storage.py               # zapis wyników do SQLite
│   ├── sync.py                  # logika synchronizacji: Garmin -> HRR60 -> baza
│   └── api.py                   # FastAPI: GET /activities, POST /sync, ...
├── scripts/
│   └── sync_last_activity.py    # szybki test z linii poleceń (bez API/serwera)
├── data/                        # baza SQLite + pobrane pliki (gitignored)
└── tests/
    └── test_hrr_calculator.py   # testy logiki HRR60 (nie wymagają logowania)
```

## Szybki start

1. Zainstaluj zależności (Windows PowerShell):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   Ważne: `pytest`, `uvicorn` itd. działają tylko **po aktywacji** `.venv`
   (`.\.venv\Scripts\Activate.ps1`) albo przez pełną ścieżkę
   `.\.venv\Scripts\python.exe -m pytest`. Sam `pytest` w terminalu bez
   aktywacji zwróci błąd "term not recognized".
2. Uzupełnij plik `.env` swoimi danymi logowania do Garmin Connect
   (skopiuj `.env.example`, jeśli `.env` nie istnieje).
3. Uruchom testy jednostkowe (nie wymagają połączenia z Garminem):
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -v
   ```

## Jak sprawdzić, że ostatni trening zostanie pobrany i policzony HRR60

Najszybciej przez skrypt CLI (bez uruchamiania serwera API):

```powershell
.\.venv\Scripts\python.exe scripts\sync_last_activity.py
```

To zaloguje się do Garmin Connect (przy pierwszym uruchomieniu może poprosić
o kod MFA w konsoli, jeśli masz włączone 2FA), pobierze **ostatnią** aktywność,
wyliczy HRR60 i wypisze wynik, np.:

```
Aktywność: Bieg poranny (id=24408599358)
Start: 2026-09-18T07:12:00
Status: ok
  t0  (koniec sesji): 2026-09-18T07:42:10+00:00  HR=158
  t0+60s:              2026-09-18T07:43:10+00:00  HR=112.0
  HRR60 = 46.0 bpm
```

Wynik zostaje też zapisany w `data/hrr.db`. Możliwe statusy:
- `ok` — HRR60 policzone i zapisane,
- `skipped_no_hr_data` — aktywność nie ma danych o tętnie albo trwa krócej
  niż 60s po punkcie odniesienia (np. bardzo krótki trening),
- `error` — problem z pobraniem danych (np. wygasła sesja, błąd sieci).

Żeby sprawdzić więcej niż jedną aktywność: `--limit 5`.
Żeby zobaczyć szczegółowe logi (np. debugować logowanie): `-v` / `--verbose`.

Alternatywnie, przez API (po uruchomieniu serwera):
```powershell
.\.venv\Scripts\uvicorn.exe garmin_hrr.api:app --reload --app-dir src
```
```powershell
# w drugim terminalu:
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/sync?limit=1"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/activities"
```

## Status implementacji (zgodnie z PLAN.md, sekcja 6)

- [x] 1. Szkielet projektu
- [x] 2. Logowanie do Garmin (`garmin_client.py`)
- [x] 3. Wyciąganie próbek tętna z wielu źródeł, z fallbackiem API -> TCX (`hr_extractor.py`, `sync.py`)
- [x] 4. Kalkulator HRR60 z testami (`hrr_calculator.py`)
- [x] 5. Storage SQLite (`storage.py`)
- [x] 6. Pełne API (`GET /activities`, `GET /activities/{id}/hrr60`, `POST /sync`)
- [ ] 7. Scheduler (automatyczne sprawdzanie nowych aktywności co N minut)
- [ ] 8. Discord notifier (opcjonalnie)
- [ ] 9. Frontend (opcjonalnie)

## Bezpieczeństwo

- Plik `.env` zawiera Twoje prawdziwe hasło do Garmin Connect - jest wpisany
  w `.gitignore` i **nigdy** nie trafi do repozytorium git.
- Token sesji Garmina (`data/.garth_session/`) też jest ignorowany przez git.
- Do commitowania trafia wyłącznie `.env.example` (szablon bez żadnych
  prawdziwych danych).
