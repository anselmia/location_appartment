import logging

from huey.contrib.djhuey import periodic_task
from huey import crontab

from logement.models import Logement
from logement.services.calendar_service import sync_external_ical

# Setup a logger
logger = logging.getLogger(__name__)


@periodic_task(crontab(minute=0))
def sync_calendar():
    results = {}

    for logement in Logement.objects.all():
        logement_results = {}

        airbnb_url = logement.airbnb_calendar_link
        booking_url = logement.booking_calendar_link

        if airbnb_url:
            try:
                logger.info(f"Syncing Airbnb calendar for logement {logement.code}...")
                added, updated, deleted = sync_external_ical(logement, airbnb_url, source="airbnb")
                logement_results["airbnb"] = {
                    "added": added,
                    "updated": updated,
                    "deleted": deleted,
                }
                logger.info(f"Airbnb sync completed for logement {logement.code}.")
            except Exception as e:
                logger.error(f"Airbnb sync failed for logement {logement.code}: {e}")
                logement_results["airbnb"] = "error"

        if booking_url:
            try:
                logger.info(f"Syncing Booking calendar for logement {logement.code}...")
                added, updated, deleted = sync_external_ical(logement, booking_url, source="booking")
                logement_results["booking"] = {
                    "added": added,
                    "updated": updated,
                    "deleted": deleted,
                }
                logger.info(f"Booking sync completed for logement {logement.code}.")
            except Exception as e:
                logger.error(f"Booking sync failed for logement {logement.code}: {e}")
                logement_results["booking"] = "error"

        results[logement.id] = logement_results

    return results
