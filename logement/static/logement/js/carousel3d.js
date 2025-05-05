// Functions 
let angle = 0;
let currentIndex = 0;

function setupFlatpickr(id) {
    flatpickr("#calendar_inline", {
        mode: "range",
        inline: true,
        minDate: "today",
        disable: reservedDates,
        onDayCreate: function (_, __, ___, dayElem) {
            const date = dayElem.dateObj.toISOString().slice(0, 10);
            if (reservedDates.includes(date)) {
                dayElem.classList.add("booked-day");
            } else if (date === today) {
                dayElem.classList.add("today-day");
            } else {
                dayElem.classList.add("free-day");
            }
        },
        onChange: function (selectedDates, dateStr) {
            // Push selected range into hidden input
            document.getElementById("calendar_range").value = dateStr;
        }
    });
}

function positionItems() {
    items.forEach((item, index) => {
        item.classList.remove("active", "prev", "next");
        if (index === currentIndex) {
            item.classList.add("active");
        } else if (index === (currentIndex - 1 + total) % total) {
            item.classList.add("prev");
        } else if (index === (currentIndex + 1) % total) {
            item.classList.add("next");
        }
    });
}

function rotate(indexDelta) {
    currentIndex = (currentIndex + indexDelta + total) % total;
    updateClasses(); // ⛔ no transform here
}

function updateClasses() {
    items.forEach((item, index) => {
        item.classList.remove("active", "prev", "next", "hidden", "fade-out");

        if (index === currentIndex) {
            item.style.display = 'block';
            item.classList.add("active");
        } else if (index === (currentIndex + 1) % total) {
            item.style.display = 'block';
            item.classList.add("next");
        } else if (index === (currentIndex - 1 + total) % total) {
            item.style.display = 'block';
            item.classList.add("prev");
        } else {
            item.classList.add("fade-out"); // trigger animation
            setTimeout(() => {
                item.classList.add("hidden");
            }, 300); // hide after animation
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    carousel = document.getElementById('carousel3d');
    items = carousel.querySelectorAll('.carousel-item3d');
    total = items.length;

    // Adjust radius based on item count for spread
    radius = 360 + total * 10;

    document.getElementById('left-arrow').addEventListener('click', () => rotate(-1));
    document.getElementById('right-arrow').addEventListener('click', () => rotate(1));

    positionItems(); // applies transform + classes
    setupFlatpickr("#calendar_range");
});



document.querySelectorAll('.carousel-item3d img').forEach(img => {
    img.addEventListener('click', () => {
        document.getElementById('modalImage').src = img.src;
        document.getElementById('imageModal').style.display = "block";
    });
});

const filterButtons = document.querySelectorAll('.room-filter-button');
const carouselItems = document.querySelectorAll('.carousel-item3d');
filterButtons.forEach(button => {
    button.addEventListener('click', function () {
        // Reset active state of filter buttons
        filterButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active'); // Add active class to the selected button

        const roomFilter = button.getAttribute('data-room');

        // Filter carousel items based on the selected room
        carouselItems.forEach(item => {
            if (roomFilter === 'all' || item.classList.contains(roomFilter)) {
                item.style.display = 'block'; // Show the item
            } else {
                item.style.display = 'none'; // Hide the item
            }
        });
    });
});

document.getElementById('closeModal').addEventListener('click', () => {
    document.getElementById('imageModal').style.display = "none";
});

document.querySelector("form").addEventListener("submit", function (e) {
    const rangeInput = document.getElementById("calendar_range").value;
    if (!rangeInput.includes(" to ")) return; // one date selected

    const [start, end] = rangeInput.split(" to ");
    const startDate = new Date(start);
    const endDate = new Date(end);

    const booked = reservedDates.some(dateStr => {
        const reserved = new Date(dateStr);
        return reserved >= startDate && reserved <= endDate;
    });

    if (booked) {
        e.preventDefault();
        alert("❌ La période sélectionnée contient des dates déjà réservées.");
    }
});