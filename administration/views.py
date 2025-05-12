from datetime import datetime, timedelta, date
import json
from django.utils.dateformat import format as date_format
from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from logement.models import Logement, Room, Photo, Price, Reservation, booking_booking, airbnb_booking
from .forms import LogementForm
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.db.models import Count
from .models import SiteVisit
from .serializers import DailyPriceSerializer
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action


def is_admin(user):
    return user.is_authenticated and user.is_admin  # or use a custom flag


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    logements = Logement.objects.all()
    return render(request, "administration/dashboard.html", {"logements": logements})


@login_required
@user_passes_test(is_admin)
def add_logement(request):
    if request.method == "POST":
        form = LogementForm(request.POST)
        if form.is_valid():
            logement = form.save()
            return redirect("administration:edit_logement", logement.id)
    else:
        form = LogementForm()
    return render(request, "administration/add_logement.html", {"form": form})


@login_required
@user_passes_test(is_admin)
def edit_logement(request, logement_id):
    logement = Logement.objects.prefetch_related("photos").first()
    rooms = logement.rooms.all().order_by("name")
    photos = logement.photos.all().order_by("order")

    if request.method == "POST":
        form = LogementForm(request.POST, instance=logement)
        if form.is_valid():
            form.save()
    else:
        form = LogementForm(instance=logement)

    return render(
        request,
        "administration/edit_logement.html",
        {"form": form, "logement": logement, "rooms": rooms, "photos": photos},
    )


