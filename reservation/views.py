import json
import logging
from typing import Optional
from datetime import date, timedelta

from django.conf import settings
from django.utils.dateparse import parse_date, parse_time
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q
from django.utils import timezone

from reservation.forms import LogementReservationForm, ActivityReservationForm
from reservation.models import Reservation, ActivityReservation
from reservation.decorators import (
    user_has_reservation,
    user_is_reservation_admin,
    user_is_reservation_customer,
)
from reservation.services.reservation_service import (
    cancel_and_refund_reservation,
    get_reservation_years_and_months,
    mark_reservation_cancelled,
    get_valid_reservations,
)
from reservation.services.logement import (
    get_logement_reservations_queryset,
    get_booked_dates,
    is_period_booked,
    validate_reservation_inputs as validate_logement_reservation_inputs,
    create_or_update_reservation,
)
from reservation.services.activity import (
    create_reservation,
    validate_reservation_inputs as validate_activity_reservation_inputs,
    get_activity_reservations_queryset,
    get_available_slots,
)
from payment.services.payment_service import (
    create_stripe_checkout_session_with_deposit,
    create_stripe_checkout_session_with_manual_capture,
    capture_reservation_payment,
    PAYMENT_FEE_VARIABLE,
)

from logement.models import Logement
from logement.decorators import user_has_logement
from logement.services.logement_service import get_logements

from activity.decorators import user_has_activity
from activity.models import Activity
from activity.services.activity import get_activity

from common.decorators import is_admin
from common.services.helper_fct import paginate_queryset
from common.services.network import get_client_ip

logger = logging.getLogger(__name__)


@login_required
def book_logement(request: HttpRequest, logement_id: int) -> HttpResponse:
    """
    Handle the booking process for a logement, including form validation and Stripe session creation.
    """
    try:
        logement = get_object_or_404(Logement.objects.prefetch_related("photos"), id=logement_id)
        user = request.user
        reserved_dates_start, reserved_dates_end = get_booked_dates(logement, user)
        logement_data = {
            "id": logement.id,
            "name": logement.name,
            "description": logement.description,
            "price": str(logement.price),
            "max_traveler": logement.max_traveler,
            "nominal_traveler": logement.nominal_traveler,
            "fee_per_extra_traveler": str(logement.fee_per_extra_traveler),
            "cleaning_fee": str(logement.cleaning_fee),
            "tax": str(logement.tax),
            "caution": logement.caution,
            "type_display": logement.get_type_display(),
            "cancelation_period": logement.cancelation_period,
            "bedrooms": logement.bedrooms,
            "bathrooms": logement.bathrooms,
            "beds": logement.beds,
            "ville": logement.ville.name if logement.ville else "Not Available",
            "payment_fee": PAYMENT_FEE_VARIABLE,
        }
        if request.method == "POST":
            form = LogementReservationForm(request.POST)
            if form.is_valid():
                reservation_price = request.POST.get("reservation_price", None)
                reservation_tax = request.POST.get("reservation_tax", None)
                start = form.cleaned_data["start"]
                end = form.cleaned_data["end"]
                guest_adult = form.cleaned_data["guest_adult"]
                guest_minor = form.cleaned_data["guest_minor"]
                if (
                    reservation_price is not None
                    and reservation_tax is not None
                    and start
                    and end
                    and guest_adult
                    and guest_minor >= 0
                ):
                    price = float(reservation_price)
                    tax = float(reservation_tax)
                    if validate_logement_reservation_inputs(
                        logement, user, start, end, guest_adult, guest_minor, price, tax
                    ):
                        reservation = create_or_update_reservation(
                            logement, user, start, end, guest_adult, guest_minor, price, tax
                        )
                        ip_address = get_client_ip(request)
                        accepted_at = timezone.now()
                        reservation.cgu_version = settings.CGU_VERSION
                        reservation.cgv_version = settings.CGV_VERSION
                        reservation.accepted_at = accepted_at
                        reservation.ip_address = ip_address
                        reservation.save()
                        session = create_stripe_checkout_session_with_deposit(reservation, request)
                        logger.info(f"Reservation created and Stripe session initialized for user {user}")
                        return redirect(session["checkout_session_url"])
                else:
                    messages.error(request, "Une erreur est survenue")
        else:
            start_date = request.GET.get("start")
            end_date = request.GET.get("end")
            guest_adult = request.GET.get("guest_adult", 1)
            guest_minor = request.GET.get("guest_minor", 0)
            form = LogementReservationForm(
                start_date=start_date,
                end_date=end_date,
                max_guests=logement.max_traveler,
                guest_adult=guest_adult,
                guest_minor=guest_minor,
            )
        return render(
            request,
            "reservation/book_logement.html",
            {
                "form": form,
                "logement": logement,
                "logement_data": logement_data,
                "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
                "reserved_dates_start_json": json.dumps(sorted(reserved_dates_start)),
                "reserved_dates_end_json": json.dumps(sorted(reserved_dates_end)),
                "photo_urls": [photo.image.url for photo in logement.photos.all()],
            },
        )
    except Exception as e:
        logger.exception(f"Booking failed: {e}")
        raise


