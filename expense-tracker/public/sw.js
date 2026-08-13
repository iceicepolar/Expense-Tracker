/* ===========================================================
   Ledger service worker

   Strategy:
     - static assets  -> cache first (they are versioned by deploy)
     - page loads     -> network first, fall back to the last good copy
     - everything else (POST, /api, /health) -> straight to the network

   Only successful 200 responses are cached, so the "database
   unreachable" page never gets stored and replayed later.
   =========================================================== */

const VERSION = "ledger-v1";
const SHELL = `${VERSION}-shell`;
const PAGES = `${VERSION}-pages`;

const SHELL_ASSETS = [
  "/static/css/style.css",
  "/static/css/mobile.css",
  "/static/js/app.js",
  "/static/js/charts.js",
  "/icons/icon-192.png",
  "/offline",
];

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

  // Static assets: cache first, refresh in the background
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
