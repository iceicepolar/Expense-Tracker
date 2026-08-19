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
const VERSION = "ledger-v6";
const SHELL = `${VERSION}-shell`;
const PAGES = `${VERSION}-pages`;

const SHELL_ASSETS = [
  "/static/css/style.css",
  "/static/css/mobile.css",
  "/static/js/app.js",
  "/static/js/auth.js",
  "/static/js/offline.js",
  "/static/js/charts.js",
  "/icons/icon-192.png",
  "/offline",
];

// Pages worth having offline. /add is the important one: without it, tapping
// "Add Transaction" with no signal finds nothing cached, falls back to the
// dashboard, and the form is never reached - so there is nothing to queue.
// They cannot go in SHELL_ASSETS because they need a signed-in session, which
// does not exist yet when the worker installs. offline.js asks for them once
// a real page has loaded.
const WARM_PAGES = ["/add", "/", "/transactions?month=all", "/goals"];

// Warm the cache from inside the worker.
//
// Relying on the page to ask was fragile: on the first load after an update
// the page is still controlled by the OLD worker, so the request went to a
// worker that had never heard of it and was silently dropped. Doing it here,
// off the back of any successful navigation, needs no cooperation from the
// page and no agreement about versions.
let warmedAt = 0;

function warmPages() {
  const now = Date.now();
  if (now - warmedAt < 60000) return Promise.resolve();   // at most once a minute
  warmedAt = now;

  return caches.open(PAGES).then((cache) =>
    Promise.all(
      WARM_PAGES.map((url) =>
        fetch(url, { credentials: "same-origin" })
          .then((response) => {
            if (!response.ok) return;
            // A redirect to /login means no session. Caching that would
            // show a sign-in page offline for good.
            if (response.redirected && response.url.indexOf("/login") !== -1) return;
            return cache.put(url, response.clone());
          })
          .catch(() => {})
      )
    )
  );
}

self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "WARM_PAGES") return;
  event.waitUntil(warmPages());
});

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

// Background Sync: the browser fires this when connectivity returns, even
// if no page is open. Not available on iOS Safari, where offline.js falls
// back to flushing on the online event and on page load instead.
self.addEventListener("sync", (event) => {
  if (event.tag !== "flush-outbox") return;
  event.waitUntil(
    self.clients.matchAll({ includeUncontrolled: true }).then((clients) => {
      if (clients.length) {
        // A page is open - it owns the IndexedDB logic, so ask it to upload
        clients.forEach((c) => c.postMessage({ type: "FLUSH_OUTBOX" }));
        return;
      }
      // No page open. Opening one lets offline.js run and flush the queue.
      return self.clients.openWindow("/");
    })
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
            // Opening any page is enough to keep /add available offline
            warmPages();
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
