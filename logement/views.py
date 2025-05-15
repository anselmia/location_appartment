from datetime import datetime
import json

import logging
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.http import HttpResponse
from .forms import ReservationForm
from .models import Logement, Reservation, Price
from services.reservation_service import (
    is_period_booked,
    get_booked_dates,
    create_or_update_reservation,
)
from services.calendar_service import generate_ical
from services.payment_service import create_stripe_checkout_session


logger = logging.getLogger(__name__)


def home(request):
    logement = Logement.objects.prefetch_related("photos").first()
    rooms = logement.rooms.all()
    user = request.user

    if not logement:
        logger.warning("Aucun logement configuré – redirection selon l'utilisateur")
        if request.user.is_authenticated and request.user.is_staff:
            return redirect("administration:dashboard")
        else:
            return render(
                request, "logement/no_logement.html"
            )  # Optional friendly page

    # Fetch reserved dates for that logement
    reserved_dates = get_booked_dates(logement, user)

    return render(
        request,
        "logement/home.html",
        {
            "logement": logement,
            "rooms": rooms,
            "reserved_dates_json": json.dumps(sorted(reserved_dates)),
            "photo_urls": [photo.image.url for photo in logement.photos.all()],
        },
    )


@login_required
def book(request, logement_id):
    logement = Logement.objects.prefetch_related("photos").first()
    user = request.user

    # Fetch reserved dates for that logement
    reserved_dates = get_booked_dates(logement, user)

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
            start = form.cleaned_data["start"]
            end = form.cleaned_data["end"]
            guest = form.cleaned_data["guest"]

            if reservation_price and start and end and guest:
                price = float(reservation_price)
                reservation = create_or_update_reservation(
                    logement, user, start, end, guest, price
                )

                # Create the URLs based on the URL name
                success_url = reverse("logement:payment_success", args=[reservation.id])
                cancel_url = reverse("logement:payment_cancel", args=[reservation.id])

                # Build full URLs with request.build_absolute_uri
                success_url = request.build_absolute_uri(success_url)
                cancel_url = request.build_absolute_uri(cancel_url)

                # Create a Stripe session and pass reservation details
                session = create_stripe_checkout_session(
                    reservation, success_url, cancel_url
                )

                return redirect(session.url)
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
            "reserved_dates_json": json.dumps(sorted(reserved_dates)),
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
def payment_success(request, reservation_id):
    reservation = Reservation.objects.get(id=reservation_id)
    reservation.status = "confirmee"
    reservation.save()

    return render(
        request, "logement/payment_success.html", {"reservation": reservation}
    )


@login_required
def payment_cancel(request, reservation_id):
    try:
        # Fetch the reservation object by ID
        reservation = get_object_or_404(Reservation, id=reservation_id)
        logement = Logement.objects.prefetch_related("photos").first()
        # Create form and pass the user and the dates in the form initialization

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
        # If the reservation does not exist, redirect to the home page
        return redirect("logement:home")


@login_required
def cancel_booking(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id, user=request.user)

    if reservation.start <= timezone.now().date():
        messages.error(
            request,
            "❌ Vous ne pouvez pas annuler une réservation déjà commencée ou passée.",
        )
    else:
        reservation.delete()
        messages.success(request, "✅ Réservation annulée avec succès.")

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
