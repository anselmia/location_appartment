let isReservationValid = false;

document.addEventListener("DOMContentLoaded", function () {
  const formStart = document.getElementById("id_start");
  const formEnd = document.getElementById("id_end");
  const formGuestAdult = document.getElementById("id_guest_adult");
  const formGuestMinor = document.getElementById("id_guest_minor");

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

  if (
    formStart.value &&
    formEnd.value &&
    formGuestAdult.value &&
    formGuestMinor.value &&
    validateGuestInput()
  ) {
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
  function areInputCorrect(startDate, endDate, guest_adult, guest_minor) {
    const url = `/reservation/check-logement-input/${logementId}?start=${startDate}&end=${endDate}&guest_adult=${guest_adult}&guest_minor=${guest_minor}`;
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
    let guestAdultValue = parseInt(formGuestAdult.value.trim(), 10) || 1;
    let guestMinorValue = parseInt(formGuestMinor.value.trim(), 10) || 0;

    if (startDateStr && endDateStr) {
      areInputCorrect(
        startDateStr,
        endDateStr,
        formGuestAdult.value,
        formGuestMinor.value
      ).then((available) => {
        if (!available) {
          // Rien à faire, resetReservation() a déjà été appelée dans isDateBooked
          return;
        }

        const startDate = new Date(startDateStr);
        const endDate = new Date(endDateStr);

        // Update the reservation summary dynamically
        document.getElementById("start-date").innerText = startDateStr; // Update start date in summary
        document.getElementById("end-date").innerText = endDateStr; // Update end date in summary
        document.getElementById("guest-adult-count").innerText =
          guestAdultValue;
        document.getElementById("guest-minor-count").innerText =
          guestMinorValue;

        axios.defaults.headers.common["X-CSRFToken"] = csrfToken;
        axios
          .post("/logement/prices/calculate_price/", {
            logement_id: logementId,
            start: startDate.toISOString().split("T")[0],
            end: endDate.toISOString().split("T")[0],
            guest_adult: guestAdultValue,
            guest_minor: guestMinorValue,
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
              guests: guestAdultValue + guestMinorValue,
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
      });
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
              guest_adult: parseInt(formGuestAdult.value, 10),
              guest_minor: parseInt(formGuestMinor.value, 10),
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
    let guestAdult = formGuestAdult.value.trim();
    let guestMinor = formGuestMinor.value.trim();

    // Allow empty input while user is editing
    if (guestAdult === "" || guestMinor === "") {
      return false;
    }

    guestAdult = parseInt(guestAdult, 10);
    guestMinor = parseInt(guestMinor, 10);

    max_minor = logement_js.max_traveler - 1;

    // Check if input is a valid positive integer within allowed range
    if (
      isNaN(guestAdult) ||
      guestAdult <= 0 ||
      formGuestAdult.value.includes(".")
    ) {
      Swal.fire({
        icon: "error",
        title: "Nombre invalide",
        text: `❌ Veuillez entrer un nombre valide d'adulte(s) (entre 1 et ${logement_js.max_traveler}).`,
        toast: true,
        position: "top-end",
        timer: 4000,
        showConfirmButton: false,
      });

      return false;
    }

    if (
      isNaN(guestMinor) ||
      guestMinor < 0 ||
      formGuestMinor.value.includes(".")
    ) {
      Swal.fire({
        icon: "error",
        title: "Nombre invalide",
        text: `❌ Veuillez entrer un nombre valide de mineur(s) (entre 0 et ${max_minor}).`,
        toast: true,
        position: "top-end",
        timer: 4000,
        showConfirmButton: false,
      });

      if (guestAdult + guestMinor > logement_js.max_traveler) {
        Swal.fire({
          icon: "error",
          title: "Capacité dépassée",
          text: `❌ Le nombre total de voyageurs dépasse la capacité maximale (${logement_js.max_traveler}).`,
          toast: true,
          position: "top-end",
          timer: 4000,
          showConfirmButton: false,
        });
        return false;
      }

      return false;
    }

    return true;
  }

  const debouncedUpdatePrice = debounce(updateFinalPrice, 300);
  // Recalculate the price on input change
  function handleArrowKey(e, inputElement) {
    const allowedKeys = ["ArrowUp", "ArrowDown", "Tab", "Backspace"];
    if (!allowedKeys.includes(e.key)) {
      e.preventDefault();
      return;
    }

    if (["ArrowUp", "ArrowDown"].includes(e.key)) {
      // Delay to let the input value actually update
      setTimeout(() => {
        if (validateGuestInput()) {
          updateFinalPrice();
        }
      }, 100);
    }
  }

  formGuestAdult.addEventListener("change", function () {
    if (validateGuestInput()) {
      updateFinalPrice();
    }
  });

  formGuestAdult.addEventListener("input", function () {
    if (validateGuestInput()) {
      debouncedUpdatePrice();
    }
  });

  formGuestAdult.addEventListener("blur", function () {
    if (formGuestAdult.value.trim() === "") {
      formGuestAdult.value = 1;
    }
  });

  formGuestMinor.addEventListener("change", function () {
    if (validateGuestInput()) {
      updateFinalPrice();
    }
  });

  formGuestMinor.addEventListener("input", function () {
    if (validateGuestInput()) {
      debouncedUpdatePrice();
    }
  });

  formGuestMinor.addEventListener("blur", function () {
    if (formGuestMinor.value.trim() === "") {
      formGuestMinor.value = 0;
    }
  });

  formGuestAdult.addEventListener("keydown", function (e) {
    handleArrowKey(e, formGuestAdult);
  });

  formGuestMinor.addEventListener("keydown", function (e) {
    handleArrowKey(e, formGuestMinor);
  });

  formStart.addEventListener("input", function () {
    if (validateGuestInput()) {
      debouncedUpdatePrice();
    }
  });

  formEnd.addEventListener("input", function () {
    if (validateGuestInput()) {
      debouncedUpdatePrice();
    }
  });

  const stripe = Stripe(stripe_public_key);

  window.validateGuestInput = validateGuestInput;
  window.updateFinalPrice = updateFinalPrice;
});
