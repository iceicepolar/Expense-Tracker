/* ===========================================================
   Offline capture for new transactions.

   A transaction added with no signal is written to IndexedDB instead of the
   network, listed on the dashboard as pending, and uploaded when the
   connection returns.

   Only ADDING works this way. Editing and deleting still need the server,
   because resolving "you edited this offline while the other device deleted
   it" is a different and much larger problem. Those still say so out loud.

   Every queued transaction carries a clientId. The server treats a clientId
   it has already stored as a duplicate and returns the existing row, so a
   flush that runs twice - a retry, flaky signal, the app reopened mid-upload
   - cannot create the same transaction twice. That guarantee is the whole
   reason this is safe to use with real money.
   =========================================================== */

(function () {
  "use strict";

  var DB_NAME = "budgetwise-outbox";
  var STORE = "pending";
  var VERSION = 1;

  // ---- IndexedDB, wrapped in promises -----------------------------------

  function openDB() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, VERSION);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: "clientId" });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function withStore(mode, run) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var t = db.transaction(STORE, mode);
        var request = run(t.objectStore(STORE));
        t.oncomplete = function () {
          resolve(request ? request.result : undefined);
        };
        t.onerror = function () { reject(t.error); };
        t.onabort = function () { reject(t.error); };
      });
    });
  }

  function putEntry(entry) {
    return withStore("readwrite", function (s) { return s.put(entry); });
  }

  function deleteEntry(id) {
    return withStore("readwrite", function (s) { return s.delete(id); });
  }

  function allEntries() {
    return withStore("readonly", function (s) { return s.getAll(); });
  }

  function newId() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    // Older browsers: random plus time is unique enough for one device queue
    return "c-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  // ---- Capturing the add form -------------------------------------------

  function readForm(form) {
    var data = new FormData(form);
    function field(name) {
      var v = data.get(name);
      return v === null ? "" : String(v);
    }
    return {
      clientId: newId(),
      queuedAt: Date.now(),
      body: {
        description: field("description").trim(),
        category: field("category"),
        amount: field("amount"),
        transaction_type: field("transaction_type"),
        transaction_date: field("transaction_date"),
        notes: field("notes") || null
      }
    };
  }

  function looksComplete(body) {
    return Boolean(
      body.description && body.category && body.amount &&
      body.transaction_type && body.transaction_date
    );
  }

  function captureAddForm() {
    var forms = document.querySelectorAll("form[method='post'], form[method='POST']");
    Array.prototype.forEach.call(forms, function (form) {
      var action = form.getAttribute("action") || "";
      // Only the add form. Edit and delete keep needing the server.
      if (action.indexOf("/add") === -1) return;

      form.addEventListener("submit", function (event) {
        if (navigator.onLine) return;

        var entry = readForm(form);
        // Let the browser show its own validation for a half-filled form
        if (!looksComplete(entry.body)) return;

        event.preventDefault();
        event.stopImmediatePropagation();

        putEntry(entry)
          .then(requestSync)
          .then(function () { window.location.href = "/?queued=1"; })
          .catch(function () {
            window.alert(
              "Could not store this on the device. Reconnect and try again."
            );
          });
      }, true);   // capture, so this runs before the older offline blocker
    });
  }

  // ---- Uploading ---------------------------------------------------------

  var flushing = false;

  function sendOne(entry) {
    var payload = { client_id: entry.clientId };
    Object.keys(entry.body).forEach(function (k) { payload[k] = entry.body[k]; });

    return fetch("/api/transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    }).then(function (response) {
      // 201 created, 200 already there - either way it is stored
      if (response.status === 200 || response.status === 201) {
        return deleteEntry(entry.clientId).then(function () { return true; });
      }
      if (response.status === 422) {
        // The contents were refused. Retrying forever cannot help, so drop
        // it rather than leaving a poison entry blocking the queue.
        return deleteEntry(entry.clientId).then(function () {
          window.alert(
            "A queued transaction was rejected and has been discarded: " +
            (entry.body.description || "(no description)")
          );
          return false;
        });
      }
      // Signed out, or the server is unhappy. Keep it and try later.
      throw new Error("upload failed with " + response.status);
    });
  }

  function flush() {
    if (flushing || !navigator.onLine) return Promise.resolve(0);
    flushing = true;

    return allEntries().then(function (entries) {
      if (!entries || !entries.length) return 0;

      // Oldest first, one at a time, so the server receives them in the
      // order they were entered and one failure stops the rest.
      entries.sort(function (a, b) { return a.queuedAt - b.queuedAt; });

      return entries.reduce(function (chain, entry) {
        return chain.then(function (count) {
          return sendOne(entry).then(function (stored) {
            return stored ? count + 1 : count;
          });
        });
      }, Promise.resolve(0));
    }).then(function (count) {
      flushing = false;
      if (count > 0) window.location.reload();
      return count;
    }).catch(function () {
      flushing = false;
      return 0;
    });
  }

  function requestSync() {
    // Background Sync uploads even with the app closed. Absent on iOS
    // Safari, where the online and page-load handlers below are all there
    // is - so on an iPhone a queued item waits until the app is reopened.
    if (!("serviceWorker" in navigator) || !("SyncManager" in window)) {
      return Promise.resolve();
    }
    return navigator.serviceWorker.ready.then(function (reg) {
      return reg.sync.register("flush-outbox");
    }).catch(function () { /* handled by the fallbacks */ });
  }

  // ---- The pending list --------------------------------------------------

  function money(value) {
    var n = Number(value) || 0;
    return "₱" + n.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function buildRow(entry, onRemoved) {
    var li = document.createElement("li");

    var desc = document.createElement("span");
    desc.className = "pending__desc";
    // textContent, never innerHTML - the description is whatever was typed
    desc.textContent = entry.body.description;

    var meta = document.createElement("span");
    meta.className = "pending__meta";
    meta.textContent = entry.body.category + " · " + entry.body.transaction_date;

    var amount = document.createElement("span");
    amount.className = "pending__amount";
    amount.textContent =
      (entry.body.transaction_type === "Income" ? "+" : "-") + money(entry.body.amount);

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "pending__remove";
    remove.setAttribute("aria-label", "Discard " + entry.body.description);
    remove.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    remove.addEventListener("click", function () {
      var ok = window.confirm(
        "Discard this queued transaction? It has not been saved anywhere."
      );
      if (!ok) return;
      deleteEntry(entry.clientId).then(onRemoved);
    });

    li.appendChild(desc);
    li.appendChild(meta);
    li.appendChild(amount);
    li.appendChild(remove);
    return li;
  }

  function renderPending() {
    var host = document.getElementById("pendingQueue");
    if (!host) return Promise.resolve();

    return allEntries().then(function (entries) {
      host.innerHTML = "";

      if (!entries || !entries.length) {
        host.hidden = true;
        return;
      }

      entries.sort(function (a, b) { return b.queuedAt - a.queuedAt; });

      var title = document.createElement("p");
      title.className = "pending__title";
      var icon = document.createElement("i");
      icon.className = "fa-solid fa-clock-rotate-left";
      title.appendChild(icon);
      title.appendChild(document.createTextNode(
        " " + entries.length + " transaction" + (entries.length === 1 ? "" : "s") +
        (navigator.onLine ? " uploading…" : " waiting for a connection")
      ));

      var list = document.createElement("ul");
      entries.forEach(function (e) {
        list.appendChild(buildRow(e, renderPending));
      });

      host.appendChild(title);
      host.appendChild(list);
      host.hidden = false;
    });
  }

  // The figures on the page are calculated by the server and do not include
  // anything still queued. That is why these are listed separately instead
  // of being mixed into the table - a pending row sitting inside the table
  // would make the totals above it look wrong.

  // ---- Wiring ------------------------------------------------------------

  captureAddForm();
  renderPending();

  window.addEventListener("online", function () {
    renderPending();
    flush().then(renderPending);
  });

  window.addEventListener("offline", renderPending);

  if (navigator.onLine) {
    flush().then(renderPending);
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", function (event) {
      if (event.data && event.data.type === "FLUSH_OUTBOX") {
        flush().then(renderPending);
      }
    });
  }

  // Exposed so the browser console can inspect the queue when debugging
  window.BudgetWiseOutbox = {
    flush: flush,
    render: renderPending,
    all: allEntries
  };
})();
