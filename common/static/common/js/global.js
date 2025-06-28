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
  fetchWithLoader("/api/log-js/", {
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

  const banner = document.getElementById("cookie-banner");
  const acceptBtn = document.getElementById("accept-cookies");

  // Show banner if no consent cookie
  if (!document.cookie.includes("cookie_consent=true")) {
    banner.style.display = "block";
  }

  acceptBtn.addEventListener("click", function () {
    // Set a cookie for 6 months
    const date = new Date();
    date.setMonth(date.getMonth() + 6);
    document.cookie = `cookie_consent=true; expires=${date.toUTCString()}; path=/; SameSite=Lax`;

    banner.style.display = "none";

    // OPTIONAL: initialize services
    initOptionalCookies(); // e.g., analytics, chat widgets, etc.
  });

  const showCookieBtn = document.getElementById("show-cookie-banner");
  const cookieBanner = document.getElementById("cookie-banner");
  if (showCookieBtn && cookieBanner) {
    showCookieBtn.addEventListener("click", function (e) {
      e.preventDefault();
      cookieBanner.style.display = "block";
    });
  }
});

function initOptionalCookies() {
  loadAnalytics();
  showMapOrPlaceholder();
}

function loadAnalytics() {
  if (!window.gaLoaded) {
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=G-W05PFMYJQH";
    document.head.appendChild(s);

    var inline = document.createElement("script");
    inline.innerHTML = `
                window.dataLayer = window.dataLayer || [];
                function gtag(){dataLayer.push(arguments);}
                gtag('js', new Date());
                gtag('config', 'G-W05PFMYJQH');
            `;
    document.head.appendChild(inline);
    window.gaLoaded = true;
  }
}

function showMapOrPlaceholder() {
  const placeholder = document.getElementById("map-placeholder");
  if (!placeholder) return;
  // Check if consent cookie is present
  if (document.cookie.includes("cookie_consent=true")) {
    // Show the map
    placeholder.innerHTML = `<iframe class="logement-map"
            src="${window.logementMapLink}"
            style="border:0; width:100%; height:220px;"
            allowfullscreen=""
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"></iframe>`;
  } else {
    // Show the placeholder
    placeholder.innerHTML = `
            <div>
                <p>La carte Google Maps est désactivée tant que vous n'avez pas accepté les cookies.</p>
                <button id="enable-map" class="btn btn-primary btn-sm">Afficher la carte</button>
            </div>
        `;
    // Allow manual activation if user clicks
    const btn = document.getElementById("enable-map");
    if (btn) {
      btn.addEventListener("click", function () {
        // Set consent cookie for 6 months
        const date = new Date();
        date.setMonth(date.getMonth() + 6);
        document.cookie = `cookie_consent=true; expires=${date.toUTCString()}; path=/; SameSite=Lax`;
        showMapOrPlaceholder();
        // Optionally: trigger other consent-dependent features
        if (typeof initOptionalCookies === "function") {
          initOptionalCookies();
        }
      });
    }
  }
}

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
