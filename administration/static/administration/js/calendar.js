document.addEventListener('DOMContentLoaded', function () {
  const calendarEl = document.getElementById('calendar');
  const logementId = calendarEl.dataset.logementId;

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
      const newPrice = prompt("Entrez le nouveau prix pour le " + info.dateStr);
      if (newPrice) {
        axios.post(`/admin-area/prices/`, {
          logement: logementId,
          date: info.dateStr,
          value: newPrice
        }).then(() => calendar.refetchEvents());
      }
    },

    select: function (selectionInfo) {
      const value = prompt(`Prix pour la période du ${selectionInfo.startStr} au ${selectionInfo.endStr} (exclu) :`);
      if (value) {
        axios.post(`/admin-area/prices/bulk_update/`, {
          logement_id: logementId,
          start: selectionInfo.startStr,
          end: dayBefore(selectionInfo.endStr), // ajuster car endStr est exclusif
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
          content = `<img src="${info.event.extendedProps.avatar}" alt="avatar"> ${content}`;
        }
    
        info.el.innerHTML = content;
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