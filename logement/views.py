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
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.db.models import Count, Q
from .forms import ReservationForm
from .models import Logement, Reservation, Price, City, Equipment, EquipmentType
from logement.services.reservation_service import (
    is_period_booked,
    get_booked_dates,
    create_or_update_reservation,
    validate_reservation_inputs,
    cancel_and_refund_reservation,    
    get_available_logement_in_period,
)

from logement.services.calendar_service import generate_ical
from logement.services.payment_service import (
    create_stripe_checkout_session_with_deposit,
    handle_charge_refunded,
    handle_payment_failed,
    handle_payment_intent_succeeded,
    handle_checkout_session_completed,
)
from administration.models import HomePageConfig
from accounts.forms import ContactForm
from collections import defaultdict


logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def home(request):
    config = HomePageConfig.objects.prefetch_related(
        "services", "testimonials", "commitments"
    ).first()

    logements = Logement.objects.prefetch_related("photos").filter(statut="open")

    initial_data = {
        "name": request.user.get_full_name() if request.user.is_authenticated else "",
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


def autocomplete_cities(request):
    q = request.GET.get("q", "")
    cities = City.objects.filter(name__icontains=q).order_by("name")[:5]
    return HttpResponse("".join(f"<option value='{c.name}'></option>" for c in cities))


def view_logement(request, logement_id):
    logement = get_object_or_404(
        Logement.objects.prefetch_related("photos"), id=logement_id
    )
    rooms = logement.rooms.all()
    user = request.user

    grouped_equipment = defaultdict(list)
    for equip in logement.equipment.all():
        grouped_equipment[equip.type].append(equip)

    if not logement:
        logger.warning("Aucun logement configuré – redirection selon l'utilisateur")
        if request.user.is_authenticated and request.user.is_staff:
            return redirect("administration:dashboard")
        else:
            return render(
                request, "logement/no_logement.html"
            )  # Optional friendly page

    # Fetch reserved dates for that logement
    reserved_dates_start, reserved_dates_end = get_booked_dates(logement, user)

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
        },
    )


@login_required
def book(request, logement_id):
    logement = get_object_or_404(
        Logement.objects.prefetch_related("photos"), id=logement_id
    )
    user = request.user

    # Fetch reserved dates for that logement
    reserved_dates_start, reserved_dates_end = get_booked_dates(logement, user)

    logement_data = {
        "id": logement.id,
        "name": logement.name,
        "description": logement.description,
        "price": str(logement.price),  # Ensure the price is converted to a string
        "max_traveler": logement.max_traveler,
        "nominal_traveler": logement.nominal_traveler,
        "fee_per_extra_traveler": str(logement.fee_per_extra_traveler),
        "cleaning_fee": str(logement.cleaning_fee),
        "tax": str(logement.tax),
    }

    if request.method == "POST":
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation_price = request.POST.get("reservation_price", None)
            reservation_tax = request.POST.get("reservation_tax", None)
            start = form.cleaned_data["start"]
            end = form.cleaned_data["end"]
            guest = form.cleaned_data["guest"]

            if reservation_price and reservation_tax and start and end and guest:
                price = float(reservation_price)
                tax = float(reservation_tax)

                if validate_reservation_inputs(
                    logement, user, start, end, guest, price, tax
                ):
                    reservation = create_or_update_reservation(
                        logement, user, start, end, guest, price, tax
                    )

                    # Create the URLs based on the URL name
                    success_url = reverse(
                        "logement:payment_success", args=[reservation.id]
                    )
                    cancel_url = reverse(
                        "logement:payment_cancel", args=[reservation.id]
                    )

                    # Build full URLs with request.build_absolute_uri
                    success_url = request.build_absolute_uri(success_url)
                    cancel_url = request.build_absolute_uri(cancel_url)

                    # Create a Stripe session and pass reservation details
                    session = create_stripe_checkout_session_with_deposit(
                        reservation, success_url, cancel_url
                    )

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
            "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,  # Pass the public key to the template
            "reserved_dates_start_json": json.dumps(sorted(reserved_dates_start)),
            "reserved_dates_end_json": json.dumps(sorted(reserved_dates_end)),
            "photo_urls": [photo.image.url for photo in logement.photos.all()],
        },
    )


