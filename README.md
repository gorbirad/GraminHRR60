# Garmin HRR60 Tracker

Automatyczne pobieranie treningów z Garmin Connect i wyliczanie **HRR60**
(Heart Rate Recovery 60s) - spadku tętna 60 sekund po zakończeniu głównej
sesji treningowej.

Pełny plan projektu: [PLAN.md](./PLAN.md).
Historia decyzji projektowych (rozmowa wstępna): [info1.md](./info1.md).

## Struktura projektu

```
Garmin/
├── PLAN.md                      # plan projektu i architektura
├── info1.md                     # notatki z wstępnej analizy
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
│   └── api.py                   # FastAPI: GET /activities, GET /activities/{id}/hrr60
├── data/                        # baza SQLite + pobrane pliki (gitignored)
└── tests/
    └── test_hrr_calculator.py   # testy logiki HRR60 (nie wymagają logowania)
```

## Szybki start

1. Zainstaluj zależności:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Uzupełnij plik `.env` swoimi danymi logowania do Garmin Connect
   (skopiuj `.env.example`, jeśli `.env` nie istnieje).
3. Uruchom testy (nie wymagają połączenia z Garminem):
   ```powershell
   pytest
   ```
4. Uruchom API (na razie tylko odczyt zapisanych wyników - synchronizacja
   z Garmin Connect jest w trakcie implementacji, patrz `PLAN.md`):
   ```powershell
   uvicorn garmin_hrr.api:app --reload --app-dir src
   ```

## Status implementacji (zgodnie z PLAN.md, sekcja 6)

- [x] 1. Szkielet projektu
- [x] 2. Logowanie do Garmin (`garmin_client.py`) - podstawowa wersja
- [x] 3. Wyciąganie próbek tętna z wielu źródeł (`hr_extractor.py`)
- [x] 4. Kalkulator HRR60 z testami (`hrr_calculator.py`)
- [x] 5. Storage SQLite (`storage.py`)
- [ ] 6. Pełne API (na razie tylko odczyt, `POST /sync` jest placeholderem)
- [ ] 7. Scheduler (automatyczne sprawdzanie nowych aktywności)
- [ ] 8. Discord notifier (opcjonalnie)
- [ ] 9. Frontend (opcjonalnie)

## Bezpieczeństwo

- Plik `.env` zawiera Twoje prawdziwe hasło do Garmin Connect - jest wpisany
  w `.gitignore` i **nigdy** nie trafi do repozytorium git.
- Token sesji Garmina (`data/.garth_session/`) też jest ignorowany przez git.
- Do commitowania trafia wyłącznie `.env.example` (szablon bez żadnych
  prawdziwych danych).
