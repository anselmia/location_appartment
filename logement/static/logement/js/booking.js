let isReservationValid = false;

document.addEventListener('DOMContentLoaded', function () {
    const formStart = document.getElementById('id_start');
    const formEnd = document.getElementById('id_end');
    const formGuest = document.getElementById('id_guest');
    const logementId = logement_js.id; // Get the logement ID from Django context

    if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
        document.getElementById("visible_start").addEventListener("touchend", function () {
            this._flatpickr.open();
        });

        document.getElementById("visible_end").addEventListener("touchend", function () {
            this._flatpickr.open();
        });
    }

    flatpickr("#visible_start", {
        dateFormat: "Y-m-d",
        minDate: "today",
        defaultDate: document.getElementById("id_start").value || null,
        onChange: function (selectedDates, dateStr) {
            document.getElementById("id_start").value = dateStr;
            updateFinalPrice();
        }
    });

    flatpickr("#visible_end", {
        dateFormat: "Y-m-d",
        minDate: "today",
        defaultDate: document.getElementById("id_end").value || null,
        onChange: function (selectedDates, dateStr) {
            document.getElementById("id_end").value = dateStr;
            updateFinalPrice();
        }
    });

    if (formStart.value && formEnd.value) {
        updateFinalPrice();
    }

    function resetReservation() {
        formStart.value = '';
        formEnd.value = '';

        document.getElementById('start-date').innerText = '';
        document.getElementById('end-date').innerText = '';
        document.getElementById('final-price').innerText = '0.00';
        document.getElementById('reservation-price').value = '0.00';
        document.getElementById('reservation-tax').value = '0.00';
        document.getElementById('details').innerHTML = '';

        // Disable submit button
        document.getElementById('submit-booking').disabled = true;

        isReservationValid = false;
    }

    // Function to check if the input are correct
    function areInputCorrect(startDate, endDate, guest) {
        const url = `/api/check_booking_input/${logementId}?start=${startDate}&end=${endDate}&guest=${guest}`;
        return new Promise((resolve, reject) => {
            fetch(url)
                .then(response => response.json())
                .then(data => {
                    if (data.correct) {
                        resolve(true);
                    } else {
                        if (data.error) {
                            resetReservation();
                            Swal.fire({
                                icon: 'error',
                                title: 'Validation échouée',
                                text: `❌ ${data.error}`,
                                toast: true,
                                position: 'top-end',
                                timer: 4000,
                                showConfirmButton: false,
                            });
                        }
                        resolve(false);
                    }
                })
                .catch(err => {
                    logToServer("error", "Erreur lors de la vérification des champs : " + err, {
                        start: startDate,
                        end: endDate,
                        logementId: logementId
                    });
                    resetReservation();
                    reject(err);
                });
        });
    }

    function updateFinalPrice() {
        const startDateStr = formStart.value;
        const endDateStr = formEnd.value;
        const guestValue = parseInt(formGuest.value.trim(), 10) || 1;

        areInputCorrect(startDateStr, endDateStr, formGuest.value)
            .then((available) => {
                if (!available) {
                    // Rien à faire, resetReservation() a déjà été appelée dans isDateBooked
                    return;
                }
                // If guestCount is not provided or is falsy (null, undefined, 0, etc.), set it to 1
                const guestCount = parseInt(formGuest.value, 10) || 1;
                const startDate = new Date(startDateStr);
                const endDate = new Date(endDateStr);

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
                        const tax = response.data.tax;
                        const details = response.data.details;

                        // Update the final price in the UI
                        document.getElementById('final-price').innerText = finalPrice.toFixed(2);
                        document.getElementById('reservation-price').value = finalPrice.toFixed(2);
                        document.getElementById('reservation-tax').value = tax.toFixed(2);

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

    function validateGuestInput() {
        const guestValue = formGuest.value.trim();

        // Allow empty input while user is editing
        if (guestValue === '') {
            return false;
        }

        const guestNumber = parseInt(guestValue, 10);

        // Check if input is a valid positive integer within allowed range
        if (
            isNaN(guestNumber) ||
            guestNumber <= 0 ||
            guestValue.includes('.') ||
            guestNumber > logement_js.max_traveler
        ) {
            Swal.fire({
                icon: 'error',
                title: 'Nombre invalide',
                text: `❌ Veuillez entrer un nombre valide de voyageurs (entre 1 et ${logement_js.max_traveler}).`,
                toast: true,
                position: 'top-end',
                timer: 4000,
                showConfirmButton: false,
            });

            return false;
        }

        return true;
    }

    const debouncedUpdatePrice = debounce(updateFinalPrice, 300);
    // Recalculate the price on input change

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

    formGuest.addEventListener('blur', function () {
        if (formGuest.value.trim() === '') {
            formGuest.value = 1;
        }
    });

    const stripe = Stripe(stripe_public_key);

    function validateDateInput(inputElement, label = "Date") {
        const value = inputElement.value.trim();

        // Allow empty value while the user is typing
        if (value === "") {
            return false;
        }

        const parsedDate = new Date(value);
        if (isNaN(parsedDate.getTime())) {
            return false;
        }

        return true;
    }

    formStart.addEventListener('change', function () {
        if (validateDateInput(formStart, "Date de début")) {
            updateFinalPrice();
        }
    });

    formEnd.addEventListener('change', function () {
        if (validateDateInput(formEnd, "Date de fin")) {
            updateFinalPrice();
        }
    });

    formStart.addEventListener('input', function () {
        if (validateDateInput(formStart, "Date de début")) {
            updateFinalPrice();
        }
    });

    formEnd.addEventListener('input', function () {
        if (validateDateInput(formEnd, "Date de fin")) {
            updateFinalPrice();
        }
    });

    formStart.addEventListener('blur', function () {
        const startDate = new Date(formStart.value.trim());
        if (isNaN(startDate.getTime())) {
            Swal.fire({
                icon: 'info',
                title: 'Date de début requise',
                text: 'Veuillez sélectionner une date de début.',
                toast: true,
                position: 'top-end',
                timer: 3000,
                showConfirmButton: false,
            });
        }
    });

    formEnd.addEventListener('blur', function () {
        const endDate = new Date(formEnd.value.trim());
        if (isNaN(endDate.getTime())) {
            Swal.fire({
                icon: 'info',
                title: 'Date de Fin requise',
                text: 'Veuillez sélectionner une date de fin.',
                toast: true,
                position: 'top-end',
                timer: 3000,
                showConfirmButton: false,
            });
        }
    });
});