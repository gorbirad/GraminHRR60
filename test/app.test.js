import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { createApp } from '../src/app.js';

async function withServer(handler, callback) {
  const server = http.createServer(handler);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');

  try {
    const address = server.address();
    return await callback(`http://127.0.0.1:${address.port}`);
  } finally {
    server.close();
    await once(server, 'close');
  }
}

test('GET /api/results returns normalized HRR60 results', async () => {
  const app = createApp({
    env: { GARMIN_CONNECT_JSON_PATH: '/ignored.json' },
    readFileImpl: async (path) => {
      if (path === '/ignored.json') {
        return JSON.stringify({
          activities: [
            {
              activityId: 42,
              activityName: 'Test trening',
              startTimeLocal: '2026-09-01T10:00:00Z',
              activityType: { typeKey: 'running' },
              summary: { mainSessionEndSec: 120 },
              heartRateSamples: [
                { timeSec: 120, heartRate: 170 },
                { timeSec: 180, heartRate: 141 }
              ]
            }
          ]
        });
      }

      if (path.endsWith('/public/index.html')) {
        return '<!doctype html><title>ok</title>';
      }

      throw new Error(`unexpected path: ${path}`);
    }
  });

  await withServer(app.handler, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/results`);
    const payload = await response.json();

    assert.equal(response.status, 200);
    assert.equal(payload.results.length, 1);
    assert.equal(payload.results[0].hrr60, 29);
    assert.equal(payload.results[0].classification, 'dobry');
    assert.equal(payload.results[0].status, 'calculated');
  });
});

test('GET /health exposes degraded status when refresh fails', async () => {
  const app = createApp({
    env: { GARMIN_CONNECT_JSON_PATH: '/missing.json' },
    readFileImpl: async (path) => {
      if (path.endsWith('/public/index.html')) {
        return '<!doctype html><title>ok</title>';
      }

      throw new Error(`ENOENT: ${path}`);
    }
  });

  await app.refreshResults();

  await withServer(app.handler, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/health`);
    const payload = await response.json();

    assert.equal(response.status, 200);
    assert.equal(payload.status, 'degraded');
    assert.match(payload.error, /ENOENT/);
  });
});

test('POST /api/refresh clears stale results after a later refresh failure', async () => {
  let shouldFail = false;
  const app = createApp({
    env: { GARMIN_CONNECT_JSON_PATH: '/flaky.json' },
    readFileImpl: async (path) => {
      if (path.endsWith('/public/index.html')) {
        return '<!doctype html><title>ok</title>';
      }

      if (path === '/flaky.json' && !shouldFail) {
        return JSON.stringify({
          activities: [
            {
              activityId: 77,
              activityName: 'Stabilny trening',
              startTimeLocal: '2026-09-02T10:00:00Z',
              activityType: { typeKey: 'running' },
              summary: { mainSessionEndSec: 60 },
              heartRateSamples: [
                { timeSec: 60, heartRate: 150 },
                { timeSec: 120, heartRate: 120 }
              ]
            }
          ]
        });
      }

      throw new Error(`ENOENT: ${path}`);
    }
  });

  await withServer(app.handler, async (baseUrl) => {
    const firstResponse = await fetch(`${baseUrl}/api/results`);
    const firstPayload = await firstResponse.json();

    assert.equal(firstResponse.status, 200);
    assert.equal(firstPayload.results.length, 1);

    shouldFail = true;

    const refreshResponse = await fetch(`${baseUrl}/api/refresh`, { method: 'POST' });
    const refreshPayload = await refreshResponse.json();

    assert.equal(refreshResponse.status, 500);
    assert.equal(refreshPayload.results.length, 0);
    assert.equal(refreshPayload.source, null);

    const secondResponse = await fetch(`${baseUrl}/api/results`);
    const secondPayload = await secondResponse.json();

    assert.equal(secondResponse.status, 500);
    assert.equal(secondPayload.results.length, 0);
    assert.equal(secondPayload.source, null);
    assert.match(secondPayload.error, /ENOENT/);
  });
});
