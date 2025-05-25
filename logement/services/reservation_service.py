import stripe
from decimal import Decimal
from datetime import timedelta, date, datetime
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404
import logging
from django.db.models import Q
from logement.models import (
    Reservation,
    airbnb_booking,
    booking_booking,
    Price,
    Discount,
    Logement,
)
from logement.services.payment_service import refund_payment
from django.db.models.functions import ExtractYear, ExtractMonth


logger = logging.getLogger(__name__)


def get_reservations(user, logement_id=None):
    try:
        if logement_id:
            logement = get_object_or_404(Logement, id=logement_id)
            if logement.is_logement_admin(user):
                return Reservation.objects.filter(logement=logement)
            return Reservation.objects.none()
        if user.is_admin:
            return Reservation.objects.all()
        logements = Logement.objects.filter(Q(owner=user) | Q(admins=user))
        return Reservation.objects.filter(logement__in=logements)
    except Exception as e:
        logger.error(
            f"Error occurred while retrieving reservations: {e}", exc_info=True
        )
        raise


def get_valid_reservations_for_admin(user, logement_id=None, year=None, month=None):
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
        return qs
    except Exception as e:
        logger.error(f"Error fetching admin reservations: {e}", exc_info=True)
        raise


def get_reservation_years_and_months():
    try:
        years = (
            Reservation.objects.annotate(y=ExtractYear("start"))
            .values_list("y", flat=True)
            .distinct()
            .order_by("y")
        )
        months = (
            Reservation.objects.annotate(m=ExtractMonth("start"))
            .values_list("m", flat=True)
            .distinct()
            .order_by("m")
        )
        return years, months
    except Exception as e:
        logger.error(f"Error fetching reservation years/months: {e}", exc_info=True)
        return [], []


def get_available_logement_in_period(start, end, logements):
    try:
        logger.info(f"Fetching available logements between {start} and {end}.")
        reservation_conflits = Reservation.objects.filter(
            statut="confirmee", start__lt=end, end__gt=start
        ).values_list("logement_id", flat=True)
        airbnb_conflits = airbnb_booking.objects.filter(
            start__lt=end, end__gt=start
        ).values_list("logement_id", flat=True)
        booking_conflits = booking_booking.objects.filter(
            start__lt=end, end__gt=start
        ).values_list("logement_id", flat=True)
        conflits_ids = set(reservation_conflits).union(
            airbnb_conflits, booking_conflits
        )
        logements = logements.exclude(id__in=conflits_ids)
        logements = [l for l in logements if l.booking_limit <= start]
        logger.debug(f"Found {len(logements)} available logements.")
        return Logement.objects.filter(id__in=[l.id for l in logements])
    except Exception as e:
        logger.error(f"Error checking logement availability: {e}", exc_info=True)
        return Logement.objects.none()


def get_booked_dates(logement, user=None):
    try:
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
            reservations = reservations.filter(
                Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user))
            )
        else:
            reservations = reservations.filter(statut="confirmee")
        for r in reservations.order_by("start"):
            current = r.start
            while current < r.end:
                reserved_start.add(current.isoformat())
                if current != r.start or (
                    current == r.start
                    and (current - timedelta(days=1)).isoformat() in reserved_end
                ):
                    reserved_end.add(current.isoformat())
                current += timedelta(days=1)
        for model in [airbnb_booking, booking_booking]:
            for r in model.objects.filter(logement=logement, end__gte=today).order_by(
                "start"
            ):
                current = r.start
                while current < r.end:
                    reserved_start.add(current.isoformat())
                    if current != r.start or (
                        current == r.start
                        and (current - timedelta(days=1)).isoformat() in reserved_end
                    ):
                        reserved_end.add(current.isoformat())
                    current += timedelta(days=1)
        logger.debug(
            f"{len(reserved_start)} dates réservées calculées pour logement {logement.id}"
        )
        return sorted(reserved_start), sorted(reserved_end)
    except Exception as e:
        logger.error(
            f"Error fetching booked dates for logement {logement.id}: {e}",
            exc_info=True,
        )
        return [], []


def is_period_booked(start, end, logement_id, user):
    try:
        logger.info(
            f"Checking if period {start} to {end} is booked for logement {logement_id}."
        )
        reservations = Reservation.objects.filter(
            logement_id=logement_id, start__lt=end, end__gt=start
        ).filter(Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user)))
        airbnb_reservations = airbnb_booking.objects.filter(
            logement_id=logement_id, start__lt=end, end__gt=start
        )
        booking_reservations = booking_booking.objects.filter(
            logement_id=logement_id, start__lt=end, end__gt=start
        )
        if (
            reservations.exists()
            or airbnb_reservations.exists()
            or booking_reservations.exists()
        ):
            logger.debug(f"Period {start} to {end} is already booked.")
            return True
        logger.debug(f"Period {start} to {end} is available.")
        return False
    except Exception as e:
        logger.error(
            f"Error checking period booking for logement {logement_id}: {e}",
            exc_info=True,
        )
        return True


