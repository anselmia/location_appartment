// Function to handle photo room change

document.querySelectorAll('.room-select').forEach(select => {
    select.addEventListener('change', (e) => {
        const photoId = e.target.closest('.photo-item').getAttribute('data-photo-id');
        const roomId = e.target.value;

        // Fetch the base URL from the hidden element and replace the placeholder
        const urlTemplate = document.getElementById('change-photo-room-url').getAttribute('data-url');
        const url = urlTemplate.replace('1', photoId); // Replace the placeholder with the actual photo_id

        fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({
                    room_id: roomId
                })
            }).then(response => response.json())
            .catch(error => {
                logToServer("error", "Erreur lors du calcul du prix : " + error, {
                    logementId: logementId,
                    start: selectedStart,
                    end: selectedEnd || selectedStart,
                    guests: guestCount,
                    base_price: updatedBasePrice
                });
            });
    });
});

// Function to handle photo reorder (up or down)
document.querySelectorAll('.move-photo').forEach(button => {
    button.addEventListener('click', (e) => {
        const photoId = e.target.closest('.photo-item').getAttribute('data-photo-id');
        const direction = e.target.getAttribute('data-direction');

        // Fetch the base URL from the hidden element and replace the placeholders
        const urlTemplate = document.getElementById('move-photo-url').getAttribute('data-url');
        const url = urlTemplate.replace('1', photoId).replace('UP', direction);

        fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
            }).then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update photo order in the list
                    const photoItem = e.target.closest('.photo-item');
                    const currentOrder = parseInt(photoItem.getAttribute('data-photo-order'));
                    const newOrder = direction === 'up' ? currentOrder - 1 : currentOrder + 1;

                    // Reorder the photo in the list based on direction
                    const sibling = direction === 'up' ?
                        photoItem.previousElementSibling :
                        photoItem.nextElementSibling;

                    if (sibling) {
                        if (direction === 'up') {
                            photoItem.parentNode.insertBefore(photoItem, sibling);
                        } else {
                            photoItem.parentNode.insertBefore(photoItem, sibling.nextSibling);
                        }
                    }

                    // Update photo's order data attribute
                    photoItem.setAttribute('data-photo-order', newOrder);
                }
            })
            .catch(error => {
                logToServer("error", "Erreur lors du calcul du prix : " + error, {
                    logementId: logementId,
                    start: selectedStart,
                    end: selectedEnd || selectedStart,
                    guests: guestCount,
                    base_price: updatedBasePrice
                });
            });
    });
});

// Function to handle photo deletion
document.querySelectorAll('.delete-photo').forEach(button => {
    button.addEventListener('click', (e) => {
        const photoId = e.target.closest('.photo-item').getAttribute('data-photo-id');

        if (confirm('Êtes-vous sûr de vouloir supprimer cette photo ?')) {
            // Fetch the base URL from the hidden element and replace the placeholder
            const urlTemplate = document.getElementById('delete-photo-url').getAttribute('data-url');
            const url = urlTemplate.replace('1', parseInt(photoId)); // Replace the placeholder with the actual photo_id

            fetch(url, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': csrfToken,
                    },
                }).then(response => response.json())
                .then(data => {
                    if (data.success) {
                        e.target.closest('.photo-item').remove();
                    }
                })
                .catch(error => {
                    logToServer("error", "Erreur lors du calcul du prix : " + error, {
                        logementId: logementId,
                        start: selectedStart,
                        end: selectedEnd || selectedStart,
                        guests: guestCount,
                        base_price: updatedBasePrice
                    });
                });
        }
    });
});