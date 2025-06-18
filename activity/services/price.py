import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from activity.models import Activity, Price, CloseDate
from payment.services.payment_service import get_payment_fee

logger = logging.getLogger(__name__)


def set_price(
    activity: Any,
    start: date,
    guest: int,
    base_price: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Calculate the total price for a booking, including discounts, extra guest fees, taxes, and payment fees.

    Args:
        activity (Activity): The activity instance for which to calculate the price.
        start (date): The start date of the booking.
        end (date): The end date of the booking.
        guest (int): Number of guests.
        base_price (Decimal, optional): Custom base price per night. Defaults to None.

    Returns:
        dict: A dictionary with detailed price breakdown:
            - total_base_price (Decimal)
            - total_extra_guest_fee (Decimal)
            - discount_totals (dict)
            - payment_fee (Decimal)
            - total_price (Decimal)

    Raises:
        Exception: If any error occurs during price calculation.
    """
    try:
        key = f"activity_{activity.id}_price_{start}_{guest}_{base_price}"
        cached_result = cache.get(key)
        if cached_result is not None:
            return cached_result

        # Handle zero or negative nights or guests
        if guest <= 0:
            result = {
                "total_base_price": Decimal("0.00"),
                "total_extra_guest_fee": Decimal("0.00"),
                "payment_fee": Decimal("0.00"),
                "total_price": Decimal("0.00"),
            }
            cache.set(key, result, 300)
            return result

        default_price = Decimal(str(activity.price))
        base_price = Decimal(str(base_price)) if base_price else None

        custom_price = Price.objects.filter(activity_id=activity.id, date__exact=start).first()
        total_base = base_price if base_price else (custom_price.value if custom_price else default_price)
        total_price = total_base
        extra_guests = max(guest - activity.nominal_guests, 0)
        extra_fee = Decimal(str(activity.fee_per_extra_guest)) * extra_guests
        total_price += extra_fee

        payment_fee = get_payment_fee(total_price)
        total_price += Decimal(str(payment_fee))

        result = {
            "total_base_price": total_base,
            "total_extra_guest_fee": extra_fee,  # snake_case for consistency
            "payment_fee": payment_fee,
            "total_price": total_price,
        }
        cache.set(key, result, 300)  # 5 min
        return result
    except Exception as e:
        logger.exception(f"Error calculating price: {e}")
        raise


def get_price_context(activity_id: int, start: str, end: str, base_price: float, guest: int) -> Dict[str, Any]:
    """
    Calculate the price details for an activity booking.
    """
    activity = get_object_or_404(Activity, id=activity_id)
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    price_data = set_price(activity, start_date, guest, base_price)
    details = {"Total Activité": f"{round(price_data['total_base_price'], 2)} €"}
    if price_data["total_extra_guest_fee"] != 0:
        details["Participants(s) supplémentaire(s)"] = f"+ {round(price_data['total_extra_guest_fee'], 2)} €"

    details["Frais de transaction"] = f"+ {round(price_data['payment_fee'], 2)} €"
    return {
        "final_price": round(price_data["total_price"], 2),
        "details": details,
    }


def get_daily_price_data(activity_id: int, start_str: str, end_str: str) -> Dict[str, Any]:
    from activity.services.reservation import get_valid_reservations_in_period

    start = datetime.fromisoformat(start_str).date()
    end = datetime.fromisoformat(end_str).date()
    activity = get_object_or_404(Activity, id=activity_id)
    default_price = activity.price

    start = datetime.fromisoformat(start_str).date()

    custom_prices = Price.objects.filter(activity_id=activity_id, date__range=(start, end))
    price_map = {p.date: p.value for p in custom_prices}

    closed_date = CloseDate.objects.filter(activity_id=activity_id, date__range=(start, end))
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
            "name": b.user.name,
            "guests": b.participants,
            "total_price": str(b.price),
        }
        for b in get_valid_reservations_in_period(activity_id, start, end)
    ]

    closed_days = [{"date": c.date.isoformat()} for c in closed_date]
    return {
        "data": daily_data,
        "data_bookings": data_bookings,
        "closed_days": closed_days,
    }


def bulk_update_prices(activity_id: int, start: str, end: str, price: float, statut: int) -> Dict[str, Any]:
    """
    Bulk update prices and close/open dates for a logement.
    """
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if not price or price <= 0:
        return {"error": "Le prix doit être supérieur à 0.", "status": 400}
    if not all([activity_id, start_date, end_date]):
        return {"error": "Missing required parameters.", "status": 400}
    for i in range((end_date - start_date).days + 1):
        day = start_date + timedelta(days=i)
        Price.objects.update_or_create(activity_id=activity_id, date=day, defaults={"value": price})
        if statut == 0:
            CloseDate.objects.get_or_create(activity_id=activity_id, date=day)
        else:
            CloseDate.objects.filter(activity_id=activity_id, date=day).delete()
    return {"status": "updated"}
