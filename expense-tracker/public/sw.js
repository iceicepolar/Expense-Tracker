/* ===========================================================
   Ledger service worker

   Strategy:
     - static assets  -> cache first (they are versioned by deploy)
     - page loads     -> network first, fall back to the last good copy
     - everything else (POST, /api, /health) -> straight to the network

   Only successful 200 responses are cached, so the "database
   unreachable" page never gets stored and replayed later.
   =========================================================== */

// Bump this on every deploy that changes cached assets - activate() deletes
// every cache whose name does not start with the current VERSION.
const VERSION = "ledger-v3";
const SHELL = `${VERSION}-shell`;
const PAGES = `${VERSION}-pages`;

const SHELL_ASSETS = [
  "/static/css/style.css",
  "/static/css/mobile.css",
  "/static/js/app.js",
  "/static/js/auth.js",
  "/static/js/charts.js",
  "/icons/icon-192.png",
  "/offline",
];

// The sign-in page asks for this as soon as it loads. Cached pages belong to
// whoever was signed in when they were stored, so they must not survive a
// sign-out and reappear for the next person to use this device.
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "PURGE_PAGES") {
    event.waitUntil(caches.delete(PAGES));
  }
});

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      // addAll fails the whole install if one file 404s, so add individually
      .then((cache) =>
        Promise.all(
          SHELL_ASSETS.map((url) =>
            cache.add(url).catch(() => console.warn("skipped caching", url))
          )
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => !key.startsWith(VERSION))
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never interfere with writes, other origins, or live-status endpoints
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/") ||
    url.pathname === "/health"
  ) {
    return;
  }

  // Page loads: show fresh data when online, last known copy when not
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(PAGES).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          return (
            (await caches.match(request)) ||
            (await caches.match("/")) ||
            (await caches.match("/offline")) ||
            new Response("Offline", { status: 503 })
          );
        })
    );
    return;
  }

  // Stylesheets and scripts: network first, cache only as an offline fallback.
  //
  // These were cache-first, which meant an edited stylesheet kept losing to
  // the copy already in the cache - the page would render with whatever CSS
  // was current the first time the worker saw it, and new rules simply never
  // arrived. Serving them fresh costs a few KB and removes a whole class of
  // "my change did not show up" confusion.
  if (/\.(css|js)$/.test(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Everything else (icons, images): cache first, refresh in the background
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);

      return cached || network;
    })
  );
});
