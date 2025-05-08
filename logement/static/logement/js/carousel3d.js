// Functions 
let currentIndex = 0;
let selectedRoom = 'all'; // Default to showing all items
let filteredItems = []; // List of items after filtering by room

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

function positionItems() {
    // Loop through filtered items and apply the active, prev, and next classes
    filteredItems.forEach((item, index) => {
        item.classList.remove("active", "prev", "next", "hidden");

        if (index === currentIndex) {
            item.classList.add("active");
        } else if (index === (currentIndex - 1 + filteredItems.length) % filteredItems.length) {
            item.classList.add("prev");
        } else if (index === (currentIndex + 1) % filteredItems.length) {
            item.classList.add("next");
        } else {
            item.classList.add("hidden");
        }
    });
}

function rotate(indexDelta) {
    if (filteredItems.length === 0) return; // No filtered items available

    // Update the currentIndex based on the filtered items length
    currentIndex = (currentIndex + indexDelta + filteredItems.length) % filteredItems.length;
    updateClasses(); // Re-apply the active, prev, next classes based on updated currentIndex
}

function isMobile() {
    return window.innerWidth <= 768;
}

function updateClasses() {
    items.forEach(item => {
        item.classList.remove("active", "prev", "next", "hidden", "fade-out");
    });
    
    // Desktop logic
    filteredItems.forEach((item, index) => {
        item.style.display = 'block';
        if (index === currentIndex) {
            item.classList.add("active");
        } else if (index === (currentIndex + 1) % filteredItems.length) {
            item.classList.add("next");
        } else if (index === (currentIndex - 1 + filteredItems.length) % filteredItems.length) {
            item.classList.add("prev");
        }
    });

    items.forEach(item => {
        if (!filteredItems.includes(item)) {
            item.style.display = 'none';
        }
    });
    
}

document.addEventListener('DOMContentLoaded', () => {
    carousel = document.getElementById('carousel3d');
    items = carousel.querySelectorAll('.carousel-item3d');
    total = items.length;

    // Set initial filtered items to all items (no filter)
    filteredItems = Array.from(items);

    document.getElementById('left-arrow').addEventListener('click', () => rotate(-1));
    document.getElementById('right-arrow').addEventListener('click', () => rotate(1));

    positionItems(); // applies transform + classes
    setupFlatpickr("#calendar_range");
});

document.querySelectorAll('.carousel-item3d img').forEach(img => {
    img.addEventListener('click', () => {
        document.getElementById('modalImage').src = img.src;
        document.getElementById('imageModal').style.display = "flex"; // Use flex for centering
    });
});

const filterButtons = document.querySelectorAll('.room-filter-button');
filterButtons.forEach(button => {
    button.addEventListener('click', function () {
        // Reset active state of filter buttons
        filterButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active'); // Add active class to the selected button

        const roomFilter = button.getAttribute('data-room');
        selectedRoom = roomFilter; // Set the selected room

        // Filter items based on the selected room
        filteredItems = Array.from(items).filter(item => selectedRoom === 'all' || item.classList.contains(selectedRoom));

        // Reset current index and position the items again
        currentIndex = 0; // Start from the first photo in the selected room
        positionItems(); // Apply new filter and re-position items
        updateClasses();
    });
});

const select = document.getElementById("room-filter-select");
    if (select) {
        select.addEventListener("change", function () {
            const selectedRoom = this.value;

            // Filter items based on the selected room
            filteredItems = Array.from(items).filter(item => selectedRoom === 'all' || item.classList.contains(selectedRoom));

            // Reset current index and position the items again
            currentIndex = 0; // Start from the first photo in the selected room
            positionItems(); // Apply new filter and re-position items
            updateClasses();
        });
    }

document.getElementById('closeModal').addEventListener('click', () => {
    document.getElementById('imageModal').style.display = "none";
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
    document.getElementById("id_end").value = endDate.toISOString().split('T')[0];   // Format to YYYY-MM-DD

});