def create_or_update_reservation(logement, user, start, end, guest, price, tax):
    try:
        logger.info(
            f"Creating or updating reservation for logement {logement.id}, user {user.id}, dates {start} to {end}."
        )
        reservation = Reservation.objects.filter(
            logement=logement, user=user, start=start, end=end, statut="en_attente"
        ).first()
        if reservation:
            reservation.start = start
            reservation.end = end
            reservation.guest = guest
            reservation.price = price
            reservation.tax = tax
            reservation.save()
            logger.info(f"Reservation {reservation.id} updated.")
        else:
            reservation = Reservation.objects.create(
                logement=logement,
                user=user,
                guest=guest,
                start=start,
                end=end,
                price=price,
                tax=tax,
                statut="en_attente",
            )
            logger.info(f"Reservation {reservation.id} created.")
        return reservation
    except Exception as e:
        logger.exception(f"Error creating or updating reservation: {e}")
        raise


def get_best_discounts(discounts, start_date, end_date):
    try:
        logger.info(f"Fetching best discounts for dates {start_date} to {end_date}.")

        best_min_nights = None
        best_days_before = None
        best_date_range_discounts = []

        nights = (end_date - start_date).days
        today = date.today()
        days_before = (start_date - today).days

        for d in discounts:
            if d.min_nights and nights >= d.min_nights:
                if not best_min_nights or d.min_nights > best_min_nights.min_nights:
                    best_min_nights = d

            if d.days_before_min or d.days_before_max:
                is_valid = True
                if d.days_before_min and days_before < d.days_before_min:
                    is_valid = False
                if d.days_before_max and days_before > d.days_before_max:
                    is_valid = False
                if is_valid:
                    if not best_days_before or (
                        (d.days_before_min or 0)
                        > (best_days_before.days_before_min or 0)
                    ):
                        best_days_before = d

            if d.start_date and d.end_date:
                best_date_range_discounts.append(d)

        logger.debug("Best discounts retrieved.")
        return {
            "min_nights": best_min_nights,
            "days_before": best_days_before,
            "date_range": best_date_range_discounts,
        }
    except Exception as e:
        logger.exception(f"Error determining best discounts: {e}")
        return {"min_nights": None, "days_before": None, "date_range": []}


def apply_discounts(base_price, current_day, discounts_by_type):
    try:
        logger.debug(
            f"Applying discounts to price {base_price} for date {current_day}."
        )

        base_price = (
            Decimal(str(base_price))
            if not isinstance(base_price, Decimal)
            else base_price
        )
        discount_applied = []

        for key in ["min_nights", "days_before"]:
            d = discounts_by_type.get(key)
            if d:
                try:
                    value = Decimal(str(d.value))
                    discount = (base_price * value) / Decimal("100")
                    base_price -= discount
                    discount_applied.append((d.name, discount))
                    logger.debug(f"Applied {d.name}: -{discount:.2f}")
                except (InvalidOperation, TypeError) as e:
                    logger.warning(
                        f"Invalid discount value for {d.name}: {d.value} – {e}"
                    )

        for d in discounts_by_type.get("date_range", []):
            if d.start_date <= current_day <= d.end_date:
                try:
                    value = Decimal(str(d.value))
                    discount = (base_price * value) / Decimal("100")
                    base_price -= discount
                    discount_applied.append((d.name, discount))
                    logger.debug(f"Applied {d.name}: -{discount:.2f}")
                except (InvalidOperation, TypeError) as e:
                    logger.warning(
                        f"Invalid discount value for {d.name}: {d.value} – {e}"
                    )

        return base_price, discount_applied
    except Exception as e:
        logger.exception(
            f"Error applying discounts on {current_day} with base {base_price}: {e}"
        )
        raise


