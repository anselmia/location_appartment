document.addEventListener("DOMContentLoaded", function () {
    const toggle = document.getElementById("navToggle");
    const links = document.getElementById("navLinks");

    // Initial state: force hidden
    links.classList.remove("show");

    // Toggle menu on hamburger click
    toggle.addEventListener("click", function (e) {
        e.stopPropagation();
        links.classList.toggle("show");
    });

    // Close menu on outside click
    document.addEventListener("click", function (e) {
        if (!links.contains(e.target) && !toggle.contains(e.target)) {
            links.classList.remove("show");
        }
    });

    // Close on any link click except dropdown toggle
    links.querySelectorAll("a:not(.dropdown-toggle)").forEach(link => {
        link.addEventListener("click", () => {
            links.classList.remove("show");
        });
    });

    // Dropdown toggle (mobile only)
    const dropdownToggle = links.querySelector(".dropdown-toggle");
    const dropdown = dropdownToggle?.closest(".dropdown");

    if (dropdownToggle && dropdown) {
        dropdownToggle.addEventListener("click", function (e) {
            e.preventDefault();
            dropdown.classList.toggle("show");
        });
    }
});