document.addEventListener('DOMContentLoaded', function () {
  const calendarEl = document.getElementById('calendar');
  const logementId = calendarEl.dataset.logementId;

  let selectedStart = null;
  let selectedEnd = null;
  let reservedDates = new Set();
  let reductions = []; // Store active reductions
  let dailyPriceMap = {};

  axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
  axios.defaults.headers.post['Content-Type'] = 'application/json';

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: 'dayGridMonth',
    height: 'auto',
    locale: 'fr',

    selectable: true,
    selectMirror: true,

    events: function (fetchInfo, successCallback, failureCallback) {
      const params = new URLSearchParams({
        logement_id: logementId,
        start: fetchInfo.startStr,
        end: fetchInfo.endStr,
      });

      reservedDates.clear();

      axios.get(`/admin-area/prices/?${params.toString()}`)
        .then(res => {
          // 1. Daily Prices (background display)
          const priceEvents = res.data.data.map(e => ({
            start: e.date,
            display: 'background',
            className: 'fc-event-price',
            title: `${parseFloat(e.value).toFixed(2)} €`
          }));

          // 2. Internal reservations
          const bookings = res.data.data_bookings.map(b => ({
            start: b.start,
            end: b.end,
            title: `${b.name} • ${b.guests} guests - ${b.total_price}€`,
            className: 'booking-event internal',
          }));

          // 3. Airbnb
          const airbnbBookings = res.data.airbnb_bookings.map(b => ({
            start: b.start,
            end: b.end,
            title: `Airbnb`,
            className: 'booking-event airbnb'
          }));

          // 4. Booking.com
          const bookingBookings = res.data.booking_bookings.map(b => ({
            start: b.start,
            end: b.end,
            title: `Booking.com`,
            className: 'booking-event bookingcom'
          }));

          dailyPriceMap = {};
          res.data.data.forEach(e => {
            dailyPriceMap[e.date] = parseFloat(e.value);
          });

          function addReservedRange(start, end) {
            const current = new Date(start);
            const endDate = new Date(end);
            while (current < endDate) {
              reservedDates.add(current.toISOString().split('T')[0]);
              current.setDate(current.getDate() + 1);
            }
          }

          // Ajoute les jours réservés
          res.data.data_bookings.forEach(b => addReservedRange(b.start, b.end));
          res.data.airbnb_bookings.forEach(b => addReservedRange(b.start, b.end));
          res.data.booking_bookings.forEach(b => addReservedRange(b.start, b.end));

          successCallback([
            ...priceEvents,
            ...bookings,
            ...airbnbBookings,
            ...bookingBookings
          ]);
        })
        .catch(failureCallback);
    },

    dateClick: function (info) {
      if (reservedDates.has(info.dateStr)) return;
      showPanel(info.dateStr);
    },

    select: function (selectionInfo) {
      const hasConflict = isReservedRange(selectionInfo.startStr, selectionInfo.endStr);
      if (hasConflict) return;
      showPanel(selectionInfo.startStr, selectionInfo.endStr);
    },

    eventDidMount: function (info) {
      if (info.event.classNames.includes('fc-event-price')) {
        info.el.innerHTML = `<div class="fc-event-price">${info.event.title}</div>`;
        return;
      }

      if (info.event.classNames.includes('discount-event')) {
        info.el.innerHTML = `<div class="discount-label">${info.event.title}</div>`;
        return;
      }


      if (info.event.classNames.includes('booking-event')) {
        let content = `<span class="booking-span">${info.event.title}</span>`;

        if (info.event.extendedProps.avatar) {
          content = `<img src="${info.event.extendedProps.avatar}" alt="avatar" style="width:22px;height:22px;border-radius:50%;margin-right:6px;"> ${content}`;
        }

        info.el.innerHTML = content;

        // ✅ Tooltip content
        let tooltipText = `
          <strong>Source :</strong> ${getSourceLabel(info.event.classNames)}<br>
          <strong>Nom :</strong> ${info.event.title}<br>
          <strong>Début :</strong> ${info.event.start.toLocaleDateString()}<br>
          <strong>Fin :</strong> ${info.event.end ? new Date(info.event.end.getTime() - 86400000).toLocaleDateString() : ''}<br>
        `;

        tippy(info.el, {
          content: tooltipText,
          allowHTML: true,
          theme: 'light-border',
          placement: 'top',
        });
      }

      function getSourceLabel(classList) {
        if (classList.includes('airbnb')) return 'Airbnb';
        if (classList.includes('bookingcom')) return 'Booking.com';
        return 'Réservation interne';
      }
    }
  });

  calendar.render();

  // Helper pour décrémenter la date de fin d’un jour (car FullCalendar donne une fin exclusive)
  function dayBefore(dateStr) {
    const date = new Date(dateStr);
    date.setDate(date.getDate() - 1);
    return date.toISOString().split('T')[0];
  }

  function showPanel(startStr, endStr = null) {
    selectedStart = startStr;
    selectedEnd = endStr;

    document.querySelector('.calendar-wrapper').classList.add('with-panel');
    document.getElementById('price-panel').classList.remove('hidden');

    document.getElementById('panel-dates').innerText = endStr ?
      `Du ${startStr} au ${dayBefore(endStr)}` :
      `Date : ${startStr}`;

    let price = 0;
    let priceDetails = []; // Store the breakdown of price calculation steps

    if (!endStr) {
      // Single date
      price = dailyPriceMap[startStr] || 0;
    } else {
      // Multiple days: min price
      const start = new Date(startStr);
      const end = new Date(endStr);
      let minPrice = Infinity;

      for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
        const key = d.toISOString().split('T')[0];
        if (dailyPriceMap[key] !== undefined) {
          const current = parseFloat(dailyPriceMap[key]);
          if (current < minPrice) minPrice = current;
        }
      }

      price = (minPrice !== Infinity) ? minPrice : 0;
    }

    // Show base price
    let basePrice = price;
    priceDetails.push({
      type: 'Base Price',
      value: basePrice
    });
    document.getElementById('base-price').value = basePrice.toFixed(2);

    updateFinalPrice();

    setTimeout(() => calendar.updateSize(), 10);
  }

  function hidePanel() {
    document.getElementById('price-panel').classList.add('hidden');
    document.querySelector('.calendar-wrapper').classList.remove('with-panel');
    setTimeout(() => calendar.updateSize(), 10);
  }

  // Calcul automatique
  document.getElementById('base-price').addEventListener('input', function () {
    // Get the updated base price
    const base_price = parseFloat(this.value);
    const guestCount = parseFloat(document.getElementById('guest-count').value);

    // Call the calculatePrice function with the updated base price
    updateFinalPrice(base_price, guestCount);
  });


  function updateFinalPrice(updatedBasePrice, guestCount) {
    // If guestCount is not provided or is falsy (null, undefined, 0, etc.), set it to 1
    if (!guestCount) {
      guestCount = 1;
    }
    axios.post('/admin-area/prices/calculate_price/', {
        logement_id: logementId,
        start: selectedStart,
        end: selectedEnd || selectedStart,
        base_price: updatedBasePrice,
        guests: guestCount // Send the number of guests to the backend
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
        const detailh3 = document.createElement('h3');
        detailh3.innerText = 'Détails';
        detailsContainer.appendChild(detailh3);

        const guestDiv = document.createElement('div');
        guestDiv.innerHTML = `
          <label for="guest-count">Nombre de personnes</label>
          <input type="number" id="guest-count" value="${guestCount}" step="1" min="1">
        `;
        detailsContainer.appendChild(guestDiv);

        // Attach the change event listener to the guest count input field
        document.getElementById('guest-count').addEventListener('input', function () {
          const guestCount = parseInt(this.value, 10); // Get the number of guests
          const base_price = parseFloat(document.getElementById('base-price').value);
          updateFinalPrice(base_price, guestCount); // Call the function to recalculate the price
        });

        // Create an unordered list to contain the details
        const detailsList = document.createElement('ul');
        detailsList.classList.add('price-details-list');

        // Iterate over the details and create a list item for each one
        for (const [key, value] of Object.entries(details)) {
          const listItem = document.createElement('li');
          listItem.classList.add('price-breakdown-item');

          // Set the content of each list item
          listItem.innerHTML = `<strong>${key}:</strong> ${value}`;

          // Append the list item to the list
          detailsList.appendChild(listItem);
        }

        // Append the list to the container
        detailsContainer.appendChild(detailsList);
      })
      .catch(error => {
        console.error('Error fetching price calculation:', error);
      });
  }

  function isReservedRange(startStr, endStr) {
    const start = new Date(startStr);
    const end = new Date(endStr);
    for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
      const dStr = d.toISOString().split('T')[0];
      if (reservedDates.has(dStr)) {
        return true;
      }
    }
    return false;
  }

  // Appliquer
  document.getElementById('apply-price').addEventListener('click', () => {
    const price = document.getElementById('base-price').value;

    const payload = {
      logement_id: logementId,
      value: price,
      start: selectedStart,
      end: selectedEnd ? dayBefore(selectedEnd) : selectedStart
    };

    const url = '/admin-area/prices/bulk_update/';
    const method = 'post';

    axios[method](url, payload).then(() => {
      calendar.refetchEvents();
      hidePanel();
    });
  });

  // Annuler
  document.getElementById('cancel-price').addEventListener('click', hidePanel);

  const resizeObserver = new ResizeObserver(() => {
    calendar.updateSize();
  });
  resizeObserver.observe(document.querySelector('.calendar-wrapper'));
});