document.addEventListener("DOMContentLoaded", function () {
    const toggle = document.getElementById("navToggle");
    const links = document.getElementById("navLinks");

    // Initial state: force menu hidden
    links.classList.remove("show");

    // Toggle hamburger menu
    toggle?.addEventListener("click", function (e) {
        e.stopPropagation();
        links.classList.toggle("show");
    });

    // Close menu when clicking outside
    document.addEventListener("click", function (e) {
        if (!links.contains(e.target) && !toggle.contains(e.target)) {
            links.classList.remove("show");
        }
    });

    // Close menu when clicking a non-dropdown link
    links.querySelectorAll("a:not(.dropdown-toggle)").forEach(link => {
        link.addEventListener("click", () => {
            links.classList.remove("show");
        });
    });

    // Handle all dropdowns
    const dropdownToggles = links.querySelectorAll(".dropdown-toggle");

    dropdownToggles.forEach(toggle => {
        const dropdown = toggle.closest(".dropdown");

        toggle.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();

            // Close other open dropdowns
            document.querySelectorAll(".dropdown.show").forEach(open => {
                if (open !== dropdown) {
                    open.classList.remove("show");
                }
            });

            dropdown.classList.toggle("show");
        });
    });

    // Close dropdowns on outside click
    document.addEventListener("click", function (e) {
        document.querySelectorAll(".dropdown.show").forEach(dropdown => {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove("show");
            }
        });
    });
});
