import time
import stripe
import json
import logging

from datetime import datetime
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils.dateparse import parse_date
from .forms import ReservationForm
from .models import Logement, Reservation, Price, City, Equipment, EquipmentType
from logement.services.reservation_service import (
    is_period_booked,
    get_booked_dates,
    create_or_update_reservation,
    validate_reservation_inputs,
    cancel_and_refund_reservation,
)
from logement.services.logement import filter_logements

from logement.services.calendar_service import generate_ical
from logement.services.payment_service import create_stripe_checkout_session_with_deposit, PAYMENT_FEE_VARIABLE
from administration.models import HomePageConfig
from accounts.forms import ContactForm
from collections import defaultdict
from common.services.stripe.stripe_webhook import handle_stripe_webhook_request
from common.decorators import user_has_reservation


logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def home(request):
    logger.info("Rendering homepage")
    try:
        config = HomePageConfig.objects.prefetch_related("services", "testimonials", "commitments").first()
        logements = Logement.objects.prefetch_related("photos").filter(statut="open")

        initial_data = {
            "name": (request.user.get_full_name() if request.user.is_authenticated else ""),
            "email": request.user.email if request.user.is_authenticated else "",
        }

        contact_form = ContactForm(**initial_data)

        return render(
            request,
            "logement/home.html",
            {
                "logements": logements,
                "config": config,
                "contact_form": contact_form,
            },
        )
    except Exception as e:
        logger.exception(f"Error rendering homepage: {e}")
        return HttpResponse("Erreur interne du serveur", status=500)


def autocomplete_cities(request):
    q = request.GET.get("q", "")
    try:
        cities = City.objects.filter(name__icontains=q).order_by("name")[:5]
        logger.info(f"Autocomplete for query '{q}', {cities.count()} results")
        return HttpResponse("".join(f"<option value='{c.name}'></option>" for c in cities))
    except Exception as e:
        logger.exception(f"Autocomplete city search failed: {e}")


def view_logement(request, logement_id):
    try:
        logement = get_object_or_404(Logement.objects.prefetch_related("photos"), id=logement_id)
        rooms = logement.rooms.all()
        user = request.user

        grouped_equipment = defaultdict(list)
        for equip in logement.equipment.all():
            grouped_equipment[equip.type].append(equip)

        reserved_dates_start, reserved_dates_end = get_booked_dates(logement, user)

        logger.info(f"Viewing logement ID {logement_id}")

        return render(
            request,
            "logement/view_logement.html",
            {
                "logement": logement,
                "rooms": rooms,
                "reserved_dates_start_json": json.dumps(sorted(reserved_dates_start)),
                "reserved_dates_end_json": json.dumps(sorted(reserved_dates_end)),
                "photo_urls": [photo.image.url for photo in logement.photos.all()],
                "grouped_equipment": grouped_equipment,
                "EquipmentType": EquipmentType,
                "payment_fee": PAYMENT_FEE_VARIABLE * 100,
            },
        )
    except Exception as e:
        logger.exception(f"Error loading logement detail: {e}")


