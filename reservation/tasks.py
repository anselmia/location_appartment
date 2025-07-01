import logging
from django.utils import timezone
from django.db.models import Q

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
    result = {
        "model": model.__name__,
        "deleted": 0,
        "pending_minutes": pending_minutes,
        "errors": None,
    }

    try:
        now = timezone.now()

        # Detect if 'start' is a date or datetime field
        start_field = model._meta.get_field("start")
        if start_field.get_internal_type() == "DateField":
            start_compare = now.date()
        else:
            start_compare = now

        expiry_pending = now - timedelta(minutes=pending_minutes)
        count_pending, _ = (
            model.objects.filter(statut="en_attente")
            .filter(Q(date_reservation__lt=expiry_pending) | Q(start__gt=start_compare))
            .delete()
        )

        logger.info(f"Deleted {count_pending} expired pending reservations for {model.__name__}")
        result["deleted"] = count_pending
    except Exception as e:
        logger.exception(f"Error deleting expired reservations for {model.__name__}: {e}")
        result["errors"] = str(e)

    return result


def _end_reservations(model):
    result = {
        "model": model.__name__,
        "ended": 0,
        "errors": None,
    }

    try:
        today = timezone.now()
        ended_qs = model.objects.filter(statut="confirmee", end__lt=today)
        count = ended_qs.count()
        ended_qs.update(statut="terminee")
        logger.info(f"Ended {count} reservations for {model.__name__}")
        result["ended"] = count
    except Exception as e:
        logger.exception(f"Error ending reservations for {model.__name__}: {e}")
        result["errors"] = str(e)

    return result


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
    return send_pre_checkin_reminders()


@periodic_task(crontab(hour=0, minute=10))  # every day at midnight
def send_pre_check_in_activity():
    return send_pre_checkin_activity_reminders()
