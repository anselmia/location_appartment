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

// Auto-collapse and redirect manually on conversation click (mobile only)
document.querySelectorAll(".messaging-sidebar a").forEach((link) => {
  link.addEventListener("click", (e) => {
    if (window.innerWidth < 768) {
      e.preventDefault(); // Stop immediate navigation
      const href = link.getAttribute("href");

      layout.classList.add("sidebar-collapsed");
      document.body.classList.remove("sidebar-open-mobile");

      // Delay navigation to let collapse animation finish
      setTimeout(() => {
        window.location.href = href;
      }, 200); // Match your CSS transition (0.3s if using 300ms)
    }
  });
});
