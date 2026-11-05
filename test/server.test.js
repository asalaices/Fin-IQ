import assert from 'node:assert/strict';
import { once } from 'node:events';
import test from 'node:test';
import { createServer } from '../src/server.js';

async function serve(t) {
  const server = createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise((resolve, reject) => {
    server.close(error => error ? reject(error) : resolve());
    server.closeAllConnections();
  }));
  return `http://127.0.0.1:${server.address().port}`;
}

test('health endpoint and analysis API work over HTTP', async t => {
  const url = await serve(t);
  const health = await fetch(`${url}/health`);
  assert.equal(health.status, 200);
  assert.deepEqual(await health.json(), { status: 'ok' });
  const response = await fetch(`${url}/analysis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({
      openingBalanceCents: 1000,
      periodStart: '2026-01-01',
      periodEnd: '2026-01-31',
      transactions: [],
    }),
  });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal((await response.json()).outlook.projectedBalanceCents, 1000);
});

test('API returns useful errors for invalid requests', async t => {
  const url = await serve(t);
  for (const [path, options, status] of [
    ['/missing', {}, 404],
    ['/analysis', {}, 405],
    ['/analysis', { method: 'POST', body: '{}' }, 415],
    ['/analysis', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{',
    }, 400],
    ['/analysis', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    }, 400],
    ['/analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: ' '.repeat(1_048_577),
    }, 413],
  ]) {
    const response = await fetch(`${url}${path}`, options);
    assert.equal(response.status, status);
    assert.equal(typeof (await response.json()).error, 'string');
    if (status === 405) assert.equal(response.headers.get('allow'), 'POST');
  }
});
