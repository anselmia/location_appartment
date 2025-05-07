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
        return new Promise((resolve, reject) => {
            fetch(`/api/check_availability/${logementId}?start=${startDate}&end=${endDate}`)
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
                                totalNightsElement.innerText = `${totalNights} nuits`;
                                cleaningFeeElement.innerText = `${cleaningFee} €`;
                                touristTaxElement.innerText = `${taxAmount.toFixed(2)} €`;
                                totalElement.innerText = `${totalPrice.toFixed(2)} €`;
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
});