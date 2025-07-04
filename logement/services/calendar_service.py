import requests
from icalendar import Calendar, Event
from datetime import datetime, date, time
from django.conf import settings
from django.utils.timezone import make_aware
from django.shortcuts import get_object_or_404
from reservation.models import airbnb_booking, booking_booking
from reservation.services.reservation_service import delete_old_reservations
from reservation.models import Reservation, Logement
from logement.services.logement_service import get_logements
import logging
from django.http import HttpResponse

logger = logging.getLogger(__name__)


def generate_ical(code):
    """
    Generate an iCal file for a given logement code.

    Args:
        code (str): The unique code of the logement.

    Returns:
        bytes: The iCal file content in bytes.

    Raises:
        Exception: If logement is not found or iCal generation fails.
    """
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
        logger.error("Erreur lors de la génération du fichier iCal")
        raise e


def sync_external_ical(logement, url, source):
    """
    Synchronize external iCal data for a logement from a given URL and source.

    Args:
        logement (Logement): The logement instance to sync for.
        url (str): The iCal feed URL.
        source (str): The source identifier (e.g., 'airbnb', 'booking').

    Returns:
        tuple: (added, updated, deleted) counts of reservations.

    Raises:
        ValueError: If iCal data is empty or sync fails.
    """
    try:
        ical_data = requests.get(url).text
        if not ical_data:
            logger.error(f"Empty iCal data received from {source}")
            raise ValueError("Empty iCal data received")

        cal = Calendar.from_ical(ical_data)
        added, updated, deleted = process_calendar(logement, cal, source)
        return added, updated, deleted
    except Exception as e:
        logger.error(f"Error syncing iCal for {logement}: {str(e)}")
        raise ValueError(f"Error syncing iCal for {logement}: {str(e)}")


def process_calendar(logement, calendar, source):
    """
    Process an iCal calendar object and update reservations for a logement.

    Args:
        logement (Logement): The logement instance.
        calendar (Calendar): The parsed iCal Calendar object.
        source (str): The source identifier (e.g., 'airbnb', 'booking').

    Returns:
        tuple: (added, updated, deleted) counts of reservations.

    Raises:
        ValueError: If processing fails.
    """
    added = 0
    updated = 0
    try:
        # Gather all the events' start and end dates
        event_dates = []
        for component in calendar.walk():
            if component.name == "VEVENT":
                dtstart = component.get("DTSTART")
                dtend = component.get("DTEND")
                if dtstart is None or dtend is None:
                    logger.warning("Event missing DTSTART or DTEND, skipping.")
                    continue
                start = dtstart.dt
                end = dtend.dt

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

                # Create or update the reservation for Airbnb or Booking
                if source == "airbnb":
                    # Process the reservation based on the event's summary
                    if component.get("SUMMARY", "") == "Reserved":
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
    except Exception as e:
        logger.error(f"Error processing calendar from {source}: {str(e)}")
        raise ValueError(f"Error processing calendar from {source}: {str(e)}")


def get_calendar_context(user):
    logements = get_logements(user)
    if not logements.exists():
        return {"redirect": True}
    return {
        "logements": logements,
        "logements_json": [{"id": l.id, "name": l.name, "calendar_link": l.calendar_link} for l in logements],
    }


def export_ical_service(code: str):
    logger = logging.getLogger(__name__)
    try:
        ics_content = generate_ical(code)
        if ics_content:
            response = HttpResponse(ics_content, content_type="text/calendar")
            response["Content-Disposition"] = f"attachment; filename={code}_calendar.ics"
            return {"success": True, "response": response}
        else:
            return {"success": False, "error": "Aucune donnée à exporter", "status": 204}
    except Exception as e:
        logger.error(f"Error exporting iCal:  {e}")
        return {"success": False, "error": "Erreur interne serveur", "status": 500}
