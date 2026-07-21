// miny-ven service worker
// v4: never cache-first hashed assets or HTML shell — that pinned post-deploy
// clients to old index-*.js (MIME text/html via SPA rewrite) after 980f1ea.
const CACHE_NAME = 'miny-ven-v4';

// Precache only stable, non-hashed shell assets. Do NOT precache '/' — the
// HTML references content-hashed JS/CSS that change every deploy.
const PRECACHE_URLS = [
  '/manifest.json',
  '/favicon-32x32.png',
  '/favicon-16x16.png',
  '/apple-touch-icon.png',
  '/branding/minylogo.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name !== CACHE_NAME)
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isHashedAsset(url) {
  // Vite content-hashed bundles: /assets/index-XXXX.js|css
  return /\/assets\/[^/]+\.[a-fA-F0-9_-]+\.(js|css|woff2?)$/.test(url.pathname)
    || /\/assets\/index-[A-Za-z0-9_-]+\.(js|css)$/.test(url.pathname);
}

function isApiOrData(url) {
  return (
    url.hostname.includes('miny-database.exe.xyz')
    || url.hostname.includes('firestore.googleapis.com')
    || url.hostname.includes('googleapis.com')
    || url.pathname.startsWith('/api/')
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try {
    url = new URL(req.url);
  } catch {
    return;
  }

  // Always hit network for PB / APIs — never serve stale feed from cache.
  if (isApiOrData(url)) {
    event.respondWith(fetch(req));
    return;
  }

  // Navigations: network-first, offline fallback to last shell only.
  // Do not rewrite-cache '/' with every response (that pinned old HTML).
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((response) => {
          // Cache a copy as offline fallback only (not used while online).
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put('/__offline_shell__', clone));
          }
          return response;
        })
        .catch(() =>
          caches.match('/__offline_shell__').then((r) => r || caches.match('/manifest.json')),
        ),
    );
    return;
  }

  // Hashed build assets: network-first (new deploy must win). Cache as
  // fallback only after a successful network response.
  if (isHashedAsset(url) || url.pathname.startsWith('/assets/')) {
    event.respondWith(
      fetch(req)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return response;
        })
        .catch(() => caches.match(req)),
    );
    return;
  }

  // Icons / branding: cache-first is fine (stable paths).
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return response;
      });
    }),
  );
});
