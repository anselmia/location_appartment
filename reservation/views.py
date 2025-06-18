import json
import logging
from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, Page
from django.db.models import Q, QuerySet

from reservation.forms import ReservationForm
from reservation.models import Reservation
from reservation.decorators import (
    user_has_reservation,
    user_is_reservation_admin,
    user_is_reservation_customer,
)
from reservation.services.reservation_service import (
    is_period_booked,
    get_booked_dates,
    create_or_update_reservation,
    validate_reservation_inputs,
    cancel_and_refund_reservation,
    get_valid_reservations_for_admin,
    get_reservation_years_and_months,
    mark_reservation_cancelled,
)
from payment.services.payment_service import create_stripe_checkout_session_with_deposit, PAYMENT_FEE_VARIABLE
from logement.models import Logement
from logement.decorators import user_has_logement
from logement.services.logement_service import get_logements
from common.decorators import is_admin

logger = logging.getLogger(__name__)


def paginate_queryset(queryset: QuerySet, request: HttpRequest, per_page: int = 20) -> Page:
    """
    Paginate a queryset for the given request.
    """
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


@login_required
def book(request: HttpRequest, logement_id: int) -> HttpResponse:
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
            form = ReservationForm(request.POST)
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
                    if validate_reservation_inputs(logement, user, start, end, guest_adult, guest_minor, price, tax):
                        reservation = create_or_update_reservation(
                            logement, user, start, end, guest_adult, guest_minor, price, tax
                        )
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
            form = ReservationForm(
                start_date=start_date,
                end_date=end_date,
                max_guests=logement.max_traveler,
                guest_adult=guest_adult,
                guest_minor=guest_minor,
            )
        return render(
            request,
            "reservation/book.html",
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
def check_booking_input(request: HttpRequest, logement_id: int) -> JsonResponse:
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
        validate_reservation_inputs(logement, user, start, end, guest_adult, guest_minor)
        return JsonResponse({"correct": True})
    except ValueError as e:
        return JsonResponse({"correct": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error validating booking input: {e}")
        return JsonResponse({"correct": False, "error": "Erreur interne serveur."}, status=500)


@login_required
@user_has_reservation
def cancel_booking(request: HttpRequest, code: str) -> HttpResponse:
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
@is_admin
def manage_reservations(request: HttpRequest) -> HttpResponse:
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
    return render(request, "reservation/manage_reservations.html", context)


@login_required
@user_is_reservation_admin
@require_POST
def cancel_reservation(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin action to cancel a reservation.
    """
    reservation = get_object_or_404(Reservation, code=code)
    if reservation.statut != "annulee":
        mark_reservation_cancelled(reservation)
        messages.success(request, "Réservation annulée avec succès.")
    else:
        messages.warning(request, "La réservation est déjà annulée.")
    return redirect("reservation:reservation_detail", code=code)


@login_required
@user_is_reservation_admin
def reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Admin view for reservation details.
    """
    reservation = get_object_or_404(Reservation, code=code)
    return render(request, "reservation/reservation_detail.html", {"reservation": reservation})


@login_required
@user_has_logement
def reservation_dashboard(request: HttpRequest, logement_id: Optional[int] = None) -> HttpResponse:
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
        reservations = get_valid_reservations_for_admin(
            user=request.user,
            logement_id=logement_id,
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
        years, months = get_reservation_years_and_months()
        return render(
            request,
            "reservation/reservations.html",
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
@user_is_reservation_customer
def customer_reservation_detail(request: HttpRequest, code: str) -> HttpResponse:
    """
    Customer view for their own reservation details.
    """
    reservation = get_object_or_404(Reservation, code=code)
    return render(request, "reservation/customer_reservation_detail.html", {"reservation": reservation})
