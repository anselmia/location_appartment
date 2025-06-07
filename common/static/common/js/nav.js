document.addEventListener("DOMContentLoaded", function () {
    const toggle = document.getElementById("navToggle");
    const links = document.getElementById("navLinks");

    // Hide menu on load
    links.classList.remove("show");
    document.body.classList.remove("nav-open");

    // Hamburger toggle
    toggle?.addEventListener("click", function (e) {
        e.stopPropagation();
        links.classList.toggle("show");
        document.body.classList.toggle("nav-open");
    });

    // Close menu when clicking outside
    document.addEventListener("click", function (e) {
        if (!links.contains(e.target) && !toggle.contains(e.target)) {
            links.classList.remove("show");
            document.body.classList.remove("nav-open");
            closeAllDropdowns();
        }
    });

    // Close menu when clicking a link (non-dropdown)
    links.querySelectorAll("a:not(.dropdown-toggle)").forEach(link => {
        link.addEventListener("click", () => {
            links.classList.remove("show");
            document.body.classList.remove("nav-open");
        });
        link.addEventListener("touchend", () => {
            setTimeout(() => {
                links.classList.remove("show");
                document.body.classList.remove("nav-open");
            }, 200);
        });
    });

    // Dropdown logic
    const dropdownToggles = links.querySelectorAll(".dropdown-toggle");

    dropdownToggles.forEach(toggle => {
        const dropdown = toggle.closest(".dropdown");

        // Make focusable
        toggle.setAttribute("tabindex", "0");

        // Open/close on click
        toggle.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();

            document.querySelectorAll(".dropdown.show").forEach(open => {
                if (open !== dropdown) open.classList.remove("show");
            });

            dropdown.classList.toggle("show");
        });

        // Support Enter or Space key
        toggle.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggle.click();
            }
        });
    });

    // Close dropdowns when clicking outside
    document.addEventListener("click", function (e) {
        document.querySelectorAll(".dropdown.show").forEach(dropdown => {
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
            closeAllDropdowns();
        }
    });

    function closeAllDropdowns() {
        document.querySelectorAll(".dropdown.show").forEach(d => d.classList.remove("show"));
    }

    // Optional: support close button if added in HTML
    window.closeMenu = function () {
        links.classList.remove("show");
        document.body.classList.remove("nav-open");
        closeAllDropdowns();
    };
});
