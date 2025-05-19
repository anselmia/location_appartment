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
)
from logement.services.payment_service import refund_payment
from logement.services.email_service import send_mail_on_new_reservation, send_mail_on_refund_result

logger = logging.getLogger(__name__)


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


def calculate_price(logement, start, end, guestCount, base_price=None):
    default_price = logement.price

    # Calculate the number of nights
    number_of_nights = (end - start).days
    if number_of_nights == 0:
        number_of_nights = 1

    # Get custom prices in range
    custom_prices = Price.objects.filter(
        logement_id=logement.id, date__range=(start, end)
    )
    price_map = {p.date: p.value for p in custom_prices}

    total_base_price = 0  # Total base price for the whole range
    discount_totals = {}  # To store total discount amount per discount type

    # Get active discounts
    active_discounts = Discount.objects.filter(logement_id=logement.id)
    # Filter discounts with min_nights that apply for the date range
    valid_min_nights_discounts = [
        discount
        for discount in active_discounts
        if discount.min_nights and (end - start).days >= discount.min_nights
    ]
    # Keep only the discount with the highest min_nights
    if valid_min_nights_discounts:
        # Keep only the discount with the highest min_nights
        active_discounts = [
            max(valid_min_nights_discounts, key=lambda d: d.min_nights)
        ] + [discount for discount in active_discounts if not discount.min_nights]
    else:
        active_discounts = [
            discount for discount in active_discounts if not discount.min_nights
        ]

    valid_nights_before_discounts = [
        discount
        for discount in active_discounts
        if discount.days_before and (start - datetime.today().date()).days
    ]
    # Keep only the discount with the highest days_before
    if valid_nights_before_discounts:
        # Keep only the discount with the highest days_before
        active_discounts = [
            max(valid_nights_before_discounts, key=lambda d: d.days_before)
        ] + [discount for discount in active_discounts if not discount.days_before]
    else:
        active_discounts = [
            discount for discount in active_discounts if not discount.days_before
        ]

    # Apply discounts for each day in the range
    for day in range(number_of_nights):
        current_day = start + timedelta(days=day)
        daily_price = (
            float(base_price)
            if base_price
            else float(price_map.get(current_day, default_price))
        )

        # Add to total base price
        total_base_price += daily_price

        # Apply discounts with no date range first (always applicable)
        for discount in active_discounts:
            if not discount.start_date or not discount.end_date:
                # Apply the discount (percentage-based)
                discount_amount = daily_price * (float(discount.value) / 100)

                # Accumulate discount amount for total discount calculation
                if discount.discount_type.name not in discount_totals:
                    discount_totals[discount.discount_type.name] = 0
                discount_totals[discount.discount_type.name] += discount_amount

        # Apply discounts with a date range (only if within the date range)
        for discount in active_discounts:
            if discount.start_date and discount.end_date:  # Has a date range
                if discount.start_date <= current_day <= discount.end_date:
                    # Apply the discount (percentage-based)
                    discount_amount = daily_price * (float(discount.value) / 100)
                    daily_price -= discount_amount

                    # Accumulate discount amount for total discount calculation
                    if discount.discount_type.name not in discount_totals:
                        discount_totals[discount.discount_type.name] = 0
                    discount_totals[discount.discount_type.name] += discount_amount

    # Calculate the total price after all discounts have been applied
    total_price = total_base_price - sum(discount_totals.values())
    TotalextraGuestFee = float(
        max(
            (
                logement.fee_per_extra_traveler
                * (guestCount - logement.nominal_traveler)
                * number_of_nights
            ),
            0,
        )
    )
    total_price += TotalextraGuestFee
    PricePerNight = total_price / number_of_nights

    # Calculate the tax amount (tax * average price per night * total nights)
    taxRate = min(
        ((float(logement.tax) / 100) * (float(PricePerNight) / guestCount)), 6.43
    )
    taxAmount = taxRate * guestCount * number_of_nights

    total_price = float(total_price) + float(taxAmount) + float(logement.cleaning_fee)

    return {
        "number_of_nights": number_of_nights,
        "total_base_price": total_base_price,
        "TotalextraGuestFee": TotalextraGuestFee,
        "discount_totals": discount_totals,
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
            abs(expected_price - real_price) > 0.01
            or abs(expected_tax - real_tax) > 0.01
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
            refund_payment(reservation.stripe_payment_intent_id)
            return ("✅ Réservation annulée et remboursée avec succès.", None)
        except Exception:
            send_mail_on_refund_result(reservation, success=False, error_message=str(e))
            return (
                "⚠️ Réservation annulée, mais remboursement échoué.",
                "❗ Le remboursement a échoué. Contactez l’assistance.",
            )
    send_mail_on_refund_result(reservation, success=True)
    return ("✅ Réservation annulée (aucun paiement à rembourser).", None)


def handle_checkout_session_completed(data):
    reservation_id = data["metadata"].get("reservation_id")
    payment_intent = data.get("payment_intent")
    logger.info(
        f"🔔 Handling checkout.session.completed for reservation {reservation_id}"
    )

    try:
        reservation = Reservation.objects.get(id=reservation_id)

        if reservation.statut != "confirmee":
            reservation.statut = "confirmee"
            reservation.stripe_payment_intent_id = payment_intent
            reservation.save()
            logger.info(f"✅ Reservation {reservation.id} confirmed")

            try:
                send_mail_on_new_reservation(
                    reservation.logement, reservation, reservation.user
                )
            except Exception as e:
                logger.exception(
                    f"❌ Error sending mail for reservation {reservation.id}: {e}"
                )

        else:
            logger.info(f"ℹ️ Reservation {reservation.id} was already confirmed.")

    except Reservation.DoesNotExist:
        logger.warning(f"⚠️ Reservation {reservation_id} not found.")
    except Exception as e:
        logger.exception(
            f"❌ Unexpected error in handle_checkout_session_completed: {e}"
        )
