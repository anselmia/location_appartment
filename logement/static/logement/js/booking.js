let isReservationValid = false;

document.addEventListener("DOMContentLoaded", function () {
  const formStart = document.getElementById("id_start");
  const formEnd = document.getElementById("id_end");
  const formGuest = document.getElementById("id_guest");
  const logementId = logement_js.id; // Get the logement ID from Django context

  const checkbox = document.getElementById("cgv-check");
  const submitBtn = document.getElementById("submit-booking");

  if (checkbox && submitBtn) {
    checkbox.addEventListener("change", function () {
      submitBtn.disabled = !(this.checked && isReservationValid);
    });
  }

  // 🔥 iOS Safari fix: ensure calendar opens on touch
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  logToServer("info", "Ios Device", {
    isIosDevice: isIOS,
  });

  if (formStart.value && formEnd.value) {
    updateFinalPrice();
  }

  function resetReservation() {
    formStart.value = "";
    formEnd.value = "";

    document.getElementById("start-date").innerText = "";
    document.getElementById("end-date").innerText = "";
    document.getElementById("final-price").innerText = "0.00";
    document.getElementById("reservation-price").value = "0.00";
    document.getElementById("reservation-tax").value = "0.00";
    document.getElementById("details").innerHTML = "";

    // Disable submit button
    checkbox.checked = false;
    submitBtn.disabled = true;
    isReservationValid = false;
  }

  // Function to check if the input are correct
  function areInputCorrect(startDate, endDate, guest) {
    const url = `/api/check_booking_input/${logementId}?start=${startDate}&end=${endDate}&guest=${guest}`;
    return new Promise((resolve, reject) => {
      fetchWithLoader(url)
        .then((response) => response.json())
        .then((data) => {
          if (data.correct) {
            resolve(true);
          } else {
            if (data.error) {
              resetReservation();
              Swal.fire({
                icon: "error",
                title: "Validation échouée",
                text: `❌ ${data.error}`,
                toast: true,
                position: "top-end",
                timer: 4000,
                showConfirmButton: false,
              });
            }
            resolve(false);
          }
        })
        .catch((err) => {
          logToServer(
            "error",
            "Erreur lors de la vérification des champs : " + err,
            {
              start: startDate,
              end: endDate,
              logementId: logementId,
            }
          );
          resetReservation();
          reject(err);
        });
    });
  }

  function updateFinalPrice() {
    const startDateStr = formStart.value;
    const endDateStr = formEnd.value;
    const guestValue = parseInt(formGuest.value.trim(), 10) || 1;

    if (startDateStr && endDateStr) {
      areInputCorrect(startDateStr, endDateStr, formGuest.value).then(
        (available) => {
          if (!available) {
            // Rien à faire, resetReservation() a déjà été appelée dans isDateBooked
            return;
          }
          // If guestCount is not provided or is falsy (null, undefined, 0, etc.), set it to 1
          const guestCount = parseInt(formGuest.value, 10) || 1;
          const startDate = new Date(startDateStr);
          const endDate = new Date(endDateStr);

          // Update the reservation summary dynamically
          document.getElementById("start-date").innerText = startDateStr; // Update start date in summary
          document.getElementById("end-date").innerText = endDateStr; // Update end date in summary
          document.getElementById("guest-count").innerText = guestCount;

          axios.defaults.headers.common["X-CSRFToken"] = csrfToken;
          axios
            .post("/admin-area/prices/calculate_price/", {
              logement_id: logementId,
              start: startDate.toISOString().split("T")[0],
              end: endDate.toISOString().split("T")[0],
              guests: parseInt(guestCount, 10), // Send the number of guests to the backend
            })
            .then((response) => {
              const finalPrice = response.data.final_price;
              const tax = response.data.tax;
              const details = response.data.details;

              // Update the final price in the UI
              document.getElementById("final-price").innerText =
                finalPrice.toFixed(2);
              document.getElementById("reservation-price").value =
                finalPrice.toFixed(2);
              document.getElementById("reservation-tax").value = tax.toFixed(2);

              // Display detailed breakdown in a list
              const detailsContainer = document.getElementById("details");
              detailsContainer.innerHTML = ""; // Clear any existing details

              // Create the section header (optional)
              const detailh3 = document.createElement("h4");
              detailh3.innerText = "Détails du Prix";
              detailh3.classList.add("text-center");
              detailh3.classList.add("mb-4");
              detailsContainer.appendChild(detailh3);

              // Iterate over the details and create a list item for each one
              for (const [key, value] of Object.entries(details)) {
                const line = document.createElement("div");
                line.classList.add("price-line");

                // Optional: color indicator based on sign
                if (value.trim().startsWith("-")) {
                  line.classList.add("negative");
                } else if (value.trim().startsWith("+")) {
                  line.classList.add("positive");
                }

                const label = document.createElement("span");
                label.classList.add("label");
                label.innerHTML = `<strong>${key}</strong>`;

                const val = document.createElement("span");
                val.classList.add("value");
                val.innerText = value;

                line.appendChild(label);
                line.appendChild(val);
                detailsContainer.appendChild(line);
              }

              isReservationValid = true;

              logToServer("info", "Prix calculé avec succès", {
                finalPrice: finalPrice,
                start: startDateStr,
                end: endDateStr,
                guests: guestCount,
                logementId: logementId,
              });

              submitBtn.disabled = !checkbox.checked;
            })
            .catch((error) => {
              resetReservation();
              logToServer("error", "Erreur lors du calcul du prix" + error, {
                start: startDate,
                end: endDate,
                logementId: logementId,
              });
            });
        }
      );
    }
  }

  document
    .getElementById("reservation-form")
    .addEventListener("submit", function (e) {
      e.preventDefault(); // Prevent default immediately
      updateFinalPrice(); // run validation one last time

      // Delay a little to wait for async availability check
      setTimeout(() => {
        if (isReservationValid) {
          logToServer(
            "info",
            "Soumission du formulaire de réservation validée",
            {
              start: formStart.value,
              end: formEnd.value,
              guests: parseInt(formGuest.value, 10),
              logementId: logementId,
            }
          );

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
    if (guestValue === "") {
      return false;
    }

    const guestNumber = parseInt(guestValue, 10);

    // Check if input is a valid positive integer within allowed range
    if (
      isNaN(guestNumber) ||
      guestNumber <= 0 ||
      guestValue.includes(".") ||
      guestNumber > logement_js.max_traveler
    ) {
      Swal.fire({
        icon: "error",
        title: "Nombre invalide",
        text: `❌ Veuillez entrer un nombre valide de voyageurs (entre 1 et ${logement_js.max_traveler}).`,
        toast: true,
        position: "top-end",
        timer: 4000,
        showConfirmButton: false,
      });

      return false;
    }

    return true;
  }

  const debouncedUpdatePrice = debounce(updateFinalPrice, 300);
  // Recalculate the price on input change

  formGuest.addEventListener("change", function () {
    if (validateGuestInput()) {
      updateFinalPrice();
    }
  });

  formGuest.addEventListener("input", function () {
    if (validateGuestInput()) {
      debouncedUpdatePrice();
    }
  });

  formGuest.addEventListener("blur", function () {
    if (formGuest.value.trim() === "") {
      formGuest.value = 1;
    }
  });


  formGuest.addEventListener("keydown", function (e) {
    // allow only up/down arrows, tab, and backspace
    const allowedKeys = ["ArrowUp", "ArrowDown", "Tab", "Backspace"];
    if (!allowedKeys.includes(e.key)) {
      e.preventDefault();
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

  endInput.addEventListener("change", function () {
    if (validateDateInput(formEnd, "Date de fin")) {
      updateFinalPrice();
    }
  });
});
