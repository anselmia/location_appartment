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
}, 10000);

let isSending = false;

function scrollChatToBottom() {
  const chatLog = document.getElementById("chat-log");
  if (chatLog) {
    chatLog.scrollTop = chatLog.scrollHeight;
  }
}

async function sendMessage() {
  if (isSending) return;

  const input = document.getElementById("user-message");
  const chatLog = document.getElementById("chat-log");
  const message = input.value.trim();
  if (!message) return;

  isSending = true;

  // Ajouter le message utilisateur
  const userMsg = document.createElement("p");
  userMsg.className = "user-message";
  userMsg.innerHTML = `<strong>Vous:</strong> ${message}`;
  chatLog.appendChild(userMsg);

  input.value = "";

  scrollChatToBottom();

  try {
    const response = await fetch(chat_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message }),
    });

    const data = await response.json();

    const botMsg = document.createElement("p");
    botMsg.className = "bot-message";
    botMsg.innerHTML = `<strong>Bot:</strong> ${
      data.response || data.error || "Erreur inconnue"
    }`;
    chatLog.appendChild(botMsg);
  } catch (e) {
    const errorMsg = document.createElement("p");
    errorMsg.className = "text-danger";
    errorMsg.innerHTML = `<strong>Erreur:</strong> Une erreur est survenue.`;
    chatLog.appendChild(errorMsg);
  }

  scrollChatToBottom();
  isSending = false;
}

function toggleChat() {
  const window = document.getElementById("chatbot-window");
  window.style.display = window.style.display === "none" ? "block" : "none";
}
