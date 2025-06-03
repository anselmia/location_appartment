from reservation.models import Reservation
from huey.contrib.djhuey import periodic_task
from huey import crontab


@periodic_task(crontab(hour=2, minute=0))  # toutes les jours à 2h
def transfert_funds():
    from payment.services.payment_service import charge_reservation

    reservations = Reservation.objects.filter(statut="confirmee")
    for reservation in reservations:
        if reservation.refundable_period_passed:
            charge_reservation(reservation)
