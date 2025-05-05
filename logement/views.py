from datetime import timedelta
import requests
from icalendar import Calendar
from datetime import datetime
import json
from django.shortcuts import render, get_object_or_404, redirect
from .models import Logement, Reservation

airbnb_calendar = "https://www.airbnb.fr/calendar/ical/48121442.ics?s=610867e1dc2cc14aba2f7b792ed5a4b1"


def home(request):
    logement = Logement.objects.prefetch_related("photos").first()

    if not logement:
        if request.user.is_authenticated and request.user.is_staff:
            return redirect("administration:dashboard")
        else:
            return render(
                request, "logement/no_logement.html"
            )  # Optional friendly page

    rooms = logement.rooms.all()

    # Fetch reserved dates for that logement
    reserved_dates = set()
    if logement:
        reservations = Reservation.objects.filter(logement=logement)
        for r in reservations:
            current = r.date_debut
            while current < r.date_fin:
                reserved_dates.add(current.isoformat())
                current += timedelta(days=1)

    return render(
        request,
        "logement/home.html",
        {
            "logement": logement,
            "rooms": rooms,
            "reserved_dates_json": json.dumps(sorted(reserved_dates)),
        },
    )


def reserver(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)

    if request.method == "POST":
        date_debut = request.POST.get("date_debut")
        date_fin = request.POST.get("date_fin")
        # Tu peux ici soit rediriger vers un formulaire complet, soit réserver direct
        return render(
            request,
            "logement/confirmation.html",
            {
                "logement": logement,
                "date_debut": date_debut,
                "date_fin": date_fin,
            },
        )

def fetch_airbnb_bookings(ical_url):
    response = requests.get(ical_url)
    calendar = Calendar.from_ical(response.text)
    bookings = []
    for component in calendar.walk():
        if component.name == "VEVENT":
            start = component.get("DTSTART").dt
            end = component.get("DTEND").dt
            bookings.append((start, end))
    return bookings