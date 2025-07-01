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
    logements = Logement.objects.all()
    total_synced = 0
    total_errors = 0

    for logement in logements:
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
                total_synced += 1
                logger.info(f"✅ Airbnb sync completed for logement {logement.code}.")
            except Exception as e:
                logger.error(f"❌ Airbnb sync failed for logement {logement.code}: {e}")
                logement_results["airbnb"] = {"error": str(e)}
                total_errors += 1
        else:
            logement_results["airbnb"] = "skipped"

        if booking_url:
            try:
                logger.info(f"Syncing Booking calendar for logement {logement.code}...")
                added, updated, deleted = sync_external_ical(logement, booking_url, source="booking")
                logement_results["booking"] = {
                    "added": added,
                    "updated": updated,
                    "deleted": deleted,
                }
                total_synced += 1
                logger.info(f"✅ Booking sync completed for logement {logement.code}.")
            except Exception as e:
                logger.error(f"❌ Booking sync failed for logement {logement.code}: {e}")
                logement_results["booking"] = {"error": str(e)}
                total_errors += 1
        else:
            logement_results["booking"] = "skipped"

        results[logement.code] = logement_results

    final_summary = {
        "synced_logements": total_synced,
        "errors": total_errors,
        "logements": results,
    }

    logger.info(f"📅 Calendar sync summary: {final_summary}")
    return final_summary