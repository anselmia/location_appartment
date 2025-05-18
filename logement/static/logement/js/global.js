function fetchWithLoader(url, options = {}) {
    const loader = document.getElementById("loader");
    if (loader) {
        loader.style.display = "flex";
    }

    return fetch(url, options)
        .finally(() => {
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