@login_required
def book(request, logement_id):
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
        }

        if request.method == "POST":
            form = ReservationForm(request.POST)
            if form.is_valid():
                reservation_price = request.POST.get("reservation_price")
                reservation_tax = request.POST.get("reservation_tax")
                start = form.cleaned_data["start"]
                end = form.cleaned_data["end"]
                guest = form.cleaned_data["guest"]

                if reservation_price and reservation_tax and start and end and guest:
                    price = float(reservation_price)
                    tax = float(reservation_tax)

                    if validate_reservation_inputs(logement, user, start, end, guest, price, tax):
                        reservation = create_or_update_reservation(logement, user, start, end, guest, price, tax)
                        session = create_stripe_checkout_session_with_deposit(reservation, request)
                        logger.info(f"Reservation created and Stripe session initialized for user {user}")
                        return redirect(session["checkout_session_url"])
                else:
                    messages.error(request, "Une erreur est survenue")
        else:
            start_date = request.GET.get("start")
            end_date = request.GET.get("end")
            guest = request.GET.get("guest", 1)
            form = ReservationForm(
                start_date=start_date,
                end_date=end_date,
                max_guests=logement.max_traveler,
                guest=guest,
            )

        return render(
            request,
            "logement/book.html",
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


@login_required
def get_price_for_date(request, logement_id, date):
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        logement = Logement.objects.get(id=logement_id)
        price = Price.objects.filter(logement=logement, date=parsed_date).first()
        logger.info(f"Price requested for logement {logement_id} on {date}")
        return JsonResponse({"price": str(price.value) if price else str(logement.price)})
    except Logement.DoesNotExist:
        logger.warning(f"Logement {logement_id} not found")
        return JsonResponse({"error": "Logement not found"}, status=404)
    except Exception as e:
        logger.exception(f"Failed to fetch price for date: {e}")
        return JsonResponse({"error": "Erreur interne serveur"}, status=500)


@login_required
def check_availability(request, logement_id):
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
def check_booking_input(request, logement_id):
    try:
        start = parse_date(request.GET.get("start"))
        end = parse_date(request.GET.get("end"))
        guest = int(request.GET.get("guest"))
        logement = Logement.objects.get(id=logement_id)
        user = request.user

        if not start or not end or guest <= 0:
            return JsonResponse({"correct": False})

        validate_reservation_inputs(logement, user, start, end, guest)
        return JsonResponse({"correct": True})
    except ValueError as e:
        return JsonResponse({"correct": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error validating booking input: {e}")
        return JsonResponse({"correct": False, "error": "Erreur interne serveur."}, status=500)


@login_required
@user_has_reservation
def payment_success(request, code):
    try:
        reservation = Reservation.objects.get(code=code)

        # Wait up to 3 seconds for the reservation to be confirmed
        max_wait = 3  # seconds
        interval = 0.5  # seconds
        waited = 0

        while reservation.statut != "confirmee" and waited < max_wait:
            time.sleep(interval)
            waited += interval
            reservation.refresh_from_db()

        if reservation.statut != "confirmee":
            messages.warning(
                request,
                "Votre paiement semble incomplet ou non encore confirmé. Veuillez vérifier plus tard ou contacter l’assistance.",
            )
        return render(request, "logement/payment_success.html", {"reservation": reservation})
    except Reservation.DoesNotExist:
        messages.error(request, f"Réservation {code} introuvable.")
        return redirect("logement:book", logement_id=1)
    except Exception as e:
        logger.exception(f"Error handling payment success: {e}")


@login_required
@user_has_reservation
def payment_cancel(request, code):
    try:
        reservation = get_object_or_404(Reservation, code=code)
        logement = Logement.objects.prefetch_related("photos").first()
        messages.info(
            request,
            "Votre paiement a été annulé. Vous pouvez modifier ou reprogrammer votre réservation.",
        )
        query_params = urlencode(
            {
                "start": reservation.start.isoformat(),
                "end": reservation.end.isoformat(),
                "guest": reservation.guest,
                "code": reservation.code,
            }
        )
        return redirect(f"{reverse('logement:book', args=[logement.id])}?{query_params}")
    except Exception as e:
        logger.exception(f"Error handling payment cancellation: {e}")
        messages.error(request, "Une erreur est survenue.")
        return redirect("logement:home")


@login_required
@user_has_reservation
def cancel_booking(request, code):
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


def export_ical(request, code):
    try:
        ics_content = generate_ical(code)
        if ics_content:
            response = HttpResponse(ics_content, content_type="text/calendar")
            response["Content-Disposition"] = "attachment; filename=valrose_calendar.ics"
            return response
        else:
            return HttpResponse("Aucune donnée à exporter", status=204)
    except Exception as e:
        logger.exception(f"Error exporting iCal:  {e}")


@csrf_exempt
def stripe_webhook(request):
    handle_stripe_webhook_request(request)
    return HttpResponse(status=200)


def logement_search(request):
    try:
        number_range = [1, 2, 3, 4, 5]
        equipment_names = [
            "Piscine",
            "Parking gratuit sur place",
            "Garage",
            "Climatisation",
            "Chauffage",
            "Terasse ou balcon",
            "Télévision",
            "Wifi",
            "Machine à laver",
            "Lave-vaisselle",
            "Four à micro-ondes",
            "Four",
            "Accès mobilité réduite",
        ]
        equipments = Equipment.objects.filter(name__in=equipment_names)
        raw_types = Logement.objects.values_list("type", flat=True).distinct()
        type_display_map = dict(Logement._meta.get_field("type").choices)
        types = [(val, type_display_map.get(val, val)) for val in raw_types]

        page_obj, equipment_ids, guests, type = filter_logements(request)

        selected_equipment_ids = [str(eid) for eid in equipment_ids]
        guests = int(guests) if guests and str(guests).isdigit() else 1

        logger.info(f"Search returned {page_obj.paginator.count} logements")

        return render(
            request,
            "logement/search_results.html",
            {
                "logements": page_obj,
                "equipments": equipments,
                "destination": request.GET.get("destination", ""),
                "guests": guests,
                "page_obj": page_obj,
                "selected_equipment_ids": selected_equipment_ids,
                "number_range": number_range,
                "types": types,
                "selected_type": type,
            },
        )
    except Exception as e:
        logger.exception(f"Error in logement search: {e}")
