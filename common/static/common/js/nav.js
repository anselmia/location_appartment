document.addEventListener("DOMContentLoaded", function () {
  const toggle = document.getElementById("navToggle");
  const links = document.getElementById("navLinks");

  // Hide menu on load
  links.classList.remove("show");
  document.body.classList.remove("nav-open");
  enableBodyScroll();

  // Hamburger toggle
  toggle?.addEventListener("click", function (e) {
    e.stopPropagation();
    links.classList.toggle("show");
    document.body.classList.toggle("nav-open");
    if (links.classList.contains("show")) {
      disableBodyScroll();
      trapFocus(links);
    } else {
      enableBodyScroll();
    }
  });

  // Close menu when clicking outside
  document.addEventListener("click", function (e) {
    if (!links.contains(e.target) && !toggle.contains(e.target)) {
      links.classList.remove("show");
      document.body.classList.remove("nav-open");
      enableBodyScroll();
      closeAllDropdowns();
    }
  });

  // Close menu when clicking a link (non-dropdown)
  links.querySelectorAll("a:not(.dropdown-toggle)").forEach((link) => {
    link.addEventListener("click", () => {
      links.classList.remove("show");
      document.body.classList.remove("nav-open");
      enableBodyScroll();
    });
    link.addEventListener("touchend", () => {
      setTimeout(() => {
        links.classList.remove("show");
        document.body.classList.remove("nav-open");
        enableBodyScroll();
      }, 200);
    });
  });

  // Dropdown logic
  const dropdownToggles = links.querySelectorAll(".dropdown-toggle");

  dropdownToggles.forEach((toggle) => {
    const dropdown = toggle.closest(".dropdown");

    // Make focusable
    toggle.setAttribute("tabindex", "0");

    function handleDropdownToggle(e) {
      e.preventDefault();
      e.stopPropagation();

      // If already open, close it
      if (dropdown.classList.contains("show")) {
        dropdown.classList.remove("show");
        return;
      }

      // Close other open dropdowns
      document.querySelectorAll(".dropdown.show").forEach((open) => {
        if (open !== dropdown) open.classList.remove("show");
      });

      dropdown.classList.add("show");
      dropdown.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    toggle.addEventListener("click", handleDropdownToggle);
    toggle.addEventListener("touchend", function (e) {
      // Prevent double firing on mobile
      if (e.cancelable) e.preventDefault();
      handleDropdownToggle(e);
    });

    // Support Enter or Space key
    toggle.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleDropdownToggle(e);
      }
    });
  });

  // Close dropdowns when clicking outside
  document.addEventListener("click", function (e) {
    document.querySelectorAll(".dropdown.show").forEach((dropdown) => {
      if (!dropdown.contains(e.target)) {
        dropdown.classList.remove("show");
      }
    });
  });

  // Escape closes menu and dropdowns
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      links.classList.remove("show");
      document.body.classList.remove("nav-open");
      enableBodyScroll();
      closeAllDropdowns();
    }
  });

  function closeAllDropdowns() {
    document
      .querySelectorAll(".dropdown.show")
      .forEach((d) => d.classList.remove("show"));
  }

  // Optional: support close button if added in HTML
  window.closeMenu = function () {
    links.classList.remove("show");
    document.body.classList.remove("nav-open");
    enableBodyScroll();
    closeAllDropdowns();
  };

  // Prevent body scroll when menu is open
  function disableBodyScroll() {
    document.body.style.overflow = "hidden";
    document.body.style.touchAction = "none";
  }
  function enableBodyScroll() {
    document.body.style.overflow = "";
    document.body.style.touchAction = "";
  }

  // Trap focus inside menu
  function trapFocus(container) {
    const focusable = container.querySelectorAll(
      'a, button, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    let first = focusable[0],
      last = focusable[focusable.length - 1];
    function handleTab(e) {
      if (e.key === "Tab") {
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    container.addEventListener("keydown", handleTab);
    setTimeout(() => first.focus(), 100);
    // Remove trap when menu closes
    function cleanup() {
      container.removeEventListener("keydown", handleTab);
    }
    links.addEventListener("transitionend", cleanup, { once: true });
  }
});
