function fetchWithLoader(url, options = {}) {
  const loader = document.getElementById("loader");
  if (loader) {
    loader.style.display = "flex";
  }

  return fetch(url, options).finally(() => {
    if (loader) {
      loader.style.display = "none";
    }
  });
}

function logToServer(level, message, meta = {}) {
  fetchWithLoader("/admin-area/api/log-js/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify({
      level: level,
      message: message,
      meta: meta,
    }),
  }).catch((error) => console.error("Logging failed:", error));
}

document.addEventListener("DOMContentLoaded", function () {
  const loader = document.getElementById("loader");
  if (loader) {
    loader.style.display = "none";
  }
});

if (!localStorage.getItem("cookiesAccepted")) {
  document.getElementById("cookie-banner").style.display = "flex";
}

document.getElementById("accept-cookies").addEventListener("click", () => {
  localStorage.setItem("cookiesAccepted", true);
  document.getElementById("cookie-banner").style.display = "none";
});

setTimeout(() => {
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach((alert) => {
    alert.classList.remove("show");
    alert.classList.add("hide");
    setTimeout(() => alert.remove(), 300);
  });
}, 5000);

let isSending = false;

async function sendMessage() {
  if (isSending) return;

  const message = document.getElementById("user-message").value.trim();
  if (!message) return;

  isSending = true;

  const response = await fetch(chat_url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: message }),
  });

  const data = await response.json();

  document.getElementById(
    "chat-log"
  ).innerHTML += `<p class="user-message"><strong>Vous:</strong> ${message}</p>`;

  if (data.response) {
    document.getElementById(
      "chat-log"
    ).innerHTML += `<p class="bot-message"><strong>Bot:</strong> ${data.response}</p>`;
  } else {
    document.getElementById(
      "chat-log"
    ).innerHTML += `<p class='text-danger'><strong>Erreur:</strong> ${data.error}</p>`;
  }

  document.getElementById("user-message").value = ""; // clear input
  isSending = false;
}

function toggleChat() {
  const window = document.getElementById("chatbot-window");
  window.style.display = window.style.display === "none" ? "block" : "none";
}
