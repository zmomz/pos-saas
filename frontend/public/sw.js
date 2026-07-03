/* Offline POS app-shell service worker (Phase E).
 *
 * Update strategy (ISSUE-2 — no more stale-shell pinning):
 *  - Navigations / HTML shell: NETWORK-FIRST. A fresh deploy is served the moment
 *    it is available; we fall back to the cached shell only when offline so the
 *    POS still loads. This is what stops returning browsers from being stuck on an
 *    old index.html (and therefore old JS hashes) forever.
 *  - Hashed static assets (/assets/*): CACHE-FIRST. They are content-hashed and
 *    immutable, so serving them from cache is both correct and fast.
 *  - API traffic (/api/*) and any non-GET: never cached — they go straight to the
 *    network and fail fast so the IndexedDB offline queue can take over.
 *
 * The cache name embeds a per-build hash (injected at build time, see
 * vite.config.ts). Because the name changes whenever the built bundle changes,
 * the `activate` handler below evicts every prior build's cache on update.
 */
const BUILD_HASH = '__BUILD_HASH__';
const CACHE = `pos-shell-${BUILD_HASH}`;
const SHELL = ['/', '/index.html'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL).catch(() => undefined))
  );
  // Take over as soon as installed so the new build is used without a second reload.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

/** True for requests that should resolve to the HTML app shell. */
function isShellRequest(request, url) {
  if (request.mode === 'navigate') return true;
  const accept = request.headers.get('accept') || '';
  return accept.includes('text/html') && !url.pathname.startsWith('/assets/');
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never cache API traffic — let it hit the network (and fail when offline so
  // the IndexedDB queue handles the sale).
  if (request.method !== 'GET' || url.pathname.startsWith('/api/')) {
    return;
  }

  // Network-first for the HTML shell so new deploys are picked up immediately;
  // fall back to the cached shell (or index.html) when offline.
  if (isShellRequest(request, url)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === 'basic') {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match('/index.html'))
        )
    );
    return;
  }

  // Cache-first for hashed static assets (immutable) and other same-origin GETs,
  // falling back to the network and caching successful responses for next time.
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
