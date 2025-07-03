import logging
import inspect
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
    """Delete expired pending reservations for logements."""
    from common.signals import update_last_task_result

    logger.info("Deleting expired pending logement reservations.")
    summary = _delete_expired_pending(Reservation)
    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)
    return summary


@periodic_task(crontab(hour=3, minute=10))  # every day at 3a:10
def delete_expired_pending_reservations_activity():
    """Delete expired pending reservations for activities."""
    from common.signals import update_last_task_result

    logger.info("Deleting expired pending activity reservations.")
    summary = _delete_expired_pending(ActivityReservation)
    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)
    return summary


@periodic_task(crontab(hour=4, minute=0))  # every day at 4am
def end_reservations_logement():
    """End reservations for logements that have passed their end date."""
    from common.signals import update_last_task_result

    logger.info("Ending logement reservations that have passed their end date.")
    summary = _end_reservations(Reservation)
    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)
    return summary


@periodic_task(crontab(hour=4, minute=10))  # every day at 4am
def end_reservations_activity():
    """End reservations for activities that have passed their end date."""
    from common.signals import update_last_task_result

    logger.info("Ending activity reservations that have passed their end date.")
    summary = _end_reservations(ActivityReservation)
    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)
    return summary


@periodic_task(crontab(hour=0, minute=0))  # every day at midnight
def send_pre_check_in_logement():
    """Send pre-check-in reminders for logement reservations."""
    from common.signals import update_last_task_result

    logger.info("Sending pre-check-in reminders for logement reservations.")
    summary = send_pre_checkin_reminders()
    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)
    return summary


@periodic_task(crontab(hour=0, minute=10))  # every day at midnight
def send_pre_check_in_activity():
    """Send pre-check-in reminders for activity reservations."""
    from common.signals import update_last_task_result

    logger.info("Sending pre-check-in reminders for activity reservations.")
    summary = send_pre_checkin_activity_reminders()
    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)
    return summary


@periodic_task(crontab(minute=0, hour=1))  # Runs daily at 1:00 AM
def clean_sensitive_payment_data():
    from common.signals import update_last_task_result
    from payment.services.payment_service import detach_stripe_payment_method

    now = timezone.now().date()
    cutoff_date = now - timedelta(days=30)
    cleaned_count = 0
    failed = 0
    cleaned_codes = []

    try:
        queryset = Reservation.objects.filter(
            statut__in=["terminee", "annulee", "echec_paiement"], end__lt=cutoff_date
        ).exclude(
            Q(stripe_saved_payment_method_id__isnull=True)
            & Q(stripe_payment_intent_id__isnull=True)
            & Q(stripe_deposit_payment_intent_id__isnull=True)
        )

        for resa in queryset:
            try:
                logger.info(f"Cleaning payment data for reservation {resa.code}")
                if resa.stripe_saved_payment_method_id:
                    detach_stripe_payment_method(resa)
                cleaned_codes.append(resa.code)
                resa.stripe_saved_payment_method_id = None
                resa.stripe_payment_intent_id = None
                resa.stripe_deposit_payment_intent_id = None
                resa.save(
                    update_fields=[
                        "stripe_saved_payment_method_id",
                        "stripe_payment_intent_id",
                        "stripe_deposit_payment_intent_id",
                    ]
                )
                cleaned_count += 1
            except Exception as e:
                logger.warning(f"Failed to clean reservation {resa.code}: {e}")
                failed += 1

        queryset = ActivityReservation.objects.filter(
            statut__in=["terminee", "annulee", "echec_paiement"], end__lt=cutoff_date
        ).exclude(
            Q(stripe_saved_payment_method_id__isnull=True)
            & Q(stripe_payment_intent_id__isnull=True)
        )

        for resa in queryset:
            try:
                logger.info(f"Cleaning payment data for reservation {resa.code}")
                if resa.stripe_saved_payment_method_id:
                    detach_stripe_payment_method(resa)
                cleaned_codes.append(resa.code)
                resa.stripe_saved_payment_method_id = None
                resa.stripe_payment_intent_id = None
                resa.save(update_fields=["stripe_saved_payment_method_id", "stripe_payment_intent_id"])
                cleaned_count += 1
            except Exception as e:
                logger.warning(f"Failed to clean reservation {resa.code}: {e}")
                failed += 1

        summary = {
            "cutoff_date": str(cutoff_date),
            "cleaned": cleaned_count,
            "failed": failed,
            "reservation_codes": cleaned_codes,
        }

        logger.info(f"Cleaned sensitive data for {cleaned_count} reservation(s).")
        name = inspect.currentframe().f_code.co_name
        update_last_task_result(name, summary)

    except Exception as e:
        logger.exception(f"Error cleaning reservation payment data: {e}")
        name = inspect.currentframe().f_code.co_name
        update_last_task_result(name, {"error": str(e)})
