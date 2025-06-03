import logging
from django.utils import timezone
from datetime import timedelta
from reservation.models import Reservation
from huey.contrib.djhuey import periodic_task
from huey import crontab

# Setup a logger
logger = logging.getLogger(__name__)


@periodic_task(crontab(hour=3, minute=0))  # toutes les jours à 3h
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


@periodic_task(crontab(hour=4, minute=0))  # toutes les jours à 4h
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
