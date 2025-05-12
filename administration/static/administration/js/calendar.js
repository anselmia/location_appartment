document.addEventListener('DOMContentLoaded', function () {
  const calendarEl = document.getElementById('calendar');
  const logementId = calendarEl.dataset.logementId;

  let reservedDates = new Set();
  let selecting = false; // ← Flag de protection

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
            title: `${e.value} €`
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
      if (selecting) {
        selecting = false; // ← annule le flag
        return;
      }

      const dateStr = info.dateStr;
      if (reservedDates.has(dateStr)) {
        alert("Impossible de modifier le prix : date déjà réservée.");
        return;
      }

      const newPrice = prompt("Entrez le nouveau prix pour le " + dateStr);
      if (newPrice) {
        axios.post(`/admin-area/prices/`, {
          logement: logementId,
          date: dateStr,
          value: newPrice
        }).then(() => calendar.refetchEvents());
      }
    },

    select: function (selectionInfo) {
      selecting = true; // ← on est dans un vrai "select"

      const start = new Date(selectionInfo.startStr);
      const end = new Date(selectionInfo.endStr);
      const error = [];

      for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
        const dStr = d.toISOString().split('T')[0];
        if (reservedDates.has(dStr)) error.push(dStr);
      }

      if (error.length > 0) {
        alert("Impossible de modifier le prix sur une période contenant des réservations :\n" + error.join(", "));
        return;
      }

      const value = prompt(`Prix pour la période du ${selectionInfo.startStr} au ${selectionInfo.endStr} (exclu) :`);
      if (value) {
        axios.post(`/admin-area/prices/bulk_update/`, {
          logement_id: logementId,
          start: selectionInfo.startStr,
          end: dayBefore(selectionInfo.endStr),
          value: value
        }).then(() => calendar.refetchEvents());
      }
    },

    eventDidMount: function (info) {
      if (info.event.classNames.includes('fc-event-price')) {
        info.el.innerHTML = `<div class="fc-event-price">${info.event.title}</div>`;
        return;
      }

      if (info.event.classNames.includes('booking-event')) {
        let content = `<span>${info.event.title}</span>`;

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
});