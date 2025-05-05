from celery import shared_task
import requests
from icalendar import Calendar
from .models import Logement, Client, Reservation
import datetime


@shared_task
def fetch_airbnb_calendar():
    url = "https://www.airbnb.fr/calendar/ical/48121442.ics?s=610867e1dc2cc14aba2f7b792ed5a4b1"
    response = requests.get(url)
    print(response)

    if response.status_code != 200:
        raise ValueError(
            f"Failed to fetch calendar. Status code: {response.status_code}"
        )

    print(response.text)

    # Check for valid iCal content
    if response.headers.get("Content-Type", "").startswith("text/calendar"):
        calendar = Calendar.from_ical(response.text)

        for component in calendar.walk():
            if component.name == "VEVENT":
                start = component.get("DTSTART").dt
                end = component.get("DTEND").dt
                title = component.get("SUMMARY", "")
                description = component.get("DESCRIPTION", "")

                # Ensure the start and end dates are in correct format (handle timezone or UTC)
                if isinstance(start, datetime.date):
                    start = datetime.datetime.combine(start, datetime.time.min)
                if isinstance(end, datetime.date):
                    end = datetime.datetime.combine(end, datetime.time.min)

                logement = Logement.objects.first()

                # Create or update the reservation
                reservation, created = Reservation.objects.update_or_create(
                    client=None,
                    logement=logement,
                    date_debut=start,
                    date_fin=end,
                    defaults={"statut": "confirmee"},
                )

                if created:
                    print(f"Reservation created: {reservation}")
                else:
                    print(f"Reservation updated: {reservation}")

    else:
        raise ValueError("Received non-icalendar response")