@login_required
@user_passes_test(is_admin)
def add_room(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    Room.objects.create(name=request.POST["name"], logement=logement)
    return redirect("administration:edit_logement", logement_id)


@login_required
@user_passes_test(is_admin)
@require_POST
def delete_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    logement_id = room.logement.id
    room.delete()
    return redirect("administration:edit_logement", logement_id)


@login_required
@user_passes_test(is_admin)
@require_POST
def upload_photos(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    room_id = request.POST.get("room_id")
    room = (
        Room.objects.filter(id=room_id, logement=logement).first() if room_id else None
    )

    for uploaded_file in request.FILES.getlist("photo"):
        Photo.objects.create(logement=logement, room=room, image=uploaded_file)
    return redirect("administration:edit_logement", logement_id)


# Change the room of a photo
@login_required
@user_passes_test(is_admin)
@require_POST
def change_photo_room(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id)
    room_id = request.POST.get("room_id")
    if room_id:
        room = Room.objects.filter(id=room_id).first()
        if room:
            photo.room = room
            photo.save()
            return JsonResponse({"success": True})
    return JsonResponse({"success": False}, status=400)


# Move photo up or down
@login_required
@user_passes_test(is_admin)
@require_POST
def move_photo(request, photo_id, direction):
    photo = get_object_or_404(Photo, id=photo_id)
    if direction == "up":
        previous_photo = (
            Photo.objects.filter(logement=photo.logement, order__lt=photo.order)
            .order_by("-order")
            .first()
        )
        if previous_photo:
            photo.order, previous_photo.order = previous_photo.order, photo.order
            photo.save()
            previous_photo.save()
    elif direction == "down":
        next_photo = (
            Photo.objects.filter(logement=photo.logement, order__lt=photo.order)
            .order_by("order")
            .first()
        )
        if next_photo:
            photo.order, next_photo.order = next_photo.order, photo.order
            photo.save()
            next_photo.save()
    return JsonResponse({"success": True})


# Delete photo
@login_required
@user_passes_test(is_admin)
def delete_photo(request, photo_id):
    if request.method == "DELETE":
        photo = get_object_or_404(Photo, id=photo_id)
        photo.delete()
        return JsonResponse({"success": True})


@login_required
@user_passes_test(is_admin)
def traffic_dashboard(request):
    period = request.GET.get("period", "day")  # day, week, month
    now = datetime.now()
    since = now - timedelta(days=30)

    if period == "week":
        truncate = TruncWeek("timestamp")
    elif period == "month":
        truncate = TruncMonth("timestamp")
    else:
        truncate = TruncDay("timestamp")

    visits_qs = (
        SiteVisit.objects.filter(timestamp__gte=since)
        .annotate(period=truncate)
        .values("period")
        .annotate(count=Count("id"))
        .order_by("period")
    )

    labels = [v["period"].isoformat() for v in visits_qs]  # or strftime("%Y-%m-%d")
    data = [v["count"] for v in visits_qs]

    total_visits = SiteVisit.objects.filter(timestamp__gte=since).count()
    unique_visitors = (
        SiteVisit.objects.filter(timestamp__gte=since)
        .values("ip_address")
        .distinct()
        .count()
    )

    recent_logs = SiteVisit.objects.order_by("-timestamp")[:20]

    context = {
        "labels": json.dumps(labels),
        "data": json.dumps(data),
        "total_visits": total_visits,
        "unique_visitors": unique_visitors,
        "recent_logs": recent_logs,
        "selected_period": period,
    }
    return render(request, "administration/traffic.html", context)


@login_required
@user_passes_test(is_admin)
def calendar(request):
    logement = Logement.objects.prefetch_related("photos").first()
    return render(request, "administration/calendar.html", {"logement": logement})


class DailyPriceViewSet(viewsets.ModelViewSet):
    serializer_class = DailyPriceSerializer

    def get_queryset(self):
        # DRF still needs this for retrieve/update/etc.
        logement_id = self.request.query_params.get("logement_id")
        return Price.objects.filter(logement_id=logement_id)

    def list(self, request, *args, **kwargs):
        logement_id = request.query_params.get("logement_id")
        start_str = request.query_params.get("start")
        end_str = request.query_params.get("end")

        if not logement_id:
            return Response({"error": "Missing logement_id"}, status=400)

        logement = Logement.objects.get(id=logement_id)
        default_price = logement.price

        start = datetime.fromisoformat(start_str).date()
        end = datetime.fromisoformat(end_str).date()

        # Get custom prices in range
        custom_prices = Price.objects.filter(
            logement_id=logement_id, date__range=(start, end)
        )
        price_map = {p.date: p.value for p in custom_prices}

        daily_prices = []
        for i in range((end - start).days + 1):
            day = start + timedelta(days=i)
            daily_prices.append({
                "date": day.isoformat(),
                "value": price_map.get(day, str(default_price)),
            })

        # Bookings in range
        bookings = Reservation.objects.filter(
            logement_id=logement_id,
            start__lte=end,
            end__gte=start
        )

        data_bookings = []
        for b in bookings:
            data_bookings.append({
                "start": b.start.isoformat(),
                "end": b.end.isoformat(),  # FullCalendar exclusive
                "name": b.user.name,
                "guests": b.guest,
                "total_price": str(b.price),
            })

        bookings = airbnb_booking.objects.filter(
            logement_id=logement_id,
            start__lte=end,
            end__gte=start
        )

        airbnb_bookings = []
        for b in bookings:
            airbnb_bookings.append({
                "start": b.start.isoformat(),
                "end": b.end.isoformat(),  # FullCalendar exclusive
                "name": "Airbnb"
            })

        bookings = booking_booking.objects.filter(
            logement_id=logement_id,
            start__lte=end,
            end__gte=start
        )

        booking_bookings = []
        for b in bookings:
            booking_bookings.append({
                "start": b.start.isoformat(),
                "end": b.end.isoformat(),  # FullCalendar exclusive
                "name": "Booking"
            })

        return Response({
            "data": daily_prices,
            "data_bookings": data_bookings,
            "airbnb_bookings": airbnb_bookings,
            "booking_bookings": booking_bookings
        })

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        logement_id = request.data.get("logement_id")
        start = datetime.strptime(request.data["start"], "%Y-%m-%d").date()
        end = datetime.strptime(request.data["end"], "%Y-%m-%d").date()
        value = request.data.get("value")

        if not all([logement_id, start, end, value]):
            return Response({"error": "Missing required parameters."}, status=400)

        for i in range((end - start).days + 1):
            day = start + timedelta(days=i)
            Price.objects.update_or_create(
                logement_id=logement_id, date=day, defaults={"value": value}
            )

        return Response({"status": "updated"})
