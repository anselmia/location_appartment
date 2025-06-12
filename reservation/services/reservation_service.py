import logging
from django.core.cache import cache

from decimal import Decimal
from datetime import timedelta, date, datetime
from dateutil.relativedelta import relativedelta

from django.utils import timezone
from django.db.models.functions import ExtractYear, ExtractMonth
from django.db.models import Q, Sum, F, ExpressionWrapper, DurationField

from reservation.models import Reservation, airbnb_booking, booking_booking, Logement
from logement.models import CloseDate
from logement.services.logement import set_price
from payment.services.payment_service import refund_payment


logger = logging.getLogger(__name__)
CACHE_TIMEOUT_SHORT = 60 * 5  # 5 minutes
CACHE_TIMEOUT_LONG = 60 * 60 * 24  # 24 hours


def get_reservations(user, logement_id=None):
    cache_key = f"reservations_{user.id}_{logement_id or 'all'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        if logement_id:
            logement = Logement.objects.get(id=logement_id)
            if logement.is_logement_admin(user):
                result = Reservation.objects.filter(logement=logement)
            else:
                result = Reservation.objects.none()
        elif user.is_admin or user.is_superuser:
            result = Reservation.objects.all()
        else:
            logements = Logement.objects.filter(Q(owner=user) | Q(admin=user))
            result = Reservation.objects.filter(logement__in=logements).order_by("-date_reservation")

        cache.set(cache_key, result, CACHE_TIMEOUT_SHORT)
        return result
    except Exception as e:
        logger.error(f"Error occurred while retrieving reservations: {e}", exc_info=True)
        raise


def get_valid_reservations_for_admin(user, logement_id=None, year=None, month=None):
    cache_key = f"valid_resa_admin_{user.id}_{logement_id or 'all'}_{year or 'all'}_{month or 'all'}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        qs = get_reservations(user, logement_id)
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


def get_valid_reservations_in_period(logement_id, start, end):
    return Reservation.objects.filter(
        logement_id=logement_id,
        start__lte=end,
        end__gte=start,
    ).filter(Q(statut="confirmee") | Q(statut="terminee"))


def get_night_booked_in_period(logements, logement_id, start, end):
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


def get_user_reservation(user):
    return Reservation.objects.filter(
        user=user, statut__in=["confirmee", "annulee", "terminee", "echec_paiement"]
    ).order_by("-start")


def get_reservation_years_and_months():
    cache_key = "reservation_years_months"
    result = cache.get(cache_key)
    if result:
        return result
    try:
        years = (
            Reservation.objects.annotate(y=ExtractYear("start")).values_list("y", flat=True).distinct().order_by("y")
        )
        months = (
            Reservation.objects.annotate(m=ExtractMonth("start")).values_list("m", flat=True).distinct().order_by("m")
        )
        result = (list(years), list(months))
        cache.set(cache_key, result, CACHE_TIMEOUT_LONG)
        return result
    except Exception as e:
        logger.error(f"Error fetching reservation years/months: {e}", exc_info=True)
        return [], []


def get_available_logement_in_period(start, end, logements):
    """
    Retourne les logements disponibles dans une période donnée,
    en excluant les conflits de réservation, les fermetures, et en respectant la limite
    annuelle de 120 jours pour les résidences principales.

    :param start: date de début
    :param end: date de fin
    :param logements: queryset de Logement à filtrer
    :return: queryset de Logement disponibles, triés par nom
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


def get_booked_dates(logement, user=None):
    try:
        cache_key = f"booked_dates_{logement.id}_{user.id if user else 'anon'}"
        result = cache.get(cache_key)
        if result is not None:
            return result

        logger.info(f"Fetching booked dates for logement {logement.id}.")
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


def is_period_booked(start, end, logement_id, user):
    try:
        logger.info(f"Checking if period {start} to {end} is booked for logement {logement_id}.")

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


def create_or_update_reservation(logement, user, start, end, guest_adult, guest_minor, price, tax):
    try:
        logger.info(
            f"Creating or updating reservation for logement {logement.id}, user {user}, dates {start} to {end}."
        )
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


def validate_reservation_inputs(
    logement, user, start, end, guest_adult, guest_minor, expected_price=None, expected_tax=None
):
    try:
        logger.info(
            f"Validating reservation inputs for logement {logement.id}, user {user.id}, dates {start} to {end}."
        )

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
        real_tax = price_data["taxAmount"]

        if expected_price and expected_tax:
            if abs(Decimal(expected_price) - real_price) > Decimal("0.01") or abs(
                Decimal(expected_tax) - real_tax
            ) > Decimal("0.01"):
                raise ValueError("Les montants ne correspondent pas aux prix réels.")

        return True
    except Exception as e:
        logger.error(f"Error validating reservation inputs: {e}", exc_info=True)
        raise


def mark_reservation_cancelled(reservation):
    try:
        logger.info(f"Marking reservation {reservation.code} as cancelled.")
        reservation.statut = "annulee"
        reservation.save()
        logger.info(f"Reservation {reservation.code} has been marked as cancelled.")
    except Exception as e:
        logger.exception(f"Error cancelling reservation {reservation.code}: {e}")
        raise


def cancel_and_refund_reservation(reservation):
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


def delete_old_reservations(event_dates, source):
    """
    Deletes future reservations that are no longer present in the calendar.
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
