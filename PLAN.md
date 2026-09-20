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

### 3a. Aktualizacja (2026-09-19): Wariant A był błędny w praktyce — teraz używamy Wariantu B

Po pierwszych testach na żywo (patrz `scripts/sync_last_activity.py`) okazało się,
że **Wariant A jest bez sensu jako domyślny**: "ostatnia próbka nagrania" z
definicji nigdy nie ma 60 sekund danych *po sobie* w tym samym pliku/nagraniu,
więc HRR60 zawsze kończyło się błędem `skipped_no_hr_data`.

Zweryfikowano na dwóch prawdziwych aktywnościach (interwały biegowe), pobierając
`GarminClient.get_activity_splits()` (endpoint `activity/{id}/splits`, pole
`lapDTOs`). Każdy lap ma pole `intensityType` z wartościami zaobserwowanymi:
`WARMUP`, `ACTIVE`, `RECOVERY`, `COOLDOWN`.

Przykład (aktywność 24396666364, 2026-09-17):

| lap | intensityType | start GMT | koniec GMT | czas trwania |
|---|---|---|---|---|
| 1 | WARMUP | 14:04:43 | 14:14:43 | 600s |
| 2 | ACTIVE | 14:14:43 | 14:16:43 | 120s |
| 3 | ACTIVE | 14:16:43 | 14:19:13 | 150s |
| 4 | ACTIVE | 14:19:13 | **14:21:13** | 120s |
| 5 | RECOVERY | 14:21:13 | 14:26:13 | 300s |
| 6 | COOLDOWN | 14:26:13 | 14:31:13 | 300s |
| 7 | COOLDOWN | 14:31:13 | 14:31:15 | 2.6s |

Koniec ostatniego lapa `ACTIVE` (14:21:13 GMT) to dokładnie 16:30 minut:sekund
liczone od startu treningu (14:04:43) — czyli dokładnie to, co użytkownik
zaobserwował ręcznie w aplikacji Garmin jako "koniec głównego treningu". Ten
sam wzorzec potwierdzono na drugiej aktywności (24408599358): ostatni lap
`ACTIVE` kończy się w 18:59 (~19:00) od startu.

**Nowa definicja domyślnego punktu odniesienia (t0):**
> Koniec ostatniego lapa z `intensityType` należącym do zbioru `{"ACTIVE", "INTERVAL"}`
> w `get_activity_splits()`. Jeśli żaden lap nie ma takiego oznaczenia (np.
> jednolapowe treningi siłowe — odrzucane i tak filtrem typu aktywności, patrz
> niżej), nie ma sygnału żeby wybrać wcześniejszy punkt niż koniec całego
> nagrania — wtedy zostajemy przy starym zachowaniu (koniec całej aktywności)
> i polegamy na fallbacku ciągłego, nadgarstkowego pomiaru tętna
> (`get_heart_rates(date)`), który dostarcza próbki *po* zakończeniu
> nagrywania aktywności.

### 3b. Aktualizacja (2026-09-19, po teście na 20 aktywnościach): `INTERVAL` obok `ACTIVE`

Test na 20 ostatnich aktywnościach (`scripts/inspect_recent_activities.py --limit 20`)
ujawnił, że **nie wszystkie biegi używają `intensityType: "ACTIVE"`**. Część
treningów interwałowych (np. id `24346992108`, `24345881015`, `24212509484`,
`24170780692`, `24169366286`) ma **wszystkie** lapy oznaczone jako `INTERVAL`,
bez żadnego `WARMUP`/`RECOVERY`/`COOLDOWN` na końcu. Reguła szukająca tylko
`ACTIVE` nie znajdowałaby w nich żadnego kandydata na t0.

**Poprawiona reguła:** t0 = koniec ostatniego lapa z `intensityType` w zbiorze
`{"ACTIVE", "INTERVAL"}` (obie wartości oznaczają realny wysiłek biegowy, w
odróżnieniu od `WARMUP`/`RECOVERY`/`COOLDOWN`).

