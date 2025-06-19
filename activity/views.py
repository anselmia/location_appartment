import logging
from typing import Optional
from datetime import datetime, timedelta, date
from django.http import JsonResponse
from activity.services.reservation import get_available_slots
from django.http import HttpRequest, HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
from django.views.decorators.http import require_GET, require_POST
from django.utils.dateparse import parse_date, parse_time
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from payment.services.payment_service import PAYMENT_FEE_VARIABLE
from activity.forms import PartnerForm, ReservationForm, ActivityForm

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from activity.decorators import (
    user_is_partner,
    user_has_activity,
    user_is_reservation_admin,
    user_is_reservation_customer,
)
from activity.models import Price
from common.decorators import is_admin
from common.services.email_service import send_partner_validation_email
from common.services.helper_fct import paginate_queryset
from activity.models import Activity, Category, Partners, ActivityPhoto
from activity.services.reservation import (
    validate_reservation_inputs,
    create_reservation,
    available_by_day,
    get_valid_reservations_for_user,
    get_reservation_years_and_months,
    mark_reservation_cancelled,
    cancel_and_refund_reservation,
)
from activity.services.activity import get_activity, get_calendar_context
from activity.services.price import get_price_context, get_daily_price_data, bulk_update_prices
from logement.models import City
from activity.serializers import DailyPriceSerializer
from payment.services.payment_service import (
    create_stripe_checkout_session_with_manual_capture,
    capture_reservation_payment,
)

from django.db.models import Q
from activity.models import ActivityReservation


logger = logging.getLogger(__name__)


