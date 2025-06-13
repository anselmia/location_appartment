import json
import logging
import os
import stripe

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin

from django.db.models import Sum, Q
from django.db.models.functions import ExtractYear, ExtractMonth, TruncDate
from django.http import JsonResponse
from django.shortcuts import render, redirect


from django.views.generic import TemplateView


from common.mixins import AdminRequiredMixin
from common.views import is_admin
from common.services.helper_fct import date_to_timestamp, get_entreprise

from payment.services.payment_service import retrieve_balance

from reservation.models import Reservation

from administration.services.logs import parse_log_file

from administration.services.traffic import get_traffic_dashboard_data
from administration.forms import (
    CommitmentForm,
    EntrepriseForm,
    HomePageConfigForm,
    ServiceForm,
    TestimonialForm,
    SiteConfigForm,
)
from administration.models import HomePageConfig, SiteConfig


stripe.api_key = settings.STRIPE_PRIVATE_KEY

logger = logging.getLogger(__name__)


@login_required
@user_passes_test(is_admin)
def traffic_dashboard(request):
    try:
        period = request.POST.get("period") if request.method == "POST" else request.GET.get("period", "day")

        stats = get_traffic_dashboard_data(period=period)

        if request.method == "POST":
            return JsonResponse(stats)

        return render(
            request,
            "administration/traffic.html",
            {
                "online_visitors": stats["online_visitors"],
                "online_users": stats["online_users"],
                "labels": json.dumps(stats["labels"]),
                "data": json.dumps(stats["data"]),
                "total_visits": stats["total_visits"],
                "unique_visitors": stats["unique_visitors"],
                "recent_logs": stats["recent_logs"],
                "selected_period": period,
            },
        )
    except Exception as e:
        logger.exception(f"Error loading traffic dashboard: {e}")
        return JsonResponse({"error": "Erreur lors du chargement des données"}, status=500)


