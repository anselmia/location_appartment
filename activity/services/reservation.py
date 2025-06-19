import logging
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta, date, datetime, time
from typing import Any, List, Tuple, Optional
from django.db.models import Q, DateField
from django.db.models.functions import ExtractYear, ExtractMonth
from django.core.cache import cache
from django.db.models.functions import Cast

from activity.models import ActivityReservation, CloseDate, Activity
from activity.services.price import set_price
from payment.services.payment_service import refund_payment


logger = logging.getLogger(__name__)
CACHE_TIMEOUT_SHORT = 60 * 5  # 5 minutes
CACHE_TIMEOUT_LONG = 60 * 60 * 24  # 24 hours


def get_reservations(user: Any, activity_id: Optional[int] = None) -> Any:
    """
    Retrieve reservations for a user, optionally filtered by activity.
    Uses caching for efficiency.
    Args:
        user: The user object.
        activity_id: Optional activity ID to filter by.
    Returns:
        QuerySet of Reservation objects.
    Raises:
        Exception: If retrieval fails.
    """
    cache_key = f"reservations_{user.id}_{activity_id or 'all'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        if activity_id:
            activity = Activity.objects.get(id=activity_id)
            if activity.is_activity_admin(user):
                result = ActivityReservation.objects.filter(activity=activity)
            else:
                result = ActivityReservation.objects.none()
        elif user.is_admin or user.is_superuser:
            result = ActivityReservation.objects.all()
        else:
            activities = Activity.objects.filter(owner=user)
            result = ActivityReservation.objects.filter(activity__in=activities).order_by("-date_reservation")

        cache.set(cache_key, result, CACHE_TIMEOUT_SHORT)
        return result
    except Exception as e:
        logger.error(f"Error occurred while retrieving reservations: {e}", exc_info=True)
        raise


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
        logger.info(f"Validating reservation inputs for activity {activity.id}, user {user.id}, dates {start}.")

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


def get_valid_reservations_in_period(activity_id: int, start: date, end: date) -> Any:
    """
    Get all valid (confirmed or finished) reservations for an activity in a given period.
    Args:
        activity_id: The activity ID.
        start: Start date (datetime or date).
        end: End date (datetime or date).
    Returns:
        QuerySet of ActivityReservation objects.
    """
    return ActivityReservation.objects.filter(
        activity_id=activity_id,
        start__lt=end,
        end__gt=start,
    ).filter(Q(statut="confirmee") | Q(statut="terminee"))


def get_valid_reservations_for_user(
    user: Any, activity_id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None
) -> Any:
    """
    Retrieve valid (non-pending) reservations for an admin, optionally filtered by activity, year, and month.
    Uses caching for efficiency.
    Args:
        user: The admin user object.
        activity_id: Optional activity ID to filter by.
        year: Optional year to filter by.
        month: Optional month to filter by.
    Returns:
        QuerySet of Reservation objects.
    Raises:
        Exception: If retrieval fails.
    """
    cache_key = f"valid_resa_admin_{user.id}_{activity_id or 'all'}_{year or 'all'}_{month or 'all'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        qs = get_reservations(user, activity_id)
        qs = qs.order_by("-start").select_related("user", "activity").prefetch_related("activity__photos")
        if year:
            qs = qs.annotate(res_year=ExtractYear("start")).filter(res_year=year)
        if month:
            qs = qs.annotate(res_month=ExtractMonth("start")).filter(res_month=month)

        qs = qs.order_by("-date_reservation")
        cache.set(cache_key, qs, CACHE_TIMEOUT_SHORT)
        return qs
    except Exception as e:
        logger.error(f"Error fetching user reservations: {e}", exc_info=True)
        raise


def get_reservation_years_and_months() -> Tuple[List[int], List[int]]:
    """
    Get all years and months with at least one reservation.
    Uses cache for efficiency.
    Returns:
        Tuple of (years, months) lists.
    """
    cache_key = "activity_reservation_years_months"
    result = cache.get(cache_key)
    if result:
        return result
    try:
        years = (
            ActivityReservation.objects.annotate(y=ExtractYear("start"))
            .values_list("y", flat=True)
            .distinct()
            .order_by("y")
        )
        months = (
            ActivityReservation.objects.annotate(m=ExtractMonth("start"))
            .values_list("m", flat=True)
            .distinct()
            .order_by("m")
        )
        result = (list(years), list(months))
        cache.set(cache_key, result, CACHE_TIMEOUT_LONG)
        return result
    except Exception as e:
        logger.error(f"Error fetching reservation years/months: {e}", exc_info=True)
        return [], []


def mark_reservation_cancelled(reservation: Any) -> None:
    """
    Mark a reservation as cancelled and save it.
    Args:
        reservation: The reservation object.
    Raises:
        Exception: If update fails.
    """
    try:
        logger.info(f"Marking reservation {reservation.code} as cancelled.")
        reservation.statut = "annulee"
        reservation.save()
        logger.info(f"Reservation {reservation.code} has been marked as cancelled.")
    except Exception as e:
        logger.exception(f"Error cancelling reservation {reservation.code}: {e}")
        raise


def get_user_activity_reservation(user: Any) -> Any:
    """
    Get all activity reservations for a user, ordered by start date (descending).
    Args:
        user: The user object.
    Returns:
        QuerySet of ActivityReservation objects.
    """
    return ActivityReservation.objects.filter(
        user=user,
    ).order_by("-start")


def cancel_and_refund_reservation(reservation: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Cancel a reservation and process a refund if eligible.
    Args:
        reservation: The reservation object.
    Returns:
        Tuple of (success_message, error_message).
    Raises:
        Exception: If cancellation or refund fails.
    """
    try:
        today = timezone.now().date()
        logger.info(f"Attempting to cancel and refund reservation {reservation.code}")
        if reservation.start <= today:
            return (
                None,
                "❌ Vous ne pouvez pas annuler une réservation déjà commencée ou passée.",
            )
        if reservation.statut != "annulee":
            mark_reservation_cancelled(reservation)
        else:
            logger.info(f"Reservation {reservation.code} is already cancelled.")
            return ("✅ Réservation déjà annulée.", None)
        if reservation.refundable:
            if reservation.stripe_payment_intent_id:
                try:
                    amount_in_cents = reservation.refundable_amount * 100
                    refund_payment(reservation, refund="full", amount_cents=amount_in_cents)
                    logger.info(f"Refund successfully processed for reservation {reservation.code}.")
                    return ("✅ Réservation annulée et remboursée avec succès.", None)
                except Exception as e:
                    logger.error(f"Refund failed for reservation {reservation.code}: {e}")
                    return (
                        "⚠️ Réservation annulée, mais remboursement échoué.",
                        "❗ Le remboursement a échoué. Contactez l’assistance.",
                    )
            logger.warning(f"No Stripe payment intent for reservation {reservation.code}.")
            return (
                "⚠️ Réservation annulée, mais remboursement échoué.",
                "❗ Le remboursement a échoué pour une raison inconnue. Contactez l'assistance.",
            )
        logger.info(f"Reservation {reservation.code} cancelled without refund.")
        return ("✅ Réservation annulée (aucun paiement à rembourser).", None)
    except Exception as e:
        logger.exception(f"Error cancelling and refunding reservation {reservation.code}: {e}")
        raise