def calculate_price(logement, start, end, guestCount, base_price=None):
    try:
        logger.info(
            f"Calculating price for logement {logement.id}, dates {start} to {end}, {guestCount} guests."
        )

        nights = (end - start).days or 1
        default_price = Decimal(str(logement.price))
        base_price = Decimal(str(base_price)) if base_price else None

        custom_prices = Price.objects.filter(
            logement_id=logement.id, date__range=(start, end)
        )
        price_map = {p.date: Decimal(str(p.value)) for p in custom_prices}

        discounts = Discount.objects.filter(logement=logement, is_active=True)
        best_discounts = get_best_discounts(discounts, start, end)

        total_base = Decimal("0.00")
        total_discount_amount = Decimal("0.00")
        discount_breakdown = {}

        for day in range(nights):
            current_day = start + timedelta(days=day)
            daily_price = (
                base_price if base_price else price_map.get(current_day, default_price)
            )
            total_base += daily_price

            final_price, discounts_today = apply_discounts(
                Decimal(daily_price), current_day, best_discounts
            )
            for name, amount in discounts_today:
                amount = Decimal(str(amount))
                discount_breakdown[name] = (
                    discount_breakdown.get(name, Decimal("0.00")) + amount
                )
                total_discount_amount += amount

        total_price = total_base - total_discount_amount

        # Extra guest fee
        extra_guests = max(guestCount - logement.nominal_traveler, 0)
        extra_fee = (
            Decimal(str(logement.fee_per_extra_traveler))
            * Decimal(str(extra_guests))
            * Decimal(str(nights))
        )
        total_price += extra_fee

        # Tax calculation
        per_night = total_price / Decimal(str(nights))
        guest_decimal = Decimal(str(guestCount))
        tax_cap = Decimal(str(logement.tax_max))

        tax_rate = min(
            (Decimal(str(logement.tax)) / Decimal("100")) * (per_night / guest_decimal),
            tax_cap,
        )
        taxAmount = tax_rate * guest_decimal * Decimal(str(nights))

        total_price += Decimal(str(logement.cleaning_fee)) + taxAmount

        return {
            "number_of_nights": nights,
            "total_base_price": total_base,
            "TotalextraGuestFee": extra_fee,
            "discount_totals": discount_breakdown,
            "taxAmount": taxAmount,
            "total_price": total_price,
        }
    except Exception as e:
        logger.exception(f"Error calculating price: {e}")
        raise


def validate_reservation_inputs(
    logement, user, start, end, guest, expected_price=None, expected_tax=None
):
    try:
        logger.info(
            f"Validating reservation inputs for logement {logement.id}, user {user.id}, dates {start} to {end}."
        )

        if guest <= 0 or guest > logement.max_traveler:
            raise ValueError("Nombre de voyageurs invalide.")

        if start < logement.booking_limit:
            raise ValueError("Ces dates ne sont plus disponible.")

        if start >= end:
            raise ValueError("La date de fin doit être après la date de début.")

        duration = (end - start).days
        if duration > logement.max_days:
            raise ValueError(
                f"La durée de la réservation doit être inférieure à {logement.max_days} jour(s)."
            )

        today = datetime.today().date()
        limit_months = logement.availablity_period
        booking_horizon = today + relativedelta(months=limit_months)

        if start > booking_horizon:
            raise ValueError(
                f"Vous pouvez réserver au maximum {limit_months} mois à l'avance (jusqu'au {booking_horizon.strftime('%d/%m/%Y')})."
            )

        if is_period_booked(start, end, logement.id, user):
            raise ValueError("Les dates sélectionnées sont déjà réservées.")

        price_data = calculate_price(logement, start, end, guest)
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
        logger.info(f"Marking reservation {reservation.id} as cancelled.")
        reservation.statut = "annulee"
        reservation.save()
        logger.info(f"Reservation {reservation.id} has been marked as cancelled.")
    except Exception as e:
        logger.exception(f"Error cancelling reservation {reservation.id}: {e}")
        raise


def cancel_and_refund_reservation(reservation):
    today = timezone.now().date()
    logger.info(f"Attempting to cancel and refund reservation {reservation.id}")
    if reservation.start <= today:
        return (
            None,
            "❌ Vous ne pouvez pas annuler une réservation déjà commencée ou passée.",
        )
    mark_reservation_cancelled(reservation)
    if reservation.refundable:
        if reservation.stripe_payment_intent_id:
            try:
                refund_amount = reservation.refundable_amount * 100
                refund_payment(reservation, refund_amount)
                logger.info(
                    f"Refund successfully processed for reservation {reservation.id}."
                )
                return ("✅ Réservation annulée et remboursée avec succès.", None)
            except Exception as e:
                logger.error(f"Refund failed for reservation {reservation.id}: {e}")
                return (
                    "⚠️ Réservation annulée, mais remboursement échoué.",
                    "❗ Le remboursement a échoué. Contactez l’assistance.",
                )
        logger.warning(f"No Stripe payment intent for reservation {reservation.id}.")
        return (
            "⚠️ Réservation annulée, mais remboursement échoué.",
            "❗ Le remboursement a échoué pour une raison inconnue. Contactez l'assistance.",
        )
    logger.info(f"Reservation {reservation.id} cancelled without refund.")
    return ("✅ Réservation annulée (aucun paiement à rembourser).", None)
