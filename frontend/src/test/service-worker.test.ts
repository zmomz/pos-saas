import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// ISSUE-2 (deploy hygiene) — pin the app-shell service worker's caching
// STRATEGY so a future edit can't silently regress it back to the stale-shell
// pinning that trapped returning browsers on an old index.html:
//   * HTML navigations  -> NETWORK-FIRST (fresh deploy served immediately; cache
//     is only the offline fallback).
//   * hashed /assets/*  -> CACHE-FIRST (content-hashed + immutable).
//   * /api/* and non-GET -> never intercepted (straight to the network).
//
// The worker is plain browser JS (not a module), so we execute its source in a
// synthetic ServiceWorkerGlobalScope, capture its `fetch` handler, and drive
// synthetic FetchEvents through it — asserting which of {network, cache} is
// consulted first for each request kind.

const SW_SRC = readFileSync(
  path.resolve(__dirname, '../../public/sw.js'),
  'utf8'
);

type Handler = (event: unknown) => void;

interface Harness {
  listeners: Record<string, Handler>;
  fetchMock: ReturnType<typeof vi.fn>;
  cachesMock: {
    open: ReturnType<typeof vi.fn>;
    match: ReturnType<typeof vi.fn>;
    keys: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
  cachePut: ReturnType<typeof vi.fn>;
}

function loadWorker(): Harness {
  const listeners: Record<string, Handler> = {};
  const fetchMock = vi.fn();
  const cachePut = vi.fn(async () => undefined);
  const cachesMock = {
    open: vi.fn(async () => ({ put: cachePut, addAll: vi.fn(async () => undefined) })),
    match: vi.fn(async () => undefined),
    keys: vi.fn(async () => []),
    delete: vi.fn(async () => true),
  };
  const self = {
    addEventListener: (type: string, cb: Handler) => {
      listeners[type] = cb;
    },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  };

  // Free identifiers in sw.js (self/caches/fetch/URL) resolve to these params.
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  const run = new Function('self', 'caches', 'fetch', 'URL', SW_SRC);
  run(self, cachesMock, fetchMock, URL);

  return { listeners, fetchMock, cachesMock, cachePut };
}

/** Fire the captured fetch handler and return the promise it responded with
 *  (or the sentinel PASS_THROUGH when it declined to intercept). */
const PASS_THROUGH = Symbol('pass-through');
function dispatchFetch(h: Harness, request: unknown): Promise<unknown> | typeof PASS_THROUGH {
  let responded: Promise<unknown> | typeof PASS_THROUGH = PASS_THROUGH;
  h.listeners.fetch({
    request,
    respondWith: (p: Promise<unknown>) => {
      responded = p;
    },
  });
  return responded;
}

function req(url: string, { mode = 'cors', accept = '', method = 'GET' } = {}) {
  return {
    url,
    method,
    mode,
    headers: { get: (k: string) => (k.toLowerCase() === 'accept' ? accept : null) },
  };
}

/** A network Response the worker considers cacheable (200 + basic). */
function netResponse(tag: string) {
  const resp: Record<string, unknown> = { status: 200, type: 'basic', _tag: tag };
  resp.clone = () => ({ ...resp });
  return resp;
}

describe('app-shell service worker caching strategy (ISSUE-2)', () => {
  let h: Harness;
  beforeEach(() => {
    h = loadWorker();
  });

  it('registers install/activate/fetch handlers', () => {
    expect(typeof h.listeners.install).toBe('function');
    expect(typeof h.listeners.activate).toBe('function');
    expect(typeof h.listeners.fetch).toBe('function');
  });

  it('is NETWORK-FIRST for HTML navigations (serves the fresh network shell)', async () => {
    const fresh = netResponse('network-shell');
    h.fetchMock.mockResolvedValue(fresh);

    const res = await dispatchFetch(h, req('http://localhost/', { mode: 'navigate' }));

    // Network is consulted FIRST and its response is served (not the cache).
    expect(h.fetchMock).toHaveBeenCalledTimes(1);
    expect(res).toBe(fresh);
  });

  it('falls back to the cached shell for a navigation only when offline', async () => {
    h.fetchMock.mockRejectedValue(new Error('offline'));
    const cachedShell = { _tag: 'cached-shell' };
    h.cachesMock.match.mockResolvedValue(cachedShell);

    const res = await dispatchFetch(h, req('http://localhost/', { mode: 'navigate' }));

    expect(h.fetchMock).toHaveBeenCalledTimes(1); // tried the network first
    expect(res).toBe(cachedShell); // then fell back to cache
  });

  it('treats an Accept: text/html request as a shell navigation (network-first)', async () => {
    const fresh = netResponse('network-shell-2');
    h.fetchMock.mockResolvedValue(fresh);

    const res = await dispatchFetch(
      h,
      req('http://localhost/reports', { mode: 'cors', accept: 'text/html' })
    );

    expect(h.fetchMock).toHaveBeenCalledTimes(1);
    expect(res).toBe(fresh);
  });

  it('is CACHE-FIRST for hashed /assets/* (serves cache without touching the network)', async () => {
    const cachedAsset = { _tag: 'cached-asset' };
    h.cachesMock.match.mockResolvedValue(cachedAsset);

    const res = await dispatchFetch(
      h,
      req('http://localhost/assets/index-abc123.js', { accept: '' })
    );

    expect(res).toBe(cachedAsset);
    expect(h.fetchMock).not.toHaveBeenCalled(); // cache hit -> no network
  });

  it('an Accept: text/html request under /assets/ is NOT treated as the shell', async () => {
    // A hashed asset served with a text/html Accept must still cache-first, never
    // be mistaken for the navigable shell.
    const cachedAsset = { _tag: 'cached-asset-2' };
    h.cachesMock.match.mockResolvedValue(cachedAsset);

    const res = await dispatchFetch(
      h,
      req('http://localhost/assets/x.js', { accept: 'text/html' })
    );

    expect(res).toBe(cachedAsset);
    expect(h.fetchMock).not.toHaveBeenCalled();
  });

  it('fetches and caches an asset on a cache miss', async () => {
    h.cachesMock.match.mockResolvedValue(undefined);
    const netAsset = netResponse('network-asset');
    h.fetchMock.mockResolvedValue(netAsset);

    const res = await dispatchFetch(
      h,
      req('http://localhost/assets/index-def456.css', { accept: '' })
    );

    expect(h.fetchMock).toHaveBeenCalledTimes(1);
    expect(res).toBe(netAsset);
    // Waited on the promise; the successful response was written to the cache.
    await Promise.resolve();
    expect(h.cachePut).toHaveBeenCalled();
  });

  it('never intercepts /api/* traffic', () => {
    const res = dispatchFetch(h, req('http://localhost/api/v1/products/list'));
    expect(res).toBe(PASS_THROUGH);
    expect(h.fetchMock).not.toHaveBeenCalled();
  });

  it('never intercepts non-GET requests', () => {
    const res = dispatchFetch(
      h,
      req('http://localhost/assets/x.js', { method: 'POST' })
    );
    expect(res).toBe(PASS_THROUGH);
  });
});
