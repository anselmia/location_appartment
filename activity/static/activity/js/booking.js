let isReservationValid = false;

let not_available_date = [];

document.addEventListener("DOMContentLoaded", function () {
  const calendarBlock = document.getElementById("calendar_inline");
  const slotsSection = document.getElementById("slots-section");
  const bookingForm = document.getElementById("booking-form");
  const submitBtn = document.getElementById("submit-booking");
  const cgvCheckbox = document.getElementById("cgv-check");
  const slotInput = document.getElementById("id_slot_time"); // hidden input for slot
  const formGuest = document.getElementById("id_guest");
  const formStart = document.getElementById("id_start");

  // 🔥 iOS Safari fix: ensure calendar opens on touch
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  logToServer("info", "Ios Device", {
    isIosDevice: isIOS,
  });

  if (
    formStart.value &&
    formGuest.value &&
    slotInput.value &&
    validateGuestInput()
  ) {
    updateFinalPrice();
  }

  function resetReservation() {
    formStart.value = "";
    formGuest.value = "";
    slotInput.value = "";

    document.getElementById("start-date").innerText = "";
    document.getElementById("final-price").innerText = "0.00";
    document.getElementById("reservation-price").value = "0.00";
    document.getElementById("details").innerHTML = "";

    // Disable submit button
    cgvCheckbox.checked = false;
    submitBtn.disabled = true;
    isReservationValid = false;
  }

  // Function to check if the input are correct
  function areInputCorrect(startDate, guest, slot) {
    const url = `/activity/check_booking_input/${activityId}?start=${startDate}&slot=${slot}&guest=${guest}`;
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
              activityId: activityId,
            }
          );
          resetReservation();
          reject(err);
        });
    });
  }

  function updateFinalPrice() {
    const startDateStr = formStart.value;
    let guestValue = parseInt(formGuest.value.trim(), 10) || 1;
    let slotInputValue = slotInput.value;

    if (startDateStr) {
      areInputCorrect(startDateStr, formGuest.value, slotInputValue).then(
        (available) => {
          if (!available) {
            // Rien à faire, resetReservation() a déjà été appelée dans isDateBooked
            return;
          }

          const startDate = new Date(startDateStr);

          // Update the reservation summary dynamically
          document.getElementById("start-date").innerText = startDateStr; // Update start date in summary
          document.getElementById("guest-count").innerText = guestValue;
          document.getElementById("slot-time").innerText = slotInputValue;

          axios.defaults.headers.common["X-CSRFToken"] = csrfToken;
          axios
            .post("/activity/prices/calculate_price/", {
              activity_id: activityId,
              start: startDate.toISOString().split("T")[0],
              guests: guestValue,
            })
            .then((response) => {
              const finalPrice = response.data.final_price;
              const details = response.data.details;

              // Update the final price in the UI
              document.getElementById("final-price").innerText =
                finalPrice.toFixed(2);
              document.getElementById("reservation-price").value =
                finalPrice.toFixed(2);

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
                guest: guestValue,
                activityId: activityId,
              });

              submitBtn.disabled = !cgvCheckbox.checked;
            })
            .catch((error) => {
              resetReservation();
              logToServer("error", "Erreur lors du calcul du prix" + error, {
                start: startDate,
                activityId: activityId,
              });
            });
        }
      );
    }
  }

  // --- Calendar setup (single date selection) ---
  if (calendarBlock) {
    const initialYear = new Date(today).getFullYear();
    const initialMonth = new Date(today).getMonth() + 1;

    fetch(
      `/activity/not-available-dates/${activityId}/?year=${initialYear}&month=${initialMonth}`
    )
      .then((response) => response.json())
      .then((data) => {
        not_available_date = data.dates || [];

        const config = {
          mode: "single", // Only one date selectable
          inline: true,
          minDate: today,
          disable: [], // Reserved dates if needed
          locale: {
            firstDayOfWeek: 1, // 1 = Monday
            weekdays: {
              shorthand: ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"],
              longhand: [
                "Dimanche",
                "Lundi",
                "Mardi",
                "Mercredi",
                "Jeudi",
                "Vendredi",
                "Samedi",
              ],
            },
            months: {
              shorthand: [
                "Janv",
                "Févr",
                "Mars",
                "Avr",
                "Mai",
                "Juin",
                "Juil",
                "Août",
                "Sept",
                "Oct",
                "Nov",
                "Déc",
              ],
              longhand: [
                "Janvier",
                "Février",
                "Mars",
                "Avril",
                "Mai",
                "Juin",
                "Juillet",
                "Août",
                "Septembre",
                "Octobre",
                "Novembre",
                "Décembre",
              ],
            },
            today: "Aujourd'hui",
            clear: "Effacer",
            monthsTitle: "Mois",
            weekAbbreviation: "Sem",
            rangeSeparator: " au ",
            scrollTitle: "Défiler pour augmenter",
            toggleTitle: "Cliquer pour basculer",
            time_24hr: true,
          },
          onMonthChange: function (selectedDates, dateStr, instance) {
            const currentMonth = instance.currentMonth + 1; // Flatpickr months are 0-based
            const currentYear = instance.currentYear;
            fetch(
              `/activity/not-available-dates/${activityId}/?year=${currentYear}&month=${currentMonth}`
            )
              .then((response) => response.json())
              .then((data) => {
                not_available_date = data.dates; // Array of "YYYY-MM-DD"
                // Update the calendar to disable these dates
                instance.set("disable", not_available_date);
                instance.redraw();
              });
          },
          onDayCreate: function (_, __, ___, dayElem) {
            const date = formatLocalDate(dayElem.dateObj); // Get the current date in YYYY-MM-DD

            if (not_available_date.includes(date)) {
              dayElem.classList.add("booked-day"); // Apply booked class
            } else if (date === today) {
              dayElem.classList.add("today-day"); // Apply today class
            } else if (date >= today) {
              dayElem.classList.add("free-day"); // Apply free class
            }
          },
          onChange: function (selectedDates, dateStr, instance) {
            if (selectedDates.length !== 1) return;
            const selectedDate = selectedDates[0];
            const formattedDate = formatLocalDate(selectedDate);

            // AJAX to get slots
            fetchSlots(formattedDate);

            formStart.value = formattedDate;
          },
        };

        flatpickr("#calendar_inline", config);
      });
  }

  function formatLocalDate(date) {
    if (!(date instanceof Date)) {
      date = new Date(date); // convert from string if necessary
    }
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0"); // months are 0-indexed
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  // --- Fetch and display slots ---
  function fetchSlots(dateStr) {
    slotsSection.innerHTML =
      "<div class='text-center my-3'><span class='spinner-border'></span> Chargement des créneaux...</div>";
    fetch(`/activity/slots/${activityId}/?date=${dateStr}`)
      .then((response) => response.json())
      .then((data) => {
        slotsSection.innerHTML = "";
        if (data.slots && data.slots.length > 0) {
          const slotGroup = document.createElement("div");
          slotGroup.className = "d-flex flex-wrap gap-2 justify-content-center";
          data.slots.forEach((slot) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn slot-btn";
            btn.innerText = slot;
            btn.onclick = function () {
              document.querySelectorAll(".slot-btn").forEach((b) => {
                b.classList.remove("active");
                b.classList.remove("btn-primary");
              });
              btn.classList.add("active");
              btn.classList.add("btn-primary");
              if (slotInput) slotInput.value = slot;
              bookingForm.style.display = "block";
              validateForm();
              updateFinalPrice(); // Ajoutez ceci pour mettre à jour le prix
            };
            slotGroup.appendChild(btn);
          });
          slotsSection.appendChild(slotGroup);
          console.log(
            "Slot buttons rendered:",
            slotsSection,
            slotGroup.children.length
          );
        } else {
          slotsSection.innerHTML =
            "<div class='alert alert-warning text-center'>Aucun créneau disponible ce jour.</div>";
        }
      });
  }

  function validateForm() {
    isReservationValid = !!(slotInput && slotInput.value);
    if (cgvCheckbox && submitBtn) {
      submitBtn.disabled = !(cgvCheckbox.checked && isReservationValid);
    }
  }

  // Validate participants (example: max from data attribute)
  if (formGuest) {
    formGuest.addEventListener("input", function () {
      const max = parseInt(this.getAttribute("max")) || 99;
      if (parseInt(this.value) > max) {
        this.value = max;
      }
      validateForm();
    });
  }

  if (cgvCheckbox && submitBtn) {
    cgvCheckbox.addEventListener("change", validateForm);
  }

  bookingForm.addEventListener("submit", function (e) {
    e.preventDefault(); // Prevent default immediately
    updateFinalPrice(); // run validation one last time

    // Delay a little to wait for async availability check
    setTimeout(() => {
      if (isReservationValid) {
        logToServer(
          "info",
          "Soumission du formulaire de réservation d'activité validé",
          {
            start: formStart.value,
            guest: parseInt(formGuest.value, 10),
            activityId: activityId,
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
    let guest = formGuest.value.trim();

    // Allow empty input while user is editing
    if (guest === "") {
      return false;
    }

    guest = parseInt(guest, 10);

    max_guest = activity_js.max_traveler;

    // Check if input is a valid positive integer within allowed range
    if (isNaN(guest) || guest <= 0 || formGuest.value.includes(".")) {
      Swal.fire({
        icon: "error",
        title: "Nombre invalide",
        text: `❌ Veuillez entrer un nombre valide d'adulte(s) (entre 1 et ${activity_js.max_traveler}).`,
        toast: true,
        position: "top-end",
        timer: 4000,
        showConfirmButton: false,
      });

      return false;
    }

    if (guest > activity_js.max_traveler) {
      Swal.fire({
        icon: "error",
        title: "Capacité dépassée",
        text: `❌ Le nombre total de voyageurs dépasse la capacité maximale (${activity_js.max_traveler}).`,
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
    handleArrowKey(e, formGuest);
  });

  formStart.addEventListener("input", function () {
    if (validateGuestInput()) {
      debouncedUpdatePrice();
    }
  });

  const stripe = Stripe(stripe_public_key);

  window.validateGuestInput = validateGuestInput;
  window.updateFinalPrice = updateFinalPrice;
});
