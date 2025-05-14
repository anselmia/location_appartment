function setupFlatpickr(id) {
    const isCalendarDisabled = typeof calendarDisabled !== "undefined" ? calendarDisabled : false;
    if (isCalendarDisabled === true) {
        document.querySelector("#calendar_inline").classList.add("calendar-disabled");
    }

    // Get today's date in the user's local timezone
    const todayDate = new Date(); // This will use the browser's local timezone
    todayDate.setHours(0, 0, 0, 0); // Set time to midnight to avoid timezone issues
    const today = todayDate.toISOString().slice(0, 10); // Format the date to YYYY-MM-DD

    // Convert reserved dates to the same format (YYYY-MM-DD) using local timezone
    const reservedDatesLocal = reservedDates.map(dateStr => {
        const date = new Date(dateStr);
        date.setHours(0, 0, 0, 0); // Set time to midnight to avoid timezone issues
        return date.toISOString().slice(0, 10); // Format reserved date to YYYY-MM-DD
    });

    const config = {
        mode: "range",
        inline: true,
        minDate: todayDate, // Use the adjusted "today" date based on user's timezone
        disable: reservedDatesLocal, // Disable the reserved dates
        onDayCreate: function (_, __, ___, dayElem) {
            const date = dayElem.dateObj.toISOString().slice(0, 10); // Get the current date in YYYY-MM-DD

            if (reservedDatesLocal.includes(date)) {
                dayElem.classList.add("booked-day"); // Apply booked class
            } else if (date === today) {
                dayElem.classList.add("today-day"); // Apply today class
            } else {
                dayElem.classList.add("free-day"); // Apply free class
            }
        },
        onChange: function (selectedDates, dateStr) {
            // Push selected range into hidden input
            document.getElementById("calendar_range").value = dateStr;
        }
    };

    if (isCalendarDisabled === true) {
        config.enable = []; // Disable all selectable dates
    }

    flatpickr("#calendar_inline", config);
}

document.addEventListener('DOMContentLoaded', () => {
    setupFlatpickr("#calendar_range");
});

const bookingForm = document.querySelector(".booking-form");
if (bookingForm) {
    bookingForm.addEventListener("submit", function (e) {
        const rangeInput = document.getElementById("calendar_range").value;

        if (!rangeInput.includes(" to ")) {
            logToServer("warning", "Soumission sans plage de dates sélectionnée", {
                formValue: rangeInput
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
                end: end
            });
            e.preventDefault();
            alert("❌ La date de début ne peut pas être après la date de fin.");
            return;
        }

        if (endDate.getTime() === startDate.getTime()) {
            logToServer("warning", "Dates identiques sélectionnées", {
                start: start,
                end: end
            });
            e.preventDefault();
            alert("❌ La date de fin ne peut pas être le même jour que la date de début.");
            return;
        }

        const booked = reservedDates.some(dateStr => {
            const reserved = new Date(dateStr);
            return reserved >= startDate && reserved <= endDate;
        });

        if (booked) {
            logToServer("warning", "Tentative de réservation sur dates déjà réservées", {
                start: start,
                end: end,
                logementId: logementId
            });
            e.preventDefault();
            alert("❌ La période sélectionnée contient des dates déjà réservées.");
            return;
        }

        document.getElementById("id_start").value = startDate.toISOString().split('T')[0];
        document.getElementById("id_end").value = endDate.toISOString().split('T')[0];
    });
}