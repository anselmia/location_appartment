let isReservationValid = false;
let isStartDatePicked = false;
let isEndDatePicked = false;
let userTouchedStart = false;
let userTouchedEnd = false;
let fieldsPrefilled = false;

document.addEventListener('DOMContentLoaded', function () {
    const formStart = document.getElementById('id_start');
    const formEnd = document.getElementById('id_end');
    const formGuest = document.getElementById('id_guest');
    const logementId = logement_js.id; // Get the logement ID from Django context

    if (formStart.value && formEnd.value) {
        isStartDatePicked = true;
        isEndDatePicked = true;
        fieldsPrefilled = true; // ✅ mark them as prefilled
        updateFinalPrice();
    }

    function resetReservation() {
        formStart.value = '';
        formEnd.value = '';

        document.getElementById('start-date').innerText = '';
        document.getElementById('end-date').innerText = '';
        document.getElementById('final-price').innerText = '0.00';
        document.getElementById('reservation-price').value = '0.00';
        document.getElementById('details').innerHTML = '';

        // Disable submit button
        document.getElementById('submit-booking').disabled = true;

        isReservationValid = false;
    }

    function datesReady() {
        const startDateStr = formStart.value;
        const endDateStr = formEnd.value;

        if (!startDateStr || !endDateStr) return false;

        const startDate = new Date(startDateStr);
        const endDate = new Date(endDateStr);

        if (isNaN(startDate) || isNaN(endDate)) return false;

        return true;
    }

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
                        alert('❌ Les dates sont déjà réservées. Veuillez sélectionner de nouvelles dates.');
                        resetReservation();
                        resolve(false);
                    }
                })
                .catch(err => {
                    logToServer("error", "Erreur lors de la vérification de disponibilité : " + err, {
                        start: startDate,
                        end: endDate,
                        logementId: logementId
                    });
                    reject(err);
                });
        });
    }

    function updateFinalPrice() {
        if (
            (!isStartDatePicked || !isEndDatePicked) &&
            !fieldsPrefilled &&
            !(userTouchedStart && userTouchedEnd)
        ) {
            isReservationValid = false;
            document.getElementById('submit-booking').disabled = true;
            return;
        }

        // Wait until both date fields are filled and valid
        if (!datesReady()) {
            isReservationValid = false;
            document.getElementById('submit-booking').disabled = true;
            return;
        }

        const startDateStr = formStart.value;
        const endDateStr = formEnd.value;
        // If guestCount is not provided or is falsy (null, undefined, 0, etc.), set it to 1
        const guestCount = parseInt(formGuest.value, 10) || 1;
        const startDate = new Date(startDateStr);
        const endDate = new Date(endDateStr);


        // Vérifie si les dates sont valides
        if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
            alert("❌ Les dates sélectionnées ne sont pas valides.");
            logToServer("error", "Les dates sélectionnées ne sont pas valides.", {
                start: startDate,
                end: endDate,
                logementId: logementId
            });
            resetReservation();
            return;
        }

        // Vérifie l'ordre chronologique
        if (startDate >= endDate) {
            alert("❌ La date de fin doit être après la date de début.");
            resetReservation();
            logToServer("error", "La date de fin doit être après la date de début.", {
                start: startDate,
                end: endDate,
                logementId: logementId
            });
            return;
        }

        // Vérifie que ce ne soit pas le même jour
        if (startDate.toDateString() === endDate.toDateString()) {
            alert("❌ La date de début et la date de fin ne peuvent pas être identiques.");
            resetReservation();
            logToServer("error", "La date de début et la date de fin ne peuvent pas être identiques.", {
                start: startDate,
                end: endDate,
                logementId: logementId
            });
            return;
        }

        if (!guestCount || guestCount <= 0) {
            alert("Nombre d'invités invalide.");
            logToServer("error", "Nombre d'invités invalide", {
                guestInput: formGuest.value,
                logementId: logementId
            });
            formGuest.value = 1;
            return;
        }

        // Check if the selected dates are available
        isDateBooked(formStart.value, formEnd.value)
            .then((available) => {
                if (!available) {
                    // Rien à faire, resetReservation() a déjà été appelée dans isDateBooked
                    return;
                }
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

                        logToServer("info", "Prix calculé avec succès", {
                            finalPrice: finalPrice,
                            start: startDateStr,
                            end: endDateStr,
                            guests: guestCount,
                            logementId: logementId
                        });

                        document.getElementById('submit-booking').disabled = false;
                    })
                    .catch(error => {
                        resetReservation();
                        logToServer("error", "Erreur lors du calcul du prix" + error, {
                            start: startDate,
                            end: endDate,
                            logementId: logementId
                        });
                    });
            });
    }

    document.getElementById("reservation-form").addEventListener("submit", function (e) {
        e.preventDefault(); // Prevent default immediately
        updateFinalPrice(); // run validation one last time

        // Delay a little to wait for async availability check
        setTimeout(() => {
            if (isReservationValid) {
                logToServer("info", "Soumission du formulaire de réservation validée", {
                    start: formStart.value,
                    end: formEnd.value,
                    guests: parseInt(formGuest.value, 10),
                    logementId: logementId
                });

                e.target.submit();
            }
        }, 200); // adjust if needed
    });

    function debounce(fn, delay) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    const debouncedUpdatePrice = debounce(updateFinalPrice, 300);
    // Recalculate the price on input change

    formStart.addEventListener('change', function () {
        if (formStart.value) {
            isStartDatePicked = true;
            userTouchedStart = true;
            if (datesReady()) {
                updateFinalPrice();
            }
        } else {
            isStartDatePicked = false;
            userTouchedStart = false;
        }
    });

    formEnd.addEventListener('change', function () {
        if (formEnd.value) {
            isEndDatePicked = true;
            userTouchedEnd = true;
            if (datesReady()) {
                updateFinalPrice();
            }
        } else {
            isEndDatePicked = false;
            userTouchedEnd = false;
        }
    });

    function validateGuestInput() {
        const guestValue = formGuest.value.trim();
        const guestNumber = parseInt(guestValue, 10);

        // Empty, not a number, negative, zero, float, or too large
        if (
            !guestValue ||
            isNaN(guestNumber) ||
            guestNumber <= 0 ||
            guestValue.includes('.') ||
            guestNumber > logement_js.max_traveler
        ) {
            alert("❌ Veuillez entrer un nombre valide de voyageurs (entre 1 et " + logement_js.max_traveler +").");
            formGuest.value = 1;
            return false;
        }

        return true;
    }

    formGuest.addEventListener('change', function () {
        if (validateGuestInput()) {
            updateFinalPrice();
        }
    });

    formGuest.addEventListener('input', function () {
        if (validateGuestInput()) {
            debouncedUpdatePrice();
        }
    });

    const stripe = Stripe(stripe_public_key);

    formStart.addEventListener('input', function () {
        if (formStart.value) {
            isStartDatePicked = true;
            userTouchedStart = true;
            if (datesReady()) {
                updateFinalPrice();
            }
        } else {
            isStartDatePicked = false;
            userTouchedStart = false;
        }
    });

    formEnd.addEventListener('input', function () {
        if (formEnd.value) {
            isEndDatePicked = true;
            userTouchedEnd = true;
            if (datesReady()) {
                updateFinalPrice();
            }
        } else {
            isEndDatePicked = false;
            userTouchedEnd = false;
        }
    });
});