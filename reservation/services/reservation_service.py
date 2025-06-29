import logging

from datetime import date, datetime
from typing import Any, List, Tuple, Optional

from django.utils import timezone
from django.db.models.functions import ExtractYear, ExtractMonth
from django.db.models import Q
from django.core.cache import cache

from reservation.models import Reservation, ActivityReservation, airbnb_booking, booking_booking, ReservationHistory, ActivityReservationHistory
from payment.services.payment_service import refund_payment
from common.services.cache import CACHE_TIMEOUT_SHORT, CACHE_TIMEOUT_LONG
from accounts.models import CustomUser


logger = logging.getLogger(__name__)


def get_reservation_type(reservation: Any) -> str:
    """
    Determine the type of reservation based on its class name.
    """
    if reservation.__class__.__name__ == "Reservation":
        return "logement"
    elif reservation.__class__.__name__ == "ActivityReservation":
        return "activity"
    else:
        logger.warning(f"⚠️ Unknown reservation type for {reservation.code}, defaulting to 'unknown'.")
        raise ValueError(f"Unknown reservation type for {reservation.code}. Please check the reservation class.")


def get_reservations(
    user: Any,
    obj_id: Optional[int],
    obj_type: str,
    get_queryset_fn,
    cache_prefix: str,
) -> Any:
    """
    Generic reservation retrieval with caching.
    - get_queryset_fn: function(user, obj_id) -> QuerySet
    """
    cache_key = f"{cache_prefix}_{user.id}_{obj_id or 'all'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        result = get_queryset_fn(user, obj_id)
        cache.set(cache_key, result, CACHE_TIMEOUT_SHORT)
        return result
    except Exception as e:
        logger.error(f"Error occurred while retrieving {obj_type} reservations: {e}", exc_info=True)
        raise


def get_reservation_by_code(code: str):
    """
    Retrieve a reservation (logement or activity) by its unique code.
    Args:
        code: The unique code of the reservation.
    Returns:
        Reservation or ActivityReservation object if found, None otherwise.
    """

    for model in (Reservation, ActivityReservation):
        try:
            return model.objects.get(code=code)
        except model.DoesNotExist:
            continue

    logger.warning(f"[get_reservation_by_code] No reservation found with code '{code}'.")
    return None


def get_valid_reservations_in_period(model, fk_name: str, obj_id: int, start: date, end: date) -> Any:
    """
    Get all valid (confirmed or finished) reservations for a given object (logement or activity) in a period.
    Args:
        model: The Reservation or ActivityReservation model.
        fk_name: The foreign key field name ('logement_id' or 'activity_id').
        obj_id: The object ID.
        start: Start date.
        end: End date.
    Returns:
        QuerySet of reservation objects.
    """
    filter_kwargs = {
        fk_name: obj_id,
        "start__lt" if model.__name__ == "ActivityReservation" else "start__lte": end,
        "end__gt" if model.__name__ == "ActivityReservation" else "end__gte": start,
    }
    return model.objects.filter(**filter_kwargs).filter(Q(statut="confirmee") | Q(statut="terminee"))


def get_valid_reservations(
    user: Any,
    obj_id: Optional[int],
    obj_type: str,
    get_queryset_fn,
    cache_prefix: str,
    select_related_fields: list,
    prefetch_related_fields: list,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> Any:
    """
    Retrieve valid (non-pending) reservations for an owner/admin, optionally filtered by object, year, and month.
    Uses caching for efficiency.
    """
    cache_key = f"{cache_prefix}_{user.id}_{obj_id or 'all'}_{year or 'all'}_{month or 'all'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        qs = get_reservations(
            user,
            obj_id,
            obj_type=obj_type,
            get_queryset_fn=get_queryset_fn,
            cache_prefix=cache_prefix,
        )
        if obj_type == "logement":
            qs = qs.exclude(statut__in=["en_attente"]).order_by("-start")
        elif obj_type == "activity":
            qs = qs.order_by("-start")
        if select_related_fields:
            qs = qs.select_related(*select_related_fields)
        if prefetch_related_fields:
            qs = qs.prefetch_related(*prefetch_related_fields)
        if year:
            qs = qs.annotate(res_year=ExtractYear("start")).filter(res_year=year)
        if month:
            qs = qs.annotate(res_month=ExtractMonth("start")).filter(res_month=month)
        qs = qs.order_by("-date_reservation")
        cache.set(cache_key, qs, CACHE_TIMEOUT_SHORT)
        return qs
    except Exception as e:
        logger.error(f"Error fetching {obj_type} reservations: {e}", exc_info=True)
        raise


