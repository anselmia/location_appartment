from decimal import Decimal
from datetime import timedelta, date, datetime
from dateutil.relativedelta import relativedelta
from django.utils import timezone
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
from logement.services.email_service import (
    send_mail_on_refund_result,
)

logger = logging.getLogger(__name__)


def get_available_logement_in_period(start, end, logements):
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
    return Logement.objects.filter(id__in=logements_ids)


def get_booked_dates(logement, user=None):
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

    if reservations.exists():
        return True

    if airbnb_reservations.exists():
        return True

    if booking_reservations.exists():
        return True

    return False


def create_or_update_reservation(logement, user, start, end, guest, price, tax):
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

    logger.info(f"{'Créée' if created else 'Mise à jour'} réservation {reservation.id}")
    return reservation


def get_best_discounts(discounts, start_date, end_date):
    """Filter and return only the best discount for each logic type."""

    # Categories of logic (mutually exclusive)
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

    return {
        "min_nights": best_min_nights,
        "days_before": best_days_before,
        "date_range": best_date_range_discounts,
    }


def apply_discounts(base_price, current_day, discounts_by_type):
    """Apply applicable discounts to the given base price and return discounted price and breakdown."""

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

    if guest <= 0 or guest > logement.max_traveler:
        raise ValueError("Nombre de voyageurs invalide.")

    if start < logement.booking_limit:
        raise ValueError("Ces dates ne sont plus disponible.")

    if start >= end:
        raise ValueError("La date de fin doit être après la date de début.")

    duration = (end - start).days  # nombre de jours complets
    if duration > logement.max_days:
        raise ValueError(
            f"La durée de la réservation doit être inférieure à {logement.max_days} jour(s)."
        )

    # 🗓️ Enforce availablity_period (months from today)
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
        if (
            abs(Decimal(expected_price) - Decimal(real_price)) > Decimal("0.01")
            or abs(Decimal(expected_tax) - Decimal(real_tax)) > Decimal("0.01")
        ):
            raise ValueError("Les montants ne correspondent pas aux prix réels.")

    return True


def mark_reservation_cancelled(reservation):
    reservation.statut = "annulee"
    reservation.save()


def cancel_and_refund_reservation(reservation):
    today = timezone.now().date()

    if reservation.start <= today:
        return (
            None,
            "❌ Vous ne pouvez pas annuler une réservation déjà commencée ou passée.",
        )

    mark_reservation_cancelled(reservation)

    if reservation.stripe_payment_intent_id:
        try:
            refund_payment(reservation)
            return ("✅ Réservation annulée et remboursée avec succès.", None)
        except Exception:
            send_mail_on_refund_result(reservation, success=False, error_message=str(e))
            return (
                "⚠️ Réservation annulée, mais remboursement échoué.",
                "❗ Le remboursement a échoué. Contactez l’assistance.",
            )
    send_mail_on_refund_result(reservation, success=True)
    return ("✅ Réservation annulée (aucun paiement à rembourser).", None)
