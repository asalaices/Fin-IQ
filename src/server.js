import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { analyze, ValidationError } from './analysis.js';

const MAX_BODY_BYTES = 1_048_576;

function respond(response, status, body) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  response.end(JSON.stringify(body));
}

export function createServer() {
  return http.createServer({ requestTimeout: 15_000 }, (request, response) => {
    if (request.method === 'GET' && request.url === '/health') {
      respond(response, 200, { status: 'ok' });
      request.resume();
      return;
    }
    if (request.url !== '/analysis') {
      respond(response, 404, { error: 'Not found' });
      request.resume();
      return;
    }
    if (request.method !== 'POST') {
      response.setHeader('Allow', 'POST');
      respond(response, 405, { error: 'Use POST for /analysis' });
      request.resume();
      return;
    }
    if (request.headers['content-type']?.split(';')[0].trim().toLowerCase() !== 'application/json') {
      respond(response, 415, { error: 'Content-Type must be application/json' });
      request.resume();
      return;
    }
    let bytes = 0;
    let chunks = [];
    let rejected = false;
    request.on('data', chunk => {
      if (rejected) return;
      bytes += chunk.length;
      if (bytes > MAX_BODY_BYTES) {
        rejected = true;
        chunks = [];
        respond(response, 413, { error: 'Request body exceeds 1 MiB' });
        return;
      }
      chunks.push(chunk);
    });
    request.on('error', () => {
      rejected = true;
      chunks = [];
      if (!response.headersSent) respond(response, 400, { error: 'Unable to read request' });
    });
    request.on('end', () => {
      if (rejected) return;
      try {
        const result = analyze(JSON.parse(Buffer.concat(chunks).toString('utf8')));
        respond(response, 200, result);
      } catch (error) {
        if (error instanceof SyntaxError) {
          respond(response, 400, { error: 'Request body must be valid JSON' });
        } else if (error instanceof ValidationError) {
          respond(response, 400, { error: error.message });
        } else {
          respond(response, 500, { error: 'Analysis failed' });
        }
      }
    });
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.PORT ?? 3000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('PORT must be an integer between 1 and 65535');
  }
  createServer().listen(port, '127.0.0.1', () => {
    console.log(`Fin-IQ listening on http://127.0.0.1:${port}`);
  });
}
