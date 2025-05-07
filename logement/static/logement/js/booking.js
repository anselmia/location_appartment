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

    // Function to make an AJAX call to fetch price for a specific date
    function getPriceForDate(date) {
        return new Promise((resolve, reject) => {
            fetch(`/api/get_price/${logementId}/${date}`)
                .then(response => response.json())
                .then(data => {
                    if (data.price) {
                        resolve(parseFloat(data.price)); // Return the price as a number
                    } else {
                        reject('Price not found');
                    }
                })
                .catch(err => reject(err));
        });
    }

    // Function to check if the dates are already booked
    function isDateBooked(startDate, endDate) {
        const url = reservationId 
        ? `/api/check_availability/${logementId}?start=${startDate}&end=${endDate}&reservation_id=${reservationId}` 
        : `/api/check_availability/${logementId}?start=${startDate}&end=${endDate}`;
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

    // Function to calculate the total price
    function calculatePrice() {
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
                document.getElementById('start-date').innerText = formStart.value;  // Update start date in summary
                document.getElementById('end-date').innerText = formEnd.value;      // Update end date in summary
                document.getElementById('guest-count').innerText = guestCount; 
                
                let totalNights = 0;
                let totalPriceForNights = 0;

                // Loop through each night between the start and end date
                let currentDate = new Date(startDate);
                while (currentDate < endDate) {
                    const dateString = currentDate.toISOString().split('T')[0]; // Format date as YYYY-MM-DD
                    totalNights++;

                    // Fetch the price for each night
                    getPriceForDate(dateString)
                        .then(priceForNight => {
                            // Add the price for the current night to the total
                            totalPriceForNights += parseFloat(priceForNight); // Convert price to float

                            // If we've processed all nights, calculate the total price
                            if (totalNights === Math.ceil((endDate - startDate) / (1000 * 3600 * 24))) {
                                // Calculate the extra Guest fee 
                                const TotalextraGuestFee = Math.max((extraGuestFee * (guestCount - nominalTraveler) * totalNights), 0);

                                const PricePerNight = (totalPriceForNights + TotalextraGuestFee) / totalNights;

                                // Calculate the tax amount (tax * average price per night * total nights)
                                const taxRate = Math.min(((touristTax / 100) * (PricePerNight / guestCount)), 6.43);
                                const taxAmount = taxRate * guestCount * totalNights;



                                // Calculate the total price
                                const totalPrice = totalPriceForNights + TotalextraGuestFee + cleaningFee + taxAmount;

                                // Update the UI elements with the calculated values
                                pricePerNightElement.innerText = `${(PricePerNight).toFixed(2)} €`; // Average price per night
                                totalNightsElement.innerText = `${totalNights}`;
                                cleaningFeeElement.innerText = `${cleaningFee} €`;
                                touristTaxElement.innerText = `${taxAmount.toFixed(2)} €`;
                                totalElement.innerText = `${totalPrice.toFixed(2)} €`;

                                // Set the total price in the hidden input field
                                document.getElementById('reservation-price').value = totalPrice.toFixed(2);
                            }
                        })
                        .catch(error => console.error('Error fetching price for night:', error));

                    // Move to the next day
                    currentDate.setDate(currentDate.getDate() + 1);
                }
            })
            .catch(error => alert(error)); // Show alert if dates are already booked
    }

    // Trigger calculation when parameters are valid on page load
    if (formStart.value && formEnd.value && formGuest.value) {
        calculatePrice();
    }

    // Recalculate the price on input change
    formStart.addEventListener('change', calculatePrice);
    formEnd.addEventListener('change', calculatePrice);
    formGuest.addEventListener('change', calculatePrice);

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