**Ważna konsekwencja:** dla treningów, gdzie *wszystkie* lapy są `INTERVAL`
(brak `COOLDOWN` po nich), ostatni taki lap jest jednocześnie dosłownie
ostatnim lapem całej aktywności — więc **w samym nagraniu może zabraknąć 60s
danych po t0** (ten sam pierwotny problem co z Wariantem A). Dla tych
aktywności musi zadziałać fallback ciągłego pomiaru tętna z całego dnia
(`_extend_with_continuous_heart_rate` w `sync.py`, już zaimplementowany).
Innymi słowy: poprawka punktu t0 i fallback ciągłego tętna są **komplementarne
i oba potrzebne** - nie jest tak, że jedno zastępuje drugie.

Inne obserwacje z tego testu, potwierdzające potrzebę filtrowania po typie
aktywności (patrz sekcja poniżej): w 20 ostatnich aktywnościach wystąpiły też
`walking`, `strength_training` (1 lap, brak intensityType), `breathwork`
(77 lapów `WARMUP/INTERVAL/RECOVERY` - to trening oddechowy, nie bieg) oraz
`cycling` (2 auto-lapy `ACTIVE,ACTIVE` bez struktury interwałowej) - wszystkie
te typy mają zostać odrzucone przez filtr `activityType.typeKey`.

**Dodatkowy wymóg:** synchronizować tylko aktywności biegowe
(`activityType.typeKey` z listy dozwolonych, np. `running`, `trail_running`,
`treadmill_running`, `track_running`) — inne typy (np. `walking`) mają być
pomijane ze statusem `skipped_not_running`.

Szczegółowy plan implementacji tej zmiany: patrz commit/PR opisujący
"Poprawne wyznaczanie końca głównej sesji + filtr typu aktywności" oraz sekcja
"Status" w [README.md](./README.md).

### 3c. Aktualizacja (2026-09-19, weryfikacja na 5 aktywnościach): `intensityType`
z `get_activity_splits` jest MYLĄCE — trzeba użyć `get_activity_typed_splits`

