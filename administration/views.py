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

from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.db.models.functions import ExtractYear, ExtractMonth, TruncDate
from django.http import JsonResponse
from django.shortcuts import render, redirect


from django.views.generic import TemplateView

from common.services import email_service
from common.mixins import AdminRequiredMixin
from common.views import is_admin
from common.services.helper_fct import date_to_timestamp, get_entreprise
from common.models import TaskHistory

from payment.services.payment_service import retrieve_balance

from reservation.models import Reservation
from conciergerie.models import Conciergerie
from logement.models import PlatformFeeWaiver, Logement
from activity.models import Partners, ActivityReservation
from accounts.models import Message
from administration.services.logs import parse_log_file, count_lines

from administration.services.traffic import get_traffic_dashboard_data
from administration.forms import (
    CommitmentForm,
    EntrepriseForm,
    HomePageConfigForm,
    ServiceForm,
    TestimonialForm,
    SiteConfigForm,
    PlatformFeeWaiverForm,
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
    log_file_path = os.path.join(settings.LOG_DIR, "django.log")
    selected_level = request.GET.get("level") if request.GET.get("level") != "None" else None
    selected_logger = request.GET.get("logger") if request.GET.get("logger") != "None" else None
    query = (
        request.GET.get("query", "").strip().lower()
        if request.GET.get("query") and request.GET.get("query").strip().lower() != ""
        else None
    )

    try:
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 500))
    except ValueError:
        page = 1
        page_size = 500

    def read_all_lines(file_path):
        """Read all lines of a file."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()

    try:
        total_lines = count_lines(log_file_path)
        if total_lines == 0:
            messages.error(request, "Le fichier de log est vide.")
            return render(
                request,
                "administration/log_viewer.html",
                {
                    "logs": [],
                    "loggers": [],
                    "levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    "selected_level": selected_level,
                    "query": query,
                    "page": page,
                    "page_size": page_size,
                    "has_next": False,
                    "has_prev": False,
                    "paginator": None,
                },
            )

        # Read all lines from the log file
        raw_lines = read_all_lines(log_file_path)
        raw_lines = raw_lines[::-1]  # Newest first
        # Parse all lines into log entries (multi-line aware)
        logs, all_loggers = parse_log_file(
            lines=raw_lines, level=selected_level, logger_filter=selected_logger, query=query
        )
        # Use Django's Paginator
        paginator = Paginator(logs, page_size)
        page_obj = paginator.get_page(page)
    except Exception as e:
        logger.exception(f"Erreur lors de la lecture du fichier de log: {e}")
        page_obj = None
        all_loggers = []
        paginator = None

    return render(
        request,
        "administration/log_viewer.html",
        {
            "logs": page_obj.object_list if page_obj else [],
            "loggers": sorted(all_loggers),
            "levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "selected_level": selected_level,
            "query": query,
            "page": page,
            "page_size": page_size,
            "has_next": page_obj.has_next() if page_obj else False,
            "has_prev": page_obj.has_previous() if page_obj else False,
            "paginator": paginator,
            "page_obj": page_obj,
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


@login_required
@user_passes_test(is_admin)
def waiver_platform_fee_view(request, waiver_id=None):
    # If waiver_id is provided, we're editing an existing waiver
    if waiver_id:
        waiver_instance = PlatformFeeWaiver.objects.filter(pk=waiver_id).first()
    else:
        waiver_instance = None

    # Filtering logic
    waivers = PlatformFeeWaiver.objects.select_related("owner").all().order_by("-id")
    status = request.GET.get("status")
    owner_name = request.GET.get("owner_name", "").strip()
    if status == "active":
        waivers = [w for w in waivers if (w.is_active() if callable(w.is_active) else w.is_active)]
    elif status == "expired":
        waivers = [w for w in waivers if not (w.is_active() if callable(w.is_active) else w.is_active)]
    if owner_name:
        waivers = [
            w
            for w in waivers
            if w.owner and owner_name.lower() in (w.owner.name.lower() + " " + w.owner.last_name.lower())
        ]

    if request.method == "POST":
        # Handle delete
        if "delete_waiver" in request.POST and waiver_instance:
            waiver_instance.delete()
            messages.success(request, "Exemption supprimée.")
            return redirect("administration:waiver_platform_fee")
        # Handle add/edit
        form = PlatformFeeWaiverForm(request.POST, instance=waiver_instance)
        if form.is_valid():
            form.save()
            if waiver_instance:
                messages.success(request, "Exemption modifiée.")
            else:
                messages.success(request, "Exemption ajoutée.")
            return redirect("administration:waiver_platform_fee")
    else:
        form = PlatformFeeWaiverForm(instance=waiver_instance)

    # Annotate each waiver with is_active and total_used for template
    for w in waivers:
        w.is_active = w.is_active() if callable(w.is_active) else w.is_active
        w.total_used = w.total_used or 0

    context = {
        "form": form,
        "waivers": waivers,
    }
    return render(request, "administration/waiver_platform_fee.html", context)


@login_required
@user_passes_test(is_admin)
def delete_waiver_platform_fee(request, waiver_id):
    waiver = PlatformFeeWaiver.objects.filter(pk=waiver_id).first()
    if request.method == "POST" and waiver:
        waiver.delete()
        messages.success(request, "Exemption supprimée.")
    return redirect("administration:waiver_platform_fee")


@login_required
@user_passes_test(is_admin)
def huey_tasks_status(request):
    # Get task history from the database
    history = TaskHistory.objects.order_by("-started_at")[:100]
    return render(request, "administration/huey_tasks_status.html", {"history": history})


EMAIL_FUNCTIONS = [
    ("send_mail_new_account_validation", "Validation de nouveau compte"),
    ("resend_confirmation_email", "Renvoyer l'email de confirmation"),
    ("send_mail_on_new_reservation", "Nouvelle réservation logement"),
    ("send_mail_on_new_activity_reservation", "Nouvelle réservation activité"),
    ("send_pre_checkin_reminders", "Rappel pré-checkin logement"),
    ("send_pre_checkin_activity_reminders", "Rappel pré-checkin activité"),
    ("send_mail_on_logement_refund", "Remboursement logement"),
    ("send_mail_on_activity_refund", "Remboursement activité"),
    ("send_mail_on_new_transfer", "Nouveau virement logement"),
    ("send_mail_on_new_activity_transfer", "Nouveau virement activité"),
    ("send_mail_payment_link", "Lien de paiement"),
    ("send_mail_activity_payment_link", "Lien de paiement activité"),
    ("send_mail_on_payment_failure", "Échec de paiement logement"),
    ("send_mail_on_activity_payment_failure", "Échec de paiement activité"),
    ("send_mail_contact", "Contact"),
    ("send_email_new_message", "Nouveau message"),
    ("send_mail_conciergerie_request_accepted", "Conciergerie acceptée"),
    ("send_mail_conciergerie_request_refused", "Conciergerie refusée"),
    ("send_mail_conciergerie_request_new", "Nouvelle demande conciergerie"),
    ("send_mail_conciergerie_stop_management", "Arrêt gestion conciergerie"),
    ("send_partner_validation_email", "Validation partenaire"),
    ("notify_vendor_new_reservation", "Nouvelle réservation activité (vendor)"),
]


@login_required
@user_passes_test(is_admin)
def test_email_view(request):
    if request.method == "POST":
        func_name = request.POST.get("email_function")
        reservation = Reservation.objects.order_by("-id").first()
        activity_reservation = ActivityReservation.objects.order_by("-id").first()
        activity_reservation.activity.owner.email = "anselmi.arnaud@yahoo.fr"
        activity_reservation.user.email = "anselmi.arnaud@yahoo.fr"
        reservation.logement.owner.email = "anselmi.arnaud@yahoo.fr"
        reservation.user.email = "anselmi.arnaud@yahoo.fr"
        partner = Partners.objects.order_by("-id").first()
        partner.user.email = "anselmi.arnaud@yahoo.fr"
        logement = Logement.objects.order_by("-id").first()
        logement.owner.email = "anselmi.arnaud@yahoo.fr"
        conciergerie = Conciergerie.objects.order_by("-id").first()
        conciergerie.user.email = "anselmi.arnaud@yahoo.fr"
        user = reservation.user if reservation else None
        session = {"checkout_session_url": "https://dummy-checkout-url.com"}
        cd = {"name": "Test", "email": "test@example.com", "message": "Ceci est un test."}
        msg = Message.objects.order_by("-id").first()
        func = getattr(email_service, func_name, None)
        try:
            if func_name == "notify_vendor_new_reservation":
                func(activity_reservation)
            elif func_name in [
                "send_mail_on_new_activity_reservation",
                "send_mail_on_activity_refund",
                "send_mail_on_activity_payment_failure",
                "send_mail_on_new_activity_transfer",
            ]:
                func(activity_reservation.activity, activity_reservation, activity_reservation.user)
            elif func_name in ["send_mail_new_account_validation", "resend_confirmation_email"]:
                func(user, settings.SITE_ADDRESS)
            elif func_name == "send_partner_validation_email":
                func(partner)
            elif func_name in [
                "send_mail_on_logement_refund",
                "send_mail_on_payment_failure",
                "send_mail_on_new_reservation",
            ]:
                func(logement, reservation, user)
            elif func_name == "send_mail_on_new_transfer":
                func(logement, reservation, "owner")
            elif func_name == "send_mail_payment_link":
                func(reservation, session)
            elif func_name == "send_mail_activity_payment_link":
                func(activity_reservation, session)
            elif func_name == "send_mail_contact":
                func(cd)
            elif func_name == "send_email_new_message":
                func(msg)
            elif func_name in [
                "send_mail_conciergerie_stop_management",
                "send_mail_conciergerie_request_refused",
                "send_mail_conciergerie_request_accepted",
            ]:
                func(logement.owner, conciergerie, logement)
            elif func_name == "send_mail_conciergerie_request_new":
                func(conciergerie.user, logement, logement.owner)
            elif func_name in ["send_pre_checkin_reminders", "send_pre_checkin_activity_reminders"]:
                func()
            else:
                messages.warning(request, f"Aucune logique de test pour {func_name}")
            messages.success(request, f"Email envoyé avec succès via {func_name}")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'envoi: {e}")
    return render(request, "administration/test_email.html", {"email_functions": EMAIL_FUNCTIONS})