def activity_search(request):
    # Récupération des filtres GET
    category = request.GET.get("category")
    city = request.GET.get("city")
    date = request.GET.get("date")
    page_number = request.GET.get("page", 1)

    # Préparation du queryset
    activities = Activity.objects.filter(is_active=True).select_related("owner")
    if category:
        activities = activities.filter(category__name=category)
    if city:
        activities = activities.filter(location__name=city)
    if date:
        try:
            # Try to convert date string to a date object
            if isinstance(date, str):
                date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                date_obj = date  # Already a date object
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
@user_has_activity
def reservation_dashboard(request: HttpRequest, activity_id: Optional[int] = None) -> HttpResponse:
    """
    Dashboard for activity owners to view reservations with filters and pagination.
    """
    try:
        if not (request.user.is_admin or request.user.is_superuser):
            activities = get_activity(request.user)
            if not activities.exists():
                messages.info(request, "Vous devez ajouter une activité avant d’accéder au tableau des réservations.")
                return redirect("activity:activity_dashboard")

        status = request.GET.get("status", "all")
        year = request.GET.get("year", "")
        month = request.GET.get("month", "")
        search = request.GET.get("search", "")

        reservations = get_valid_reservations_for_user(
            user=request.user,
            activity_id=activity_id,
            year=year,
            month=month,
        )

        # Status filter
        if status and status != "all":
            reservations = reservations.filter(statut=status)

        # Search filter (by client name, username, or code)
        if search:
            reservations = reservations.filter(
                Q(user__username__icontains=search)
                | Q(user__name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(code__icontains=search)
            )

        # Pagination
        paginator = Paginator(reservations.order_by("-date_reservation"), 20)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        # For year/month filter dropdowns
        years, months = get_reservation_years_and_months()

        context = {
            "reservations": page_obj,
            "page_obj": page_obj,
            "status": status,
            "available_years": years,
            "available_months": months,
            "current_year": year,
            "current_month": month,
            "search": search,
        }
        return render(request, "activity/reservation_dashboard.html", context)
    except Exception as e:
        logger.error(f"Error in reservation_dashboard: {e}", exc_info=True)
        raise


@login_required
def manage_discounts(request):
    # TODO: Gestion des remises pour les activités
    return render(request, "activity/manage_discounts.html")


@login_required
def revenu(request):
    # TODO: Statistiques de revenus pour le partenaire
    return render(request, "activity/revenu.html")


def detail(request, pk):
    activity = get_object_or_404(Activity.objects.select_related("owner"), pk=pk)
    # Pré-charger le partenaire pour affichage
    partner = Partners.objects.filter(user=activity.owner).first()
    activity.partner_obj = partner

    context = {
        "activity": activity,
    }

    return render(request, "activity/detail.html", context)


@login_required
def book(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handle the booking process for a logement, including form validation and Stripe session creation.
    """
    try:
        activity = get_object_or_404(Activity.objects.prefetch_related("photos"), id=pk)
        user = request.user
        activity_data = {
            "id": activity.id,
            "name": activity.name,
            "description": activity.description,
            "price": str(activity.price),
            "max_traveler": activity.max_participants,
            "payment_fee": PAYMENT_FEE_VARIABLE,
        }
        if request.method == "POST":
            form = ReservationForm(request.POST)
            if form.is_valid():
                reservation_price = request.POST.get("reservation_price", None)
                start = form.cleaned_data["start"]
                guest = form.cleaned_data["guest"]
                slot = form.cleaned_data["slot_time"]
                if reservation_price is not None and start and guest > 0 and slot:
                    price = float(reservation_price)
                    slot = parse_time(slot)
                    if validate_reservation_inputs(activity, user, start, guest, slot, price):
                        reservation = create_reservation(activity, user, start, slot, guest, price)
                        session = create_stripe_checkout_session_with_manual_capture(reservation, request)
                        logger.info(f"Reservation created and Stripe session initialized for user {user}")
                        return redirect(session["checkout_session_url"])
                else:
                    messages.error(request, "Une erreur est survenue")
        else:
            start_date = request.GET.get("start")
            guest = request.GET.get("guest", 1)
            form = ReservationForm(
                start_date=start_date,
                max_guests=activity.max_participants,
                guest=guest,
            )
        return render(
            request,
            "activity/book.html",
            {
                "form": form,
                "activity": activity,
                "activity_data": activity_data,
                "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
                "photo_urls": [photo.image.url for photo in activity.photos.all()],
            },
        )
    except Exception as e:
        logger.exception(f"Booking failed: {e}")
        raise


def activity_slots(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    day_str = request.GET.get("date")
    if not day_str:
        return JsonResponse({"slots": []})
    day = date.fromisoformat(day_str)
    slots = get_available_slots(activity, day)

    return JsonResponse({"slots": slots})


@login_required
def check_booking_input(request: HttpRequest, activity_id: int) -> JsonResponse:
    """
    Validate booking input fields for a logement.
    """
    try:
        start = parse_date(request.GET.get("start"))
        guest = int(request.GET.get("guest"))
        slot = parse_time(request.GET.get("slot"))
        activity = Activity.objects.get(id=activity_id)
        user = request.user
        if not start or not slot or guest <= 0:
            return JsonResponse({"correct": False})
        validate_reservation_inputs(activity, user, start, guest, slot)
        return JsonResponse({"correct": True})
    except ValueError as e:
        return JsonResponse({"correct": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error validating booking input: {e}")
        return JsonResponse({"correct": False, "error": "Erreur interne serveur."}, status=500)


@require_GET
def not_available_dates(request, pk):
    """
    Return all not-available dates for the visible Flatpickr grid (6x7 days).
    Expects ?year=YYYY&month=MM in GET.
    """
    try:
        activity = Activity.objects.get(pk=pk)
        year = int(request.GET.get("year"))
        month = int(request.GET.get("month"))
        not_available = []

        # 1. Find the first day to display (start of the grid)
        first_of_month = date(year, month, 1)
        # Always start grid on Monday
        first_weekday = first_of_month.weekday()  # Monday=0
        grid_start = first_of_month - timedelta(days=first_weekday)
        # Flatpickr starts week on Sunday by default, adjust if needed
        grid_start = first_of_month - timedelta(days=first_of_month.weekday())

        # 2. List all 42 days in the grid
        grid_dates = [grid_start + timedelta(days=i) for i in range(42)]

        # 3. Find not-available dates (no slot available or closed)
        for day in grid_dates:
            if not get_available_slots(activity, day):
                not_available.append(day.isoformat())

        return JsonResponse({"dates": not_available})
    except Exception as e:
        return JsonResponse({"dates": [], "error": str(e)}, status=400)


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


@login_required
@user_is_reservation_admin
def reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin view for reservation details.
    """
    reservation = get_object_or_404(ActivityReservation, code=code)
    return render(request, "activity/reservation_detail.html", {"reservation": reservation})


@login_required
@user_is_reservation_admin
@require_POST
def cancel_reservation(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin action to cancel a reservation.
    """
    reservation = get_object_or_404(ActivityReservation, code=code)
    if reservation.statut != "annulee":
        mark_reservation_cancelled(reservation)
        messages.success(request, "Réservation annulée avec succès.")
    else:
        messages.warning(request, "La réservation est déjà annulée.")
    return redirect("activity:reservation_detail", code=code)


@login_required
@user_has_activity
def cancel_booking(request: HttpRequest, code: str) -> HttpResponse:
    """
    Cancel a booking and process refund if possible.
    """
    try:
        reservation = get_object_or_404(ActivityReservation, code=code, user=request.user)
        success_message, error_message = cancel_and_refund_reservation(reservation)
        if success_message:
            messages.success(request, success_message)
        if error_message:
            messages.error(request, error_message)
    except Exception as e:
        logger.exception(f"Error canceling booking: {e}")
        messages.error(request, "Erreur lors de l'annulation. Veuillez nous contacter")
    return redirect("accounts:dashboard")


@login_required
@user_has_activity
def validate_reservation(request, code):
    reservation = get_object_or_404(ActivityReservation, code=code)
    if request.method == "POST":
        if reservation.statut == "en_attente":
            charge_result = capture_reservation_payment(reservation)
            if charge_result.get("success"):
                messages.success(request, "Le paiement a été prélevé avec succès.")
            else:
                error_msg = charge_result.get("error") or "Une erreur est survenue lors du prélèvement du paiement."
                messages.error(request, error_msg)
        else:
            messages.warning(request, "La réservation n'est pas en attente ou a déjà été traitée.")
    return redirect("activity:reservation_detail", code=reservation.code)


@login_required
@user_is_reservation_customer
def customer_reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Customer view for their own reservation details.
    """
    reservation = get_object_or_404(ActivityReservation, code=code)
    return render(request, "activity/customer_reservation_detail.html", {"reservation": reservation})


@login_required
@is_admin
def manage_reservations(request: HttpRequest) -> HttpResponse:
    """
    Admin view to manage all reservations with search and pagination.
    """
    query = request.GET.get("q")
    reservations = ActivityReservation.objects.select_related("activity", "user")
    if query:
        reservations = reservations.filter(code__icontains=query)
    reservations = reservations.order_by("-date_reservation")
    page_obj = paginate_queryset(reservations, request)
    context = {
        "reservations": page_obj,
        "query": query,
        "page_obj": page_obj,
    }
    return render(request, "activity/manage_reservations.html", context)
