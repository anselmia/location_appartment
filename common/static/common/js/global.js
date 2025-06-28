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
  if (loader) loader.style.display = "none";

  const banner = document.getElementById("cookie-banner");
  const acceptBtn = document.getElementById("accept-cookies");
  const refuseBtn = document.getElementById("refuse-cookies");
  const customizeBtn = document.getElementById("customize-cookies");
  const customizePanel = document.getElementById("cookie-customize-panel");
  const savePrefsBtn = document.getElementById("save-cookie-preferences");
  const analyticsBox = document.getElementById("consent-analytics");
  const mapsBox = document.getElementById("consent-maps");
  const showCookieBtn = document.getElementById("show-cookie-banner");

  // Helper: set consent cookie (6 months)
  function setConsent(consent) {
    const date = new Date();
    date.setMonth(date.getMonth() + 6);
    document.cookie = `cookie_consent=${encodeURIComponent(
      JSON.stringify(consent)
    )}; expires=${date.toUTCString()}; path=/; SameSite=Lax`;
  }

  // Helper: get consent object from cookie
  function getConsent() {
    const match = document.cookie.match(/cookie_consent=([^;]+)/);
    if (match) {
      try {
        return JSON.parse(decodeURIComponent(match[1]));
      } catch (e) {}
    }
    return null;
  }

  // Show banner if no consent
  let consent = getConsent();
  if (!consent) banner.style.display = "block";

  // Accept all
  acceptBtn.addEventListener("click", function () {
    consent = { analytics: true, maps: true };
    setConsent(consent);
    banner.style.display = "none";
    initOptionalCookies(consent);
  });

  // Refuse all
  refuseBtn.addEventListener("click", function () {
    consent = { analytics: false, maps: false };
    setConsent(consent);
    banner.style.display = "none";
    initOptionalCookies(consent);
  });

  // Show customize panel
  customizeBtn.addEventListener("click", function () {
    customizePanel.style.display = "block";
    analyticsBox.checked = false;
    mapsBox.checked = false;
    if (consent) {
      analyticsBox.checked = !!consent.analytics;
      mapsBox.checked = !!consent.maps;
    }
  });

  // Save preferences
  savePrefsBtn.addEventListener("click", function () {
    consent = {
      analytics: analyticsBox.checked,
      maps: mapsBox.checked,
    };
    setConsent(consent);
    banner.style.display = "none";
    customizePanel.style.display = "none";
    initOptionalCookies(consent);
  });

  // Allow user to re-open the banner
  if (showCookieBtn && banner) {
    showCookieBtn.addEventListener("click", function (e) {
      e.preventDefault();
      banner.style.display = "block";
      customizePanel.style.display = "none";
    });
  }

  // On page load, apply consent if already set
  if (consent) initOptionalCookies(consent);
});

// Load optional cookies/scripts based on consent
function initOptionalCookies(consent) {
  consent = consent || {};
  if (consent.analytics) loadAnalytics();
  if (consent.maps) showMapOrPlaceholder();
  else showMapOrPlaceholder(false); // show placeholder if not allowed
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

function showMapOrPlaceholder(allowMap = undefined) {
  const placeholder = document.getElementById("map-placeholder");
  if (!placeholder) return;
  // If allowMap is undefined, check consent cookie
  if (allowMap === undefined) {
    const consent = (function () {
      const match = document.cookie.match(/cookie_consent=([^;]+)/);
      if (match) {
        try {
          return JSON.parse(decodeURIComponent(match[1]));
        } catch (e) {}
      }
      return {};
    })();
    allowMap = !!consent.maps;
  }
  if (allowMap && window.logementMapLink) {
    placeholder.innerHTML = `<iframe class="logement-map"
            src="${window.logementMapLink}"
            style="border:0; width:100%; height:220px;"
            allowfullscreen=""
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"></iframe>`;
  } else {
    placeholder.innerHTML = `
            <div>
                <p>La carte Google Maps est désactivée tant que vous n'avez pas accepté les cookies tiers.</p>
            </div>
        `;
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