def get_future_reservations(model, logement_or_activity) -> Any:
    """
    Récupère toutes les réservations futures pour un logement ou une activité, triées par date de début.
    Args:
        model: Reservation ou ActivityReservation.
        logement_or_activity: L'objet Logement ou Activity.
    Returns:
        QuerySet des réservations futures.
    """
    # Détecte le nom du champ FK selon le modèle
    if model.__name__ == "Reservation":
        fk_field = "logement"
        start_filter = timezone.now().date()
    elif model.__name__ == "ActivityReservation":
        fk_field = "activity"
        start_filter = timezone.now()
    else:
        raise ValueError("Modèle non supporté pour get_future_reservations")

    filter_kwargs = {
        fk_field: logement_or_activity,
        "start__gte": start_filter,
        "statut__in": ["confirmee", "terminee"],
    }
    return model.objects.filter(**filter_kwargs).order_by("start")


def get_payment_failed_reservations(model, logement_or_activity) -> Any:
    """
    Get all reservations with payment failure for a given logement or activity.
    Args:
        model: Reservation or ActivityReservation model.
        logement_or_activity: The Logement or Activity object.
    Returns:
        QuerySet of reservations with payment failure.
    """
    if model.__name__ == "Reservation":
        fk_field = "logement"
    elif model.__name__ == "ActivityReservation":
        fk_field = "activity"
    else:
        raise ValueError("Unsupported model for get_payment_failed_reservations")

    return model.objects.filter(**{fk_field: logement_or_activity, "statut": "echec_paiement"}).order_by(
        "-date_reservation"
    )


def get_user_reservations(user: Any, model, statut_list: Optional[list] = None, order_by: str = "-start") -> Any:
    """
    Get all reservations for a user, ordered by start date (descending) and filtered by statut if provided.
    Args:
        user: The user object.
        model: The Reservation or ActivityReservation model.
        statut_list: Optional list of statuses to filter by.
        order_by: Field to order by (default: '-start').
    Returns:
        QuerySet of reservation objects.
    """
    qs = model.objects.filter(user=user)
    if statut_list is not None:
        qs = qs.filter(statut__in=statut_list)
    return qs.order_by(order_by)


def get_reservation_years_and_months(model, cache_key_prefix: str) -> Tuple[List[int], List[int]]:
    """
    Get all years and months with at least one reservation for the given model.
    Uses cache for efficiency.
    Returns:
        Tuple of (years, months) lists.
    """
    cache_key = f"{cache_key_prefix}_reservation_years_months"
    result = cache.get(cache_key)
    if result:
        return result
    try:
        years = model.objects.annotate(y=ExtractYear("start")).values_list("y", flat=True).distinct().order_by("y")
        months = model.objects.annotate(m=ExtractMonth("start")).values_list("m", flat=True).distinct().order_by("m")
        result = (list(years), list(months))
        cache.set(cache_key, result, CACHE_TIMEOUT_LONG)
        return result
    except Exception as e:
        logger.error(f"Error fetching reservation years/months for {model.__name__}: {e}", exc_info=True)
        return [], []


def mark_reservation_cancelled(reservation: Any) -> None:
    """
    Mark any reservation as cancelled and save it.
    Args:
        reservation: The reservation object.
        statut_field: The name of the status field (default: "statut").
        cancelled_value: The value to set for cancellation (default: "annulee").
    Raises:
        Exception: If update fails.
    """
    try:
        logger.info(f"Marking reservation {getattr(reservation, 'code', repr(reservation))} as cancelled.")
        setattr(reservation, "statut", "annulee")
        reservation.save()
        logger.info(f"Reservation {getattr(reservation, 'code', repr(reservation))} has been marked as cancelled.")
    except Exception as e:
        logger.exception(f"Error cancelling reservation {getattr(reservation, 'code', repr(reservation))}: {e}")
        raise


