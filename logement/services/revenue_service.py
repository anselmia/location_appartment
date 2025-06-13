import calendar as cal
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal
from django.db.models import Sum, F
from logement.services.logement_service import get_logements
from reservation.services.reservation_service import get_valid_reservations_for_admin, get_night_booked_in_period
from django.db.models.functions import ExtractYear, ExtractMonth, TruncMonth
from reservation.models import Reservation
from calendar import month_name
from typing import Any, Dict


def get_revenue_context(user, request) -> Dict[str, Any]:
    logements = get_logements(user)
    year = request.GET.get("year")
    month = request.GET.get("month")
    logement_id = request.GET.get("logement_id")
    if logement_id == "" or logement_id is None:
        logement_id = None
    else:
        logement_id = int(logement_id)
    reservations = get_valid_reservations_for_admin(user)
    all_years = reservations.annotate(year=ExtractYear("start")).values("year").distinct().order_by("year")
    all_years = [y["year"] for y in all_years]
    selected_year = int(year) if year and year.isdigit() else max(all_years, default=datetime.now().year)
    all_months = (
        reservations.filter(start__year=selected_year)
        .annotate(month=ExtractMonth("start"))
        .values("month")
        .distinct()
        .order_by("month")
    )
    all_months = [m["month"] for m in all_months]
    selected_month = int(month) if month and month.isdigit() else max(all_months, default=datetime.now().month)
    reservations = get_valid_reservations_for_admin(user, logement_id, selected_year, selected_month)
    brut_revenue = reservations.aggregate(Sum("price"))["price__sum"] or Decimal("0.00")
    total_refunds = reservations.aggregate(Sum("refund_amount"))["refund_amount__sum"] or Decimal("0.00")
    platform_earnings = reservations.aggregate(Sum("platform_fee"))["platform_fee__sum"] or Decimal("0.00")
    total_payment_fee = reservations.aggregate(Sum("payment_fee"))["payment_fee__sum"] or Decimal("0.00")
    tax = reservations.aggregate(Sum("tax"))["tax__sum"] or Decimal("0.00")
    total_revenu = brut_revenue - total_refunds - platform_earnings - total_payment_fee
    total_reservations = reservations.count()
    average_price = brut_revenue / total_reservations if total_reservations else Decimal("0.00")
    nights_in_month = cal.monthrange(selected_year, selected_month)[1]
    month_start = date(selected_year, selected_month, 1)
    last_day = cal.monthrange(selected_year, selected_month)[1]
    month_end = date(selected_year, selected_month, last_day)
    reserved_nights = get_night_booked_in_period(logements, logement_id, month_start, month_end)
    occupancy_rate = (
        round((reserved_nights / (nights_in_month * (logements.count() if not logement_id else 1))) * 100, 1)
        if nights_in_month
        else 0
    )
    context = {
        "logement_id": logement_id,
        "logements": logements,
        "selected_year": selected_year,
        "available_years": all_years,
        "selected_month": selected_month,
        "available_months": all_months,
        "total_revenue": total_revenu,
        "platform_earnings": platform_earnings or Decimal("0.00"),
        "tax": tax,
        "total_payment_fee": total_payment_fee,
        "total_deposits": reservations.aggregate(Sum("amount_charged"))["amount_charged__sum"] or Decimal("0.00"),
        "total_refunds": total_refunds,
        "total_reservations": total_reservations,
        "average_price": average_price,
        "reservations": reservations.order_by("-date_reservation")[:100],
        "occupancy_rate": occupancy_rate,
        "days_booked": reserved_nights,
    }
    # Monthly data
    reservations_year = get_valid_reservations_for_admin(user, logement_id, selected_year)
    monthly_data = (
        reservations_year.annotate(month=TruncMonth("start"))
        .values("month")
        .annotate(
            brut=Sum("price"),
            refunds=Sum("refund_amount"),
            fees=Sum("payment_fee"),
            platform=Sum("platform_fee"),
            tax=Sum("tax"),
        )
        .order_by("month")
    )
    monthly_manual_data = defaultdict(lambda: {"admin_transfer": 0, "owner_transfer": 0})
    for reservation in reservations_year:
        month = reservation.start.replace(day=1)
        monthly_manual_data[month]["admin_transfer"] += reservation.admin_transferable_amount or 0
        monthly_manual_data[month]["owner_transfer"] += reservation.transferable_amount - reservation.tax or 0
    final_monthly_data = []
    for row in monthly_data:
        month = row["month"]
        manual_data = monthly_manual_data.get(month, {"admin_transfer": 0, "owner_transfer": 0})
        row["admin_transfer"] = manual_data["admin_transfer"]
        row["owner_transfer"] = manual_data["owner_transfer"]
        final_monthly_data.append(row)
    monthly_chart = defaultdict(
        lambda: {
            "revenue_brut": Decimal("0.00"),
            "revenue_net": Decimal("0.00"),
            "admin_revenue": Decimal("0.00"),
            "refunds": Decimal("0.00"),
            "payment_fee": Decimal("0.00"),
            "platform_fee": Decimal("0.00"),
            "tax": Decimal("0.00"),
        }
    )
    for item in monthly_data:
        month_key = item["month"].month
        monthly_chart[month_key]["revenue_brut"] = item["brut"] or Decimal("0.00")
        monthly_chart[month_key]["revenue_net"] = item["owner_transfer"] or Decimal("0.00")
        monthly_chart[month_key]["admin_revenue"] = item["admin_transfer"] or Decimal("0.00")
        monthly_chart[month_key]["refunds"] = item["refunds"] or Decimal("0.00")
        monthly_chart[month_key]["payment_fee"] = item["fees"] or Decimal("0.00")
        monthly_chart[month_key]["platform_fee"] = item["platform"] or Decimal("0.00")
        monthly_chart[month_key]["tax"] = item["tax"] or Decimal("0.00")
    chart_labels = [cal.month_abbr[m] for m in range(1, 13)]
    revenue_brut_data = [float(monthly_chart[m]["revenue_brut"]) for m in range(1, 13)]
    revenue_net_data = [float(monthly_chart[m]["revenue_net"]) for m in range(1, 13)]
    admin_revenue_data = [float(monthly_chart[m]["admin_revenue"]) for m in range(1, 13)]
    refunds_data = [float(monthly_chart[m]["refunds"]) for m in range(1, 13)]
    payment_fee_data = [float(monthly_chart[m]["payment_fee"]) for m in range(1, 13)]
    platform_fee_data = [float(monthly_chart[m]["platform_fee"]) for m in range(1, 13)]
    tax_data = [float(monthly_chart[m]["tax"]) for m in range(1, 13)]
    context.update(
        {
            "chart_labels": chart_labels,
            "revenue_brut_data": revenue_brut_data,
            "revenue_net_data": revenue_net_data,
            "admin_revenue_data": admin_revenue_data,
            "refunds_data": refunds_data,
            "payment_fee_data": payment_fee_data,
            "platform_fee_data": platform_fee_data,
            "tax_data": tax_data,
        }
    )
    return context


def get_economie_stats(logement_id, year, month="all"):
    qs = Reservation.objects.filter(logement_id=logement_id, start__year=year, statut="confirmee")
    if month != "all":
        qs = qs.filter(start__month=int(month))
    total_revenue = qs.aggregate(total=Sum("price"))["total"] or 0
    total_taxes = qs.aggregate(taxes=Sum("tax"))["taxes"] or 0
    net_profit = total_revenue - total_taxes
    monthly_data = (
        qs.annotate(month=F("start__month")).values("month").annotate(monthly_total=Sum("price")).order_by("month")
    )
    chart = {m: 0.0 for m in range(1, 13)}
    for entry in monthly_data:
        chart[entry["month"]] = float(entry["monthly_total"])
    return {
        "total_revenue": total_revenue,
        "total_taxes": total_taxes,
        "net_profit": net_profit,
        "chart_labels": [month_name[m][:3] for m in range(1, 13)],
        "chart_values": [chart[m] for m in range(1, 13)],
    }
