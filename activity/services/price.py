import logging
import calendar as cal
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.db.models.functions import ExtractYear, ExtractMonth, TruncMonth
from django.core.cache import cache

from activity.services.activity import get_activity
from activity.models import Activity, Price, CloseDate
from reservation.models import ActivityReservation
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
    from reservation.services.reservation_service import get_valid_reservations_in_period

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
        for b in get_valid_reservations_in_period(ActivityReservation, "activity_id", activity_id, start, end)
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


def get_revenue_context(user, request) -> Dict[str, Any]:
    from reservation.services.reservation_service import get_valid_reservations
    from reservation.services.activity import get_activity_reservations_queryset

    activities = get_activity(user)
    year = request.GET.get("year")
    month = request.GET.get("month")
    activity_id = request.GET.get("activity_id")
    activity_id = int(activity_id) if activity_id and str(activity_id).isdigit() else None

    # Get all reservations for the user (optionally filtered by activity)
    reservations = get_valid_reservations(
        user,
        activity_id,
        obj_type="activity",
        get_queryset_fn=get_activity_reservations_queryset,
        cache_prefix="valid_activity_resa_admin",
        select_related_fields=["user", "activity"],
        prefetch_related_fields=["activity__photos"],
        year=year,
        month=month,
    )

    reservations = reservations.exclude(statut="en_attente")

    # Years available
    all_years = list(
        reservations.annotate(year=ExtractYear("start")).values_list("year", flat=True).distinct().order_by("year")
    )
    selected_year = (
        int(year)
        if year and str(year).isdigit() and int(year) in all_years
        else (max(all_years) if all_years else datetime.now().year)
    )

    # Months available for the selected year
    months_qs = (
        reservations.filter(start__year=selected_year)
        .annotate(month=ExtractMonth("start"))
        .values_list("month", flat=True)
        .distinct()
        .order_by("month")
    )
    all_months = list(months_qs)
    if all_months and month and str(month).isdigit() and int(month) in all_months:
        selected_month = int(month)
    elif all_months:
        selected_month = max(all_months)
    else:
        selected_month = datetime.now().month

    # Reservations for selected year and month
    filtered_reservations = reservations.filter(start__year=selected_year, start__month=selected_month)

    # Aggregates
    aggregates = filtered_reservations.aggregate(
        brut_revenue=Sum("price"),
        total_refunds=Sum("refund_amount"),
        platform_earnings=Sum("platform_fee"),
        total_payment_fee=Sum("payment_fee"),
        owner_transfer=Sum("transferred_amount"),
    )
    # Add computed property manually
    aggregates["net_revenue"] = sum(res.transferable_amount for res in filtered_reservations)

    brut_revenue = aggregates["brut_revenue"] or Decimal("0.00")
    total_refunds = aggregates["total_refunds"] or Decimal("0.00")
    platform_earnings = aggregates["platform_earnings"] or Decimal("0.00")
    total_payment_fee = aggregates["total_payment_fee"] or Decimal("0.00")
    owner_transfer = aggregates["owner_transfer"] or Decimal("0.00")
    total_revenu = aggregates["net_revenue"] or Decimal("0.00")
    total_reservations = filtered_reservations.count()
    average_price = brut_revenue / total_reservations if total_reservations else Decimal("0.00")

    # Monthly data for charts
    reservations_year = reservations.filter(start__year=selected_year)
    monthly_data = (
        reservations_year.annotate(month=TruncMonth("start"))
        .values("month")
        .annotate(
            brut=Sum("price"),
            refunds=Sum("refund_amount"),
            fees=Sum("payment_fee"),
            platform=Sum("platform_fee"),
            transfers=Sum("transferred_amount"),
        )
        .order_by("month")
    )

    monthly_chart = defaultdict(
        lambda: {
            "revenue_brut": Decimal("0.00"),
            "revenue_net": Decimal("0.00"),
            "transfers": Decimal("0.00"),
            "refunds": Decimal("0.00"),
            "payment_fee": Decimal("0.00"),
            "platform_fee": Decimal("0.00"),
        }
    )

    for row in monthly_data:
        date = row["month"]
        month_key = date.month
        monthly_chart[month_key]["revenue_brut"] = row["brut"] or Decimal("0.00")
        monthly_chart[month_key]["revenue_net"] = (
            row["brut"] - row["refunds"] - row["fees"] - row["platform"]
        ) or Decimal("0.00")
        monthly_chart[month_key]["transfers"] = row["transfers"] or Decimal("0.00")
        monthly_chart[month_key]["refunds"] = row["refunds"] or Decimal("0.00")
        monthly_chart[month_key]["payment_fee"] = row["fees"] or Decimal("0.00")
        monthly_chart[month_key]["platform_fee"] = row["platform"] or Decimal("0.00")

    chart_labels = [cal.month_abbr[m] for m in range(1, 13)]
    revenue_brut_data = [float(monthly_chart[m]["revenue_brut"]) for m in range(1, 13)]
    revenue_net_data = [float(monthly_chart[m]["revenue_net"]) for m in range(1, 13)]
    transfer_data = [float(monthly_chart[m]["transfers"]) for m in range(1, 13)]
    refunds_data = [float(monthly_chart[m]["refunds"]) for m in range(1, 13)]
    payment_fee_data = [float(monthly_chart[m]["payment_fee"]) for m in range(1, 13)]
    platform_fee_data = [float(monthly_chart[m]["platform_fee"]) for m in range(1, 13)]

    context = {
        "activity_id": activity_id,
        "activities": activities,
        "selected_year": selected_year,
        "available_years": all_years,
        "selected_month": selected_month,
        "available_months": all_months,
        "total_revenue": total_revenu,
        "platform_earnings": platform_earnings,
        "total_payment_fee": total_payment_fee,
        "total_refunds": total_refunds,
        "total_reservations": total_reservations,
        "average_price": average_price,
        "reservations": filtered_reservations.order_by("-date_reservation")[:100],
        "chart_labels": chart_labels,
        "revenue_brut_data": revenue_brut_data,
        "revenue_net_data": revenue_net_data,
        "transfer_data": transfer_data,
        "refunds_data": refunds_data,
        "payment_fee_data": payment_fee_data,
        "platform_fee_data": platform_fee_data,
    }
    return context
