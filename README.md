# GraminHRR60

Minimalna aplikacja pobiera treningi Garmin Connect z pliku JSON albo z adresu URL, wylicza HRR60 (spadek tętna 60 sekund po zakończeniu głównej sesji) i prezentuje wyniki na prostym dashboardzie webowym.

## Uruchomienie

```bash
npm install
npm start
```

Aplikacja startuje na `http://localhost:3000`.

## Konfiguracja źródła Garmin Connect

Domyślnie serwer czyta przykładowe dane z `/data/sample-garmin-connect.json`. Możesz podać własne źródło:

- `GARMIN_CONNECT_JSON_PATH` — ścieżka do pliku JSON z aktywnościami
- `GARMIN_CONNECT_JSON_URL` — URL zwracający JSON z aktywnościami Garmin Connect
- `GARMIN_CONNECT_BEARER_TOKEN` — opcjonalny token ****** zapytania HTTP
- `GARMIN_CONNECT_COOKIE` — opcjonalny nagłówek Cookie do zapytania HTTP
- `FETCH_INTERVAL_MS` — interwał automatycznego odświeżania (domyślnie 900000 ms)
- `PORT` — port HTTP serwera

Obsługiwany format danych:

```json
{
  "activities": [
    {
      "activityId": 1001,
      "activityName": "Bieg progowy",
      "startTimeLocal": "2026-09-18T18:00:00Z",
      "activityType": { "typeKey": "running" },
      "summary": { "mainSessionEndSec": 900 },
      "heartRateSamples": [
        { "timeSec": 900, "heartRate": 172 },
        { "timeSec": 960, "heartRate": 146 }
      ]
    }
  ]
}
```

`HRR60 = tętno na końcu głównej sesji - tętno po 60 sekundach`.

## Testy

```bash
npm test
```