@login_required
@user_passes_test(is_admin)
def log_viewer(request):
    import itertools

    log_file_path = os.path.join(settings.LOG_DIR, "django.log")
    selected_level = request.GET.get("level")
    selected_logger = request.GET.get("logger")
    query = request.GET.get("query", "").strip().lower()

    # Pagination params
    try:
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 500))
    except ValueError:
        page = 1
        page_size = 500

    def tail_lines(file_path, n):
        """Read last n lines of a file efficiently."""
        with open(file_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            lines = []
            size = 1024
            block = -1
            data = b""
            while len(lines) <= n and abs(block * size) < end:
                f.seek(block * size, os.SEEK_END)
                data = f.read(size) + data
                lines = data.splitlines()
                block -= 1
            return [l.decode(errors="replace") for l in lines[-n:]]

    try:
        # Read enough lines for pagination
        total_lines_to_read = page * page_size
        raw_lines = tail_lines(log_file_path, total_lines_to_read)
        # Reverse to get newest first
        raw_lines = raw_lines[::-1]
        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        page_lines = raw_lines[start:end]
        # Use parse_log_file on just these lines
        logs, all_loggers = parse_log_file(
            lines=page_lines,  # You need to update parse_log_file to accept 'lines' param
            level=selected_level,
            logger_filter=selected_logger,
            query=query,
        )
        has_next = end < len(raw_lines)
        has_prev = page > 1
    except Exception as e:
        logger.exception(f"Erreur lors de la lecture du fichier de log: {e}")
        logs = []
        all_loggers = []
        has_next = False
        has_prev = False

    return render(
        request,
        "administration/log_viewer.html",
        {
            "logs": logs,
            "loggers": sorted(all_loggers),
            "levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "selected_level": selected_level,
            "query": query,
            "page": page,
            "page_size": page_size,
            "has_next": has_next,
            "has_prev": has_prev,
        },
    )


@login_required
@user_passes_test(is_admin)
def homepage_admin_view(request):
    try:
        config, _ = HomePageConfig.objects.get_or_create(id=1)
        service_form = ServiceForm()
        testimonial_form = TestimonialForm()
        commitment_form = CommitmentForm()
        main_form = HomePageConfigForm(instance=config)

        site_config = SiteConfig.objects.first() or SiteConfig.objects.create()
        site_config_form = SiteConfigForm(instance=site_config)

        if request.method == "POST":
            if "delete_service_id" in request.POST:
                config.services.filter(id=request.POST["delete_service_id"]).delete()
            elif "delete_testimonial_id" in request.POST:
                config.testimonials.filter(id=request.POST["delete_testimonial_id"]).delete()
            elif "delete_commitment_id" in request.POST:
                config.commitments.filter(id=request.POST["delete_commitment_id"]).delete()
            elif "add_service" in request.POST:
                service_form = ServiceForm(request.POST, request.FILES)
                if service_form.is_valid():
                    instance = service_form.save(commit=False)
                    instance.config = config
                    instance.save()
            elif "add_testimonial" in request.POST:
                testimonial_form = TestimonialForm(request.POST)
                if testimonial_form.is_valid():
                    instance = testimonial_form.save(commit=False)
                    instance.config = config
                    instance.save()
            elif "add_commitment" in request.POST:
                commitment_form = CommitmentForm(request.POST, request.FILES)
                if commitment_form.is_valid():
                    instance = commitment_form.save(commit=False)
                    instance.config = config
                    instance.save()
            elif "update_site_config" in request.POST:
                site_config_form = SiteConfigForm(request.POST, instance=site_config)
                if site_config_form.is_valid():
                    site_config_form.save()
                    messages.success(request, "La configuration du site a bien été mise à jour.")
            else:
                main_form = HomePageConfigForm(request.POST, request.FILES, instance=config)
                if main_form.is_valid():
                    main_form.save()

            return redirect("administration:homepage_admin_view")

        context = {
            "form": main_form,
            "config": config,
            "services": config.services.all(),
            "testimonials": config.testimonials.all(),
            "commitments": config.commitments.all(),
            "service_form": service_form,
            "testimonial_form": testimonial_form,
            "commitment_form": commitment_form,
            "site_config_form": site_config_form,
        }
        return render(request, "administration/base_site.html", context)
    except Exception as e:
        logger.exception(f"Erreur dans homepage_admin_view: {e}")
        raise


@login_required
@user_passes_test(is_admin)
def edit_entreprise(request):
    try:
        entreprise = get_entreprise()
        if request.method == "POST":
            form = EntrepriseForm(request.POST, request.FILES, instance=entreprise)
            if form.is_valid():
                form.save()
                messages.success(request, "Les informations ont été mises à jour.")
                return redirect("administration:edit_entreprise")
        else:
            form = EntrepriseForm(instance=entreprise)

        return render(request, "administration/edit_entreprise.html", {"form": form})
    except Exception as e:
        logger.exception(f"Erreur dans edit_entreprise: {e}")
        raise


class FinancialDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "administration/financial_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        year = self.request.GET.get("year")
        all_years = (
            Reservation.objects.filter(Q(statut="confirmee") | Q(statut="annulee"))
            .annotate(year=ExtractYear("start"))
            .values_list("year", flat=True)
            .distinct()
        )
        selected_year = int(year) if year and year.isdigit() else max(all_years, default=datetime.now().year)

        reservations = Reservation.objects.filter(start__year=selected_year).exclude(statut="en_attente")

        monthly_data = (
            reservations.filter(date_reservation__year=selected_year)
            .annotate(month=ExtractMonth("date_reservation"))
            .values("month")
            .annotate(total=Sum("platform_fee"))
            .order_by("month")
        )

        brut_revenue = reservations.aggregate(Sum("price"))["price__sum"] or Decimal("0.00")
        total_refunds = reservations.aggregate(Sum("refund_amount"))["refund_amount__sum"] or Decimal("0.00")
        total_revenu = brut_revenue - total_refunds

        total_reservations = reservations.count()
        average_price = brut_revenue / total_reservations if total_reservations else Decimal("0.00")

        # Fill all 12 months, even if 0
        monthly_revenue = [0] * 12
        for entry in monthly_data:
            month_index = entry["month"] - 1
            monthly_revenue[month_index] = float(entry["total"])

        context.update(
            {
                "selected_year": selected_year,
                "monthly_revenue": monthly_revenue,
                "available_years": sorted(all_years),
                "total_revenue": total_revenu,
                "platform_earnings": reservations.aggregate(Sum("platform_fee"))["platform_fee__sum"]
                or Decimal("0.00"),
                "total_payment_fee": reservations.aggregate(Sum("payment_fee"))["payment_fee__sum"] or Decimal("0.00"),
                "total_deposits": reservations.aggregate(Sum("amount_charged"))["amount_charged__sum"]
                or Decimal("0.00"),
                "total_refunds": total_refunds,
                "total_reservations": total_reservations,
                "average_price": average_price,
                "reservations": reservations.order_by("-date_reservation")[:100],
            }
        )

        daily_data = (
            reservations.annotate(day=TruncDate("date_reservation"))
            .values("day")
            .annotate(total=Sum("price"))
            .order_by("day")
        )

        # Convert to dict for frontend { "2025-06-01": 240.0, ... }
        daily_revenue = {date_to_timestamp(entry["day"].isoformat()): float(entry["total"]) for entry in daily_data}

        context["daily_revenue"] = daily_revenue

        try:
            balance = retrieve_balance()
            context["stripe_balance_available"] = balance["available"][0]["amount"] / 100
            context["stripe_balance_pending"] = balance["pending"][0]["amount"] / 100
        except Exception:
            context["stripe_balance_available"] = None
            context["stripe_balance_pending"] = None

        return context
