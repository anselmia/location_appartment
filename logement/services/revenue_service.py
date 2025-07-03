import calendar as cal
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal
from collections import OrderedDict
from django.db.models import F, Sum
from logement.services.logement_service import get_logements
from reservation.services.logement import get_night_booked_in_period
from django.db.models.functions import ExtractYear, ExtractMonth, TruncMonth
from reservation.models import Reservation
from calendar import month_name
from typing import Any, Dict


def get_revenue_context(user, request) -> Dict[str, Any]:
    from reservation.services.reservation_service import get_valid_reservations
    from reservation.services.logement import get_logement_reservations_queryset

    logements = get_logements(user)
    year = request.GET.get("year")
    month = request.GET.get("month")
    logement_id = request.GET.get("logement_id")
    logement_id = int(logement_id) if logement_id and str(logement_id).isdigit() else None

    reservations = get_valid_reservations(
        user,
        logement_id,
        obj_type="logement",
        get_queryset_fn=get_logement_reservations_queryset,
        cache_prefix="valid_logement_resa_admin",
        select_related_fields=["user", "logement"],
        prefetch_related_fields=["logement__photos"],
        year=year,
        month=month,
    )

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
        tax=Sum("tax"),
        admin_transfer=Sum("admin_transferred_amount"),
        owner_transfer=Sum("transferred_amount"),
    )
    # Add computed property manually
    aggregates["net_revenue"] = sum(res.transferable_amount for res in filtered_reservations)

    # Yearly Calculation
    brut_revenue = aggregates["brut_revenue"] or Decimal("0.00")
    total_refunds = aggregates["total_refunds"] or Decimal("0.00")
    platform_earnings = aggregates["platform_earnings"] or Decimal("0.00")
    total_payment_fee = aggregates["total_payment_fee"] or Decimal("0.00")
    tax = aggregates["tax"] or Decimal("0.00")
    admin_transfer = aggregates["admin_transfer"] or Decimal("0.00")
    owner_transfer = aggregates["owner_transfer"] or Decimal("0.00")
    total_revenu = aggregates["net_revenue"] or Decimal("0.00")
    total_reservations = filtered_reservations.count()
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
            admin_transfers=Sum("admin_transferred_amount"),
            tax=Sum("tax"),
        )
        .order_by("month")
    )

    # Get reservations grouped by month
    reservations_by_month = defaultdict(list)
    for r in reservations_year:
        month = r.start.replace(day=1)
        reservations_by_month[month].append(r)

    # Add admin_revenu sum per month (Python-side)
    for entry in monthly_data:
        month = entry["month"].replace(day=1)
        reservations = reservations_by_month.get(month, [])
        entry["revenue_net"] = sum((r.owner_revenu for r in reservations), Decimal("0.00"))
        entry["revenue_net_admin"] = sum((r.admin_revenu for r in reservations), Decimal("0.00"))

    monthly_chart = defaultdict(
        lambda: {
            "revenue_brut": Decimal("0.00"),
            "revenue_net": Decimal("0.00"),
            "revenue_net_admin": Decimal("0.00"),
            "transfers": Decimal("0.00"),
            "admin_transfers": Decimal("0.00"),
            "refunds": Decimal("0.00"),
            "payment_fee": Decimal("0.00"),
            "platform_fee": Decimal("0.00"),
            "tax": Decimal("0.00"),
        }
    )

    for row in monthly_data:
        date_selected = row["month"]
        month_key = date_selected.month
        monthly_chart[month_key]["revenue_brut"] = row["brut"] or Decimal("0.00")
        monthly_chart[month_key]["revenue_net"] = row["revenue_net"] or Decimal("0.00")
        monthly_chart[month_key]["revenue_net_admin"] = row["revenue_net_admin"] or Decimal("0.00")
        monthly_chart[month_key]["transfers"] = row["transfers"] or Decimal("0.00")
        monthly_chart[month_key]["refunds"] = row["refunds"] or Decimal("0.00")
        monthly_chart[month_key]["payment_fee"] = row["fees"] or Decimal("0.00")
        monthly_chart[month_key]["platform_fee"] = row["platform"] or Decimal("0.00")
        monthly_chart[month_key]["admin_transfers"] = row["admin_transfers"] or Decimal("0.00")
        monthly_chart[month_key]["tax"] = row["tax"] or Decimal("0.00")

    chart_labels = [cal.month_abbr[m] for m in range(1, 13)]
    revenue_brut_data = [float(monthly_chart[m]["revenue_brut"]) for m in range(1, 13)]
    revenue_net_data = [float(monthly_chart[m]["revenue_net"]) for m in range(1, 13)]
    revenue_net_admin_data = [float(monthly_chart[m]["revenue_net_admin"]) for m in range(1, 13)]
    owner_transfer_data = [float(monthly_chart[m]["transfers"]) for m in range(1, 13)]
    admin_transfer_data = [float(monthly_chart[m]["admin_transfers"]) for m in range(1, 13)]
    refunds_data = [float(monthly_chart[m]["refunds"]) for m in range(1, 13)]
    payment_fee_data = [float(monthly_chart[m]["payment_fee"]) for m in range(1, 13)]
    platform_fee_data = [float(monthly_chart[m]["platform_fee"]) for m in range(1, 13)]
    tax_data = [float(monthly_chart[m]["tax"]) for m in range(1, 13)]

    context = {
        "logement_id": logement_id,
        "logements": logements,
        "occupancy_rate": occupancy_rate,
        "reserved_nights": reserved_nights,
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
        "revenue_net_admin_data": revenue_net_admin_data,
        "owner_transfer_data": owner_transfer_data,
        "admin_transfer_data": admin_transfer_data,
        "refunds_data": refunds_data,
        "payment_fee_data": payment_fee_data,
        "platform_fee_data": platform_fee_data,
        "tax_data": tax_data,
        "has_conciergerie": any(getattr(r.logement, "admin", None) is not None for r in filtered_reservations),
    }

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
