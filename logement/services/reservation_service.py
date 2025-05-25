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


logger = logging.getLogger(__name__)


def get_reservations(user, logement_id=None):
    try:
        if logement_id:
            # Use get_object_or_404 for safe retrieval of the logement
            logement = get_object_or_404(Logement, id=logement_id)

            # Check if the user is an admin or part of the admins for the logement
            if logement.is_logement_admin(user):
                qs = Reservation.objects.filter(logement=logement)
            else:
                qs = Reservation.objects.none()
        else:
            if user.is_admin:
                # Admin users can see all reservations
                qs = Reservation.objects.all()
            else:
                # Non-admin users: filter logements where the user is either the owner or an admin
                logements = Logement.objects.filter(Q(owner=user) | Q(admins=user))
                qs = Reservation.objects.filter(logement__in=logements)

        return qs

    except Exception as e:
        # Log the error and raise an exception
        logger.error(
            f"Error occurred while retrieving reservations: {e}", exc_info=True
        )
        # Optionally, you can re-raise the error or return a safe result, depending on the use case
        raise


def get_available_logement_in_period(start, end, logements):
    logger.info(f"Fetching available logements between {start} and {end}.")

    reservation_conflits = Reservation.objects.filter(
        statut="confirmee",
        start__lt=end,
        end__gt=start,
    ).values_list("logement_id", flat=True)

    airbnb_conflits = airbnb_booking.objects.filter(
        start__lt=end, end__gt=start
    ).values_list("logement_id", flat=True)

    booking_conflits = booking_booking.objects.filter(
        start__lt=end, end__gt=start
    ).values_list("logement_id", flat=True)

    conflits_ids = set(reservation_conflits).union(airbnb_conflits, booking_conflits)

    logements = logements.exclude(id__in=conflits_ids)

    logements = [l for l in logements if l.booking_limit <= start]

    logements_ids = [l.id for l in logements]

    logger.debug(f"Found {len(logements_ids)} available logements.")
    return Logement.objects.filter(id__in=logements_ids)


def get_booked_dates(logement, user=None):
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
        ).order_by("start")
    else:
        reservations = reservations.filter(statut="confirmee").order_by("start")

    for r in reservations:
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


