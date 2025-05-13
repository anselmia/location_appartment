let isReservationValid = false;

document.addEventListener('DOMContentLoaded', function () {
    const formStart = document.getElementById('id_start');
    const formEnd = document.getElementById('id_end');
    const formGuest = document.getElementById('id_guest');
    const logementId = logement_js.id; // Get the logement ID from Django context

    // Function to check if the dates are already booked
    function isDateBooked(startDate, endDate) {
        const url = reservationId ?
            `/api/check_availability/${logementId}?start=${startDate}&end=${endDate}&reservation_id=${reservationId}` :
            `/api/check_availability/${logementId}?start=${startDate}&end=${endDate}`;
        return new Promise((resolve, reject) => {
            fetch(url)
                .then(response => response.json())
                .then(data => {
                    if (data.available) {
                        resolve(true);
                    } else {
                        reject('Les dates sont déjà réservées. Veuillez sélectionner de nouvelles dates.');
                    }
                })
                .catch(err => reject('Error checking availability'));
        });
    }

    function updateFinalPrice() {
        const startDateStr = formStart.value;
        const endDateStr = formEnd.value;
        // If guestCount is not provided or is falsy (null, undefined, 0, etc.), set it to 1
        const guestCount = parseInt(formGuest.value, 10) || 1;

        if (!startDateStr || !endDateStr) {
            return;
        }

        const startDate = new Date(startDateStr);
        const endDate = new Date(endDateStr);

        // Vérifie si les dates sont valides
        if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
            alert("❌ Les dates sélectionnées ne sont pas valides.");
            isReservationValid = false;
            return;
        }

        // Vérifie l'ordre chronologique
        if (startDate >= endDate) {
            alert("❌ La date de fin doit être après la date de début.");
            formStart.value = "";
            formEnd.value = "";
            isReservationValid = false;
            return;
        }

        // Vérifie que ce ne soit pas le même jour
        if (startDate.toDateString() === endDate.toDateString()) {
            alert("❌ La date de début et la date de fin ne peuvent pas être identiques.");
            formStart.value = "";
            formEnd.value = "";
            isReservationValid = false;
            return;
        }


        if (!guestCount || guestCount <= 0) {
            alert("Please enter a valid number of guests.");
            formGuest.value = 1;
            return;
        }

        // Check if the selected dates are available
        isDateBooked(formStart.value, formEnd.value)
            .then(() => {
                // Update the reservation summary dynamically
                document.getElementById('start-date').innerText = formStart.value; // Update start date in summary
                document.getElementById('end-date').innerText = formEnd.value; // Update end date in summary
                document.getElementById('guest-count').innerText = guestCount;
                axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
                axios.post('/admin-area/prices/calculate_price/', {
                        logement_id: logementId,
                        start: startDate.toISOString().split('T')[0],
                        end: endDate.toISOString().split('T')[0],
                        guests: parseInt(guestCount, 10) // Send the number of guests to the backend
                    })
                    .then(response => {
                        const finalPrice = response.data.final_price;
                        const details = response.data.details;

                        // Update the final price in the UI
                        document.getElementById('final-price').innerText = finalPrice.toFixed(2);
                        document.getElementById('reservation-price').value = finalPrice.toFixed(2); 

                        // Display detailed breakdown in a list
                        const detailsContainer = document.getElementById('details');
                        detailsContainer.innerHTML = ''; // Clear any existing details

                        // Create the section header (optional)
                        const detailh3 = document.createElement('h4');
                        detailh3.innerText = 'Détails du Prix';
                        detailh3.classList.add('text-center');
                        detailh3.classList.add('mb-4');
                        detailsContainer.appendChild(detailh3);


                        // Iterate over the details and create a list item for each one
                        for (const [key, value] of Object.entries(details)) {
                            const listItem = document.createElement('p');

                            // Set the content of each list item
                            listItem.innerHTML = `<strong>${key}:</strong> ${value}`;

                            // Append the list item to the list
                            detailsContainer.appendChild(listItem);
                        }

                        isReservationValid = true;
                    })
                    .catch(error => {
                        console.error('Error fetching price calculation:', error);
                        isReservationValid = false;
                    });
            })
            .catch(error => {
                alert(error);
                isReservationValid = false;
            });
    }

    // Trigger calculation when parameters are valid on page load
    if (formStart.value && formEnd.value && formGuest.value) {
        updateFinalPrice();
    }

    document.getElementById("reservation-form").addEventListener("submit", function (e) {
        e.preventDefault(); // Prevent default immediately
        updateFinalPrice(); // run validation one last time

        // Delay a little to wait for async availability check
        setTimeout(() => {
            if (isReservationValid) {
                e.target.submit();
            }
        }, 200); // adjust if needed
    });

    function debounce(fn, delay) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => fn.apply(this, args), delay);
        };
    }
    
    const debouncedUpdatePrice = debounce(updateFinalPrice, 300);
    // Recalculate the price on input change

    formStart.addEventListener('change', updateFinalPrice);
    formEnd.addEventListener('change', updateFinalPrice);
    formGuest.addEventListener('change', updateFinalPrice);
    formGuest.addEventListener('input', debouncedUpdatePrice); // fires on each keystroke

    const stripe = Stripe(stripe_public_key);
});