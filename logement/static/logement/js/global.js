

function logToServer(level, message, meta = {}) {
    fetch("/admin-area/api/log-js/", {
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