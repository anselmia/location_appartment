let reservedDates;
const startInput = document.getElementById("id_start");
const endInput = document.getElementById("id_end");

document.addEventListener("DOMContentLoaded", function () {
  const calendarBlock = document.getElementById("calendar_inline");

  // --- Calendar setup (single date selection) ---
  if (calendarBlock) {
    const initialYear = new Date(today).getFullYear();
    const initialMonth = new Date(today).getMonth() + 1;

    fetch(
      `/reservation/not-available-dates/${activityId}/?year=${initialYear}&month=${initialMonth}`
    )
      .then((response) => response.json())
      .then((data) => {
        not_available_date = data.dates || [];

        const config = {
          mode: "single", // Only one date selectable
          inline: true,
          minDate: today,
          disable: [], // Reserved dates if needed
          locale: {
            firstDayOfWeek: 1, // 1 = Monday
          },
          onMonthChange: function (selectedDates, dateStr, instance) {
            const currentMonth = instance.currentMonth + 1; // Flatpickr months are 0-based
            const currentYear = instance.currentYear;
            fetch(
              `/reservation/not-available-dates/${activityId}/?year=${currentYear}&month=${currentMonth}`
            )
              .then((response) => response.json())
              .then((data) => {
                not_available_date = data.dates; // Array of "YYYY-MM-DD"
                // Update the calendar to disable these dates
                instance.set("disable", not_available_date);
                instance.redraw();
              });
          },
          onDayCreate: function (_, __, ___, dayElem) {
            const date = formatLocalDate(dayElem.dateObj); // Get the current date in YYYY-MM-DD

            if (not_available_date.includes(date)) {
              dayElem.classList.add("booked-day"); // Apply booked class
            } else if (date === today) {
              dayElem.classList.add("today-day"); // Apply today class
            } else if (date >= today) {
              dayElem.classList.add("free-day"); // Apply free class
            }
          },
          onChange: function (selectedDates, dateStr, instance) {
            if (selectedDates.length !== 1) return;
            const selectedDate = selectedDates[0];
            const formattedDate = formatLocalDate(selectedDate);

            // AJAX to get slots
            fetchSlots(formattedDate);

            formStart.value = formattedDate;
          },
        };

        flatpickr("#calendar_inline", config);
      });
  }

  function formatLocalDate(date) {
    if (!(date instanceof Date)) {
      date = new Date(date); // convert from string if necessary
    }
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0"); // months are 0-indexed
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  // --- Fetch and display slots ---
  function fetchSlots(dateStr) {
    slotsSection.innerHTML =
      "<div class='text-center my-3'><span class='spinner-border'></span> Chargement des créneaux...</div>";
    fetch(`/reservation/slots/${activityId}/?date=${dateStr}`)
      .then((response) => response.json())
      .then((data) => {
        slotsSection.innerHTML = "";
        if (data.slots && data.slots.length > 0) {
          const slotGroup = document.createElement("div");
          slotGroup.className = "d-flex flex-wrap gap-2 justify-content-center";
          data.slots.forEach((slot) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn slot-btn";
            btn.innerText = slot;
            btn.onclick = function () {
              document.querySelectorAll(".slot-btn").forEach((b) => {
                b.classList.remove("active");
                b.classList.remove("btn-primary");
              });
              btn.classList.add("active");
              btn.classList.add("btn-primary");
              if (slotInput) slotInput.value = slot;
              bookingForm.style.display = "block";
              validateForm();
              updateFinalPrice(); // Ajoutez ceci pour mettre à jour le prix
            };
            slotGroup.appendChild(btn);
          });
          slotsSection.appendChild(slotGroup);
          console.log(
            "Slot buttons rendered:",
            slotsSection,
            slotGroup.children.length
          );
        } else {
          slotsSection.innerHTML =
            "<div class='alert alert-warning text-center'>Aucun créneau disponible ce jour.</div>";
        }
      });
  }
});
