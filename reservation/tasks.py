import logging
from django.utils import timezone
from datetime import timedelta
from huey.contrib.djhuey import periodic_task
from huey import crontab

from reservation.models import Reservation, ActivityReservation
from common.services.email_service import (
    send_pre_checkin_reminders,
    send_pre_checkin_activity_reminders,
)


logger = logging.getLogger(__name__)


def _delete_expired_pending(model, pending_minutes=30, failed_weeks=1):
    try:
        expiry_pending = timezone.now() - timedelta(minutes=pending_minutes)
        count_pending, _ = model.objects.filter(
            statut="en_attente", date_reservation__lt=expiry_pending
        ).delete()

        expiry_failed = timezone.now() - timedelta(weeks=failed_weeks)
        count_failed, _ = model.objects.filter(
            statut="echec_paiement", date_reservation__lt=expiry_failed
        ).delete()

        logger.info(f"Deleted {count_pending} expired pending reservations for {model.__name__}")
        logger.info(f"Deleted {count_failed} expired reservations in failed payment for {model.__name__}")
        return f"Deleted {count_pending} expired pending and {count_failed} failed payment reservations for {model.__name__}"
    except Exception as e:
        logger.exception(f"Error deleting expired reservations for {model.__name__}: {e}")
        return f"Failed to delete expired reservations for {model.__name__}"


def _end_reservations(model):
    try:
        today = timezone.now()
        ended = model.objects.filter(statut="confirmee", end__lt=today)
        count = ended.count()
        ended.update(statut="terminee")
        logger.info(f"Ended {count} reservations for {model.__name__}")
        return f"Ended {count} reservations for {model.__name__}"
    except Exception as e:
        logger.exception(f"Error ending reservations for {model.__name__}: {e}")
        return f"Failed to end reservations for {model.__name__}"


@periodic_task(crontab(hour=3, minute=0))  # every day at 3am
def delete_expired_pending_reservations_logement():
    return _delete_expired_pending(Reservation)


@periodic_task(crontab(hour=3, minute=10))  # every day at 3am
def delete_expired_pending_reservations_activity():
    return _delete_expired_pending(ActivityReservation)


@periodic_task(crontab(hour=4, minute=0))  # every day at 4am
def end_reservations_logement():
    return _end_reservations(Reservation)


@periodic_task(crontab(hour=4, minute=10))  # every day at 4am
def end_reservations_activity():
    return _end_reservations(ActivityReservation)


@periodic_task(crontab(hour=0, minute=0))  # every day at midnight
def send_pre_check_in_logement():
    try:
        send_pre_checkin_reminders()
        logger.info("Check-in reminders sent for logement")
        return "Check-in reminders sent successfully for logement"
    except Exception as e:
        logger.exception(f"Error sending check-in reminders for logement: {e}")
        return "Failed to send check-in reminders for logement"


@periodic_task(crontab(hour=0, minute=10))  # every day at midnight
def send_pre_check_in_activity():
    try:
        send_pre_checkin_activity_reminders()
        logger.info("Check-in reminders sent for activity")
        return "Check-in reminders sent successfully for activity"
    except Exception as e:
        logger.exception(f"Error sending check-in reminders for activity: {e}")
        return "Failed to send check-in reminders for activity"