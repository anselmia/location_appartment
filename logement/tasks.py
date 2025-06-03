import logging
import requests
from icalendar import Calendar
from datetime import datetime, date, time
from logement.models import Logement
from reservation.models import airbnb_booking, booking_booking, Reservation
from reservation.services.reservation_service import delete_old_reservations

# Setup a logger
logger = logging.getLogger(__name__)


def process_calendar(url, source):
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
                        logement = Logement.objects.first()

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
                        logement = Logement.objects.first()
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


def sync_calendar():
    results = {}

    for logement in Logement.objects.all():
        logement_results = {}

        airbnb_url = logement.airbnb_calendar_link
        booking_url = logement.booking_calendar_link

        if airbnb_url:
            try:
                logger.info(f"Syncing Airbnb calendar for logement {logement.id}...")
                added, updated, deleted = process_calendar(airbnb_url, source="airbnb")
                logement_results["airbnb"] = {
                    "added": added,
                    "updated": updated,
                    "deleted": deleted,
                }
                logger.info(f"Airbnb sync completed for logement {logement.id}.")
            except Exception as e:
                logger.error(f"Airbnb sync failed for logement {logement.id}: {e}")
                logement_results["airbnb"] = "error"

        if booking_url:
            try:
                logger.info(f"Syncing Booking calendar for logement {logement.id}...")
                added, updated, deleted = process_calendar(booking_url, source="booking")
                logement_results["booking"] = {
                    "added": added,
                    "updated": updated,
                    "deleted": deleted,
                }
                logger.info(f"Booking sync completed for logement {logement.id}.")
            except Exception as e:
                logger.error(f"Booking sync failed for logement {logement.id}: {e}")
                logement_results["booking"] = "error"

        results[logement.id] = logement_results

    return results


def transfert_funds():
    from payment.services.payment_service import charge_reservation

    reservations = Reservation.objects.filter(statut="confirmee")
    for reservation in reservations:
        if reservation.refundable_period_passed:
            charge_reservation(reservation)
