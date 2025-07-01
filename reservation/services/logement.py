import logging
from typing import Any, List, Tuple, Optional
from decimal import Decimal
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.core.cache import cache
from django.db.models.functions import ExtractYear, ExtractMonth
from django.db.models import F, ExpressionWrapper, DurationField, Sum, Q

from logement.models import Logement, CloseDate
from logement.services.price_service import set_price
from reservation.models import Reservation, airbnb_booking, booking_booking
from reservation.services.reservation_service import get_reservations
from common.services.cache import CACHE_TIMEOUT_SHORT


logger = logging.getLogger(__name__)


def get_logement_reservations_queryset(user, logement_id=None):
    if logement_id:
        logement = Logement.objects.get(id=logement_id)
        if logement.is_logement_admin(user):
            return Reservation.objects.filter(logement=logement)
        return Reservation.objects.none()
    elif user.is_admin or user.is_superuser:
        return Reservation.objects.all()
    else:
        logements = Logement.objects.filter(Q(owner=user) | Q(admin=user))
        return Reservation.objects.filter(logement__in=logements).order_by("-date_reservation")


def get_valid_reservations_for_owner(
    user: Any, logement_id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None
) -> Any:
    """
    Retrieve valid (non-pending) reservations for an owner (or admin), optionally filtered by logement, year, and month.
    Uses caching for efficiency.
    Args:
        user: The admin user object.
        logement_id: Optional logement ID to filter by.
        year: Optional year to filter by.
        month: Optional month to filter by.
    Returns:
        QuerySet of Reservation objects.
    Raises:
        Exception: If retrieval fails.
    """
    cache_key = f"valid_logement_resa_admin_{user.id}_{logement_id or 'all'}_{year or 'all'}_{month or 'all'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        qs = get_reservations(
            user,
            logement_id,
            obj_type="logement",
            get_queryset_fn=get_logement_reservations_queryset,
            cache_prefix="reservations",
            cache_timeout=CACHE_TIMEOUT_SHORT,
        )
        qs = (
            qs.exclude(statut="en_attente")
            .order_by("-start")
            .select_related("user", "logement")
            .prefetch_related("logement__photos")
        )
        if year:
            qs = qs.annotate(res_year=ExtractYear("start")).filter(res_year=year)
        if month:
            qs = qs.annotate(res_month=ExtractMonth("start")).filter(res_month=month)

        qs = qs.order_by("-date_reservation")
        cache.set(cache_key, qs, CACHE_TIMEOUT_SHORT)
        return qs
    except Exception as e:
        logger.error(f"Error fetching admin reservations: {e}", exc_info=True)
        raise


def get_night_booked_in_period(logements: Any, logement_id: Optional[int], start: date, end: date) -> int:
    """
    Calculate the total number of nights booked for a logement or list of logements in a period.
    Uses cache for efficiency.
    Args:
        logements: QuerySet or list of logements.
        logement_id: Optional logement ID.
        start: Start date.
        end: End date.
    Returns:
        int: Total nights booked.
    """
    cache_key = f"nights_booked_{logement_id or 'all'}_{start}_{end}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    total_nights = 0

    def count_nights(resa_start, resa_end):
        overlap_start = max(start, resa_start)
        overlap_end = min(end, resa_end)
        if overlap_end > overlap_start:
            return (overlap_end - overlap_start).days
        return 0

    logement_ids = [logement_id] if logement_id else [l.id for l in logements]

    for lid in logement_ids:
        # Réservations locales
        local_reservations = Reservation.objects.filter(
            logement_id=lid,
            start__lte=end,
            end__gte=start,
        ).filter(Q(statut="confirmee") | Q(statut="terminee"))

        for res in local_reservations:
            total_nights += count_nights(res.start, res.end)

        # Réservations externes (Airbnb, Booking.com, etc.)
        for model in [airbnb_booking, booking_booking]:
            external_reservations = model.objects.filter(
                logement_id=lid,
                start__lte=end,
                end__gte=start,
            )
            for res in external_reservations:
                total_nights += count_nights(res.start, res.end)

    cache.set(cache_key, total_nights, CACHE_TIMEOUT_SHORT)
    return total_nights


