import logging
from datetime import datetime

from django.http import HttpRequest, HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin

from django.views.generic import TemplateView
from django.core.paginator import Paginator

from activity.forms import PartnerForm, ActivityForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from activity.mixins import UserHasActivityMixin
from activity.decorators import (
    user_is_partner,
    user_has_activity,
)
from activity.models import Price
from activity.models import Activity, Category, Partners, ActivityPhoto
from activity.services.activity import get_activity, get_calendar_context
from activity.services.price import get_price_context, get_daily_price_data, bulk_update_prices, get_revenue_context
from activity.serializers import DailyPriceSerializer

from logement.models import City

from reservation.services.activity import available_by_day

from common.decorators import is_admin
from common.services.email_service import send_partner_validation_email

logger = logging.getLogger(__name__)


def activity_search(request):
    # Récupération des filtres GET
    category = request.GET.get("category")
    city = request.GET.get("city")
    _date = request.GET.get("date")
    page_number = request.GET.get("page", 1)

    # Préparation du queryset
    activities = Activity.objects.filter(is_active=True).select_related("owner")
    if category:
        activities = activities.filter(category__name=category)
    if city:
        activities = activities.filter(location__name=city)
    if _date:
        try:
            # Try to convert date string to a date object
            if isinstance(_date, str):
                date_obj = datetime.strptime(_date, "%Y-%m-%d").date()
            else:
                date_obj = _date  # Already a date object
            activities = available_by_day(activities, date_obj)
        except Exception as e:
            logger.error(f"Error filtering activities by date: {e}")
            activities = []

    # Pagination (9 par page)
    paginator = Paginator(activities, 9)
    activities_page = paginator.get_page(page_number)

    # Pour les filtres dynamiques
    categories = Category.objects.values_list("name", flat=True).distinct()
    cities = City.objects.values_list("name", flat=True).distinct()

    # Pré-charger les partenaires pour chaque activité (si besoin)
    partners_map = {p.user_id: p for p in Partners.objects.all()}
    for act in activities_page:
        act.partner_obj = partners_map.get(act.owner_id)

    context = {
        "activities": activities_page,
        "categories": categories,
        "cities": cities,
    }
    return render(request, "activity/search_results.html", context)


@login_required
def create_partner(request):
    if request.method == "POST":
        form = PartnerForm(request.POST, request.FILES)
        if form.is_valid():
            partner = form.save(commit=False)
            partner.user = request.user  # ← assignation ici
            partner.save()
            messages.success(request, "Partenaire créé avec succès.")
            return redirect("accounts:dashboard")  # ou autre URL
        else:
            messages.error(request, "Merci de corriger les erreurs dans le formulaire.")
    else:
        form = PartnerForm()

    return render(request, "activity/create_partner.html", {"form": form, "is_edit": False})


@user_is_partner
@login_required
def update_partner(request, pk=None):
    try:
        if pk:
            partner = Partners.objects.get(id=pk)
        else:
            partner = Partners.objects.get(user=request.user)

        if not (request.user.is_superuser or request.user.is_admin) and partner.user != request.user:
            messages.error(request, "Accès non autorisé à ce partenaire.")
            return redirect("accounts:dashboard")

    except Partners.DoesNotExist:
        messages.error(request, "Vous n'avez pas encore de compte partenaire à modifier.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = PartnerForm(request.POST, request.FILES, instance=partner)
        if form.is_valid():
            form.save()
            messages.success(request, "Compte mis à jour avec succès.")
            if request.user.is_admin or request.user.is_superuser:
                return redirect("activity:list_partners")
            else:
                return redirect("accounts:dashboard")  # ou un dashboard
        else:
            messages.error(request, "Merci de corriger les erreurs dans le formulaire.")
    else:
        form = PartnerForm(instance=partner)

    return render(request, "activity/create_partner.html", {"form": form, "is_edit": True})


@login_required
@is_admin
def list_partners(request):
    partners = Partners.objects.all()
    villes = City.objects.all()

    # Filtres
    ville_id = request.GET.get("ville")
    validated = request.GET.get("validated")

    if ville_id:
        partners = partners.filter(ville_id=ville_id)
    if validated:
        partners = partners.filter(validated=True)

    # Pagination
    paginator = Paginator(partners, 20)  # 20 partenaires par page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "activity/list_partners.html",
        {
            "partners": page_obj,
            "villes": villes,
            "page_obj": page_obj,
        },
    )


def partner_list_customer(request):
    ville_id = request.GET.get("ville")
    partners = Partners.objects.filter(actif=True, validated=True)
    if ville_id:
        partners = partners.filter(ville_id=ville_id)
    partners = partners.order_by("name")

    # Pagination (9 par page)
    paginator = Paginator(partners, 9)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Liste des villes ayant au moins un partenaire
    villes = City.objects.filter(activity_partners__isnull=False).distinct()

    context = {
        "partners": page_obj.object_list,
        "page_obj": page_obj,
        "villes": villes,
    }
    return render(request, "activity/partner_list_customer.html", context)


@login_required
@is_admin
def partner_detail(request, pk):
    partner = get_object_or_404(Partners, pk=pk)
    return render(request, "activity/partner_detail.html", {"partner": partner})


def partner_customer_detail(request, pk):
    partner = get_object_or_404(Partners, pk=pk)
    return render(request, "activity/partner_customer_card.html", {"partner": partner})