@login_required
def get_price_for_date(request, logement_id, date):
    try:
        # Parse the date from the request
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()

        # Fetch the logement
        logement = Logement.objects.get(id=logement_id)

        # Try to get the price for the date from the Price model
        price = Price.objects.filter(logement=logement, date=parsed_date).first()

        # If price is found, return it; otherwise, use the default price
        if price:
            return JsonResponse({"price": str(price.value)})
        else:
            return JsonResponse({"price": str(logement.price)})

    except Logement.DoesNotExist:
        return JsonResponse({"error": "Logement not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def check_availability(request, logement_id):
    start_date = request.GET.get("start")
    end_date = request.GET.get("end")

    if not start_date or not end_date:
        return JsonResponse(
            {"available": False, "error": "Il manque la date de début ou de fin"},
            status=400,
        )

    # Check if there are any reservations overlapping the selected dates
    user = request.user

    if is_period_booked(start_date, end_date, logement_id, user):
        return JsonResponse({"available": False})
    else:
        return JsonResponse({"available": True})


@login_required
def check_booking_input(request, logement_id):
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    guest_str = request.GET.get("guest")

    try:
        # Quick validation
        start = parse_date(start_str)
        end = parse_date(end_str)
        guest = int(guest_str)
        # Fetch the logement
        logement = Logement.objects.get(id=logement_id)
        user = request.user

        if not logement:
            return JsonResponse({"correct": False})

        if not start or not end:
            return JsonResponse({"correct": False})

        if guest <= 0:
            return JsonResponse({"correct": False})

        validate_reservation_inputs(logement, user, start, end, guest)

        return JsonResponse({"correct": True})
    except ValueError as e:
        return JsonResponse({"correct": False, "error": str(e)})
    except Exception:
        return JsonResponse(
            {"correct": False, "error": "Erreur interne serveur."}, status=500
        )


@login_required
def payment_success(request, reservation_id):
    try:
        time.sleep(1)
        reservation = Reservation.objects.get(id=reservation_id)

        if reservation.statut != "confirmee":
            messages.warning(
                request,
                "Votre paiement semble incomplet ou non encore confirmé. Veuillez vérifier plus tard ou contacter l’assistance.",
            )

        return render(
            request, "logement/payment_success.html", {"reservation": reservation}
        )

    except Reservation.DoesNotExist:
        messages.error(request, "Réservation introuvable.")
        return redirect("logement:book", logement_id=1)


@login_required
def payment_cancel(request, reservation_id):
    try:
        # Fetch the reservation object by ID
        reservation = get_object_or_404(Reservation, id=reservation_id)
        logement = Logement.objects.prefetch_related("photos").first()

        # Show a user-friendly message
        messages.info(
            request,
            "Votre paiement a été annulé. Vous pouvez modifier ou reprogrammer votre réservation.",
        )

        # Prepare query string to prefill the form
        query_params = urlencode(
            {
                "start": reservation.start.isoformat(),
                "end": reservation.end.isoformat(),
                "guest": reservation.guest,
                "reservation_id": reservation.id,
            }
        )

        return redirect(
            f"{reverse('logement:book', args=[logement.id])}?{query_params}"
        )

    except Reservation.DoesNotExist:
        # Show a user-friendly message
        messages.error(
            request,
            "Une erreur est survenue.",
        )
        # If the reservation does not exist, redirect to the home page
        return redirect("logement:home")


@login_required
def cancel_booking(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id, user=request.user)

    success_message, error_message = cancel_and_refund_reservation(reservation)

    if success_message:
        messages.success(request, success_message)
    if error_message:
        messages.error(request, error_message)

    return redirect("accounts:dashboard")


def export_ical(request):
    try:
        ics_content = generate_ical()
        if ics_content:
            response = HttpResponse(ics_content, content_type="text/calendar")
            response["Content-Disposition"] = (
                "attachment; filename=valrose_calendar.ics"
            )

            return response

    except Exception:
        return HttpResponse("Erreur interne serveur", status=500)


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        logger.error(f"❌ Stripe webhook signature error: {e}")
        return HttpResponse(status=400)

    try:
        event_type = event["type"]
        data = event["data"]["object"]

        logger.info(f"📩 Received Stripe event: {event_type}")

        if event_type == "checkout.session.completed":
            handle_checkout_session_completed(data)
        elif event_type == "charge.refunded":
            handle_charge_refunded(data)
        elif event_type == "payment_intent.payment_failed":
            handle_payment_failed(data)
        elif event_type == "payment_intent.succeeded":
            handle_payment_intent_succeeded(data)
        else:
            logger.info(f"ℹ️ Unhandled Stripe event type: {event_type}")

    except Exception as e:
        logger.exception(f"❌ Error while handling event {event_type}: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)


def logement_search(request):
    page_number = request.GET.get("page", 1)
    destination = request.GET.get("destination", "").strip()
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    guests = request.GET.get("guests")
    equipment_ids = request.GET.getlist("equipments")
    bedrooms = request.GET.get("bedrooms")
    bathrooms = request.GET.get("bathrooms")
    smoking = request.GET.get("is_smoking_allowed") == "1"
    animals = request.GET.get("is_pets_allowed") == "1"
    type = request.GET.get("type")

    number_range = [1, 2, 3, 4, 5]

    logements = Logement.objects.prefetch_related("photos").filter(statut="open")
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

    # Map to display names using choices
    type_display_map = dict(Logement._meta.get_field("type").choices)
    types = [(val, type_display_map.get(val, val)) for val in raw_types]

    if destination:
        logements = logements.filter(ville__name__icontains=destination)

    if guests:
        logements = logements.filter(max_traveler__gte=int(guests))

    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

        logements = get_available_logement_in_period(start, end, logements)

    if equipment_ids:
        # Convert to ints for safety
        equipment_ids = [int(eid) for eid in equipment_ids]

        logements = logements.annotate(
            matched_equipment_count=Count(
                "equipment", filter=Q(equipment__id__in=equipment_ids), distinct=True
            )
        ).filter(matched_equipment_count=len(equipment_ids))

    if bedrooms:
        logements = logements.filter(bedrooms__gte=int(bedrooms))

    if bathrooms:
        logements = logements.filter(bathrooms__gte=int(bathrooms))

    if smoking:
        logements = logements.filter(smoking=True)

    if animals:
        logements = logements.filter(animals=True)

    if type:
        logements = logements.filter(type=type)

    paginator = Paginator(logements, 9) 
    page_obj = paginator.get_page(page_number)

    selected_equipment_ids = [str(eid) for eid in equipment_ids]
    guests = int(guests) if guests and guests.isdigit() else 1

    return render(
        request,
        "logement/search_results.html",
        {
            "logements": page_obj,
            "equipments": equipments,
            "destination": destination,
            "guests": guests,
            "page_obj": page_obj,
            "selected_equipment_ids": selected_equipment_ids,
            "number_range": number_range,
            "types": types,
            "selected_type": type,
        },
    )