def get_available_logement_in_period(start: date, end: date, logements: Any) -> Any:
    """
    Return logements available in a given period, excluding conflicts and respecting annual limits.
    Args:
        start: Start date.
        end: End date.
        logements: QuerySet of Logement to filter.
    Returns:
        QuerySet of available Logement objects, ordered by name.
    """
    try:
        if not start or not end:
            return Logement.objects.none()

        cache_key = f"available_logement_{start}_{end}"
        result = cache.get(cache_key)
        if result is not None:
            return result

        logger.info(f"Fetching available logements between {start} and {end}.")

        # 1. Récupère les conflits de réservation (réservations confirmées)
        reservation_conflits = Reservation.objects.filter(statut="confirmee", start__lt=end, end__gt=start).values_list(
            "logement_id", flat=True
        )

        # 2. Conflits Airbnb
        airbnb_conflits = airbnb_booking.objects.filter(start__lt=end, end__gt=start).values_list(
            "logement_id", flat=True
        )

        # 3. Conflits Booking.com
        booking_conflits = booking_booking.objects.filter(start__lt=end, end__gt=start).values_list(
            "logement_id", flat=True
        )

        # 4. Fermetures manuelles (CloseDate)
        closed_conflicts = CloseDate.objects.filter(date__gte=start, date__lte=end).values_list(
            "logement_id", flat=True
        )

        # Combine tous les IDs en conflit
        conflits_ids = set(reservation_conflits).union(airbnb_conflits, booking_conflits, closed_conflicts)

        # 5. Exclure les logements en conflit et ceux qui ne respectent pas la booking_limit ou le nombre de jours minimun
        logements = logements.exclude(id__in=conflits_ids).exclude(min_booking_days__gt=(end - start).days)
        logements = [l for l in logements if l.booking_limit <= start]

        # 6. Appliquer la règle des 120 jours pour les résidences principales
        year = start.year
        days_to_add = (end - start).days

        main_logement_ids = [l.id for l in logements if l.category == "main"]

        # Agrégation du nombre de jours réservés par logement pour l'année
        usage_counts = (
            Reservation.objects.filter(
                logement_id__in=main_logement_ids,
                statut="confirmee",
                start__year=year,
            )
            .annotate(nb_days=ExpressionWrapper(F("end") - F("start"), output_field=DurationField()))
            .values("logement")
            .annotate(total=Sum("nb_days"))
        )

        # Dictionnaire : logement_id -> jours réservés
        usage_dict = {row["logement"]: row["total"].days if row["total"] else 0 for row in usage_counts}

        # 7. Filtrage final
        filtered_logement = []

        for logement in logements:
            if logement.category == "main":
                used_days = usage_dict.get(logement.id, 0)
                if used_days + days_to_add <= 120:
                    filtered_logement.append(logement)
            else:
                filtered_logement.append(logement)

        logger.debug(f"Found {len(filtered_logement)} available logements.")
        cache.set(cache_key, result, CACHE_TIMEOUT_SHORT)
        return Logement.objects.filter(id__in=[l.id for l in filtered_logement]).order_by("name")

    except Exception as e:
        logger.error(f"Error checking logement availability: {e}", exc_info=True)
        return Logement.objects.none()


