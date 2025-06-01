import logging
import requests
from icalendar import Calendar
from django.utils import timezone
from datetime import datetime, date, time, timedelta
from logement.models import Logement, airbnb_booking, booking_booking, Reservation

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


def delete_old_reservations(event_dates, source):
    """
    Deletes future reservations that are no longer present in the calendar.
    """
    try:
        deleted = 0

        # Determine the model to use based on the source
        if source == "airbnb":
            reservations = airbnb_booking.objects.filter(start__gte=datetime.now())
        elif source == "booking":
            reservations = booking_booking.objects.filter(start__gte=datetime.now())

        # Find reservations that are not in the event_dates list
        for reservation in reservations:
            is_found = False
            for event_start, event_end in event_dates:
                if reservation.start == event_start.date() and reservation.end == event_end.date():
                    is_found = True
                    break

            if not is_found:
                # If the reservation is not found in the updated calendar, delete it
                logger.info(f"Deleting reservation: {reservation}")
                reservation.delete()
                deleted += 1

        return deleted

    except Exception as e:
        logger.error(f"Error deleting old reservations from {source}: {str(e)}")
        raise ValueError(f"Error deleting old reservations from {source}: {str(e)}")


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


def delete_expired_pending_reservations():
    try:
        expiry_time = timezone.now() - timedelta(minutes=30)
        count, _ = Reservation.objects.filter(statut="en_attente", date_reservation__lt=expiry_time).delete()

        expiry_time = timezone.now() - timedelta(weeks=1)
        count2, _ = Reservation.objects.filter(statut="echec_paiement", date_reservation__lt=expiry_time).delete()

        logger.info(f"Deleted {count} expired pending reservations")
        logger.info(f"Deleted {count2} expired reservations in failed payment")
        return f"Deleted {count} expired pending reservations and {count2} expired reservations in failed payment"
    except Exception as e:
        logger.exception(f"Error deleting expired reservations: {e}")
        return "Failed to delete expired reservations"


def end_reservations():
    try:
        today = timezone.now()
        ended = Reservation.objects.filter(statut="confirmee", end__lt=today)
        count = ended.count()
        ended.update(statut="terminee")
        logger.info(f"Ended {count} reservations")
        return f"Ended {count} reservations"
    except Exception as e:
        logger.exception(f"Error ending reservations: {e}")
        return "Failed to end reservations"


def transfert_funds():
    from logement.services.payment_service import charge_reservation

    reservations = Reservation.objects.filter(statut="confirmee")
    for reservation in reservations:
        if reservation.refundable_period_passed:
            charge_reservation(reservation)
