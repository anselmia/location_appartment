import logging

from datetime import timedelta, date, datetime, time
from decimal import Decimal
from typing import Any, List, Tuple, Optional

from django.db.models import DateField
from django.db.models.functions import Cast
from django.utils import timezone

from activity.models import Activity, CloseDate
from activity.services.price import set_price
from payment.services.payment_service import refund_payment
from reservation.models import ActivityReservation

logger = logging.getLogger(__name__)
CACHE_TIMEOUT_SHORT = 60 * 5  # 5 minutes
CACHE_TIMEOUT_LONG = 60 * 60 * 24  # 24 hours


def get_activity_reservations_queryset(user, activity_id=None):
    if activity_id:
        activity = Activity.objects.get(id=activity_id)
        if activity.is_activity_admin(user):
            return ActivityReservation.objects.filter(activity=activity)
        return ActivityReservation.objects.none()
    elif user.is_admin or user.is_superuser:
        return ActivityReservation.objects.all()
    else:
        activities = Activity.objects.filter(owner=user)
        return ActivityReservation.objects.filter(activity__in=activities).order_by("-date_reservation")


def get_fully_booked_dates(activity: Any, start_date: date = None, end_date: date = None) -> List[str]:
    """
    Retourne la liste des jours où il n'y a aucun créneau disponible pour l'activité.
    """
    if start_date is None:
        start_date = date.today()
    if end_date is None:
        # You can use activity.booking_limit or set a default range
        end_date = activity.booking_limit

    fully_booked = []
    current_date = start_date
    while current_date <= end_date:
        slots = get_available_slots(activity, current_date)
        if not slots:
            fully_booked.append(current_date.isoformat())
        current_date += timedelta(days=1)
    return fully_booked


def get_available_slots(activity: Any, day: date, as_time: bool = False) -> list:
    """
    Retourne les créneaux disponibles pour le jour sélectionné.
    Résultat : { '2025-06-17': ['09:00', '11:00', ...] }
    """

    slots = []
    duration = timedelta(minutes=activity.duration)
    days_of_week = set(activity.days_of_week)  # ex: ['monday', 'wednesday']

    # Filter only reservations for the given day
    reservations = ActivityReservation.objects.annotate(start_date=Cast("start", DateField())).filter(
        activity=activity, start_date=day, statut__in=["en_attente", "confirmee", "echec_paiement"]
    )

    # If day is closed return empty list
    if CloseDate.objects.filter(activity=activity, date__exact=day).exists():
        return slots

    # If day is too close return empty list
    if day < activity.booking_limit:
        return slots

    weekday = day.strftime("%A").lower()
    if weekday not in days_of_week:
        return slots

    if activity.fixed_slots and activity.manual_time_slots:
        # Mode créneaux fixes : lire les horaires depuis manual_time_slots
        for line in activity.manual_time_slots.strip().splitlines():
            slot_time = line.strip()
            if not slot_time:
                continue
            # Vérifie si le créneau est libre (pas de réservation qui le chevauche)
            slot_start = datetime.combine(day, datetime.strptime(slot_time, "%H:%M").time())
            slot_end = slot_start + duration
            overlap = reservations.filter(start__lt=slot_end, end__gt=slot_start).exists()
            if not overlap:
                slots.append(datetime.strptime(slot_time, "%H:%M").time() if as_time else slot_time)
    else:
        # Mode automatique : créneaux toutes les 30 minutes, sans chevauchement, ready_period inclus
        start_time = activity.start
        end_time = activity.end
        slot_start = datetime.combine(day, start_time)
        slot_end = datetime.combine(day, end_time)
        step = timedelta(minutes=30)
        ready = timedelta(minutes=activity.ready_period or 0)
        while slot_start + duration <= slot_end:
            # The slot is busy for duration + ready_period
            busy_end = slot_start + duration + ready
            if slot_start + duration <= slot_end:
                overlap = reservations.filter(start__lt=busy_end, end__gt=slot_start).exists()
                if not overlap:
                    slots.append(slot_start.time() if as_time else slot_start.time().strftime("%H:%M"))
            else:
                slot_start = slot_end
            slot_start += step

    return slots


def validate_reservation_inputs(
    activity: Any,
    user: Any,
    start: date,
    guest: int,
    slot: str,
    expected_price: Optional[Decimal] = None,
) -> bool:
    """
    Validate reservation input data and raise ValueError if invalid.
    Args:
        activity: The activity object.
        user: The user object.
        start: Start date.
        guest: Number of guests.
        expected_price: Expected price (optional).
    Returns:
        bool: True if valid, raises otherwise.
    Raises:
        ValueError: If any validation fails.
    """
    try:
        if guest <= 0:
            raise ValueError("Nombre de voyageurs invalide.")

        if guest > activity.max_participants:
            raise ValueError(f"Nombre de voyageurs total invalide. (max {activity.max_traveler}) personnes")

        if start < activity.booking_limit:
            raise ValueError("Ces dates ne sont plus disponible.")

        if is_slot_booked(start, slot, activity):
            raise ValueError("L'horaire sélectionné est déjà réservé.")

        if expected_price is not None:
            price_data = set_price(activity, start, guest)
            real_price = price_data["total_price"]

            if abs(Decimal(expected_price) - real_price) > Decimal("0.01") > Decimal("0.01"):
                raise ValueError("Les montants ne correspondent pas aux prix réels.")

        return True
    except Exception as e:
        logger.error(f"Error validating reservation inputs: {e}", exc_info=True)
        raise


def available_by_day(activities: List[Activity], day: date) -> List[Activity]:
    """
    Retourne la liste des activités ayant au moins un créneau disponible pour le jour donné.
    """
    available_activities = []
    for activity in activities:
        slots = get_available_slots(activity, day)
        if slots:
            available_activities.append(activity)
    return available_activities


def is_slot_booked(start: date, slot: time, activity: int) -> bool:
    """
    Check if a slot is already booked for an activity, considering all sources.
    Args:
        start: Start date.
        slot:the start Time,
        activity_id: The activity ID.
        user: The user object.
    Returns:
        bool: True if booked, False otherwise.
    """
    try:
        logger.info(f"Checking if slot {start} {slot} is booked for activity {activity.id}.")

        # Réservations internes
        availables_slot = get_available_slots(activity, start, True)

        if slot not in availables_slot:
            logger.debug(f"Slot {start} {slot} is already booked or closed.")
            return True

        logger.debug(f"Slot {start} {slot} is available.")
        return False
    except Exception as e:
        logger.error(
            f"Error checking slot availability for activity {activity.id}: {e}",
            exc_info=True,
        )
        return True


def create_reservation(
    activity: Any,
    user: Any,
    start: date,
    slot: time,
    guest: int,
    price: Decimal,
) -> Any:
    """
    Create a reservation for a user and activity.
    Args:
        activity: The activity object.
        user: The user object.
        start: Start date.
        slot: The slot time
        guest: Number of guests.
        price: Reservation price.
    Returns:
        Reservation object.
    Raises:
        Exception: If creation fails.
    """
    try:
        logger.info(f"Creating  reservation for activity {activity.id}, user {user}, date {start}.")
        start_datetime = datetime.combine(start, slot)
        end_datetime = start_datetime + timedelta(minutes=activity.duration)
        reservation = ActivityReservation.objects.create(
            activity=activity,
            user=user,
            participants=guest,
            start=start_datetime,
            end=end_datetime,
            price=price,
            statut="en_attente",
        )
        logger.info(f"Reservation {reservation.code} created.")
        return reservation
    except Exception as e:
        logger.exception(f"Error creating or updating reservation: {e}")
        raise
