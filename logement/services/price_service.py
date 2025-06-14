import logging
from typing import Any, Dict, Optional, Tuple, List

from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from payment.services.payment_service import get_payment_fee

from logement.models import Price, CloseDate, Logement, Discount
from django.shortcuts import get_object_or_404

from reservation.models import airbnb_booking, booking_booking


logger = logging.getLogger(__name__)


def bulk_update_prices(logement_id: int, start: str, end: str, price: float, statut: int) -> Dict[str, Any]:
    """
    Bulk update prices and close/open dates for a logement.
    """
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if not price or price <= 0:
        return {"error": "Le prix doit être supérieur à 0.", "status": 400}
    if not all([logement_id, start_date, end_date]):
        return {"error": "Missing required parameters.", "status": 400}
    for i in range((end_date - start_date).days + 1):
        day = start_date + timedelta(days=i)
        Price.objects.update_or_create(logement_id=logement_id, date=day, defaults={"value": price})
        if statut == 0:
            CloseDate.objects.get_or_create(logement_id=logement_id, date=day)
        else:
            CloseDate.objects.filter(logement_id=logement_id, date=day).delete()
    return {"status": "updated"}


def calculate_price_service(
    logement_id: int, start: str, end: str, base_price, guest_adult, guest_minor
) -> Dict[str, Any]:
    """
    Calculate the price details for a logement booking.
    """
    logement = get_object_or_404(Logement, id=logement_id)
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    price_data = set_price(logement, start_date, end_date, guest_adult, guest_minor, base_price)
    details = {f"Total {price_data['number_of_nights']} Nuit(s)": f"{round(price_data['total_base_price'], 2)} €"}
    if price_data["total_extra_guest_fee"] != 0:
        details["Voyageur(s) supplémentaire(s)"] = f"+ {round(price_data['total_extra_guest_fee'], 2)} €"
    for key, value in price_data["discount_totals"].items():
        details[f"Réduction {key}"] = f"- {round(value, 2)} €"
    details["Frais de ménage"] = f"+ {round(logement.cleaning_fee, 2)} €"
    details["Taxe de séjour"] = f"+ {round(price_data['tax_amount'], 2)} €"
    details["Frais de transaction"] = f"+ {round(price_data['payment_fee'], 2)} €"
    return {
        "final_price": round(price_data["total_price"], 2),
        "tax": round(price_data["tax_amount"], 2),
        "details": details,
    }


def get_price_for_date_service(logement_id: int, date: str):
    logger = logging.getLogger(__name__)
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        logement = get_object_or_404(Logement, id=logement_id)
        price = Price.objects.filter(logement=logement, date=parsed_date).first()
        logger.info(f"Price requested for logement {logement_id} on {date}")
        return {"success": True, "price": str(price.value) if price else str(logement.price)}
    except Logement.DoesNotExist:
        logger.warning(f"Logement {logement_id} not found")
        return {"success": False, "error": "Logement not found", "status": 404}
    except Exception as e:
        logger.exception(f"Failed to fetch price for date: {e}")
        return {"success": False, "error": "Erreur interne serveur", "status": 500}


def get_daily_price_data(logement_id: int, start_str: str, end_str: str) -> Dict[str, Any]:
    from reservation.services.reservation_service import get_valid_reservations_in_period

    start = datetime.fromisoformat(start_str).date()
    end = datetime.fromisoformat(end_str).date()
    logement = get_object_or_404(Logement, id=logement_id)
    default_price = logement.price

    start = datetime.fromisoformat(start_str).date()
    end = datetime.fromisoformat(end_str).date()

    custom_prices = Price.objects.filter(logement_id=logement_id, date__range=(start, end))
    price_map = {p.date: p.value for p in custom_prices}

    closed_date = CloseDate.objects.filter(logement_id=logement_id, date__range=(start, end))
    statut_map = {p.date: 0 for p in closed_date}
    daily_data = [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "price": price_map.get(start + timedelta(days=i), str(default_price)),
            "statut": 0 if (start + timedelta(days=i)) in statut_map else 1,
        }
        for i in range((end - start).days + 1)
    ]
    data_bookings = [
        {
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "name": b.user.name,
            "guests": b.total_guest,
            "total_price": str(b.price),
        }
        for b in get_valid_reservations_in_period(logement_id, start, end)
    ]
    airbnb_bookings = [
        {
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "name": "Airbnb",
        }
        for b in airbnb_booking.objects.filter(logement_id=logement_id, start__lte=end, end__gte=start)
    ]
    booking_bookings = [
        {
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "name": "Booking",
        }
        for b in booking_booking.objects.filter(logement_id=logement_id, start__lte=end, end__gte=start)
    ]
    closed_days = [{"date": c.date.isoformat()} for c in closed_date]
    return {
        "data": daily_data,
        "data_bookings": data_bookings,
        "airbnb_bookings": airbnb_bookings,
        "booking_bookings": booking_bookings,
        "closed_days": closed_days,
    }


def get_best_discounts(discounts: Any, start_date: date, end_date: date) -> Dict[str, Any]:
    """
    Determine the best discounts for a given period.
    """
    try:
        logger.info(f"Fetching best discounts for dates {start_date} to {end_date}.")

        best_min_nights = None
        best_days_before = None
        best_date_range_discounts = []

        nights = (end_date - start_date).days
        today = date.today()
        days_before = (start_date - today).days

        # Find best min_nights discount
        for d in discounts:
            if d.min_nights and nights >= d.min_nights:
                if not best_min_nights or d.min_nights > best_min_nights.min_nights:
                    best_min_nights = d
            # Find best days_before discount
            elif d.days_before_min or d.days_before_max:
                is_valid = True
                if d.days_before_min and days_before < d.days_before_min:
                    is_valid = False
                if d.days_before_max and days_before > d.days_before_max:
                    is_valid = False
                if is_valid:
                    if not best_days_before or ((d.days_before_min or 0) > (best_days_before.days_before_min or 0)):
                        best_days_before = d
            # Collect all overlapping date_range discounts
            elif d.start_date and d.end_date:
                if d.start_date <= end_date and d.end_date >= start_date:
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


