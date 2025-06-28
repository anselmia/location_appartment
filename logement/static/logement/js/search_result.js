const flexLevels = [0, 1, 2, 3, 7];
let currentFlex = 0;
const currentYear = new Date().getFullYear();
let lastFormattedRange = "";

const picker = new Litepicker({
  element: document.getElementById("datepicker"),
  singleMode: false,
  numberOfMonths: 2,
  numberOfColumns: 2,
  lang: "fr-FR",
  format: "",
  showCancelBtn: true, // <-- This enables the clear (cross) button
  buttonText: {
    cancel: "✕ Effacer",
  },
  autoApply: false,
  dropdowns: {
    minYear: currentYear,
    maxYear: currentYear + 1,
    months: true,
    years: true,
  },
  setup: (picker) => {
    picker.on("selected", (start, end) => {
      document.getElementById("start_date").value = start.format("YYYY-MM-DD");
      document.getElementById("end_date").value = end.format("YYYY-MM-DD");

      const monthNames = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
      ];

      const formattedStart = `${start.dateInstance.getDate()} ${
        monthNames[start.dateInstance.getMonth()]
      }`;
      const formattedEnd = `${end.dateInstance.getDate()} ${
        monthNames[end.dateInstance.getMonth()]
      }`;

      lastFormattedRange = `${formattedStart} – ${formattedEnd}`;
      document.getElementById("datepicker").value = lastFormattedRange;
    });
  },
});

picker.on("hide", () => {
  if (lastFormattedRange) {
    document.getElementById("datepicker").value = lastFormattedRange;
  }
});

document.querySelectorAll(".flex-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document
      .querySelectorAll(".flex-btn")
      .forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("flexibility").value = btn.dataset.flex;
  });
});

const destinationInput = document.getElementById("destination-input");
if (destinationInput) {
  destinationInput.addEventListener("input", function () {
    const query = this.value;
    if (query.length < 2) return;

    fetch(`/cities/?q=${encodeURIComponent(query)}`)
      .then((response) => response.text())
      .then((data) => {
        document.getElementById("cities").innerHTML = data;
      });
  });
}

document.querySelectorAll(".animate-on-scroll").forEach((el) => {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) entry.target.classList.add("animated-visible");
    });
  });
  observer.observe(el);
});

function toggleFilters() {
  const panel = document.getElementById("filter-panel");
  panel.classList.toggle("show");
}

window.addEventListener("DOMContentLoaded", () => {
  const start = document.getElementById("start_date")?.value;
  const end = document.getElementById("end_date")?.value;

  if (start && end) {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const monthNames = [
      "janvier",
      "février",
      "mars",
      "avril",
      "mai",
      "juin",
      "juillet",
      "août",
      "septembre",
      "octobre",
      "novembre",
      "décembre",
    ];
    const formatted = `${startDate.getDate()} ${
      monthNames[startDate.getMonth()]
    } – ${endDate.getDate()} ${monthNames[endDate.getMonth()]}`;
    document.getElementById("datepicker").value = formatted;
  }

  // ✅ Safe map initialization
  const mapContainer = document.getElementById("logement-map");
  if (
    mapContainer &&
    typeof L !== "undefined" &&
    typeof all_logements !== "undefined"
  ) {
    const map = L.map("logement-map").setView([46.5, 2.6], 6);

    L.tileLayer("https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://osm.org">OpenStreetMap</a>',
      minZoom: 4,
      maxZoom: 18,
    }).addTo(map);

    const markerCluster = L.markerClusterGroup();

    all_logements.forEach((logement) => {
      if (logement.lat && logement.lng) {
        const marker = L.marker([logement.lat, logement.lng]);
        const popupContent = `
        <div style="min-width:220px; max-width:260px; font-family:Arial, sans-serif;">
          <div style="position:relative;">
            <img src="${logement.image}" alt="${logement.name}"
              style="width:100%; height:160px; object-fit:cover; border-radius:8px;">
            <div style="position:absolute; top:8px; right:8px; background:rgba(0,0,0,0.6); color:#fff;
                padding:2px 8px; border-radius:12px; font-size:12px;">
              <i class="fas fa-user"></i> ${logement.max_traveler || "?"}
            </div>
          </div>
          <div style="padding:8px 4px 0;">
            <strong style="font-size:14px; display:block; margin-bottom:2px;">${
              logement.name
            }</strong>
            <span style="font-size:13px; color:#777;">
              <i class="fas fa-map-marker-alt"></i> ${logement.city || ""}
            </span>
            <p style="margin:6px 0; font-size:13px;"><strong>${
              logement.price
            }</strong> € / nuit</p>
            <div style="display: flex; gap: 6px;">
              <a href="${logement.url}" class="btn btn-sm btn-primary"
                style=" padding:4px 8px; font-size:13px; border-radius:4px; text-decoration:none;">
                + INFO
              </a>
              <a href="${logement.book_url}" class="btn btn-secondary"
                style="padding:4px 8px; font-size:13px; border-radius:4px; text-decoration:none;">
                Réserver
              </a>
            </div>
          </div>
        </div>
      `;
        marker.bindPopup(popupContent);
        markerCluster.addLayer(marker);
      }
    });

    map.addLayer(markerCluster);
    const bounds = all_logements
      .filter((l) => l.lat && l.lng)
      .map((l) => [l.lat, l.lng]);

    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }

  // Automatically show filters panel if filters present in URL
  const urlParams = new URLSearchParams(window.location.search);
  const hasFilters = [
    "type",
    "equipments",
    "bedrooms",
    "bathrooms",
    "is_smoking_allowed",
    "is_pets_allowed",
  ].some((param) => urlParams.has(param));

  if (hasFilters) {
    document.getElementById("filter-panel")?.classList.add("show");
  }
});
