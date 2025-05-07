form.addEventListener("submit", function (event) {
    event.preventDefault(); // Prevent the default form submission

    const reservationId = document.getElementById("reservation-id").value;
    const url= document.getElementById('payment-checkout-url').getAttribute('data-url');

    // Send request to create checkout session on the server
    fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({
                reservation_id: reservationId // Send only the reservation ID
            })
        })
        .then(response => response.json())
        .then(session => {
            return stripe.redirectToCheckout({
                sessionId: session.id
            }); // Redirect to checkout
        })
        .then(result => {
            if (result.error) {
                // Display error if something goes wrong
                alert(result.error.message);
            }
        })
        .catch(error => {
            console.error("Error:", error);
        });
});