def apply_discounts(
    base_price: Decimal, current_day: date, discounts_by_type: Dict[str, Any]
) -> Tuple[Decimal, List[Tuple[str, Decimal]]]:
    """
    Apply all applicable discounts to a daily price.
    """
    try:
        logger.debug(f"Applying discounts to price {base_price} for date {current_day}.")

        base_price = Decimal(str(base_price)) if not isinstance(base_price, Decimal) else base_price
        discount_applied = []

        # Apply min_nights and days_before discounts
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
                    logger.warning(f"Invalid discount value for {d.name}: {d.value} – {e}")

        # Apply all date_range discounts valid for current_day
        for d in discounts_by_type.get("date_range", []):
            if d.start_date <= current_day <= d.end_date:
                try:
                    value = Decimal(str(d.value))
                    discount = (base_price * value) / Decimal("100")
                    base_price -= discount
                    discount_applied.append((d.name, discount))
                    logger.debug(f"Applied {d.name}: -{discount:.2f}")
                except (InvalidOperation, TypeError) as e:
                    logger.warning(f"Invalid discount value for {d.name}: {d.value} – {e}")

        return base_price, discount_applied
    except Exception as e:
        logger.exception(f"Error applying discounts on {current_day} with base {base_price}: {e}")
        raise


def set_price(
    logement: Any,
    start: date,
    end: date,
    guest_adult: int,
    guest_minor: int,
    base_price: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Calculate the total price for a booking, including discounts, extra guest fees, taxes, and payment fees.

    Args:
        logement (Logement): The logement instance for which to calculate the price.
        start (date): The start date of the booking.
        end (date): The end date of the booking.
        guest_adult (int): Number of adult guests.
        guest_minor (int): Number of minor guests.
        base_price (Decimal, optional): Custom base price per night. Defaults to None.

    Returns:
        dict: A dictionary with detailed price breakdown:
            - number_of_nights (int)
            - total_base_price (Decimal)
            - total_extra_guest_fee (Decimal)
            - discount_totals (dict)
            - tax_amount (Decimal)
            - payment_fee (Decimal)
            - total_price (Decimal)

    Raises:
        Exception: If any error occurs during price calculation.
    """
    try:
        key = f"logement_{logement.id}_price_{start}_{end}_{guest_adult}_{guest_minor}_{base_price}"
        cached_result = cache.get(key)
        if cached_result:
            return cached_result

        nights = (end - start).days
        total_guests = guest_adult + guest_minor

        # Handle zero or negative nights or guests
        if nights <= 0 or total_guests <= 0:
            result = {
                "number_of_nights": nights if nights > 0 else 0,
                "total_base_price": Decimal("0.00"),
                "total_extra_guest_fee": Decimal("0.00"),
                "discount_totals": {},
                "tax_amount": Decimal("0.00"),
                "payment_fee": Decimal("0.00"),
                "total_price": Decimal("0.00"),
            }
            cache.set(key, result, 300)
            return result

        default_price = Decimal(str(logement.price))
        base_price = Decimal(str(base_price)) if base_price else None

        custom_prices = Price.objects.filter(logement_id=logement.id, date__range=(start, end))
        price_map = {p.date: Decimal(str(p.value)) for p in custom_prices}

        discounts = Discount.objects.filter(logement=logement, is_active=True)
        best_discounts = get_best_discounts(discounts, start, end)

        total_base = Decimal("0.00")
        total_discount_amount = Decimal("0.00")
        discount_breakdown = {}

        for day in range(nights):
            current_day = start + timedelta(days=day)
            daily_price = base_price if base_price else price_map.get(current_day, default_price)
            total_base += daily_price

            final_price, discounts_today = apply_discounts(daily_price, current_day, best_discounts)
            for name, amount in discounts_today:
                discount_breakdown[name] = discount_breakdown.get(name, Decimal("0.00")) + amount
                total_discount_amount += amount

        total_price = total_base - total_discount_amount

        extra_guests = max(total_guests - logement.nominal_traveler, 0)
        extra_fee = Decimal(str(logement.fee_per_extra_traveler)) * extra_guests * nights
        total_price += extra_fee

        per_night = total_price / nights
        tax_cap = Decimal(str(logement.tax_max))
        guest_decimal = Decimal(str(guest_adult))
        tax_rate = min((Decimal(str(logement.tax)) / 100) * (per_night / guest_decimal), tax_cap)
        tax_amount = tax_rate * guest_decimal * nights

        total_price += Decimal(str(logement.cleaning_fee)) + tax_amount
        payment_fee = get_payment_fee(total_price)
        total_price += Decimal(str(payment_fee))

        result = {
            "number_of_nights": nights,
            "total_base_price": total_base,
            "total_extra_guest_fee": extra_fee,  # snake_case for consistency
            "discount_totals": discount_breakdown,
            "tax_amount": tax_amount,
            "payment_fee": payment_fee,
            "total_price": total_price,
        }
        cache.set(key, result, 300)  # 5 min
        return result
    except Exception as e:
        logger.exception(f"Error calculating price: {e}")
        raise
