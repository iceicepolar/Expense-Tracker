// ===============================
// Sidebar drawer (mobile)
// ===============================

(function () {
  const toggle = document.getElementById("menuToggle");
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");

  if (!toggle || !sidebar || !overlay) return;

  function setOpen(open) {
    sidebar.classList.toggle("is-open", open);
    overlay.hidden = !open;
    document.body.classList.toggle("no-scroll", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }

  toggle.addEventListener("click", function () {
    setOpen(!sidebar.classList.contains("is-open"));
  });

  overlay.addEventListener("click", function () {
    setOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setOpen(false);
  });

  // Close the drawer if the viewport grows back to desktop width
  window.addEventListener("resize", function () {
    if (window.innerWidth > 900) setOpen(false);
  });
})();

// ===============================
// Flash messages
// ===============================

(function () {
  document.querySelectorAll(".flash__close").forEach(function (button) {
    button.addEventListener("click", function () {
      button.closest(".flash").remove();
    });
  });

  window.setTimeout(function () {
    document.querySelectorAll(".flash--success").forEach(function (flash) {
      flash.remove();
    });
  }, 5000);
})();

// ===============================
// Confirm before destructive posts
// ===============================

(function () {
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });
})();

// ===============================
// Installable app + offline support
// ===============================

(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function (error) {
        console.warn("Service worker registration failed", error);
      });
    });
  }

  const banner = document.getElementById("offlineBanner");
  const bannerText = document.getElementById("offlineBannerText");
  if (!banner) return;

  const STAMP = "ledger:lastSync";

  function describeAge() {
    const saved = Number(window.localStorage.getItem(STAMP));
    if (!saved) return "";

    const minutes = Math.round((Date.now() - saved) / 60000);
    if (minutes < 1) return " from just now";
    if (minutes < 60) return ` from ${minutes} min ago`;

    const hours = Math.round(minutes / 60);
    if (hours < 24) return ` from ${hours} hr ago`;
    return ` from ${Math.round(hours / 24)} day(s) ago`;
  }

  function render() {
    const offline = !navigator.onLine;
    banner.hidden = !offline;
    document.body.classList.toggle("is-offline", offline);

    if (offline) {
      bannerText.textContent =
        "You're offline — showing saved data" + describeAge();
    } else {
      // Only stamp a real, freshly served page
      window.localStorage.setItem(STAMP, String(Date.now()));
    }
  }

  window.addEventListener("online", render);
  window.addEventListener("offline", render);
  render();

  // Editing and deleting still need the server, so say so instead of
  // failing silently. Adding is handled by offline.js, which queues it on
  // the device - so the add form is deliberately skipped here.
  document.querySelectorAll("form").forEach(function (form) {
    if (form.method && form.method.toLowerCase() !== "post") return;

    var action = form.getAttribute("action") || "";
    if (action.indexOf("/add") !== -1) return;

    form.addEventListener(
      "submit",
      function (event) {
        if (!navigator.onLine) {
          event.preventDefault();
          event.stopImmediatePropagation();
          window.alert(
            "You're offline. Reconnect to save this change — " +
              "your existing transactions are still viewable."
          );
        }
      },
      true // capture, so this runs before the delete confirmation
    );
  });
})();
