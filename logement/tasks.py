import logging

from huey.contrib.djhuey import periodic_task
from huey import crontab

from logement.models import Logement
from logement.services.calendar_service import process_calendar

# Setup a logger
logger = logging.getLogger(__name__)


@periodic_task(crontab(hour="*/1"))  # toutes les heures
def sync_calendar():
    results = {}

    for logement in Logement.objects.all():
        logement_results = {}

        airbnb_url = logement.airbnb_calendar_link
        booking_url = logement.booking_calendar_link

        if airbnb_url:
            try:
                logger.info(f"Syncing Airbnb calendar for logement {logement.id}...")
                added, updated, deleted = process_calendar(logement, airbnb_url, source="airbnb")
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
                added, updated, deleted = process_calendar(logement, booking_url, source="booking")
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