@is_admin
def bulk_action(request):
    if request.method == "POST":
        ids = request.POST.getlist("selected_ids")
        action = request.POST.get("action")

        if not ids:
            messages.warning(request, "Aucun partenaire sélectionné.")
            return redirect("activity:list_partners")

        queryset = Partners.objects.filter(id__in=ids)

        if action == "delete":
            count = queryset.count()
            queryset.delete()
            messages.success(request, f"{count} partenaire(s) supprimé(s).")

        elif action == "validate":
            for partner in queryset:
                partner.validated = True
                partner.save()
                send_partner_validation_email(partner)
            messages.success(request, f"{queryset.count()} partenaire(s) validé(s) avec notification.")

        else:
            messages.error(request, "Action non reconnue.")

    return redirect("activity:list_partners")


@login_required
def create_activity(request):
    from .forms import ActivityForm

    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES, owner=request.user)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.owner = request.user
            activity.save()
            # Gestion des photos multiples
            photos = request.FILES.getlist("photos")
            for photo in photos:
                ActivityPhoto.objects.create(activity=activity, image=photo)
            messages.success(request, "Activité créée avec succès.")
            return redirect("activity:activity_dashboard")
    else:
        form = ActivityForm(owner=request.user)
    return render(request, "activity/create_activity.html", {"form": form})


@login_required
def update_activity(request, pk):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES, instance=activity)
        # Suppression d'une photo si demandé
        if "delete_photo" in request.POST:
            photo_id = request.POST.get("delete_photo")
            photo = get_object_or_404(ActivityPhoto, id=photo_id, activity=activity)
            photo.delete()
            messages.success(request, "Photo supprimée.")
            return redirect("activity:update_activity", pk=activity.pk)
        if form.is_valid():
            form.save()
            # Ajout de nouvelles photos
            photos = request.FILES.getlist("photos")
            for photo in photos:
                ActivityPhoto.objects.create(activity=activity, image=photo)
            messages.success(request, "Activité modifiée avec succès.")
            return redirect("activity:activity_dashboard")
    else:
        form = ActivityForm(instance=activity)
    return render(request, "activity/update_activity.html", {"form": form, "activity": activity})


@login_required
def activity_dashboard(request):
    # Check if user is a partner, admin, or superuser
    has_partner = Partners.objects.filter(user=request.user).exists()
    if not (has_partner or request.user.is_admin or request.user.is_superuser):
        messages.info(
            request, "Vous devez créer un compte partenaire avant d'accéder au tableau de bord des activités."
        )
        return redirect("activity:activity_dashboard")

    activities = Activity.objects.filter(owner=request.user).order_by("-created_at")
    paginator = Paginator(activities, 9)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    return render(request, "activity/dashboard.html", {"activities": page_obj.object_list, "page_obj": page_obj})


@login_required
@user_has_activity
def activity_calendar(request):
    """
    Display the calendar view for all activities owned by the user (delegates logic to service).
    """
    context = get_calendar_context(request.user)
    if context.get("redirect"):
        messages.info(request, "Vous devez ajouter une activité avant d’accéder au tableau de revenus.")
        return redirect("activity:activity_dashboard")
    return render(request, "activity/calendar.html", context)


@login_required
def manage_discounts(request):
    # TODO: Gestion des remises pour les activités
    return render(request, "activity/manage_discounts.html")


class RevenueView(LoginRequiredMixin, UserHasActivityMixin, TemplateView):
    """
    View for displaying revenue statistics for a user's activities (delegates logic to service).
    """

    template_name = "activity/revenu.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        activities = get_activity(request.user)
        if not activities.exists():
            messages.info(request, "Vous devez ajouter une activité avant d’accéder au tableau de revenus.")
            return redirect("logement:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_revenue_context(self.request.user, self.request))
        return context


def detail(request, pk):
    activity = get_object_or_404(Activity.objects.select_related("owner"), pk=pk)
    # Pré-charger le partenaire pour affichage
    partner = Partners.objects.filter(user=activity.owner).first()
    activity.partner_obj = partner

    context = {
        "activity": activity,
    }

    return render(request, "activity/detail.html", context)


class DailyPriceViewSet(viewsets.ModelViewSet):
    serializer_class = DailyPriceSerializer

    def get_queryset(self):
        activity_id = self.request.query_params.get("activity_id")
        return Price.objects.filter(activity_id=activity_id)

    def list(self, request, *args, **kwargs):
        try:
            activity_id = request.query_params.get("activity_id")
            start_str = request.query_params.get("start")
            end_str = request.query_params.get("end")
            result = get_daily_price_data(activity_id, start_str, end_str)
            return Response(result)
        except Exception as e:
            logger.exception(f"Error fetching daily prices: {e}")
            return Response({"error": "Erreur interne serveur"}, status=500)

    def perform_create(self, serializer):
        try:
            serializer.save()
        except Exception as e:
            logger.exception(f"Error creating price: {e}")
            raise

    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        result = bulk_update_prices(
            activity_id=request.data.get("activity_id"),
            start=request.data.get("start"),
            end=request.data.get("end"),
            price=float(request.data.get("price")),
            statut=int(request.data.get("statut")),
        )
        if "error" in result:
            return Response({"error": result["error"]}, status=result.get("status", 500))
        return Response({"status": result["status"]})

    @action(detail=False, methods=["post"])
    def calculate_price(self, request):
        result = get_price_context(
            activity_id=request.data.get("activity_id"),
            start=request.data.get("start"),
            end=request.data.get("end"),
            base_price=request.data.get("base_price"),
            guest=request.data.get("guests", 1),
        )
        if "error" in result:
            return Response({"error": result["error"]}, status=500)
        return Response(result)
