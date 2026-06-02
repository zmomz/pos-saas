/* Offline POS app-shell service worker (Phase E).
 *
 * Caches the built app shell so the POS keeps loading with no network; sales
 * made while offline are buffered in IndexedDB (see src/lib/offlineQueue.ts) and
 * replayed on reconnect. API calls are never cached — they go straight to the
 * network and fail fast so the queue can take over.
 */
const CACHE = 'pos-shell-v1';
const SHELL = ['/', '/index.html', '/manifest.webmanifest'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL).catch(() => undefined))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never cache API traffic — let it hit the network (and fail when offline so
  // the IndexedDB queue handles the sale).
  if (request.method !== 'GET' || url.pathname.startsWith('/api/')) {
    return;
  }

  // Cache-first for the static app shell, falling back to the network and
  // caching successful responses for next time.
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request)
          .then((response) => {
            if (response && response.status === 200 && response.type === 'basic') {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          })
          .catch(() => cached)
    )
  );
});
