let calendar = null;

function copyShareLink() {
  const input = document.getElementById("share-link");
  input.select();
  input.setSelectionRange(0, 99999);
  document.execCommand("copy");
}

document.addEventListener("DOMContentLoaded", function () {
  const logements = JSON.parse(
    document.getElementById("logements-data").textContent
  );

  const selector = document.getElementById("logement-selector");
  const calendarEl = document.getElementById("calendar");

  let selectedStart = null;
  let selectedEnd = null;
  let reservedDates = new Set();
  let dailyPriceMap = {};
  let dailyStatutMap = {};
  axios.defaults.headers.common["X-CSRFToken"] = csrfToken;
  axios.defaults.headers.post["Content-Type"] = "application/json";

  function initCalendar(logementId) {
    if (calendar) {
      calendar.destroy(); // clean existing calendar
    }
    calendar = new FullCalendar.Calendar(calendarEl, {
      initialView: "dayGridMonth",
      height: "auto",
      locale: "fr",
      selectable: true,
      selectLongPressDelay: 0, // 👈 ensures fast response on touch
      selectMirror: true,

      events: function (fetchInfo, successCallback, failureCallback) {
        const params = new URLSearchParams({
          logement_id: logementId,
          start: fetchInfo.startStr,
          end: fetchInfo.endStr,
        });

        reservedDates.clear();

        axios
          .get(`/admin-area/prices/?${params.toString()}`)
          .then((res) => {
            logToServer(
              "info",
              "Chargement des données de prix et réservations réussi",
              {
                logementId: logementId,
                start: fetchInfo.startStr,
                end: fetchInfo.endStr,
              }
            );

            // 1. Daily Prices (background display)
            const priceEvents = res.data.data.map((e) => ({
              start: e.date,
              display: "background",
              className: "fc-event-price",
              title: `${parseFloat(e.price).toFixed(2)} €`,
            }));

            // 2. Internal reservations
            const bookings = res.data.data_bookings.map((b) => ({
              start: b.start,
              end: b.end,
              title: `${b.name} • ${b.guests} guests - ${b.total_price}€`,
              className: "booking-event internal",
            }));

            // 3. Airbnb
            const airbnbBookings = res.data.airbnb_bookings.map((b) => ({
              start: b.start,
              end: b.end,
              title: `Airbnb`,
              className: "booking-event airbnb",
            }));

            // 4. Booking.com
            const bookingBookings = res.data.booking_bookings.map((b) => ({
              start: b.start,
              end: b.end,
              title: `Booking.com`,
              className: "booking-event bookingcom",
            }));

            // 5. Closed Days
            const closedEvents = res.data.closed_days.map((c) => ({
              start: c.date,
              display: "background",
              className: "fc-day-closed", // 👈 style spécial
            }));

            dailyPriceMap = {};
            res.data.data.forEach((e) => {
              dailyPriceMap[e.date] = parseFloat(e.price);
            });

            dailyStatutMap = {};
            res.data.data.forEach((e) => {
              dailyStatutMap[e.date] = parseInt(e.statut);
            });

            function addReservedRange(start, end) {
              const current = new Date(start);
              const endDate = new Date(end);
              while (current < endDate) {
                reservedDates.add(current.toISOString().split("T")[0]);
                current.setDate(current.getDate() + 1);
              }
            }

            // Ajoute les jours réservés
            res.data.data_bookings.forEach((b) =>
              addReservedRange(b.start, b.end)
            );
            res.data.airbnb_bookings.forEach((b) =>
              addReservedRange(b.start, b.end)
            );
            res.data.booking_bookings.forEach((b) =>
              addReservedRange(b.start, b.end)
            );

            successCallback([
              ...priceEvents,
              ...closedEvents,
              ...bookings,
              ...airbnbBookings,
              ...bookingBookings,
            ]);
          })
          .catch((error) => {
            logToServer(
              "error",
              "Échec du chargement des événements du calendrier : " + error,
              {
                logementId: logementId,
                start: fetchInfo.startStr,
                end: fetchInfo.endStr,
              }
            );
            failureCallback(error);
          });
      },
      select: function (selectionInfo) {
        // Check if range is reserved
        if (isReservedRange(selectionInfo.startStr, selectionInfo.endStr)) {
          logToServer(
            "warning",
            "Conflit détecté dans la plage de dates sélectionnée",
            {
              logementId: logementId,
              start: selectionInfo.startStr,
              end: selectionInfo.endStr,
            }
          );
          alert("❌ La plage sélectionnée contient des dates réservées.");
          hidePanel();
          return;
        }

        showPanel(selectionInfo.startStr, selectionInfo.endStr);
      },

      eventDidMount: function (info) {
        if (info.event.classNames.includes("fc-event-price")) {
          info.el.innerHTML = `<div class="fc-event-price">${info.event.title}</div>`;
          return;
        }

        if (info.event.classNames.includes("discount-event")) {
          info.el.innerHTML = `<div class="discount-label">${info.event.title}</div>`;
          return;
        }

        if (info.event.classNames.includes("booking-event")) {
          let content = `<span class="booking-span">${info.event.title}</span>`;

          if (info.event.extendedProps.avatar) {
            content = `<img src="${info.event.extendedProps.avatar}" alt="avatar" style="width:22px;height:22px;border-radius:50%;margin-right:6px;"> ${content}`;
          }

          info.el.innerHTML = content;

          // ✅ Tooltip content
          let tooltipText = `
            <strong>Source :</strong> ${getSourceLabel(
              info.event.classNames
            )}<br>
            <strong>Nom :</strong> ${info.event.title}<br>
            <strong>Début :</strong> ${info.event.start.toLocaleDateString()}<br>
            <strong>Fin :</strong> ${
              info.event.end
                ? new Date(
                    info.event.end.getTime() - 86400000
                  ).toLocaleDateString()
                : ""
            }<br>
          `;

          tippy(info.el, {
            content: tooltipText,
            allowHTML: true,
            theme: "light-border",
            placement: "top",
          });
        }

        function getSourceLabel(classList) {
          if (classList.includes("airbnb")) return "Airbnb";
          if (classList.includes("bookingcom")) return "Booking.com";
          return "Réservation interne";
        }
      },
    });

    calendar.render();
  }

  // Init first calendar
  initCalendar(selector.value);

  // Change logement calendar on selector change
  selector.addEventListener("change", function () {
    const selectedId = this.value;
    const logement = logements.find((l) => l.id == selectedId);
    if (logement) {
      document.getElementById("share-link").value = logement.calendar_link;
    }
    initCalendar(this.value);
  });

  // Helper pour décrémenter la date de fin d’un jour (car FullCalendar donne une fin exclusive)
  function dayBefore(dateStr) {
    const date = new Date(dateStr);
    date.setDate(date.getDate() - 1);
    return date.toISOString().split("T")[0];
  }

  function showPanel(startStr, endStr = null) {
    selectedStart = startStr;
    selectedEnd = endStr;

    document.querySelector(".calendar-wrapper").classList.add("with-panel");
    document.getElementById("price-panel").classList.remove("hidden");

    document.getElementById("panel-dates").innerText = endStr
      ? `Du ${startStr} au ${dayBefore(endStr)}`
      : `Date : ${startStr}`;

    let price = 0;
    let statut = 1;
    let priceDetails = []; // Store the breakdown of price calculation steps

    if (!endStr) {
      // Single date
      price = dailyPriceMap[startStr] || 0;
      statut = dailyStatutMap[startStr] || 1;
    } else {
      // Multiple days: min price
      const start = new Date(startStr);
      const end = new Date(endStr);
      let minPrice = Infinity;
      let hasClosedDay = false;

      for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
        const key = d.toISOString().split("T")[0];
        if (dailyPriceMap[key] !== undefined) {
          const current = parseFloat(dailyPriceMap[key]);
          if (current < minPrice) minPrice = current;
        }
        if (dailyStatutMap[key] === 0) {
          hasClosedDay = true;
        }
      }

      price = minPrice !== Infinity ? minPrice : 0;
      statut = hasClosedDay ? 0 : 1;
    }

    // Show base price
    let basePrice = price;
    priceDetails.push({
      type: "Base Price",
      value: basePrice,
    });
    document.getElementById("base-price").value = basePrice.toFixed(2);
    document.getElementById("statut").value = statut;

    updateFinalPrice();

    setTimeout(() => calendar.updateSize(), 10);
  }

  function hidePanel() {
    document.getElementById("price-panel").classList.add("hidden");
    document.querySelector(".calendar-wrapper").classList.remove("with-panel");
    setTimeout(() => calendar.updateSize(), 10);
  }

  // Calcul automatique
  document.getElementById("base-price").addEventListener("input", function () {
    // Get the updated base price
    const base_price = parseFloat(this.value);
    const guestCount = parseFloat(document.getElementById("guest-count").value);

    // Call the calculatePrice function with the updated base price
    updateFinalPrice(base_price, guestCount);
  });

  function updateFinalPrice(updatedBasePrice, guestCount) {
    // If guestCount is not provided or is falsy (null, undefined, 0, etc.), set it to 1
    if (!guestCount) {
      guestCount = 1;
    }
    axios
      .post("/admin-area/prices/calculate_price/", {
        logement_id: selector.value,
        start: selectedStart,
        end: selectedEnd || selectedStart,
        base_price: updatedBasePrice,
        guests: guestCount, // Send the number of guests to the backend
      })
      .then((response) => {
        logToServer("info", "Calcul du prix réussi", {
          logementId: selector.value,
          start: selectedStart,
          end: selectedEnd || selectedStart,
          guests: guestCount,
          base_price: updatedBasePrice,
          final_price: response.data.final_price,
        });

        const finalPrice = response.data.final_price;
        const details = response.data.details;

        // Update the final price in the UI
        document.getElementById("final-price").innerText =
          finalPrice.toFixed(2);

        // Display detailed breakdown in a list
        const detailsContainer = document.getElementById("details");
        detailsContainer.innerHTML = ""; // Clear any existing details

        // Create the section header (optional)
        const detailH5 = document.createElement("h5");
        const strong = document.createElement("strong");
        strong.innerText = "Détails";
        detailH5.appendChild(strong);
        detailsContainer.appendChild(detailH5);

        const guestDiv = document.createElement("div");
        guestDiv.innerHTML = `
          <label for="guest-count">Nombre de personnes</label>
          <input type="number" id="guest-count" value="${guestCount}" step="1" min="1">
        `;
        detailsContainer.appendChild(guestDiv);

        // Attach the change event listener to the guest count input field
        document
          .getElementById("guest-count")
          .addEventListener("input", function () {
            const guestCount = parseInt(this.value, 10); // Get the number of guests
            const base_price = parseFloat(
              document.getElementById("base-price").value
            );
            updateFinalPrice(base_price, guestCount); // Call the function to recalculate the price
          });

        // Create an unordered list to contain the details
        const detailsList = document.createElement("ul");
        detailsList.classList.add("price-details-list");

        // Iterate over the details and create a list item for each one
        for (const [key, value] of Object.entries(details)) {
          const listItem = document.createElement("li");
          listItem.classList.add("price-breakdown-item");

          // Set the content of each list item
          listItem.innerHTML = `<strong>${key}:</strong> ${value}`;

          // Append the list item to the list
          detailsList.appendChild(listItem);
        }

        // Append the list to the container
        detailsContainer.appendChild(detailsList);
      })
      .catch((error) => {
        logToServer("error", "Erreur lors du calcul du prix : " + error, {
          logementId: selector.value,
          start: selectedStart,
          end: selectedEnd || selectedStart,
          guests: guestCount,
          base_price: updatedBasePrice,
        });
      });
  }

  function isReservedRange(startStr, endStr) {
    const start = new Date(startStr);
    const end = new Date(endStr);
    for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
      const dStr = d.toISOString().split("T")[0];
      if (reservedDates.has(dStr)) {
        return true;
      }
    }
    return false;
  }

  // Appliquer
  document.getElementById("apply-price").addEventListener("click", () => {
    const price = document.getElementById("base-price").value;
    const statut = parseInt(document.getElementById("statut").value);

    const payload = {
      logement_id: selector.value,
      price: price,
      statut: statut,
      start: selectedStart,
      end: selectedEnd ? dayBefore(selectedEnd) : selectedStart,
    };

    const url = "/admin-area/prices/bulk_update/";
    const method = "post";

    axios[method](url, payload)
      .then(() => {
        calendar.refetchEvents();
        hidePanel();
      })
      .catch((error) => {
        logToServer(
          "error",
          "Erreur lors de l'application du prix : " + error,
          {
            logementId: selector.value,
            payload: payload,
          }
        );
      });
  });

  // Annuler
  document.getElementById("cancel-price").addEventListener("click", hidePanel);

  const resizeObserver = new ResizeObserver(() => {
    calendar.updateSize();
  });
  resizeObserver.observe(document.querySelector(".calendar-wrapper"));
});