def is_period_booked(start, end, logement_id, user):
    logger.info(
        f"Checking if period {start} to {end} is booked for logement {logement_id}."
    )

    reservations = Reservation.objects.filter(
        logement_id=logement_id, start__lt=end, end__gt=start
    ).filter(Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user)))

    airbnb_reservations = airbnb_booking.objects.filter(
        logement_id=logement_id,
        start__lt=end,
        end__gt=start,
    )

    booking_reservations = booking_booking.objects.filter(
        logement_id=logement_id,
        start__lt=end,
        end__gt=start,
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


def create_or_update_reservation(logement, user, start, end, guest, price, tax):
    logger.info(
        f"Creating or updating reservation for logement {logement.id}, user {user.id}, dates {start} to {end}."
    )

    reservation = Reservation.objects.filter(
        logement=logement,
        user=user,
        start=start,
        end=end,
        statut="en_attente",
    ).first()

    if reservation:
        reservation.start = start
        reservation.end = end
        reservation.guest = guest
        reservation.price = price
        reservation.tax = tax
        reservation.save()
        created = False
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
        created = True
        logger.info(f"Reservation {reservation.id} created.")

    return reservation


def get_best_discounts(discounts, start_date, end_date):
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
                    (d.days_before_min or 0) > (best_days_before.days_before_min or 0)
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


def apply_discounts(base_price, current_day, discounts_by_type):
    logger.debug(f"Applying discounts to price {base_price} for date {current_day}.")

    discount_applied = []

    # Apply global discounts first
    for key in ["min_nights", "days_before"]:
        d = discounts_by_type.get(key)
        if d:
            discount = base_price * float(d.value) / 100
            base_price -= discount
            discount_applied.append((d.name, discount))

    # Apply date-range specific discount
    for d in discounts_by_type.get("date_range", []):
        if d.start_date <= current_day <= d.end_date:
            discount = base_price * float(d.value) / 100
            base_price -= discount
            discount_applied.append((d.name, discount))

    return base_price, discount_applied


def calculate_price(logement, start, end, guestCount, base_price=None):
    logger.info(
        f"Calculating price for logement {logement.id}, dates {start} to {end}, {guestCount} guests."
    )

    default_price = logement.price
    nights = (end - start).days or 1

    custom_prices = Price.objects.filter(
        logement_id=logement.id, date__range=(start, end)
    )
    price_map = {p.date: p.value for p in custom_prices}

    discounts = Discount.objects.filter(logement=logement, is_active=True)
    best_discounts = get_best_discounts(discounts, start, end)

    total_base = 0
    total_discount_amount = 0
    discount_breakdown = {}

    for day in range(nights):
        current_day = start + timedelta(days=day)
        daily_price = (
            float(base_price)
            if base_price
            else float(price_map.get(current_day, default_price))
        )
        total_base += daily_price

        final_price, discounts_today = apply_discounts(
            daily_price, current_day, best_discounts
        )
        for name, amount in discounts_today:
            discount_breakdown.setdefault(name, 0)
            discount_breakdown[name] += amount
            total_discount_amount += amount

    total_price = total_base - total_discount_amount

    # Extra guest fee
    extra_fee = max(
        logement.fee_per_extra_traveler
        * (guestCount - logement.nominal_traveler)
        * nights,
        0,
    )
    total_price += extra_fee

    # Taxes
    per_night = total_price / nights
    per_night_decimal = Decimal(str(per_night))
    guest_count_decimal = Decimal(str(guestCount))
    tax_cap = logement.tax_max

    # Ensure logement.tax is already a Decimal, just normalize everything else:
    taxRate = min(
        ((logement.tax / Decimal("100")) * (per_night_decimal / guest_count_decimal)),
        tax_cap,
    )
    taxAmount = taxRate * guestCount * nights

    total_price = Decimal(str(total_price))
    total_price += taxAmount + logement.cleaning_fee

    logger.debug(f"Total price calculated: {total_price}")
    return {
        "number_of_nights": nights,
        "total_base_price": total_base,
        "TotalextraGuestFee": extra_fee,
        "discount_totals": discount_breakdown,
        "taxAmount": taxAmount,
        "total_price": total_price,
    }


def validate_reservation_inputs(
    logement, user, start, end, guest, expected_price=None, expected_tax=None
):
    logger.info(
        f"Validating reservation inputs for logement {logement.id}, user {user.id}, dates {start} to {end}."
    )

    if guest <= 0 or guest > logement.max_traveler:
        logger.error(f"Invalid guest count {guest} for reservation.")
        raise ValueError("Nombre de voyageurs invalide.")

    if start < logement.booking_limit:
        logger.error(
            f"Start date {start} is before booking limit for logement {logement.id}."
        )
        raise ValueError("Ces dates ne sont plus disponible.")

    if start >= end:
        logger.error("End date is not after start date.")
        raise ValueError("La date de fin doit être après la date de début.")

    duration = (end - start).days  # nombre de jours complets
    if duration > logement.max_days:
        logger.error(
            f"Reservation duration {duration} exceeds maximum allowed days for logement {logement.id}."
        )
        raise ValueError(
            f"La durée de la réservation doit être inférieure à {logement.max_days} jour(s)."
        )

    # 🗓️ Enforce availablity_period (months from today)
    today = datetime.today().date()
    limit_months = logement.availablity_period
    booking_horizon = today + relativedelta(months=limit_months)

    if start > booking_horizon:
        logger.error(
            f"Booking attempt exceeds booking horizon for logement {logement.id}."
        )
        raise ValueError(
            f"Vous pouvez réserver au maximum {limit_months} mois à l'avance (jusqu'au {booking_horizon.strftime('%d/%m/%Y')})."
        )

    if is_period_booked(start, end, logement.id, user):
        logger.error(
            f"Dates {start} to {end} are already booked for logement {logement.id}."
        )
        raise ValueError("Les dates sélectionnées sont déjà réservées.")

    price_data = calculate_price(logement, start, end, guest)

    real_price = price_data["total_price"]
    real_tax = price_data["taxAmount"]

    if expected_price and expected_tax:
        if abs(Decimal(expected_price) - Decimal(real_price)) > Decimal("0.01") or abs(
            Decimal(expected_tax) - Decimal(real_tax)
        ) > Decimal("0.01"):
            logger.error(
                f"Expected price or tax doesn't match the real price or tax for reservation."
            )
            raise ValueError("Les montants ne correspondent pas aux prix réels.")

    return True


def mark_reservation_cancelled(reservation):
    logger.info(f"Marking reservation {reservation.id} as cancelled.")
    reservation.statut = "annulee"
    reservation.save()
    logger.info(f"Reservation {reservation.id} has been marked as cancelled.")


def cancel_and_refund_reservation(reservation):
    today = timezone.now().date()

    # Log the start of the cancellation and refund process
    logger.info(f"Attempting to cancel and refund reservation {reservation.id}")

    # Check if the reservation has already started or passed
    if reservation.start <= today:
        return (
            None,
            "❌ Vous ne pouvez pas annuler une réservation déjà commencée ou passée.",
        )

    # Mark the reservation as cancelled
    mark_reservation_cancelled(reservation)

    # Handle refund if applicable
    if reservation.refundable:
        if reservation.stripe_payment_intent_id:
            try:
                # Calculate the refund amount (converted to cents)
                refund_amount = reservation.refundable_amount * 100

                # Attempt to process the refund
                refund_payment(reservation, refund_amount)

                logger.info(
                    f"Refund successfully processed for reservation {reservation.id}."
                )
                return ("✅ Réservation annulée et remboursée avec succès.", None)
            except stripe.error.StripeError as e:
                # Handle Stripe-specific errors
                logger.error(
                    f"Stripe refund failed for reservation {reservation.id}. Error: {str(e)}"
                )
                return (
                    "⚠️ Réservation annulée, mais remboursement échoué.",
                    "❗ Le remboursement a échoué. Contactez l’assistance.",
                )
            except Exception as e:
                # Handle other unexpected errors
                logger.error(
                    f"Unexpected error during refund process for reservation {reservation.id}. Error: {str(e)}"
                )
                return (
                    "⚠️ Réservation annulée, mais remboursement échoué.",
                    "❗ Le remboursement a échoué pour une raison inconnue. Contactez l'assistance.",
                )
        else:
            logger.warning(
                f"Reservation {reservation.id} is refundable, but no Stripe payment intent found."
            )
            return (
                "⚠️ Réservation annulée, mais remboursement échoué.",
                "❗ Le remboursement a échoué pour une raison inconnue. Contactez l'assistance.",
            )

    logger.info(
        f"Reservation {reservation.id} cancelled without refund (not refundable)."
    )
    return ("✅ Réservation annulée (aucun paiement à rembourser).", None)
