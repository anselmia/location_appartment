import logging

from datetime import datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponse, HttpRequest
from django.views.generic import TemplateView
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import cache_page

from django.core.cache import cache

from logement.models import Logement, Price, EquipmentType, Photo, Discount, DiscountType, LogementRanking
from logement.services.calendar_service import (
    sync_external_ical,
    get_calendar_context,
    export_ical_service,
)
from logement.services.revenue_service import get_economie_stats
from logement.forms import LogementForm, DiscountForm, LogementRankingForm
from logement.serializers import DailyPriceSerializer
from logement.services.price_service import (
    bulk_update_prices,
    calculate_price_service,
    get_price_for_date_service,
    get_daily_price_data,
)
from logement.services.logement_service import get_logements_overview, get_owner_system_messages
from logement.decorators import (
    user_has_logement,
    user_is_logement_admin,
)
from logement.mixins import UserHasLogementMixin

from common.services.helper_fct import normalize_decimal_input
from logement.services.logement_service import (
    get_logement_form_data,
    add_room_to_logement,
    delete_room_by_id,
    upload_photos_to_logement,
    change_photo_room_service,
    get_logement_search_context,
    get_logement_dashboard_context,
    get_logement_detail_context,
    update_logement_equipment,
    autocomplete_cities_service,
    get_logements,
)
from logement.services.revenue_service import get_revenue_context
from conciergerie.models import Conciergerie, ConciergerieRequest
from common.services.email_service import (
    send_mail_conciergerie_request_new,
    send_mail_conciergerie_stop_management,
)

from reservation.models import Reservation, ReservationHistory
from reservation.decorators import user_has_reservation

logger = logging.getLogger(__name__)


def autocomplete_cities(request: HttpRequest) -> HttpResponse:
    """
    Autocomplete city names for a search input (delegates logic to service).
    """
    q = request.GET.get("q", "")
    result = autocomplete_cities_service(q)
    if result["success"]:
        return HttpResponse(result["options"])
    return JsonResponse({"error": result["error"]}, status=500)


@cache_page(60 * 10)
def view_logement(request: HttpRequest, logement_id: int) -> HttpResponse:
    """
    Display details for a single logement, including photos, rooms, and equipment (delegates logic to service).
    """
    context = get_logement_detail_context(logement_id, request.user)
    return render(request, "logement/view_logement.html", context)


@login_required
def get_price_for_date(request: HttpRequest, logement_id: int, date: str) -> JsonResponse:
    """
    Get the price for a logement on a specific date (delegates logic to service).
    """
    result = get_price_for_date_service(logement_id, date)
    if result["success"]:
        return JsonResponse({"price": result["price"]})
    return JsonResponse({"error": result["error"]}, status=result.get("status", 500))


def export_ical(request: HttpRequest, code: str) -> HttpResponse:
    """
    Export iCal data for a logement by code (delegates logic to service).
    """
    result = export_ical_service(code)
    if result["success"]:
        return result["response"]
    return HttpResponse(result["error"], status=result.get("status", 500))


def logement_search(request: HttpRequest) -> HttpResponse:
    """
    Search for logements with filters and return paginated results (delegates logic to service).
    """
    context = get_logement_search_context(request)
    return render(request, "logement/search_results.html", context)