def cancel_and_refund_reservation(reservation: Any, user: CustomUser) -> Tuple[Optional[str], Optional[str]]:
    """
    Cancel a reservation and process a refund if eligible (generic).
    Args:
        reservation: The reservation object.
    Returns:
        Tuple of (success_message, error_message).
    Raises:
        Exception: If cancellation or refund fails.
    """
    try:
        reservation_type = get_reservation_type(reservation)
        if reservation_type == "logement":
            today = timezone.now().date()
        elif reservation_type == "activity":
            today = timezone.now()
        logger.info(f"Attempting to cancel and refund reservation {getattr(reservation, 'code', repr(reservation))}")
        if reservation.start <= today:
            return (
                None,
                "❌ Vous ne pouvez pas annuler une réservation déjà commencée ou passée.",
            )
        if getattr(reservation, "statut") != "annulee":
            mark_reservation_cancelled(reservation)
            reservation_type = get_reservation_type(reservation)
            if reservation_type == "logement":
                ReservationHistory.objects.create(
                    reservation=reservation,
                    details=f"Réservation {reservation.code} annulée par {user.full_name}",
                )
            elif reservation_type == "activity":
                ActivityReservationHistory.objects.create(
                    activity_reservation=reservation,
                    details=f"Réservation {reservation.code} annulée par {user.full_name}",
                )
        else:
            logger.info(f"Reservation {getattr(reservation, 'code', repr(reservation))} is already cancelled.")
            return ("✅ Réservation déjà annulée.", None)
        if getattr(reservation, "refundable", False) and reservation.paid:
            if getattr(reservation, "stripe_payment_intent_id", None):
                try:
                    amount_in_cents = getattr(reservation, "refundable_amount", 0) * 100
                    refund_payment(reservation, refund="full", amount_cents=amount_in_cents)
                    logger.info(
                        f"Refund successfully processed for reservation {getattr(reservation, 'code', repr(reservation))}."
                    )
                    return ("✅ Réservation annulée et remboursée avec succès.", None)
                except Exception as e:
                    logger.error(
                        f"Refund failed for reservation {getattr(reservation, 'code', repr(reservation))}: {e}"
                    )
                    return (
                        "⚠️ Réservation annulée, mais remboursement échoué.",
                        "❗ Le remboursement a échoué. Contactez l’assistance.",
                    )
            logger.warning(
                f"No Stripe payment intent for reservation {getattr(reservation, 'code', repr(reservation))}."
            )
            return (
                "⚠️ Réservation annulée, mais remboursement échoué.",
                "❗ Le remboursement a échoué pour une raison inconnue. Contactez l'assistance.",
            )
        logger.info(f"Reservation {getattr(reservation, 'code', repr(reservation))} cancelled without refund.")
        return ("✅ Réservation annulée (aucun paiement à rembourser).", None)
    except Exception as e:
        logger.exception(
            f"Error cancelling and refunding reservation {getattr(reservation, 'code', repr(reservation))}: {e}"
        )
        raise


def delete_old_reservations(event_dates: List[Tuple[Any, Any]], source: str) -> int:
    """
    Deletes future reservations that are no longer present in the calendar.
    Args:
        event_dates: List of (start, end) tuples from the calendar.
        source: Source string ('airbnb' or 'booking').
    Returns:
        int: Number of deleted reservations.
    Raises:
        ValueError: If deletion fails.
    """
    try:
        deleted = 0

        # Determine the model to use based on the source
        if source == "airbnb":
            reservations = airbnb_booking.objects.filter(start__gte=datetime.now())
        elif source == "booking":
            reservations = booking_booking.objects.filter(start__gte=datetime.now())

        # Find reservations that are not in the event_dates list
        for reservation in reservations:
            # Vérifie si la réservation est toujours dans la liste des événements valides
            is_found = any(
                reservation.start == event_start.date() and reservation.end == event_end.date()
                for event_start, event_end in event_dates
            )

            if not is_found:
                logger.info(f"🗑️ Suppression de la réservation non trouvée dans le calendrier : {reservation}")
                reservation.delete()
                deleted += 1

        return deleted

    except Exception as e:
        logger.error(f"Error deleting old reservations from {source}: {str(e)}")
        raise ValueError(f"Error deleting old reservations from {source}: {str(e)}")