def get_booked_dates(logement: Any, user: Optional[Any] = None) -> Tuple[List[str], List[str]]:
    """
    Get all booked start and end dates for a logement, optionally for a user.
    Uses cache for efficiency.
    Args:
        logement: The logement object.
        user: Optional user object.
    Returns:
        Tuple of (reserved_start, reserved_end) lists as ISO date strings.
    """
    try:
        cache_key = f"booked_dates_{logement.id}_{user.id if user else 'anon'}"
        result = cache.get(cache_key)
        if result is not None:
            return result

        today = date.today()
        reserved_start = set()
        reserved_end = set()
        current_date = today
        while current_date < logement.booking_limit:
            reserved_start.add(current_date.isoformat())
            reserved_end.add(current_date.isoformat())
            current_date += timedelta(days=1)
        reservations = Reservation.objects.filter(logement=logement, end__gte=today)
        if user and user.is_authenticated:
            reservations = reservations.filter(Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user)))
        else:
            reservations = reservations.filter(statut="confirmee")
        for r in reservations.order_by("start"):
            current = r.start
            while current < r.end:
                reserved_start.add(current.isoformat())
                if current != r.start or (
                    current == r.start and (current - timedelta(days=1)).isoformat() in reserved_end
                ):
                    reserved_end.add(current.isoformat())
                current += timedelta(days=1)
        for model in [airbnb_booking, booking_booking]:
            for r in model.objects.filter(logement=logement, end__gte=today).order_by("start"):
                current = r.start
                while current < r.end:
                    reserved_start.add(current.isoformat())
                    if current != r.start or (
                        current == r.start and (current - timedelta(days=1)).isoformat() in reserved_end
                    ):
                        reserved_end.add(current.isoformat())
                    current += timedelta(days=1)

        # Ajout des dates fermées
        closed_dates = CloseDate.objects.filter(logement=logement, date__gte=today).values_list("date", flat=True)
        for d in closed_dates:
            reserved_start.add(d.isoformat())
            reserved_end.add(d.isoformat())

        if logement.min_booking_days:
            all_reserved = sorted(set(datetime.fromisoformat(d).date() for d in reserved_start))

            blocked_due_to_gap = set()

            # Check gaps between reserved blocks
            for i in range(len(all_reserved) - 1):
                gap_start = all_reserved[i] + timedelta(days=1)
                gap_end = all_reserved[i + 1]
                gap_length = (gap_end - gap_start).days

                if 0 < gap_length < logement.min_booking_days:
                    for j in range(gap_length):
                        day = gap_start + timedelta(days=j)
                        blocked_due_to_gap.add(day.isoformat())

            # Also check the gap before the first reservation and after the last one
            if all_reserved:
                # Gap before first reservation
                gap_start = today
                gap_end = all_reserved[0]
                gap_length = (gap_end - gap_start).days
                if 0 < gap_length < logement.min_booking_days:
                    for j in range(gap_length):
                        day = gap_start + timedelta(days=j)
                        blocked_due_to_gap.add(day.isoformat())

                # Gap after last reservation until booking_limit
                gap_start = all_reserved[-1] + timedelta(days=1)
                gap_end = logement.booking_limit
                gap_length = (gap_end - gap_start).days
                if 0 < gap_length < logement.min_booking_days:
                    for j in range(gap_length):
                        day = gap_start + timedelta(days=j)
                        blocked_due_to_gap.add(day.isoformat())

            reserved_start.update(blocked_due_to_gap)
            reserved_end.update(blocked_due_to_gap)

        logger.debug(f"{len(reserved_start)} dates réservées calculées pour logement {logement.id}")
        cache.set(cache_key, (reserved_start, reserved_end), CACHE_TIMEOUT_SHORT)
        return sorted(reserved_start), sorted(reserved_end)
    except Exception as e:
        logger.error(
            f"Error fetching booked dates for logement {logement.id}: {e}",
            exc_info=True,
        )
        return [], []


def is_period_booked(start: date, end: date, logement_id: int, user: Any) -> bool:
    """
    Check if a period is already booked for a logement, considering all sources.
    Args:
        start: Start date.
        end: End date.
        logement_id: The logement ID.
        user: The user object.
    Returns:
        bool: True if booked, False otherwise.
    """
    try:
        # Réservations internes
        reservations = Reservation.objects.filter(logement_id=logement_id, start__lt=end, end__gt=start).filter(
            Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user))
        )

        # Réservations externes
        airbnb_reservations = airbnb_booking.objects.filter(logement_id=logement_id, start__lt=end, end__gt=start)
        booking_reservations = booking_booking.objects.filter(logement_id=logement_id, start__lt=end, end__gt=start)

        # Dates fermées
        closed_dates = CloseDate.objects.filter(logement_id=logement_id, date__gte=start, date__lt=end)

        if (
            reservations.exists()
            or airbnb_reservations.exists()
            or booking_reservations.exists()
            or closed_dates.exists()
        ):
            logger.debug(f"Period {start} to {end} is already booked or closed.")
            return True

        logger.debug(f"Period {start} to {end} is available.")
        return False
    except Exception as e:
        logger.error(
            f"Error checking period booking for logement {logement_id}: {e}",
            exc_info=True,
        )
        return True


