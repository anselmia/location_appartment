import requests

from icalendar import Calendar, Event
from datetime import datetime, date, time

from django.conf import settings
from django.utils.timezone import make_aware
from django.shortcuts import get_object_or_404

from reservation.models import airbnb_booking, booking_booking
from reservation.services.reservation_service import delete_old_reservations
from reservation.models import Reservation, Logement

import logging

logger = logging.getLogger(__name__)


def generate_ical(code):
    try:
        logement = get_object_or_404(Logement, code=code)

        cal = Calendar()
        cal.add("prodid", f"-//{settings.DOMAIN}//iCal export//FR")
        cal.add("version", "2.0")

        reservations = Reservation.objects.filter(logement=logement, statut="confirmee")
        logger.info(f"{reservations.count()} réservations exportées vers iCal")

        for res in reservations:
            event = Event()
            event.add("summary", "Reserved")
            event.add("dtstart", make_aware(datetime.combine(res.start, datetime.min.time())))
            event.add("dtend", make_aware(datetime.combine(res.end, datetime.min.time())))
            event.add("dtstamp", datetime.now())
            event["uid"] = f"{res.code}"
            cal.add_component(event)

        return cal.to_ical()

    except Exception as e:
        logger.exception("Erreur lors de la génération du fichier iCal")
        raise e


def process_calendar(logement, url, source):
    added = 0
    updated = 0
    try:
        response = requests.get(url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch calendar from {source}. Status code: {response.status_code}")
            raise ValueError(f"Failed to fetch calendar. Status code: {response.status_code}")

        # Check for valid iCal content
        if response.headers.get("Content-Type", "").startswith("text/calendar"):
            calendar = Calendar.from_ical(response.text)

            # Gather all the events' start and end dates
            event_dates = []
            for component in calendar.walk():
                if component.name == "VEVENT":
                    start = component.get("DTSTART").dt
                    end = component.get("DTEND").dt

                    logger.info(f"{source} - {start} to {end}")

                    # Ensure the start and end dates are in correct format (handle timezone or UTC)
                    if isinstance(start, datetime):
                        start = start.replace(tzinfo=None)  # Remove timezone if any
                    elif isinstance(start, date):
                        start = datetime.combine(start, time.min)

                    if isinstance(end, datetime):
                        end = end.replace(tzinfo=None)  # Remove timezone if any
                    elif isinstance(end, date):
                        end = datetime.combine(end, time.min)

                    if not isinstance(start, datetime):
                        logger.warning(f"Invalid start date: {start}")
                        continue  # Skip this event if the start date is not valid

                    if not isinstance(end, datetime):
                        logger.warning(f"Invalid end date: {end}")
                        continue  # Skip this event if the end date is not valid

                    # Add the event's date range to the list
                    event_dates.append((start, end))

                    # Process the reservation based on the event's summary
                    if component.get("SUMMARY", "") == "Reserved":

                        # Create or update the reservation for Airbnb or Booking
                        if source == "airbnb":
                            reservation, created = airbnb_booking.objects.update_or_create(
                                logement=logement,
                                start=start,
                                end=end,
                            )
                            if created:
                                logger.info(f"Airbnb reservation created: {reservation}")
                                added += 1
                            else:
                                logger.info(f"Airbnb reservation updated: {reservation}")
                                updated += 1

                    elif source == "booking":
                        reservation, created = booking_booking.objects.update_or_create(
                            logement=logement,
                            start=start,
                            end=end,
                        )
                        if created:
                            logger.info(f"Booking reservation created: {reservation}")
                            added += 1
                        else:
                            logger.info(f"Booking reservation updated: {reservation}")
                            updated += 1

            # After processing the calendar, delete any future reservations not in the calendar
            deleted = delete_old_reservations(event_dates, source)

            return added, updated, deleted

        else:
            logger.error(f"Received non-icalendar response from {source}")
            raise ValueError("Received non-icalendar response")

    except Exception as e:
        logger.error(f"Error processing calendar from {source}: {str(e)}")
        raise ValueError(f"Error processing calendar from {source}: {str(e)}")
