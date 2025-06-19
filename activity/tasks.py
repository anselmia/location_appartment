import logging
from django.utils import timezone
from datetime import timedelta
from activity.models import ActivityReservation
from huey.contrib.djhuey import periodic_task
from huey import crontab

from common.services.email_service import send_pre_checkin_reminders

# Setup a logger
logger = logging.getLogger(__name__)


@periodic_task(crontab(hour=3, minute=0))  # tous les jours à 3h
def delete_expired_pending_reservations():
    try:
        expiry_time = timezone.now() - timedelta(minutes=30)  # 30 minutes
        count, _ = ActivityReservation.objects.filter(statut="en_attente", date_reservation__lt=expiry_time).delete()

        expiry_time = timezone.now() - timedelta(weeks=1)
        count2, _ = ActivityReservation.objects.filter(
            statut="echec_paiement", date_reservation__lt=expiry_time
        ).delete()

        logger.info(f"Deleted {count} expired pending reservations")
        logger.info(f"Deleted {count2} expired reservations in failed payment")
        return f"Deleted {count} expired pending reservations and {count2} expired reservations in failed payment"
    except Exception as e:
        logger.exception(f"Error deleting expired reservations: {e}")
        return "Failed to delete expired reservations"


@periodic_task(crontab(hour=4, minute=0))  # tous les jours à 4h
def end_reservations():
    try:
        today = timezone.now()
        ended = ActivityReservation.objects.filter(statut="confirmee", end__lt=today)
        count = ended.count()
        ended.update(statut="terminee")
        logger.info(f"Ended {count} reservations")
        return f"Ended {count} reservations"
    except Exception as e:
        logger.exception(f"Error ending reservations: {e}")
        return "Failed to end reservations"


@periodic_task(crontab(hour=0, minute=0))  # toutes les jours à 00h00
def send_pre_check_in():
    try:
        send_pre_checkin_reminders()
        logger.info("Check in reminders sent")
        return "Check-in reminders sent successfully"
    except Exception as e:
        logger.exception(f"Error sending Check in reminders: {e}")
        return "Failed to Check in reminders"
