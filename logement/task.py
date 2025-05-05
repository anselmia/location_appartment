import logging
import requests
from celery import shared_task
from icalendar import Calendar
from datetime import datetime, date, time
from logement.models import Logement, airbnb_booking, booking_booking

# Setup a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


def process_calendar(url, source):
    try:
        response = requests.get(url)
        if response.status_code != 200:
            logger.error(
                f"Failed to fetch calendar from {source}. Status code: {response.status_code}"
            )
            raise ValueError(
                f"Failed to fetch calendar. Status code: {response.status_code}"
            )

        # Check for valid iCal content
        if response.headers.get("Content-Type", "").startswith("text/calendar"):
            calendar = Calendar.from_ical(response.text)

            # Gather all the events' start and end dates
            event_dates = []
            for component in calendar.walk():
                if component.name == "VEVENT":
                    start = component.get("DTSTART").dt
                    end = component.get("DTEND").dt

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
                        logement = Logement.objects.first()

                        # Create or update the reservation for Airbnb or Booking
                        if source == "airbnb":
                            reservation, created = (
                                airbnb_booking.objects.update_or_create(
                                    logement=logement,
                                    start=start,
                                    end=end,
                                )
                            )
                            if created:
                                logger.info(
                                    f"Airbnb reservation created: {reservation}"
                                )
                            else:
                                logger.info(
                                    f"Airbnb reservation updated: {reservation}"
                                )

                    elif component.get("SUMMARY", "") == "Booked":
                        logement = Logement.objects.first()

                        if source == "booking":
                            reservation, created = (
                                booking_booking.objects.update_or_create(
                                    logement=logement,
                                    start=start,
                                    end=end,
                                )
                            )
                            if created:
                                logger.info(
                                    f"Booking reservation created: {reservation}"
                                )
                            else:
                                logger.info(
                                    f"Booking reservation updated: {reservation}"
                                )

            # After processing the calendar, delete any future reservations not in the calendar
            delete_old_reservations(event_dates, source)

        else:
            logger.error(f"Received non-icalendar response from {source}")
            raise ValueError("Received non-icalendar response")

    except Exception as e:
        logger.error(f"Error processing calendar from {source}: {str(e)}")
        raise ValueError(f"Error processing calendar from {source}: {str(e)}")


def delete_old_reservations(event_dates, source):
    """
    Deletes future reservations that are no longer present in the calendar.
    """
    try:
        # Determine the model to use based on the source
        if source == "airbnb":
            reservations = airbnb_booking.objects.filter(date_debut__gte=datetime.now())
        elif source == "booking":
            reservations = booking_booking.objects.filter(
                date_debut__gte=datetime.now()
            )

        # Find reservations that are not in the event_dates list
        for reservation in reservations:
            is_found = False
            for event_start, event_end in event_dates:
                if (
                    reservation.start == event_start
                    and reservation.end == event_end
                ):
                    is_found = True
                    break

            if not is_found:
                # If the reservation is not found in the updated calendar, delete it
                logger.info(f"Deleting reservation: {reservation}")
                reservation.delete()

    except Exception as e:
        logger.error(f"Error deleting old reservations from {source}: {str(e)}")
        raise ValueError(f"Error deleting old reservations from {source}: {str(e)}")


@shared_task
def sync_calendar():
    # Define the URLs
    airbnb_url = "https://www.airbnb.fr/calendar/ical/48121442.ics?s=610867e1dc2cc14aba2f7b792ed5a4b1"
    booking_url = (
        "https://ical.booking.com/v1/export?t=daf9d628-a484-45c2-94fd-60ff6beb6c91"
    )

    # Sync Airbnb Calendar
    logger.info("Syncing Airbnb calendar...")
    process_calendar(airbnb_url, source="airbnb")

    # Sync Booking Calendar
    logger.info("Syncing Booking calendar...")
    process_calendar(booking_url, source="booking")
