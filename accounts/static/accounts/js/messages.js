const list = document.getElementById("message-list");
if (list) list.scrollTop = list.scrollHeight;

const toggleBtn = document.getElementById("toggle-sidebar");
const layout = document.getElementById("messaging-layout");

if (toggleBtn && layout) {
  toggleBtn.addEventListener("click", () => {
    layout.classList.toggle("sidebar-collapsed");
    document.body.classList.toggle("sidebar-open-mobile");
  });
}

const mainPanel = document.querySelector(".messaging-main");

document.querySelectorAll(".messaging-sidebar a").forEach((link) => {
  link.addEventListener("click", async (e) => {
    e.preventDefault();
    const href = link.getAttribute("href");

    // Mark selected
    document
      .querySelectorAll(".messaging-sidebar a")
      .forEach((el) => el.classList.remove("active"));
    link.classList.add("active");

    // Show loading
    mainPanel.innerHTML = `<div class="p-5 text-center text-muted">Chargement...</div>`;

    try {
      const response = await fetch(href, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const html = await response.text();
      mainPanel.innerHTML = html;

      const list = document.getElementById("message-list");
      if (list) list.scrollTop = list.scrollHeight;
    } catch (err) {
      console.error("Erreur AJAX:", err);
      mainPanel.innerHTML = `<div class="p-3 text-danger">Erreur de chargement.</div>`;
    }

    // Mobile collapse
    if (window.innerWidth < 768) {
      layout.classList.add("sidebar-collapsed");
      document.body.classList.remove("sidebar-open-mobile");
    }
  });
});
