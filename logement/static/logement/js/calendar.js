function setupFlatpickr(id) {
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

    flatpickr("#calendar_inline", {
        mode: "range",
        inline: true,
        minDate: today, // Use the adjusted "today" date based on user's timezone
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
    });
}

document.addEventListener('DOMContentLoaded', () => {
    setupFlatpickr("#calendar_range");
});


document.querySelector(".booking-form").addEventListener("submit", function (e) {
    const rangeInput = document.getElementById("calendar_range").value;

    // Ensure both start and end dates are selected
    if (!rangeInput.includes(" to ")) {
        e.preventDefault();
        alert("❌ Vous devez sélectionner une plage de dates.");
        return;
    }

    const [start, end] = rangeInput.split(" to ");
    const startDate = new Date(start);
    const endDate = new Date(end);

    // Ensure start date is before end date
    if (startDate > endDate) {
        e.preventDefault();
        alert("❌ La date de début ne peut pas être après la date de fin.");
        return;
    }

    // Ensure start date is before end date
    if ((endDate == startDate)) {
        e.preventDefault();
        alert("❌ La date de fin ne peut pas être après le même jour que la date de début.");
        return;
    }

    const booked = reservedDates.some(dateStr => {
        const reserved = new Date(dateStr);
        return reserved >= startDate && reserved <= endDate;
    });

    if (booked) {
        e.preventDefault();
        alert("❌ La période sélectionnée contient des dates déjà réservées.");
    }

    // Add start_date and end_date as hidden fields to the form before submitting
    document.getElementById("id_start").value = startDate.toISOString().split('T')[0]; // Format to YYYY-MM-DD
    document.getElementById("id_end").value = endDate.toISOString().split('T')[0]; // Format to YYYY-MM-DD

});