def validate_reservation_inputs(
    logement: Any,
    user: Any,
    start: date,
    end: date,
    guest_adult: int,
    guest_minor: int,
    expected_price: Optional[Decimal] = None,
    expected_tax: Optional[Decimal] = None,
) -> bool:
    """
    Validate reservation input data and raise ValueError if invalid.
    Args:
        logement: The logement object.
        user: The user object.
        start: Start date.
        end: End date.
        guest_adult: Number of adult guests.
        guest_minor: Number of minor guests.
        expected_price: Expected price (optional).
        expected_tax: Expected tax (optional).
    Returns:
        bool: True if valid, raises otherwise.
    Raises:
        ValueError: If any validation fails.
    """
    try:
        if guest_adult <= 0:
            raise ValueError("Nombre de voyageurs adultes invalide.")

        if guest_minor < 0:
            raise ValueError("Nombre de voyageurs mineurs invalide.")

        if guest_adult + guest_minor > logement.max_traveler:
            raise ValueError(f"Nombre de voyageurs total invalide. (max {logement.max_traveler}) personnes")

        if start < logement.booking_limit:
            raise ValueError("Ces dates ne sont plus disponible.")

        if start >= end:
            raise ValueError("La date de fin doit être après la date de début.")

        duration = (end - start).days
        if duration > logement.max_days:
            raise ValueError(f"La durée de la réservation doit être inférieure à {logement.max_days} jour(s).")

        today = datetime.today().date()
        limit_months = logement.availablity_period
        booking_horizon = today + relativedelta(months=limit_months)

        if start > booking_horizon:
            raise ValueError(
                f"Vous pouvez réserver au maximum {limit_months} mois à l'avance (jusqu'au {booking_horizon.strftime('%d/%m/%Y')})."
            )

        if is_period_booked(start, end, logement.id, user):
            raise ValueError("Les dates sélectionnées sont déjà réservées.")

        price_data = set_price(logement, start, end, guest_adult, guest_minor)
        real_price = price_data["total_price"]
        real_tax = price_data["tax_amount"]

        if expected_price and expected_tax:
            if abs(Decimal(expected_price) - real_price) > Decimal("0.01") or abs(
                Decimal(expected_tax) - real_tax
            ) > Decimal("0.01"):
                raise ValueError("Les montants ne correspondent pas aux prix réels.")

        return True
    except Exception as e:
        logger.error(f"Error validating reservation inputs: {e}", exc_info=True)
        raise


def create_or_update_reservation(
    logement: Any,
    user: Any,
    start: date,
    end: date,
    guest_adult: int,
    guest_minor: int,
    price: Decimal,
    tax: Decimal,
) -> Any:
    """
    Create or update a reservation for a user and logement.
    Args:
        logement: The logement object.
        user: The user object.
        start: Start date.
        end: End date.
        guest_adult: Number of adult guests.
        guest_minor: Number of minor guests.
        price: Reservation price.
        tax: Reservation tax.
    Returns:
        Reservation object.
    Raises:
        Exception: If creation or update fails.
    """
    try:
        reservation = Reservation.objects.filter(
            logement=logement, user=user, start=start, end=end, statut="en_attente"
        ).first()
        if reservation:
            reservation.start = start
            reservation.end = end
            reservation.guest_adult = guest_adult
            reservation.guest_minor = guest_minor
            reservation.price = price
            reservation.tax = tax
            reservation.save()
            logger.info(f"Reservation {reservation.code} updated.")
        else:
            reservation = Reservation.objects.create(
                logement=logement,
                user=user,
                guest_adult=guest_adult,
                guest_minor=guest_minor,
                start=start,
                end=end,
                price=price,
                tax=tax,
                statut="en_attente",
            )
            logger.info(f"Reservation {reservation.code} created.")
        return reservation
    except Exception as e:
        logger.exception(f"Error creating or updating reservation: {e}")
        raise


def get_occupancy_rate(logement: Logement, start: date, end: date) -> Decimal:
    """
    Calculate the occupancy rate for a logement in a given period.
    Args:
        logement: The Logement object.
        start: Start date of the period.
        end: End date of the period.
    Returns:
        Decimal occupancy rate (0.0 to 100.0 %).
    """
    total_days = (end - start).days + 1  # Include both start and end dates
    if total_days <= 0:
        return Decimal(0.0)

    booked_days = get_night_booked_in_period([], logement.id, start, end)
    occupancy_rate = Decimal(booked_days) / Decimal(total_days) * Decimal("100")
    return occupancy_rate.quantize(Decimal("0.01"))  # Round to two decimal places


def get_average_night_price(logement: Logement, start: date, end: date) -> Decimal:
    """
    Calcule le prix moyen par nuit pour un logement sur une période donnée,
    en se basant sur toutes les réservations confirmées/terminées de la période.
    Args:
        logement: L'objet Logement.
        start: Date de début de la période.
        end: Date de fin de la période.
    Returns:
        Decimal: prix moyen par nuit.
    """
    reservations = Reservation.objects.filter(
        logement=logement, start__gte=start, end__lte=end, statut__in=["confirmee", "terminee"]
    )

    total_nights = 0
    total_price = Decimal("0.00")

    for resa in reservations:
        nights = (resa.end - resa.start).days
        if nights > 0:
            total_nights += nights
            total_price += resa.price

    if total_nights == 0:
        return None

    average_price = total_price / Decimal(total_nights)
    return average_price.quantize(Decimal("0.01"))