@login_required
def book_activity(request: HttpRequest, pk: int) -> HttpResponse:
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
            form = ActivityReservationForm(request.POST)
            if form.is_valid():
                reservation_price = request.POST.get("reservation_price", None)
                start = form.cleaned_data["start"]
                guest = form.cleaned_data["guest"]
                slot = form.cleaned_data["slot_time"]
                if reservation_price is not None and start and guest > 0 and slot:
                    price = float(reservation_price)
                    slot = parse_time(slot)
                    if validate_activity_reservation_inputs(activity, user, start, guest, slot, price):
                        reservation = create_reservation(activity, user, start, slot, guest, price)
                        ip_address = get_client_ip(request)
                        accepted_at = timezone.now()
                        reservation.cgu_version = settings.CGU_VERSION
                        reservation.cgv_version = settings.CGV_VERSION
                        reservation.accepted_at = accepted_at
                        reservation.ip_address = ip_address
                        reservation.save()

                        session = create_stripe_checkout_session_with_manual_capture(reservation, request)
                        logger.info(f"Reservation created and Stripe session initialized for user {user}")
                        return redirect(session["checkout_session_url"])
                else:
                    messages.error(request, "Une erreur est survenue")
        else:
            start_date = request.GET.get("start")
            guest = request.GET.get("guest", 1)
            form = ActivityReservationForm(
                start_date=start_date,
                max_guests=activity.max_participants,
                guest=guest,
            )
        return render(
            request,
            "reservation/book_activity.html",
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


@login_required
def check_availability(request: HttpRequest, logement_id: int) -> JsonResponse:
    """
    Check if a logement is available for the given date range.
    """
    try:
        start_date = request.GET.get("start")
        end_date = request.GET.get("end")
        if not start_date or not end_date:
            return JsonResponse(
                {"available": False, "error": "Il manque la date de début ou de fin"},
                status=400,
            )
        user = request.user
        available = not is_period_booked(start_date, end_date, logement_id, user)
        return JsonResponse({"available": available})
    except Exception as e:
        logger.exception(f"Error checking availability: {e}")
        return JsonResponse({"error": "Erreur interne serveur"}, status=500)


@login_required
def check_logement_booking_input(request: HttpRequest, logement_id: int) -> JsonResponse:
    """
    Validate booking input fields for a logement.
    """
    try:
        start = parse_date(request.GET.get("start"))
        end = parse_date(request.GET.get("end"))
        guest_adult = int(request.GET.get("guest_adult"))
        guest_minor = int(request.GET.get("guest_minor"))
        logement = Logement.objects.get(id=logement_id)
        user = request.user
        if not start or not end or guest_adult + guest_minor <= 0:
            return JsonResponse({"correct": False})
        validate_logement_reservation_inputs(logement, user, start, end, guest_adult, guest_minor)
        return JsonResponse({"correct": True})
    except ValueError as e:
        return JsonResponse({"correct": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error validating booking input: {e}")
        return JsonResponse({"correct": False, "error": "Erreur interne serveur."}, status=500)


@login_required
def check_activity_booking_input(request: HttpRequest, activity_id: int) -> JsonResponse:
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
        validate_activity_reservation_inputs(activity, user, start, guest, slot)
        return JsonResponse({"correct": True})
    except ValueError as e:
        return JsonResponse({"correct": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error validating booking input: {e}")
        return JsonResponse({"correct": False, "error": "Erreur interne serveur."}, status=500)


@login_required
@user_has_reservation
def customer_cancel_logement_booking(request: HttpRequest, code: str) -> HttpResponse:
    """
    Cancel a booking and process refund if possible.
    """
    try:
        reservation = get_object_or_404(Reservation, code=code, user=request.user)
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
def customer_cancel_activity_booking(request: HttpRequest, code: str) -> HttpResponse:
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
@is_admin
def manage_logement_reservations(request: HttpRequest) -> HttpResponse:
    """
    Admin view to manage all reservations with search and pagination.
    """
    query = request.GET.get("q")
    reservations = Reservation.objects.select_related("logement", "user").exclude(statut="en_attente")
    if query:
        reservations = reservations.filter(code__icontains=query)
    reservations = reservations.order_by("-date_reservation")
    page_obj = paginate_queryset(reservations, request)
    context = {
        "reservations": page_obj,
        "query": query,
        "page_obj": page_obj,
    }
    return render(request, "reservation/manage_logement_reservations.html", context)


@login_required
@is_admin
def manage_activity_reservations(request: HttpRequest) -> HttpResponse:
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
    return render(request, "reservation/manage_activity_reservations.html", context)


@login_required
@user_is_reservation_admin
@require_POST
def cancel_logement_reservation(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin action to cancel a reservation.
    """
    reservation = get_object_or_404(Reservation, code=code)
    if reservation.statut != "annulee":
        mark_reservation_cancelled(reservation)
        messages.success(request, "Réservation annulée avec succès.")
    else:
        messages.warning(request, "La réservation est déjà annulée.")
    return redirect("reservation:logement_reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def cancel_activity_reservation(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin action to cancel a reservation.
    """
    reservation = get_object_or_404(ActivityReservation, code=code)
    if reservation.statut != "annulee":
        mark_reservation_cancelled(reservation)
        messages.success(request, "Réservation annulée avec succès.")
    else:
        messages.warning(request, "La réservation est déjà annulée.")
    return redirect("reservation:activity_reservation_detail", code=code)


@login_required
@user_is_reservation_admin
def logement_reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin view for reservation details.
    """
    reservation = get_object_or_404(Reservation, code=code)
    return render(request, "reservation/logement_reservation_detail.html", {"reservation": reservation})


@login_required
@user_is_reservation_admin
def activity_reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin view for reservation details.
    """
    reservation = get_object_or_404(ActivityReservation, code=code)
    return render(request, "reservation/activity_reservation_detail.html", {"reservation": reservation})


@login_required
@user_has_logement
def logement_reservation_dashboard(request: HttpRequest, logement_id: Optional[int] = None) -> HttpResponse:
    """
    Dashboard for logement owners/admins to view reservations with filters and pagination.
    """
    try:
        if not (request.user.is_admin or request.user.is_superuser):
            logements = get_logements(request.user)
            if not logements.exists():
                messages.info(request, "Vous devez ajouter un logement avant d’accéder au tableau des réservations")
                return redirect("logement:dashboard")
        year = request.GET.get("year")
        month = request.GET.get("month")
        status = request.GET.get("status", "all")
        search_query = request.GET.get("search")
        user = request.user
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
        if status and status != "all":
            reservations = reservations.filter(statut=status)
        if search_query:
            reservations = reservations.filter(
                Q(code__icontains=search_query)
                | Q(user__name__icontains=search_query)
                | Q(user__last_name__icontains=search_query)
            )
        page_obj = paginate_queryset(reservations, request)
        years, months = get_reservation_years_and_months(Reservation, "logement")
        return render(
            request,
            "reservation/logement_reservation_dashboard.html",
            {
                "reservations": page_obj,
                "available_years": years,
                "available_months": months,
                "current_year": year,
                "current_month": month,
                "search": search_query,
                "status": status,
                "page_obj": page_obj,
            },
        )
    except Exception as e:
        logger.error(f"Error in reservation_dashboard: {e}", exc_info=True)
        raise


@login_required
@user_has_activity
def activity_reservation_dashboard(request: HttpRequest, activity_id: Optional[int] = None) -> HttpResponse:
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
        user = request.user

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
        page_obj = paginate_queryset(reservations, request)

        # For year/month filter dropdowns
        years, months = get_reservation_years_and_months(ActivityReservation, "activity")

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
        return render(request, "reservation/activity_reservation_dashboard.html", context)
    except Exception as e:
        logger.error(f"Error in reservation_dashboard: {e}", exc_info=True)
        raise


@login_required
@user_is_reservation_customer
def customer_logement_reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Customer view for their own reservation details.
    """
    reservation = get_object_or_404(Reservation, code=code)
    return render(request, "reservation/customer_logement_reservation_detail.html", {"reservation": reservation})


@login_required
@user_is_reservation_customer
def customer_activity_reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Customer view for their own reservation details.
    """
    reservation = get_object_or_404(ActivityReservation, code=code)
    return render(request, "reservation/customer_activity_reservation_detail.html", {"reservation": reservation})


@login_required
@user_has_activity
def validate_activity_reservation(request, code):
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
    return redirect("reservation:activity_reservation_detail", code=reservation.code)


def activity_slots(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    day_str = request.GET.get("date")
    if not day_str:
        return JsonResponse({"slots": []})
    day = date.fromisoformat(day_str)
    slots = get_available_slots(activity, day)

    return JsonResponse({"slots": slots})


@require_GET
def activity_not_available_dates(request, pk):
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