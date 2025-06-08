document.addEventListener("DOMContentLoaded", function () {
  document
    .querySelectorAll('#logementTabs button[data-bs-toggle="tab"]')
    .forEach((tab) => {
      tab.addEventListener("shown.bs.tab", function (e) {
        const target = e.target.getAttribute("data-bs-target");
        localStorage.setItem("activeLogementTab", target);
      });
    });

  // Restaurer l'onglet actif au rechargement
  const lastTab = localStorage.getItem("activeLogementTab");
  if (lastTab) {
    const triggerEl = document.querySelector(
      `#logementTabs button[data-bs-target="${lastTab}"]`
    );
    if (triggerEl) {
      new bootstrap.Tab(triggerEl).show();
    }
  }

  const uploadForm = document.getElementById("upload_photos");
  if (uploadForm) {
    uploadForm.addEventListener("submit", function () {
      showLoader();
    });
  }
});

function showLoader() {
  document.getElementById("loader").style.display = "flex";
}

// Function to handle photo room change
document.querySelectorAll(".room-select").forEach((select) => {
  select.addEventListener("change", (e) => {
    const photoId = e.target
      .closest(".photo-item")
      .getAttribute("data-photo-id");
    let roomId = e.target.value;
    if (roomId === "") {
      roomId = null;
    }

    // Fetch the base URL from the hidden element and replace the placeholder
    const urlTemplate = document
      .getElementById("change-photo-room-url")
      .getAttribute("data-url");
    const url = urlTemplate.replace("1", photoId); // Replace the placeholder with the actual photo_id

    fetchWithLoader(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({
        room_id: roomId,
      }),
    })
      .then((response) => response.json())
      .catch((error) => {
        logToServer("error", "Erreur lors du changement de pièce : " + error, {
          logementId: logementId,
          start: selectedStart,
          end: selectedEnd || selectedStart,
          guests: guestCount,
          base_price: updatedBasePrice,
        });
      });
  });
});

// Function to handle photo reorder (up or down)
document.querySelectorAll(".move-photo").forEach((button) => {
  button.addEventListener("click", (e) => {
    const photoItem = e.target.closest(".photo-item");
    const photoId = photoItem.dataset.photoId;
    const direction = e.target.dataset.direction;

    const urlTemplate = document.getElementById("move-photo-url").dataset.url;
    const url = urlTemplate.replace("1", photoId).replace("UP", direction);

    fetchWithLoader(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          const list = document.getElementById("photo-list");
          const current = photoItem;
          const sibling =
            direction === "up"
              ? current.previousElementSibling
              : current.nextElementSibling;

          if (sibling && sibling.classList.contains("photo-item")) {
            // Move the element in DOM
            if (direction === "up") {
              list.insertBefore(current, sibling);
            } else {
              list.insertBefore(sibling, current);
            }

            // Recalculate order attributes for all photo items
            const items = Array.from(list.querySelectorAll(".photo-item"));
            items.forEach((item, index) => {
              item.setAttribute("data-photo-order", index + 1);
              const badge = item.querySelector("small.text-muted");
              if (badge) badge.textContent = `#${index + 1}`;
            });
          }
        }
      })
      .catch((error) => {
        logToServer("error", "Erreur lors du calcul du prix : " + error, {
          logementId: logementId,
          start: selectedStart,
          end: selectedEnd || selectedStart,
          guests: guestCount,
          base_price: updatedBasePrice,
        });
      });
  });
});

// Function to handle photo deletion
document.querySelectorAll(".delete-photo").forEach((button) => {
  button.addEventListener("click", (e) => {
    const photoId = e.target
      .closest(".photo-item")
      .getAttribute("data-photo-id");

    if (confirm("Êtes-vous sûr de vouloir supprimer cette photo ?")) {
      // Fetch the base URL from the hidden element and replace the placeholder
      const urlTemplate = document
        .getElementById("delete-photo-url")
        .getAttribute("data-url");
      const url = urlTemplate.replace("1", parseInt(photoId)); // Replace the placeholder with the actual photo_id

      fetchWithLoader(url, {
        method: "DELETE",
        headers: {
          "X-CSRFToken": csrfToken,
        },
      })
        .then((response) => response.json())
        .then((data) => {
          if (data.success) {
            e.target.closest(".photo-item").remove();
          }
        })
        .catch((error) => {
          logToServer("error", "Erreur lors du calcul du prix : " + error, {
            logementId: logementId,
            start: selectedStart,
            end: selectedEnd || selectedStart,
            guests: guestCount,
            base_price: updatedBasePrice,
          });
        });
    }
  });
});

document.querySelectorAll(".rotate-photo").forEach((button) => {
  button.addEventListener("click", function () {
    const photoId = this.dataset.photoId;
    const urlTemplate = document
      .getElementById("rotate-photo-url")
      .getAttribute("data-url");
    const url = urlTemplate.replace("1", parseInt(photoId));

    fetchWithLoader(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: "degrees=90",
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.status === "ok") {
          const photoId = this.dataset.photoId;
          const img = document.querySelector(
            `.photo-item[data-photo-id="${photoId}"] img`
          );

          if (!img) return;

          // Get current angle or initialize
          let angle = parseInt(img.dataset.angle || "0");
          angle = (angle + 90) % 360;
          img.dataset.angle = angle; // Store on element

          // Remove existing rotation classes
          img.classList.remove(
            "rotated-0",
            "rotated-90",
            "rotated-180",
            "rotated-270"
          );

          // Apply new rotation class
          img.classList.add(`rotated-${angle}`);
        } else {
          alert("Erreur : " + data.message);
        }
      })
      .catch((err) => {
        logToServer("error", "Erreur lors de la rotation : " + err, {
          PhotoId: photoId,
        });
      });
  });
});

document
  .getElementById("delete-all-photos")
  .addEventListener("click", function () {
    if (!confirm("⚠️ Êtes-vous sûr de vouloir supprimer TOUTES les photos ?"))
      return;

    const url = document.getElementById("delete-all-photos-url").dataset.url;

    fetchWithLoader(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        "Content-Type": "application/x-www-form-urlencoded",
      },
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "ok") {
          location.reload(); // 🔄 Recharge la page pour voir les effets
        } else {
          alert("Une erreur est survenue lors de la suppression.");
        }
      })
      .catch((err) => {
        console.error(
          "Erreur lors de la suppression de toutes les photos :",
          err
        );
      });
  });

document.getElementById("photos").addEventListener("change", function (event) {
  const maxSize = 2 * 1024 * 1024; // 2MB
  const files = event.target.files;
  for (let file of files) {
    if (file.size > maxSize) {
      alert(`Le fichier "${file.name}" dépasse 2 Mo.`);
      event.target.value = ""; // Clear input
      break;
    }
  }
});

$(document).ready(function () {
    $('.sync-calendar').on('click', function () {
        const url = $(this).data('url');
        const source = $(this).data('source');
        const button = $(this);
        const statusDiv = $('#sync-status');

        button.prop('disabled', true).text('🔄…');

        $.ajax({
            url: url,
            method: 'POST',
            headers: {'X-CSRFToken': csrfToken},
            success: function (data) {
                statusDiv.html(
                    `<div class="alert alert-success">${source.toUpperCase()} : ${data.message}</div>`
                );
            },
            error: function (xhr) {
                statusDiv.html(
                    `<div class="alert alert-danger">${source.toUpperCase()} : ${xhr.responseJSON?.error || 'Erreur lors de la synchronisation'}</div>`
                );
            },
            complete: function () {
                button.prop('disabled', false).text('🔄');
            }
        });
    });
});
