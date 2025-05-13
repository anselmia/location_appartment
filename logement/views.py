from datetime import timedelta, date, datetime
import json
import stripe
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .forms import ReservationForm
from .models import Logement, Reservation, airbnb_booking, booking_booking, Price


# Set up Stripe with the secret key
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def home(request):
    logement = Logement.objects.prefetch_related("photos").first()

    if not logement:
        if request.user.is_authenticated and request.user.is_staff:
            return redirect("administration:dashboard")
        else:
            return render(
                request, "logement/no_logement.html"
            )  # Optional friendly page

    rooms = logement.rooms.all()

    # Fetch reserved dates for that logement
    reserved_dates = set()
    if logement:
        # Get today's date
        today = date.today()

        user = request.user

        reservations = Reservation.objects.filter(
            logement_id=logement.id, end__gte=today
        )

        if user.is_authenticated:
            reservations = reservations.filter(
                Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user))
            )
        else:
            reservations = reservations.filter(statut="confirmee")

        reservations_airbnb = airbnb_booking.objects.filter(
            logement=logement, end__gte=today
        )

        reservations_booking = booking_booking.objects.filter(
            logement=logement, end__gte=today
        )

        for r in reservations:
            current = r.start
            while current < r.end:
                reserved_dates.add(current.isoformat())
                current += timedelta(days=1)
        for r in reservations_airbnb:
            current = r.start
            while current < r.end:
                reserved_dates.add(current.isoformat())
                current += timedelta(days=1)
        for r in reservations_booking:
            current = r.start
            while current < r.end:
                reserved_dates.add(current.isoformat())
                current += timedelta(days=1)

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
    # Create form and pass the user and the dates in the form initialization

    # Fetch reserved dates for that logement
    reserved_dates = set()
    if logement:
        # Get today's date
        today = date.today()

        user = request.user
        reservations = Reservation.objects.filter(
            logement_id=logement_id, end__gte=today
        ).filter(Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user)))

        reservations_airbnb = airbnb_booking.objects.filter(
            logement=logement, end__gte=today
        )
        reservations_booking = booking_booking.objects.filter(
            logement=logement, end__gte=today
        )
        for r in reservations:
            current = r.start
            while current < r.end:
                reserved_dates.add(current.isoformat())
                current += timedelta(days=1)
        for r in reservations_airbnb:
            current = r.start
            while current < r.end:
                reserved_dates.add(current.isoformat())
                current += timedelta(days=1)
        for r in reservations_booking:
            current = r.start
            while current < r.end:
                reserved_dates.add(current.isoformat())
                current += timedelta(days=1)

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
            if reservation_price:
                price = float(reservation_price)

                reservation = Reservation.objects.filter(
                    logement_id=logement_id,
                    start=form.cleaned_data["start"],
                    end=form.cleaned_data["end"],
                    statut="en_attente",
                    user=user,
                ).first()

                if reservation:
                    reservation.start = form.cleaned_data["start"]
                    reservation.end = form.cleaned_data["end"]
                    reservation.guest = form.cleaned_data["guest"]
                    reservation.price = price
                    reservation.save()
                else:
                    reservation = Reservation(
                        logement=logement,
                        user=request.user,
                        guest=form.cleaned_data["guest"],
                        start=form.cleaned_data["start"],
                        end=form.cleaned_data["end"],
                        price=price,
                        statut="en_attente",  # Mark as pending until payment is successful
                    )
                    reservation.save()

                # Create the URLs based on the URL name
                success_url = reverse("logement:payment_success", args=[reservation.id])
                cancel_url = reverse("logement:payment_cancel", args=[reservation.id])

                # Build full URLs with request.build_absolute_uri
                success_url = request.build_absolute_uri(success_url)
                cancel_url = request.build_absolute_uri(cancel_url)

                # Create a Stripe session and pass reservation details
                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[
                        {
                            "price_data": {
                                "currency": "eur",
                                "product_data": {
                                    "name": f"Reservation for {logement.name}",
                                },
                                "unit_amount": int(
                                    reservation.price * 100
                                ),  # Convert to cents
                            },
                            "quantity": 1,
                        }
                    ],
                    mode="payment",
                    success_url=success_url,
                    cancel_url=cancel_url,
                    metadata={
                        "reservation_id": reservation.id
                    },  # Pass reservation ID in metadata
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


def check_availability(request, logement_id):
    start_date = request.GET.get("start")
    end_date = request.GET.get("end")
    reservation_id = request.GET.get(
        "reservation_id", None
    )  # Get the reservation_id if available

    if not start_date or not end_date:
        return JsonResponse(
            {"available": False, "error": "Missing start or end date"}, status=400
        )

    # Check if there are any reservations overlapping the selected dates
    if reservation_id:
        reservations = Reservation.objects.exclude(id=reservation_id).filter(
            logement_id=logement_id,
            start__lt=end_date,
            end__gt=start_date,
            statut__in=["confirmee", "en_attente"],
        )
    else:
        user = request.user
        reservations = Reservation.objects.filter(
            logement_id=logement_id, start__lt=end_date, end__gt=start_date
        ).filter(Q(statut="confirmee") | (Q(statut="en_attente") & ~Q(user=user)))

    airbnb_reservations = airbnb_booking.objects.filter(
        logement_id=logement_id,
        start__lt=end_date,
        end__gt=start_date,
    )

    booking_reservations = booking_booking.objects.filter(
        logement_id=logement_id,
        start__lt=end_date,
        end__gt=start_date,
    )

    if reservations.exists():
        return JsonResponse({"available": False})

    if airbnb_reservations.exists():
        return JsonResponse({"available": False})

    if booking_reservations.exists():
        return JsonResponse({"available": False})

    return JsonResponse({"available": True})


def create_checkout_session(request):
    if request.method == "POST":
        # Retrieve the reservation ID from the form data
        reservation_id = request.POST.get("reservation_id")
        reservation = Reservation.objects.get(id=reservation_id)

        # Create the URLs based on the URL name
        success_url = reverse("logement:payment_success", args=[reservation.id])
        cancel_url = reverse("logement:payment_cancel", args=[reservation.id])

        # Build full URLs with request.build_absolute_uri
        success_url = request.build_absolute_uri(success_url)
        cancel_url = request.build_absolute_uri(cancel_url)

        # Create a Stripe Checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card", "google_pay", "apple_pay"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",  # Change to your currency
                        "product_data": {
                            "name": f"Reservation for {reservation.logement.name}",
                        },
                        "unit_amount": int(
                            reservation.total_price * 100
                        ),  # Convert to cents
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"reservation_id": reservation_id},
        )

        return JsonResponse({"id": checkout_session.id})


def payment_success(request, reservation_id):
    reservation = Reservation.objects.get(id=reservation_id)
    reservation.status = "confirmee"
    reservation.save()

    return render(
        request, "logement/payment_success.html", {"reservation": reservation}
    )


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
