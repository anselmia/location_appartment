let reservedDates;
const startInput = document.getElementById("id_start");
const endInput = document.getElementById("id_end");

function setupFlatpickr(id) {
  const isCalendarDisabled =
    typeof calendarDisabled !== "undefined" ? calendarDisabled : false;
  if (isCalendarDisabled === true) {
    document
      .querySelector("#calendar_inline")
      .classList.add("calendar-disabled");
  }

  // 🗓️ Compute the booking limit
  const limitInMonths = parseInt(periodLimit); // e.g. "6"
  const maxDate = new Date(today);

  maxDate.setMonth(maxDate.getMonth() + limitInMonths);

  function formatLocalDate(date) {
    if (!(date instanceof Date)) {
      date = new Date(date); // convert from string if necessary
    }
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0"); // months are 0-indexed
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  const config = {
    mode: "range",
    inline: true,
    minDate: today, // Use the adjusted "today" date based on user's timezone
    maxDate: maxDate,
    disable: [], // Disable the reserved dates
    locale: {
      firstDayOfWeek: 1,
      weekdays: {
        shorthand: ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"],
        longhand: [
          "Dimanche",
          "Lundi",
          "Mardi",
          "Mercredi",
          "Jeudi",
          "Vendredi",
          "Samedi",
        ],
      },
      months: {
        shorthand: [
          "Janv",
          "Févr",
          "Mars",
          "Avr",
          "Mai",
          "Juin",
          "Juil",
          "Août",
          "Sept",
          "Oct",
          "Nov",
          "Déc",
        ],
        longhand: [
          "Janvier",
          "Février",
          "Mars",
          "Avril",
          "Mai",
          "Juin",
          "Juillet",
          "Août",
          "Septembre",
          "Octobre",
          "Novembre",
          "Décembre",
        ],
      },
      today: "Aujourd'hui",
      clear: "Effacer",
      monthsTitle: "Mois",
      weekAbbreviation: "Sem",
      rangeSeparator: " au ",
      scrollTitle: "Défiler pour augmenter",
      toggleTitle: "Cliquer pour basculer",
      time_24hr: true,
    },
    onDayCreate: function (_, __, ___, dayElem) {
      const date = formatLocalDate(dayElem.dateObj); // Get the current date in YYYY-MM-DD

      if (reservedDatesStart.includes(date)) {
        dayElem.classList.add("no-start");
      }

      if (reservedDatesEnd.includes(date)) {
        dayElem.classList.add("no-end");
      }

      if (reservedDatesStart.includes(date)) {
        dayElem.classList.add("booked-day"); // Apply booked class
      } else if (date === today) {
        dayElem.classList.add("today-day"); // Apply today class
      } else {
        dayElem.classList.add("free-day"); // Apply free class
      }
    },
    onChange: function (selectedDates, dateStr, instance) {
      // Remove all custom .selected from previous range
      document
        .querySelectorAll(".flatpickr-day.selected-custom")
        .forEach((el) => el.classList.remove("selected-custom"));
      if (selectedDates.length !== 2) {
        return;
      }
      const Selectedstart = selectedDates[0];
      const Selectedend = selectedDates[1];
      // Loop through all day elements
      document.querySelectorAll(".flatpickr-day").forEach((dayElem) => {
        const dayDate = dayElem.dateObj;
        if (!dayDate) return;
        // Mark all days in the range (including start and end)
        if (dayDate >= Selectedstart && dayDate <= Selectedend) {
          dayElem.classList.add("selected-custom");
        } else {
          dayElem.classList.remove("selected-custom");
        }
      });

      const startStr = formatLocalDate(selectedDates[0]);
      const endStr = formatLocalDate(selectedDates[1]);

      if (reservedDatesStart.includes(startStr)) {
        alert("Ce jour ne peut pas être sélectionné comme date de début.");
        instance.clear();
        return;
      }

      if (reservedDatesEnd.includes(endStr)) {
        alert("Ce jour ne peut pas être sélectionné comme date de fin.");
        instance.clear();
        return;
      }

      // Check for blocked intermediate dates
      let current = new Date(startStr);
      current.setHours(0, 0, 0, 0);
      current.setDate(current.getDate() + 1);
      const end = new Date(endStr);
      end.setHours(0, 0, 0, 0);

      while (current < end) {
        const currentStr = current.toISOString().slice(0, 10);
        if (reservedDatesStart.includes(currentStr)) {
          alert(
            "Une ou plusieurs dates dans la plage sélectionnée ne sont pas disponibles."
          );
          instance.clear();
          return;
        }
        current.setDate(current.getDate() + 1);
      }

      startInput.value = startStr;
      endInput.value = endStr;

      endInput.dispatchEvent(new Event("change", { bubbles: true }));

      // ✅ Safely trigger price update logic if available
      if (
        typeof window.validateGuestInput === "function" &&
        window.validateGuestInput()
      ) {
        if (typeof window.updateFinalPrice === "function") {
          window.updateFinalPrice();
        }
      }
    },
  };

  if (isCalendarDisabled === true) {
    config.enable = []; // Disable all selectable dates
  }

  flatpickr("#calendar_inline", config);
}

document.addEventListener("DOMContentLoaded", () => {
  const panel = document.getElementById("bookingPanel");
  const toggleBtn = document.getElementById("bookingToggle");

  if (panel && toggleBtn) {
    toggleBtn.addEventListener("click", function () {
      const isCollapsed = bookingPanel.classList.toggle("collapsed");
      if (isCollapsed) {
        toggleBtn.innerHTML = "Réserver";
        toggleBtn.classList.remove("open");
      } else {
        toggleBtn.innerHTML = "→"; // « symbol
        toggleBtn.classList.add("open");
      }
    });
  }

  const calendarEl = document.querySelector("#calendar_inline");
  if (calendarEl) {
    setupFlatpickr("#calendar_range");
  }
});

const bookingForm = document.querySelector(".booking-form");
if (bookingForm) {
  bookingForm.addEventListener("submit", function (e) {
    const rangeInput = document.getElementById("calendar_range").value;

    if (!rangeInput.includes(" to ")) {
      logToServer("warning", "Soumission sans plage de dates sélectionnée", {
        formValue: rangeInput,
      });
      e.preventDefault();
      alert("❌ Vous devez sélectionner une plage de dates.");
      return;
    }

    const [start, end] = rangeInput.split(" to ");
    const startDate = new Date(start);
    const endDate = new Date(end);

    if (startDate > endDate) {
      logToServer("warning", "Date de début après date de fin", {
        start: start,
        end: end,
      });
      e.preventDefault();
      alert("❌ La date de début ne peut pas être après la date de fin.");
      return;
    }

    if (endDate.getTime() === startDate.getTime()) {
      logToServer("warning", "Dates identiques sélectionnées", {
        start: start,
        end: end,
      });
      e.preventDefault();
      alert(
        "❌ La date de fin ne peut pas être le même jour que la date de début."
      );
      return;
    }

    const booked = reservedDates.some((dateStr) => {
      const reserved = new Date(dateStr);
      return reserved >= startDate && reserved <= endDate;
    });

    if (booked) {
      logToServer(
        "warning",
        "Tentative de réservation sur dates déjà réservées",
        {
          start: start,
          end: end,
          logementId: logementId,
        }
      );
      e.preventDefault();
      alert("❌ La période sélectionnée contient des dates déjà réservées.");
      return;
    }

    document.getElementById("id_start").value = startDate
      .toISOString()
      .split("T")[0];
    document.getElementById("id_end").value = endDate
      .toISOString()
      .split("T")[0];
  });
}
