import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const DEFAULT_SAMPLE_PATH = fileURLToPath(new URL('../data/sample-garmin-connect.json', import.meta.url));

function extractActivities(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload?.activities)) {
    return payload.activities;
  }

  throw new Error('Niepoprawny format danych Garmin Connect. Oczekiwano tablicy lub pola activities.');
}

export async function loadGarminActivities({
  env = process.env,
  fetchImpl = globalThis.fetch,
  readFileImpl = readFile
} = {}) {
  const url = env.GARMIN_CONNECT_JSON_URL;

  if (url) {
    if (typeof fetchImpl !== 'function') {
      throw new Error('Brak implementacji fetch dla źródła Garmin Connect skonfigurowanego przez URL.');
    }

    const headers = { accept: 'application/json' };

    if (env.GARMIN_CONNECT_BEARER_TOKEN) {
      headers.authorization = ['Bearer', env.GARMIN_CONNECT_BEARER_TOKEN].join(' ');
    }

    if (env.GARMIN_CONNECT_COOKIE) {
      headers.cookie = env.GARMIN_CONNECT_COOKIE;
    }

    const response = await fetchImpl(url, { headers });

    if (!response.ok) {
      throw new Error(`Nie udało się pobrać danych Garmin Connect (${response.status})`);
    }

    return {
      source: url,
      activities: extractActivities(await response.json())
    };
  }

  const filePath = env.GARMIN_CONNECT_JSON_PATH ?? DEFAULT_SAMPLE_PATH;
  const payload = JSON.parse(await readFileImpl(filePath, 'utf8'));

  return {
    source: filePath,
    activities: extractActivities(payload)
  };
}
