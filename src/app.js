import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { normalizeGarminActivity } from './garmin.js';
import { loadGarminActivities } from './source.js';

const DASHBOARD_PATH = fileURLToPath(new URL('../public/index.html', import.meta.url));

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, { 'content-type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify(payload));
}

export function createApp({
  env = process.env,
  fetchImpl = globalThis.fetch,
  readFileImpl = readFile,
  clock = () => new Date().toISOString()
} = {}) {
  const state = {
    results: [],
    source: null,
    refreshedAt: null,
    lastError: null
  };

  let refreshPromise = null;
  let intervalHandle = null;

  async function refreshResults() {
    if (refreshPromise) {
      return refreshPromise;
    }

    refreshPromise = (async () => {
      try {
        const { activities, source } = await loadGarminActivities({ env, fetchImpl, readFileImpl });
        state.results = activities
          .map(normalizeGarminActivity)
          .sort((left, right) => String(right.startTime ?? '').localeCompare(String(left.startTime ?? '')));
        state.source = source;
        state.refreshedAt = clock();
        state.lastError = null;
      } catch (error) {
        state.results = [];
        state.source = null;
        state.refreshedAt = clock();
        state.lastError = error.message;
      } finally {
        refreshPromise = null;
      }

      return state;
    })();

    return refreshPromise;
  }

  async function serveDashboard(response) {
    const html = await readFileImpl(DASHBOARD_PATH, 'utf8');
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end(html);
  }

  async function handler(request, response) {
    const url = new URL(request.url, `http://${request.headers.host ?? 'localhost'}`);

    if (request.method === 'GET' && url.pathname === '/') {
      return serveDashboard(response);
    }

    if (request.method === 'GET' && url.pathname === '/health') {
      return sendJson(response, 200, {
        status: state.lastError ? 'degraded' : 'ok',
        results: state.results.length,
        refreshedAt: state.refreshedAt,
        error: state.lastError
      });
    }

    if (request.method === 'GET' && url.pathname === '/api/results') {
      if (!state.refreshedAt) {
        await refreshResults();
      }

      return sendJson(response, state.lastError ? 500 : 200, {
        source: state.source,
        refreshedAt: state.refreshedAt,
        error: state.lastError,
        results: state.results
      });
    }

    if (request.method === 'POST' && url.pathname === '/api/refresh') {
      await refreshResults();

      return sendJson(response, state.lastError ? 500 : 200, {
        source: state.source,
        refreshedAt: state.refreshedAt,
        error: state.lastError,
        results: state.results
      });
    }

    sendJson(response, 404, { error: 'Not found' });
  }

  function startAutoRefresh() {
    stopAutoRefresh();
    const intervalMs = Number.parseInt(env.FETCH_INTERVAL_MS ?? '900000', 10);

    if (Number.isFinite(intervalMs) && intervalMs > 0) {
      intervalHandle = setInterval(() => {
        refreshResults().catch(() => {});
      }, intervalMs);
    }
  }

  function stopAutoRefresh() {
    if (intervalHandle) {
      clearInterval(intervalHandle);
      intervalHandle = null;
    }
  }

  return { handler, refreshResults, startAutoRefresh, stopAutoRefresh, state };
}
