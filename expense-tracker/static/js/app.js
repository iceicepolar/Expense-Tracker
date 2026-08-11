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
