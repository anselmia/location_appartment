from datetime import timedelta, date, datetime
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from .forms import ReservationForm
from .models import Logement, Reservation, airbnb_booking, booking_booking, Price

airbnb_calendar = "https://www.airbnb.fr/calendar/ical/48121442.ics?s=610867e1dc2cc14aba2f7b792ed5a4b1"


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

        reservations = Reservation.objects.filter(logement=logement, end__gte=today)
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
        },
    )


def book(request, logement_id):
    logement = Logement.objects.prefetch_related("photos").first()
    # Create form and pass the user and the dates in the form initialization

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
            # Handle form submission here
            return render(request, "logement/success.html", {"logement": logement_data})
    else:
        start_date = request.GET.get("start")
        end_date = request.GET.get("end")
        form = ReservationForm(
            user=request.user,
            start_date=start_date,
            end_date=end_date,
            max_guests=logement.max_traveler,
        )

    return render(
        request,
        "logement/book.html",
        {
            "form": form,
            "logement": logement_data,
            "photos": list(logement.photos.all()),
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

    if not start_date or not end_date:
        return JsonResponse(
            {"available": False, "error": "Missing start or end date"}, status=400
        )

    # Check if there are any reservations overlapping the selected dates
    reservations = Reservation.objects.filter(
        logement_id=logement_id,
        start__lt=end_date,
        end__gt=start_date,
        statut__in=["confirmee", "en_attente"],
    )

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
