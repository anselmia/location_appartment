document.addEventListener('DOMContentLoaded', function () {
    const formStart = document.getElementById('id_start');
    const formEnd = document.getElementById('id_end');
    const formGuest = document.getElementById('id_guest');

    const pricePerNightElement = document.getElementById('price-per-night');
    const totalNightsElement = document.getElementById('total-nights');
    const cleaningFeeElement = document.getElementById('cleaning-fee');
    const touristTaxElement = document.getElementById('tourist-tax');
    const totalElement = document.getElementById('total-price');

    const cleaningFee = parseFloat(logement_js.cleaning_fee);
    const touristTax = parseFloat(logement_js.tax);
    const extraGuestFee = parseFloat(logement_js.fee_per_extra_traveler);
    const nominalTraveler = parseInt(logement_js.nominal_traveler);
    const logementId = logement_js.id; // Get the logement ID from Django context

    function openModal(index) {
        // Set active photo in modal to the clicked one
        let carouselItems = document.querySelectorAll('#carouselImages .carousel-item');
        carouselItems.forEach((item, idx) => {
            item.classList.remove('active');
            if (idx === index) {
                item.classList.add('active');
            }
        });
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
                        reject('The selected dates are already booked');
                    }
                })
                .catch(err => reject('Error checking availability'));
        });
    }

    function updateFinalPrice() {
        // If guestCount is not provided or is falsy (null, undefined, 0, etc.), set it to 1
        const startDate = new Date(formStart.value);
        const endDate = new Date(formEnd.value);
        const guestCount = formGuest.value;

        // Safety checks
        if (!startDate || !endDate || startDate >= endDate || startDate.toISOString().split('T')[0] === endDate.toISOString().split('T')[0]) {
            alert("Please select valid start and end dates.");
            return;
        }

        if (!guestCount || guestCount <= 0) {
            alert("Please enter a valid number of guests.");
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
                    })
                    .catch(error => {
                        console.error('Error fetching price calculation:', error);
                    });
            })
            .catch(error => alert(error)); // Show alert if dates are already booked
    }

    // Trigger calculation when parameters are valid on page load
    if (formStart.value && formEnd.value && formGuest.value) {
        updateFinalPrice();
    }

    // Recalculate the price on input change
    formStart.addEventListener('change', updateFinalPrice);
    formEnd.addEventListener('change', updateFinalPrice);
    formGuest.addEventListener('change', updateFinalPrice);

    // Function to open modal with selected image
    function openModal(index) {
        // Get all the carousel items in the modal
        const carouselItems = document.querySelectorAll('#carouselImages .carousel-item');

        // Remove the active class from all images
        carouselItems.forEach((item, idx) => {
            item.classList.remove('active');
            // Add the active class to the selected image based on the index
            if (idx === index) {
                item.classList.add('active');
            }
        });
    }

    // Adding click event listeners to small images to open modal
    const smallImages = document.querySelectorAll('.carousel-small-images .carousel-item-img img');
    smallImages.forEach((img, index) => {
        img.addEventListener('click', function () {
            openModal(index);
            // Manually trigger the modal to open
            $('#photoModal').modal('show');
        });
    });

    // Optional: Listen for clicks on the modal's controls (prev/next)
    $('#photoModal').on('hidden.bs.modal', function () {
        // Reset the carousel to the first item when the modal is closed
        $('#modalCarousel').carousel(0);
    });

    const stripe = Stripe(stripe_public_key);

});