@login_required
def logement_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Dashboard for a user's logements with pagination (delegates logic to service).
    """
    context = get_logement_dashboard_context(request.user, request)
    return render(request, "logement/dashboard.html", context)


@login_required
@user_has_logement
@user_is_logement_admin
@require_http_methods(["GET", "POST"])
def manage_logement(request: HttpRequest, logement_id: int = None) -> HttpResponse:
    """
    Add or edit a logement, including rooms, photos, and equipment (delegates logic to service).
    """
    logement = None
    is_editing = logement_id is not None
    pending_request = None

    if is_editing:
        logement = get_object_or_404(Logement.objects.prefetch_related("rooms", "photos", "equipment"), id=logement_id)
        admin_user = None
        admin_user_name = None
        if logement and logement.admin:
            admin_user = logement.admin
            conciergerie = Conciergerie.objects.filter(user=admin_user).first()
            if conciergerie:
                admin_user_name = conciergerie.name
            else:
                admin_user_name = str(admin_user)
        if logement:
            pending_request = ConciergerieRequest.objects.filter(logement=logement, status="pending").first()

    action = request.POST.get("action") if request.method == "POST" else None

    # Remove admin if requested
    if request.method == "POST" and request.POST.get("remove_admin") and logement:
        logement.admin = None
        logement.save()
        messages.success(request, "L'administrateur du logement a été supprimé.")
        return redirect("logement:edit_logement", logement.id)

    # Handle conciergerie request form
    if request.method == "POST" and action == "conciergerie_request" and logement:
        conciergerie_id = request.POST.get("conciergerie_id")
        if not conciergerie_id:
            messages.error(request, "Veuillez sélectionner une conciergerie.")
            return redirect("logement:edit_logement", logement.id)
        conciergerie = Conciergerie.objects.filter(id=conciergerie_id, actif=True).first()
        if conciergerie:
            exists = ConciergerieRequest.objects.filter(
                logement=logement, conciergerie=conciergerie, status="pending"
            ).exists()
            if not exists:
                ConciergerieRequest.objects.create(logement=logement, conciergerie=conciergerie)
                if conciergerie.user and conciergerie.user.email:
                    send_mail_conciergerie_request_new(conciergerie.user, logement, logement.owner)
                messages.success(request, "Demande envoyée à la conciergerie. Elle doit valider la demande.")
            else:
                messages.info(request, "Une demande en attente existe déjà pour cette conciergerie.")
        else:
            messages.error(request, "Conciergerie introuvable ou inactive.")
        return redirect("logement:edit_logement", logement.id)

    # Handle logement edit form
    if request.method == "POST" and (action == "edit_logement" or not action):
        form = LogementForm(request.POST, instance=logement, user=request.user)
        if form.is_valid():
            logement = form.save()
            if is_editing:
                logger.info(f"Logement {logement.id} updated")
            else:
                logger.info(f"Logement created with ID {logement.id}")
            return redirect("logement:edit_logement", logement.id)
    else:
        form = LogementForm(request.POST or None, instance=logement, user=request.user)
        # BLOCK is_owner_admin users here
        if request.user.is_owner_admin and not (request.user.is_admin or request.user.is_superuser):
            messages.error(request, "Vous n'avez pas l'autorisation d'ajouter un logement.")
            return redirect("logement:dashboard")

    # 2. Ajouter la liste des conciergeries actives au contexte
    active_conciergeries = Conciergerie.objects.filter(actif=True).order_by("name")

    context = get_logement_form_data(logement, request.user)
    context.update(
        {
            "form": form,
            "logement": logement,
            "is_editing": is_editing,
            "equipment_type_choices": EquipmentType.choices,
            "admin_user": admin_user_name if is_editing else None,
            "active_conciergeries": active_conciergeries,
            "pending_request": pending_request,
        }
    )
    return render(request, "logement/edit_logement.html", context)


@login_required
@user_has_logement
@user_is_logement_admin
def delete_logement(request, pk):
    try:
        thirty_days_ago = timezone.now().date() - timezone.timedelta(days=30)
        logement = Logement.objects.get(id=pk)
        reservations = Reservation.objects.filter(
            logement=logement, statut__in=["en_attente", "confirmee", "echec_paiement"]
        )
        ended_reservation = Reservation.objects.filter(logement=logement, statut="terminee", end__gt=thirty_days_ago)
        if reservations.exists() or ended_reservation.exists():
            messages.error(request, "Vous ne pouvez pas supprimer ce logement tant qu'il a des réservations en cours.")
            return redirect("logement:dashboard")

        logement.delete()
        messages.success(request, "Logement supprimé avec succès.")
    except Logement.DoesNotExist:
        messages.error(request, "Ce logement n'existe pas.")

    return redirect("logement:dashboard")


@login_required
@user_is_logement_admin
def add_room(request: HttpRequest, logement_id: int) -> HttpResponse:
    """
    Add a new room to a logement (delegates logic to service).
    """
    result = add_room_to_logement(request.POST, logement_id)
    if not result["success"]:
        messages.error(request, result["error"])
    return redirect("logement:edit_logement", logement_id)


@login_required
@user_is_logement_admin
@require_POST
def delete_room(request: HttpRequest, room_id: int) -> HttpResponse:
    """
    Delete a room from a logement (delegates logic to service).
    """
    result = delete_room_by_id(room_id)
    if not result["success"]:
        messages.error(request, result["error"])
        return redirect("logement:dashboard")
    return redirect("logement:edit_logement", result["logement_id"])


MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB


@login_required
@user_is_logement_admin
@require_POST
def upload_photos(request: HttpRequest, logement_id: int) -> HttpResponse:
    """
    Upload photos for a logement and assign them to a room (delegates logic to service).
    """
    files = request.FILES.getlist("photo")
    room_id = request.POST.get("room_id")
    result = upload_photos_to_logement(files, logement_id, room_id)
    if not result["success"]:
        messages.error(request, result["error"])
    return redirect("logement:edit_logement", logement_id)


@login_required
@user_is_logement_admin
@require_POST
def change_photo_room(request: HttpRequest, photo_id: int) -> JsonResponse:
    """
    Change the room assignment for a photo (delegates logic to service).
    """
    result = change_photo_room_service(photo_id, request.body)
    if result.get("success"):
        return JsonResponse({"success": True})
    return JsonResponse({"success": False, "error": result["error"]}, status=result.get("status", 500))


@login_required
@user_is_logement_admin
@require_POST
def move_photo(request: HttpRequest, photo_id: int, direction: str) -> JsonResponse:
    """
    Move a photo in the order for a logement.
    """
    try:
        photo = get_object_or_404(Photo, id=photo_id)
        success, message = photo.move_in_order(direction)
        if success:
            logger.info(f"Photo {photo_id} moved {direction}")
            return JsonResponse({"success": True})
        logger.warning(f"Failed to move photo {photo_id}: {message}")
        return JsonResponse({"success": False, "message": message}, status=400)
    except Exception as e:
        logger.error(f"Error moving photo {photo_id}: {e}")
        return JsonResponse({"success": False, "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
@require_http_methods(["DELETE"])
def delete_photo(request: HttpRequest, photo_id: int) -> JsonResponse:
    """
    Delete a photo from a logement.
    """
    try:
        photo = get_object_or_404(Photo, id=photo_id)
        photo.safe_delete()
        logger.info(f"Photo {photo_id} deleted")
        return JsonResponse({"success": True})
    except Exception as e:
        logger.error(f"Error deleting photo {photo_id}: {e}")
        return JsonResponse({"success": False, "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
@require_POST
def delete_all_photos(request: HttpRequest, logement_id: int) -> JsonResponse:
    """
    Delete all photos for a logement.
    """
    try:
        logement = get_object_or_404(Logement, id=logement_id)
        for photo in logement.photos.all():
            photo.safe_delete()
        logger.info(f"All photos deleted for logement {logement_id}")
        return JsonResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Error deleting all photos for logement {logement_id}: {e}")
        return JsonResponse({"status": "error", "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
@require_POST
def rotate_photo(request: HttpRequest, photo_id: int) -> JsonResponse:
    """
    Rotate a photo by a given number of degrees.
    """
    try:
        degrees = int(request.POST.get("degrees", 90))
        photo = get_object_or_404(Photo, pk=photo_id)
        photo.rotate(degrees)
        logger.info(f"Photo {photo_id} rotated by {degrees} degrees")
        return JsonResponse({"status": "ok", "rotation": photo.rotation})
    except Exception as e:
        logger.error(f"Error rotating photo {photo_id}: {e}")
        return JsonResponse({"status": "error", "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
def update_equipment(request: HttpRequest, logement_id: int) -> HttpResponse:
    """
    Update the equipment for a logement (delegates logic to service).
    """
    if request.method == "POST":
        equipment_ids = request.POST.getlist("equipment")
        update_logement_equipment(logement_id, equipment_ids)
    return redirect("logement:edit_logement", logement_id)


@login_required
@user_has_logement
def calendar(request: HttpRequest) -> HttpResponse:
    """
    Display the calendar view for all logements owned by the user (delegates logic to service).
    """
    context = get_calendar_context(request.user)
    if context.get("redirect"):
        messages.info(request, "Vous devez ajouter un logement avant d’accéder au tableau de revenus.")
        return redirect("logement:dashboard")
    return render(request, "logement/calendar.html", context)


class DailyPriceViewSet(viewsets.ModelViewSet):
    serializer_class = DailyPriceSerializer

    def get_queryset(self):
        logement_id = self.request.query_params.get("logement_id")
        return Price.objects.filter(logement_id=logement_id)

    def list(self, request, *args, **kwargs):
        try:
            logement_id = request.query_params.get("logement_id")
            start_str = request.query_params.get("start")
            end_str = request.query_params.get("end")
            result = get_daily_price_data(logement_id, start_str, end_str)
            return Response(result)
        except Exception as e:
            logger.error(f"Error fetching daily prices: {e}")
            return Response({"error": "Erreur interne serveur"}, status=500)

    def perform_create(self, serializer):
        try:
            serializer.save()
        except Exception as e:
            logger.error(f"Error creating price: {e}")
            raise

    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        result = bulk_update_prices(
            logement_id=request.data.get("logement_id"),
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
        result = calculate_price_service(
            logement_id=request.data.get("logement_id"),
            start=request.data.get("start"),
            end=request.data.get("end"),
            base_price=request.data.get("base_price"),
            guest_adult=request.data.get("guest_adult", 1),
            guest_minor=request.data.get("guest_minor", 0),
        )
        if "error" in result:
            return Response({"error": result["error"]}, status=500)
        return Response(result)


@login_required
@user_has_logement
def manage_discounts(request: HttpRequest) -> HttpResponse:
    """
    View to manage discounts for a user's logement. Handles creation, update, and deletion of discounts.
    """
    try:
        logements = get_logements(request.user)
        logement_id = request.GET.get("logement_id") or request.POST.get("logement_id")
        logement = get_object_or_404(Logement, id=logement_id) if logement_id else logements.first()

        if not logement:
            messages.info(request, "Vous devez ajouter un logement avant d’accéder au tableau de revenus.")
            return redirect("logement:dashboard")

        discounts = Discount.objects.filter(logement=logement)
        discount_types = DiscountType.objects.all()

        if request.method == "POST":
            post_data = normalize_decimal_input(request.POST)
            action = post_data.get("action")

            if action == "delete":
                Discount.objects.filter(id=post_data["discount_id"], logement=logement).delete()
                messages.success(request, "Réduction supprimée avec succès.")

            elif action == "update":
                instance = get_object_or_404(Discount, id=post_data["discount_id"], logement=logement)
                form = DiscountForm(post_data, instance=instance, logement=logement)
                if form.is_valid():
                    form.save()
                    messages.success(request, "Réduction mise à jour.")
                else:
                    messages.error(request, "Erreur lors de la mise à jour.")
                    return render(
                        request,
                        "logement/discounts.html",
                        {
                            "logement": logement,
                            "discounts": discounts,
                            "discount_types": discount_types,
                            "all_logements": logements,
                            "form": form,
                        },
                    )
            else:
                form = DiscountForm(post_data, logement=logement)
                if form.is_valid():
                    new_discount = form.save(commit=False)
                    new_discount.logement = logement
                    new_discount.save()
                    messages.success(request, "Réduction ajoutée.")
                else:
                    messages.error(request, "Erreur lors de la création.")
                    return render(
                        request,
                        "logement/discounts.html",
                        {
                            "logement": logement,
                            "discounts": discounts,
                            "discount_types": discount_types,
                            "all_logements": logements,
                            "form": form,
                        },
                    )

            return redirect(f"{reverse('logement:manage_discounts')}?logement_id={logement.id}")

        return render(
            request,
            "logement/discounts.html",
            {
                "logement": logement,
                "discounts": discounts,
                "discount_types": discount_types,
                "all_logements": logements,
                "form": DiscountForm(logement=logement),
            },
        )
    except Exception as e:
        logger.error(f"Error managing discounts: {e}")
        # Optionally, show a user-friendly error message
        messages.error(request, "Erreur interne serveur. Veuillez réessayer plus tard.")
        return redirect("logement:dashboard")


class RevenueView(LoginRequiredMixin, UserHasLogementMixin, TemplateView):
    """
    View for displaying revenue statistics for a user's logements (delegates logic to service).
    """

    template_name = "logement/revenu.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        logements = get_logements(request.user)
        if not logements.exists():
            messages.info(request, "Vous devez ajouter un logement avant d’accéder au tableau de revenus.")
            return redirect("logement:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_revenue_context(self.request.user, self.request))
        return context


def api_economie_data(request, logement_id):
    try:
        year = request.GET.get("year", datetime.now().year)
        month = request.GET.get("month", "all")
        cache_key = f"eco_stats_{logement_id}_{year}_{month}"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse(cached)

        data = get_economie_stats(...)
        cache.set(cache_key, data, 600)
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Erreur dans api_economie_data: {e}")
        return JsonResponse({"error": "Erreur interne serveur"}, status=500)


@login_required
@require_POST
@user_is_logement_admin
def sync_airbnb_calendar_view(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    try:
        added, updated, deleted = sync_external_ical(logement, logement.airbnb_calendar_link, "airbnb")
        return JsonResponse({"message": f"{added} ajoutés, {updated} mis à jour, {deleted} supprimés"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
@user_is_logement_admin
def sync_booking_calendar_view(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    try:
        added, updated, deleted = sync_external_ical(logement, logement.booking_calendar_link, "booking")
        return JsonResponse({"message": f"{added} ajoutés, {updated} mis à jour, {deleted} supprimés"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def stop_managing_logement(request):
    logement_id = request.POST.get("logement_id")
    user = request.user
    if not logement_id:
        return JsonResponse({"error": "Missing logement_id"}, status=400)
    logement = get_object_or_404(Logement, id=logement_id)
    if logement.admin != user:
        return JsonResponse({"error": "Vous n'êtes pas l'administrateur de ce logement."}, status=403)
    # Save conciergerie before removing admin
    conciergerie = getattr(user, "conciergeries", None).first() if hasattr(user, "conciergeries") else None
    owner = logement.owner
    logement.admin = None
    logement.save()
    # Send email to owner
    if owner and conciergerie:
        send_mail_conciergerie_stop_management(owner, conciergerie, logement)
    return JsonResponse({"success": True})


@login_required
@user_is_logement_admin
def dashboard(request: HttpRequest) -> HttpResponse:
    """
    Affiche le tableau de bord de gestion des logements pour l'utilisateur connecté,
    avec toutes les données nécessaires pour les KPI, le calendrier, les réservations récentes, les tâches à faire, etc.
    """
    user = request.user
    # Récupère les stats compilées pour tous les logements de l'utilisateur
    logement_stats = get_logements_overview(user)

    if not user.onboarded:
        show_onboarding = True
        user.onboarded = True
        user.save()
    else:
        show_onboarding = False

    messages_systems = get_owner_system_messages(user)
    for resa in logement_stats["futur_reservations"]:
        resa.nb_days_until = (resa.start - timezone.localdate()).days

    context = {
        "occupancy_rate": logement_stats["occupancy_rate"],
        "total_revenue": logement_stats["total_revenue"],
        "futur_reservations": logement_stats["futur_reservations"],
        "futur_reservations_count": logement_stats["futur_reservations_count"],
        "average_night_price": logement_stats.get("average_night_price", 0),  # Si tu veux afficher le prix moyen/nuit
        "failed_reservations": logement_stats["total_failed_reservations"],
        "history": logement_stats["history"],
        "show_onboarding": show_onboarding,
        "messages_systems": messages_systems,
    }
    context["today"] = timezone.localdate()

    return render(request, "logement/dash.html", context)


@login_required
@user_has_reservation
def rate(request, code):
    reservation = get_object_or_404(Reservation, code=code)
    logement = reservation.logement

    # Check if a rating already exists for this reservation
    rating = LogementRanking.objects.filter(reservation=reservation).first()
    already_rated = rating is not None

    if already_rated:
        messages.info(request, "Vous avez déjà donné votre avis pour ce logement.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = LogementRankingForm(request.POST)
        if form.is_valid():
            new_rating = form.save(commit=False)
            new_rating.reservation = reservation
            new_rating.logement = logement
            new_rating.save()
            messages.success(request, "Merci pour votre avis sur ce logement !")
            ReservationHistory.objects.create(
                reservation=reservation,
                details=f"Nouveau commentaire reçu pour la réservation {reservation.code}.",
            )
            return redirect("accounts:dashboard")
    else:
        form = LogementRankingForm()

    return render(
        request,
        "logement/rate_logement.html",
        {
            "form": form,
            "logement": logement,
            "reservation": reservation,
            "already_rated": False,
            "rating": None,
        },
    )
