# Plan projektu: Garmin HRR60 Tracker

Cel: automatyczne pobieranie treningów z Garmin Connect, wyliczanie spadku tętna
60 sekund po zakończeniu głównej sesji treningowej (Heart Rate Recovery, HRR60)
i prezentacja wyników (strona web / dashboard, opcjonalnie powiadomienia na Discord).

Ten dokument zbiera wnioski z rozmowy w [info1.md](./info1.md) i doprecyzowuje je
w konkretny, wykonalny plan pracy.

---

## 1. Kluczowa zmiana względem pierwotnego pomysłu: sposób logowania do Garmina

W `info1.md` opisano podejście "ręczne cookies + CSRF + endpointy `/gc-api/...`".
Działa, ale jest kruche (Garmin zmienia endpointy, tokeny wygasają, trzeba ręcznie
wyciągać cookies z przeglądarki za każdym razem).

**Rekomendacja:** użyć biblioteki [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
(oparta o `garth`), która:
- obsługuje pełne logowanie (login/hasło, MFA/2FA),
- sama zarządza tokenami OAuth1/OAuth2 i ich odświeżaniem,
- zapisuje sesję na dysku (`~/.garth` lub własna ścieżka) — logujesz się raz,
  kolejne uruchomienia programu używają zapisanego tokenu,
- ma gotowe metody, m.in.:
  - `get_activities(start, limit)` – lista treningów,
  - `download_activity(activity_id, dl_fmt=...)` – pobranie TCX/GPX/FIT/oryginału,
  - `get_activity_details(activity_id)` – **surowe próbki danych aktywności
    (w tym tętno w czasie) bezpośrednio z API, bez parsowania pliku TCX/FIT**,
  - `get_activity_hr_in_timezones(...)`, `get_heart_rates(date)` – dane tętna.

Dzięki temu nie musimy w ogóle parsować TCX/FIT ręcznie (choć jako fallback/backup
warto też pobierać i archiwizować oryginalny plik FIT/TCX).

To skraca i stabilizuje całą "Opcję A" z `info1.md`.

## 2. Wybór języka: Python (potwierdzenie wcześniejszej rekomendacji)

Zgadzam się z wnioskiem z rozmowy: **Python na backendzie**, ponieważ:
- `garminconnect`/`garth` istnieją tylko w Pythonie,
- łatwa analiza szeregów czasowych tętna (proste porównania czasowe, bez pandas
  nawet nie jest to konieczne przy tej skali danych),
- FastAPI daje gotowe REST API dla frontendu bez dodatkowego boilerplate'u.

Frontend (jeśli/gdy powstanie) może być prostym HTML+JS (Jinja2 + Chart.js) albo
osobnym SPA — to nie wpływa na backend, więc decyzję można podjąć później.

## 3. Definicja "koniec głównej sesji treningu" (do ustalenia z Tobą, patrz pytania niżej)

Trzy warianty, każdy da się zaimplementować, różnią się dokładnością:

| Wariant | Opis | Kiedy dobry |
|---|---|---|
| A. Koniec całej aktywności | ostatnia próbka tętna z całej aktywności | proste treningi bez rozgrzewki/schłodzenia po zakończeniu |
| B. Koniec ostatniego "lapa"/interwału głównego | timestamp końca wskazanego lapa (np. przedostatni lap, jeśli ostatni to "cooldown") | treningi z podziałem na lapy (interwały, cool-down jako osobny lap) |
| C. Ręczny wybór minuty | użytkownik/algorytm wskazuje minutę treningu (np. koniec najintensywniejszego fragmentu po tętnie/tempie) | treningi bez wyraźnej struktury lapów |

Domyślnie proponuję zacząć od **wariantu A** (najprostszy, w pełni automatyczny),
z możliwością ręcznego wskazania innego punktu (wariant C) w interfejsie później,
i dodania wariantu B jeśli dane z lapów są dostępne w API.

## 4. Algorytm HRR60 (bez zmian koncepcyjnych względem info1.md)

1. Pobierz próbki tętna z `get_activity_details()` (lista `{timestamp, heartRate}`).
2. `t0` = timestamp punktu odniesienia (patrz pkt 3).
3. `hr0` = tętno w `t0`.
4. `t1 = t0 + 60s`.
5. Znajdź próbkę najbliższą `t1` (interpolacja liniowa między dwoma najbliższymi
   próbkami, jeśli częstotliwość próbkowania > 1s — Garmin zwykle próbkuje HR co
   kilka sekund, więc interpolacja daje dokładniejszy wynik niż "najbliższy punkt").
6. `hrr60 = hr0 - hr1`.
7. Zapisz wynik + metadane (data, typ treningu, czas trwania, hr0, hr1, hrr60).

## 5. Architektura docelowa

```
Garmin/
├── PLAN.md                  <- ten plik
├── info1.md                 <- wstępna rozmowa/notatki
├── pyproject.toml / requirements.txt
├── .env.example              (dane logowania Garmin - NIGDY w repo jako sekrety)
├── src/
│   └── garmin_hrr/
│       ├── __init__.py
│       ├── config.py          # wczytywanie ustawień/.env
│       ├── garmin_client.py   # logowanie + pobieranie aktywności (garminconnect)
│       ├── hr_extractor.py    # wyciąganie próbek tętna z odpowiedzi API/TCX
│       ├── hrr_calculator.py  # logika HRR60 (punkt odniesienia + interpolacja)
│       ├── storage.py         # zapis wyników (SQLite na start)
│       ├── discord_notifier.py# (opcjonalnie) wysyłka embed/wyniku na Discord
│       ├── api.py             # FastAPI: GET /activities, GET /activities/{id}/hrr60
│       └── scheduler.py       # okresowe sprawdzanie nowych aktywności (APScheduler)
├── data/
│   └── hrr.db                 # baza SQLite (gitignore)
├── tests/
│   └── test_hrr_calculator.py # testy jednostkowe na przykładowych danych
└── README.md
```

## 6. Etapy prac (kolejność realizacji)

1. **Szkielet projektu** – struktura folderów, `requirements.txt`, `.gitignore`,
   `.env.example`.
2. **Logowanie do Garmin** (`garmin_client.py`) – jednorazowe logowanie, zapis
   sesji tokenów, funkcja `list_new_activities(since)`.
3. **Pobieranie danych tętna** (`hr_extractor.py`) – najpierw przez
   `get_activity_details`, z fallbackiem do pobrania i sparsowania TCX
   (`download_activity(..., dl_fmt="TCX")`), gdyby API nie zwracało HR dla
   danego typu aktywności.
4. **Kalkulator HRR60** (`hrr_calculator.py`) – z testami jednostkowymi na
   ręcznie przygotowanych/przykładowych danych (nie wymaga logowania do Garmina
   do testowania!).
5. **Storage** – SQLite (najprostsze na start, łatwe do przeniesienia na
   PostgreSQL później).
6. **API (FastAPI)** – `GET /activities`, `GET /activities/{id}/hrr60`,
   `POST /sync` (ręczne wywołanie synchronizacji).
7. **Scheduler** – automatyczne sprawdzanie nowych aktywności co N minut.
8. **(Opcjonalnie) Discord notifier** – wysyłka embeda z wynikiem HRR60 po
   każdej nowej aktywności.
9. **(Opcjonalnie) Prosty frontend** – lista treningów + wykres tętna z
   zaznaczonym punktem `t0`/`t0+60s`.

## 7. Bezpieczeństwo i dane wrażliwe

- Dane logowania Garmin (login/hasło) trzymane wyłącznie w `.env` (dodane do
  `.gitignore`), nigdy nie trafiają do repo ani do Discorda.
- Token sesji `garth` zapisywany lokalnie (np. `data/.garth_session/`),
  również w `.gitignore`.
- Jeśli w przyszłości pojawi się frontend dostępny w sieci — dodać
  uwierzytelnianie dostępu do dashboardu (to nie jest publiczna usługa dla
  wielu użytkowników, tylko Twój prywatny panel).

## 8. Otwarte pytania do ustalenia przed startem implementacji

Patrz wiadomość czatu — zadam je jako osobne pytania, żeby ustalić:
- czy zaczynamy scaffolding kodu już teraz, czy plan ma na razie zostać sam,
- który wariant punktu odniesienia (A/B/C z pkt 3) na start,
- czy Discord jest potrzebny od razu, czy to etap "later",
- czy backend ma działać lokalnie (Twój komputer) czy docelowo na serwerze/VPS
  (wpływa na wybór schedulera i sposobu przechowywania sesji).

