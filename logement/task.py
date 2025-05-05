from celery import shared_task
import requests
from icalendar import Calendar


@shared_task
def fetch_airbnb_calendar():
    url = "https://www.airbnb.com/calendar/ical/12345678.ics?s=abcdefg"
    response = requests.get(url)
    calendar = Calendar.from_ical(response.text)
    for component in calendar.walk():
        if component.name == "VEVENT":
            start = component.get("DTSTART").dt
            end = component.get("DTEND").dt
            # Save or update booking model here
