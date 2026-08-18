/* ===========================================================
   Runs on the sign-in / register pages only.

   The service worker keeps a copy of every page it serves so the app still
   works offline. That copy outlives the session: without this, signing out
   and handing the phone to somebody else would let the previous account's
   dashboard reappear from cache the moment the network dropped.

   Landing here means nobody is signed in, which is exactly the right moment
   to throw those pages away.
   =========================================================== */

(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  navigator.serviceWorker.ready
    .then(function (registration) {
      var worker = registration.active;
      if (worker) worker.postMessage({ type: "PURGE_PAGES" });
    })
    .catch(function () {
      /* No worker registered yet - nothing cached, nothing to clear. */
    });

  // The stale-data banner on the app pages reads this timestamp. Clearing it
  // stops a fresh sign-in from claiming the data is hours old.
  try {
    window.localStorage.removeItem("ledger:lastSync");
  } catch (error) {
    /* Private mode can refuse localStorage entirely. Not worth failing over. */
  }
})();