Dogłębna weryfikacja na 5 konkretnych aktywnościach (2 wyścigi + 3 treningi
interwałowe), z ręcznie podanymi przez użytkownika czasami zakończenia
"ostatniego interwału", ujawniła, że pole `intensityType` z
`get_activity_splits` (`lapDTOs`) jest w treningach interwałowych **zawsze
równe `"INTERVAL"`** dla każdego lapa — nie rozróżnia ono w ogóle
rozgrzewki/pracy/regeneracji/schładzania. Reguła z sekcji 3b ("ostatni lap
ACTIVE/INTERVAL") w efekcie wskazywała **dosłownie ostatni lap całej
aktywności**, co w 2 z 3 przypadków testowych było błędne (prawdziwy koniec
treningu był wcześniej, przed dodatkowym lapem "cooldown"/"schładzanie").

**Prawdziwa struktura treningu jest dostępna w innym endpoincie:**
`GarminClient.get_activity_typed_splits(activity_id)` (`api.get_activity_typed_splits`)
zwraca `{"splits": [...]}`, gdzie każdy segment ma pole `type` z realnymi
wartościami: `INTERVAL_WARMUP`, `INTERVAL_ACTIVE`, `INTERVAL_RECOVERY`,
`INTERVAL_COOLDOWN` — dokładnie zgodnymi z etykietami pokazywanymi w UI
Garmin Connect (np. "Bieg" = `INTERVAL_ACTIVE`, "Schładzanie" =
`INTERVAL_COOLDOWN`). Ta sama odpowiedź zawiera też **równolegle** segmenty
typu `RWD_RUN`/`RWD_WALK` (detekcja bieg/marsz) — te trzeba **zignorować**
(filtrować tylko `type` zaczynające się od `"INTERVAL_"`).

**Poprawiona (finalna) reguła:** t0 = pole `endTimeGMT` ostatniego segmentu
z `type == "INTERVAL_ACTIVE"` (po przefiltrowaniu tylko `INTERVAL_*` i
posortowaniu po `startTimeGMT`). Jeśli żaden segment nie ma tego typu (np.
wyścig — patrz niżej), t0 = koniec ostatniego segmentu `INTERVAL_*` (czyli
koniec całego nagrania), co ponownie wymaga fallbacku ciągłego tętna z całego
dnia.

**Weryfikacja matematyczna (100% zgodności na 3 aktywnościach):** użytkownik
podawał czasy "ostatniego interwału" odczytane z tabeli interwałów w Garmin
Connect. Okazało się, że te czasy to **suma skumulowana pola `duration`**
(czas aktywny/w ruchu, pomijający pauzy/przerwy w GPS), a NIE rzeczywisty
czas zegarowy liczony od `startTimeGMT` pierwszego lapa (który uwzględnia
ewentualne pauzy). Przykład (aktywność `24345881015`, gdzie rozgrzewka miała
ok. 3,5-minutową pauzę niewidoczną w `duration`):

| segment | `duration` [s] | suma skumulowana | zgadza się z UI? |
|---|---|---|---|
| WARMUP | 687.0 | 11:27.0 | ✅ ("rozgrzewka 11:27") |
| ACTIVE | 27.6 | 11:54.6 | ✅ ("1 bieg 11:55") |
| RECOVERY | 58.7 | 12:53.2 | ✅ ("regeneracja 12:53") |
| ACTIVE | 27.6 | 13:20.8 | ✅ ("2 bieg 13:21") |
| RECOVERY | 56.2 | 14:17.0 | ✅ ("regeneracja 14:17") |
| ACTIVE | 40.1 | **14:57.1** | ✅ ("3 bieg 14:57" — ostatni ACTIVE) |
| COOLDOWN | 31.1 | 15:28.2 | ✅ ("regeneracja 15:28") |

Analogiczna zgodność (co do sekundy) potwierdzona też dla `24169366286`
(9:07.45 vs. zgłoszone 9:07.5) i `24212509484` (35:26.34 vs. zgłoszone
35:26). **Ważne:** ta suma skumulowana (`duration`) służy wyłącznie do
weryfikacji "czy trafiliśmy we właściwy segment" (porównanie z UI) — do
faktycznego wyznaczenia t0 (rzeczywistego znacznika czasu potrzebnego do
interpolacji tętna) używamy pola `endTimeGMT` danego segmentu, NIE sumy
`duration`.

**Wyścigi (`eventTypeDTO.typeKey == "race"`)** — potwierdzone automatyczne
wykrywanie: pole `eventTypeDTO` w `get_activity_summary()` zawiera
`{"typeKey": "race"}` dla wyścigów i `{"typeKey": "training"}` dla zwykłych
treningów. Dla obu przetestowanych wyścigów (`24346992108`, `24170780692`)
wszystkie segmenty to `INTERVAL_ACTIVE` (brak osobnej rozgrzewki/schładzania
w strukturze), a ostatni z nich kończy się dokładnie na końcu całego
nagrania — więc dla wyścigów fallback ciągłego tętna z całego dnia pozostaje
konieczny (tak jak przewidziano w sekcji 3b).

Narzędzie `scripts/inspect_activity.py` zostało rozszerzone o sekcję
"Segmenty INTERVAL_* (z get_activity_typed_splits)", pokazującą oba
"zegary" (skumulowany `duration` oraz realny `endTimeGMT`) dla każdego
segmentu, wraz z automatycznym wskazaniem t0.

### 3d. Aktualizacja (2026-09-19, weryfikacja na 4 kolejnych aktywnościach):
dwa nowe przypadki brzegowe

Sprawdzono kolejne 4 aktywności (`22442246446`, `23651454079`, `24424012437`,
`24236535226`), co potwierdziło regułę z sekcji 3c i ujawniło **dwa nowe
przypadki brzegowe**, których wcześniejsza próbka nie obejmowała:

**Przypadek A — biegi bez żadnej struktury interwałowej** (`22442246446`:
krótki bieg na bieżni, 6:19 min; `23651454079`: długi bieg, 143:30 min).
`get_activity_typed_splits` zwraca dla nich **dokładnie jeden** segment
`INTERVAL_ACTIVE`, obejmujący całą aktywność od startu do końca. To
poprawnie wskazuje t0 = koniec całego nagrania (co jest tu prawidłowe — nie
ma żadnego wydzielonego "schładzania" do pominięcia). Ważna konsekwencja:
tak jak w "czystych INTERVAL" z sekcji 3b, prawdopodobnie zabraknie 60s
danych w samym nagraniu → fallback ciągłego tętna z całego dnia będzie
potrzebny.

**Przypadek B — wyścig z auto-lapami/PacePro, BEZ segmentów `INTERVAL_*`
w ogóle** (`24424012437`, świeży wyścig z dnia sprawdzenia). Ma 22 surowe
lapy (`intensityType: "ACTIVE"`, automatyczne co ~5 min), ale
`get_activity_typed_splits` zwraca dla niej **wyłącznie** segmenty typu
`RWD_RUN` i `PACE_PRO_SPLIT` — **zero** segmentów `INTERVAL_*`. Oznacza to,
że reguła "filtruj po `INTERVAL_*`" może nie mieć żadnego kandydata — trzeba
dodać **fallback drugiego poziomu**: gdy `get_activity_typed_splits` nie
zwróci żadnego segmentu `INTERVAL_*`, wyznacz t0 z surowych `lapDTOs`
(`get_activity_splits`) jako koniec ostatniego lapa z `intensityType` w
`{"ACTIVE", "INTERVAL"}` (reguła z sekcji 3b) — w tym przypadku wskazałoby
to koniec ostatniego (22.) lapa, czyli de facto koniec całego nagrania.

**Kluczowe potwierdzenie użytkownika:** dla tej aktywności (wyścig) t0
wypada na końcu nagrania, i - zgodnie z wcześniejszymi ustaleniami dla
wyścigów - **tętno regeneracyjne po wyścigu ma być pobierane spoza samego
nagrania aktywności** (z ciągłego pomiaru dobowego). To potwierdza, że dla
aktywności z `eventTypeDTO.typeKey == "race"` fallback ciągłego tętna
dobowego nie jest jedynie "awaryjnym planem B na wypadek błędu obliczeń",
lecz **zamierzonym, głównym mechanizmem** pozyskania danych po zakończeniu
wyścigu (bo nagranie kończy się dokładnie na mecie/finiszu, bez żadnego
"ogona" na wybieganie).

Aktywność `24236535226` (złożony trening z podwójną strukturą
rozgrzewka→interwały→rozgrzewka→interwały→schładzanie) dodatkowo
zweryfikowała regułę na bardziej skomplikowanym przypadku: t0 poprawnie
wypadło na końcu OSTATNIEGO `INTERVAL_ACTIVE` (47:52.68 / 14:50:00 GMT),
wyraźnie wcześniej niż koniec całego nagrania (58:08.56 / 15:00:17 GMT).

**Ostateczna, w pełni zweryfikowana reguła wyznaczania t0** (do
implementacji):
1. Pobierz `get_activity_typed_splits()`, przefiltruj tylko segmenty z
   `type` zaczynającym się od `"INTERVAL_"`, posortuj po `startTimeGMT`.
2. Jeśli istnieje co najmniej jeden segment `INTERVAL_ACTIVE` → t0 =
   `endTimeGMT` ostatniego z nich.
3. W przeciwnym razie (brak jakichkolwiek segmentów `INTERVAL_*`, np.
   Przypadek B) → wyznacz t0 z surowych `lapDTOs`
   (`get_activity_splits()`) jako koniec ostatniego lapa z `intensityType`
   w `{"ACTIVE", "INTERVAL"}`.
4. W przeciwnym razie (brak jakichkolwiek użytecznych danych o lapach) →
   t0 = koniec całego nagrania (ostatnia próbka tętna), tak jak dotychczas.
5. Niezależnie od powyższego: jeśli w samym nagraniu brakuje 60s danych po
   t0 (co jest NORMĄ dla wyścigów i częste dla "czystych interwałowych"/
   niestrukturyzowanych biegów) → użyj fallbacku
   `_extend_with_continuous_heart_rate` (już zaimplementowany w
   `sync.py`), łączącego dane z ciągłego pomiaru dobowego tętna.

### 3e. Aktualizacja (implementacja reguły 3d — zakończona)

Powyższa, w pełni zweryfikowana reguła została wdrożona:

- **`src/garmin_hrr/intervals.py`** (nowy moduł) — implementuje kroki 1-4
  reguły z sekcji 3d jako `determine_main_session_end(client, activity_id)`.
  Zwraca `datetime` (UTC) albo `None`, gdy nie da się wyznaczyć t0 z danych o
  lapach (wtedy wywołujący spada do historycznego zachowania: koniec
  nagrania). Wewnętrzne błędy API (`get_activity_typed_splits`/
  `get_activity_splits`) są przechwytywane i logowane, nie przerywają
  synchronizacji pozostałych aktywności.
- **`src/garmin_hrr/hrr_calculator.py`** — `compute_hrr60()` przyjmuje teraz
  opcjonalny `reference_time: datetime` (obok istniejącego
  `reference_index`). Tętno w t0 jest wtedy interpolowane liniowo tak samo
  jak w t1 (bo granica lapa rzadko trafia dokładnie w próbkę tętna).
  `HRRResult.hr_at_t0` zmieniło typ z `int` na `float` (interpolacja może
  zwrócić wartość niecałkowitą).
- **`src/garmin_hrr/sync.py`** — `sync_activity()`:
  - filtruje aktywności po `activityType.typeKey` (`RUNNING_ACTIVITY_TYPES`:
    `running`, `trail_running`, `track_running`, `treadmill_running`) —
    aktywności innych typów (np. chodzenie) dostają nowy status
    `skipped_not_running` i nie są dalej przetwarzane (punkt z sekcji 3b,
    krok 5 opisu implementacji);
  - wyznacza t0 przez `intervals.determine_main_session_end()` zamiast
    zawsze brać ostatnią próbkę nagrania; jeśli funkcja zwróci `None`,
    używa historycznego fallbacku (`reference_index` = ostatnia próbka);
  - punkt 5 z reguły (dociąganie ciągłego tętna dobowego, gdy w nagraniu
    brakuje 60s po t0) pozostaje bez zmian koncepcyjnych, tylko
    wyodrębniony do wspólnej funkcji `_compute_hrr60_with_fallback()`
    używanej niezależnie od tego, czy t0 pochodzi z lapów, czy jest końcem
    nagrania.
- Testy jednostkowe: `tests/test_intervals.py` (wszystkie warianty reguły —
  typed splits z aktywnym segmentem, brak segmentów `INTERVAL_*` z
  fallbackiem do raw laps, brak jakichkolwiek użytecznych danych, błędy API),
  `tests/test_sync.py` (filtr typów aktywności, fallback ciągłego tętna),
  rozszerzony `tests/test_hrr_calculator.py` (interpolacja HR w `t0` przy
  `reference_time`). `pytest` → 27/27 zielone.

Celowo NIE zaimplementowano jawnego sprawdzania `eventTypeDTO.typeKey ==
"race"` — okazało się niepotrzebne: reguła 3d + istniejący fallback
ciągłego tętna dobowego (krok 5) obsługują wyścigi automatycznie (t0 wypada
na końcu nagrania, więc fallback włącza się sam, tak jak dla zwykłych,
niestrukturyzowanych biegów).

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

