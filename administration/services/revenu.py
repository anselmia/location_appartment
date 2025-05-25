from calendar import month_name
from django.db.models import Sum, F
from logement.models import Reservation


def get_economie_stats(logement_id, year, month="all"):
    qs = Reservation.objects.filter(
        logement_id=logement_id, start__year=year, statut="confirmee"
    )

    if month != "all":
        qs = qs.filter(start__month=int(month))

    total_revenue = qs.aggregate(total=Sum("price"))["total"] or 0
    total_taxes = qs.aggregate(taxes=Sum("tax"))["taxes"] or 0
    net_profit = total_revenue - total_taxes

    monthly_data = (
        qs.annotate(month=F("start__month"))
        .values("month")
        .annotate(monthly_total=Sum("price"))
        .order_by("month")
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
