from datetime import datetime, timedelta
import os
import re
import logging
import json
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from logement.models import (
    Logement,
    Room,
    Photo,
    Price,
    Reservation,
    booking_booking,
    airbnb_booking,
    Discount,
    DiscountType,
)
from logement.forms import DiscountForm
from django.contrib import messages
from .forms import LogementForm
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.db.models import Count
from .models import SiteVisit
from .serializers import DailyPriceSerializer
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, F
from calendar import month_name
from django.http import JsonResponse, HttpResponseBadRequest
from logement.services.reservation_service import calculate_price


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
            daily_prices.append(
                {
                    "date": day.isoformat(),
                    "value": price_map.get(day, str(default_price)),
                }
            )

        # Bookings in range
        bookings = Reservation.objects.filter(
            logement_id=logement_id, start__lte=end, end__gte=start, statut="confirmee"
        )

        data_bookings = []
        for b in bookings:
            data_bookings.append(
                {
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),  # FullCalendar exclusive
                    "name": b.user.name,
                    "guests": b.guest,
                    "total_price": str(b.price),
                }
            )

        bookings = airbnb_booking.objects.filter(
            logement_id=logement_id, start__lte=end, end__gte=start
        )

        airbnb_bookings = []
        for b in bookings:
            airbnb_bookings.append(
                {
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),  # FullCalendar exclusive
                    "name": "Airbnb",
                }
            )

        bookings = booking_booking.objects.filter(
            logement_id=logement_id, start__lte=end, end__gte=start
        )

        booking_bookings = []
        for b in bookings:
            booking_bookings.append(
                {
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),  # FullCalendar exclusive
                    "name": "Booking",
                }
            )

        return Response(
            {
                "data": daily_prices,
                "data_bookings": data_bookings,
                "airbnb_bookings": airbnb_bookings,
                "booking_bookings": booking_bookings,
            }
        )

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        logement_id = request.data.get("logement_id")
        start = datetime.strptime(request.data["start"], "%Y-%m-%d").date()
        end = datetime.strptime(request.data["end"], "%Y-%m-%d").date()
        value = float(request.data.get("value"))

        if not all([logement_id, start, end, value]):
            return Response({"error": "Missing required parameters."}, status=400)

        for i in range((end - start).days + 1):
            day = start + timedelta(days=i)
            Price.objects.update_or_create(
                logement_id=logement_id, date=day, defaults={"value": value}
            )

        return Response({"status": "updated"})

    @action(detail=False, methods=["post"])
    def calculate_price(self, request):
        logement_id = request.data.get("logement_id")
        start_str = request.data.get("start")
        end_str = request.data.get("end")
        base_price = request.data.get("base_price")
        guestCount = request.data.get("guests", 1)

        if not logement_id or not start_str:
            return Response({"error": "Missing required parameters."}, status=400)

        logement = Logement.objects.get(id=logement_id)
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        end = datetime.strptime(end_str, "%Y-%m-%d").date()

        price_data = calculate_price(logement, start, end, guestCount, base_price)

        details = {}
        details[f"Total {price_data["number_of_nights"]} Nuit(s)"] = (
            f"{round(price_data["total_base_price"], 2)} €"
        )

        if price_data["TotalextraGuestFee"] != 0:
            details["Voyageur(s) supplémentaire(s)"] = (
                f"+ {round(price_data["TotalextraGuestFee"], 2)} €"
            )

        for key, value in price_data["discount_totals"].items():
            details[f"Réduction {key}"] = f"- {round(value, 2)} €"

        details["Frais de ménage"] = f"+ {round(logement.cleaning_fee, 2)} €"
        details["Taxe de séjour"] = f"+ {round(price_data["taxAmount"], 2)} €"

        return Response(
            {
                "final_price": round(price_data["total_price"], 2),
                "details": details,  # Send the total discount for each discount type
            }
        )


@login_required
@user_passes_test(is_admin)
def manage_discounts(request):
    logement = Logement.objects.first()
    discount_types = DiscountType.objects.all()

    if request.method == "POST":
        post_data = request.POST

        # Delete
        if "delete_id" in post_data:
            Discount.objects.filter(
                id=post_data["delete_id"], logement=logement
            ).delete()
            messages.success(request, "Réduction supprimée avec succès.")

        # Update
        elif "update_id" in post_data:
            discount = get_object_or_404(
                Discount, id=post_data["update_id"], logement=logement
            )
            form = DiscountForm(post_data, instance=discount)
            if form.is_valid():
                form.save()
                messages.success(request, "Réduction mise à jour.")
            else:
                messages.error(
                    request, "Erreur lors de la mise à jour de la réduction."
                )
                return render(
                    request,
                    "administration/discounts.html",
                    {
                        "logement": logement,
                        "discounts": Discount.objects.filter(logement=logement),
                        "discount_types": discount_types,
                        "form": form,
                    },
                )

        # Create
        else:
            form = DiscountForm(post_data)
            if form.is_valid():
                new_discount = form.save(commit=False)
                new_discount.logement = logement
                new_discount.save()
                messages.success(request, "Réduction ajoutée avec succès.")
            else:
                # Form has errors, render it with errors
                messages.error(request, "Erreur lors de la création de la réduction.")
                return render(
                    request,
                    "administration/discounts.html",
                    {
                        "logement": logement,
                        "discounts": Discount.objects.filter(logement=logement),
                        "discount_types": discount_types,
                        "form": form,
                    },
                )

        return redirect("administration:manage_discounts")

    discounts = Discount.objects.filter(logement=logement)
    empty_form = DiscountForm()
    return render(
        request,
        "administration/discounts.html",
        {
            "logement": logement,
            "discounts": discounts,
            "discount_types": discount_types,
            "form": empty_form,
        },
    )


def economie_view(request, logement_id):
    current_year = datetime.now().year
    years = list(
        Reservation.objects.filter(logement_id=logement_id)
        .dates("start", "year")
        .values_list("start__year", flat=True)
        .distinct()
    ) or [current_year]

    return render(
        request,
        "administration/revenu.html",
        {
            "logement": logement_id,
            "years": years,
        },
    )


def api_economie_data(request, logement_id):
    year = int(request.GET.get("year", datetime.now().year))
    month = request.GET.get("month", "all")

    qs = Reservation.objects.filter(
        logement_id=logement_id, start__year=year, statut="confirmee"
    )
    if month != "all":
        qs = qs.filter(start__month=int(month))

    # Calcul brut
    total_revenue = qs.aggregate(total=Sum("price"))["total"] or 0
    total_taxes = qs.aggregate(taxes=Sum("tax"))["taxes"] or 0
    net_profit = total_revenue - total_taxes

    # Graph par mois
    monthly_data = (
        qs.annotate(month=F("start__month"))
        .values("month")
        .annotate(monthly_total=Sum("price"))
        .order_by("month")
    )

    labels = []
    values = []
    for m in range(1, 13):
        labels.append(month_name[m][:3])
        month_entry = next((x for x in monthly_data if x["month"] == m), None)
        values.append(float(month_entry["monthly_total"]) if month_entry else 0)

    return JsonResponse(
        {
            "total_revenue": total_revenue,
            "total_taxes": total_taxes,
            "net_profit": net_profit,
            "chart_labels": labels,
            "chart_values": values,
        }
    )


@login_required
@user_passes_test(is_admin)
def log_viewer(request):
    log_file_path = os.path.join(settings.LOG_DIR, "django.log")
    log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    selected_level = request.GET.get("level")
    selected_logger = request.GET.get("logger")
    query = request.GET.get("query", "").strip().lower()

    logs = []
    all_logs = []
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                lines.reverse()  # latest logs first
                for line in lines:
                    match = re.match(r"\[(.*?)\] (\w+) ([^\s]+) \((.*?)\) (.*)", line)
                    if match:
                        timestamp, level, logger, location, message = match.groups()

                        all_logs.append(
                            {
                                "timestamp": timestamp,
                                "level": level,
                                "logger": logger,
                                "location": location,
                                "message": message,
                            }
                        )

                        if selected_level and level != selected_level:
                            continue
                        if selected_logger and logger != selected_logger:
                            continue
                        if query and query not in message.lower():
                            continue

                        logs.append(
                            {
                                "timestamp": timestamp,
                                "level": level,
                                "logger": logger,
                                "location": location,
                                "message": message,
                            }
                        )
        except Exception as e:
            logger.exception(f"Erreur lors de la lecture du fichier de log: {e}")
            lines = []
    loggers = sorted(set(entry["logger"] for entry in all_logs))
    context = {
        "query": query,
        "loggers": loggers,
        "logs": logs,
        "levels": log_levels,
        "selected_level": selected_level,
    }
    return render(request, "administration/log_viewer.html", context)


@csrf_exempt
def js_logger(request):
    logger = logging.getLogger("frontend")
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            level = data.get("level", "info").lower()
            message = data.get("message", "")
            meta = data.get("meta", {})

            # Format message with metadata
            formatted_msg = f"[JS] {message} | Meta: {meta}"

            if level == "debug":
                logger.debug(formatted_msg)
            elif level == "info":
                logger.info(formatted_msg)
            elif level == "warning":
                logger.warning(formatted_msg)
            elif level == "error":
                logger.error(formatted_msg)
            elif level == "critical":
                logger.critical(formatted_msg)
            else:
                logger.info(formatted_msg)

            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception(f"Failed to log JS message: {e}")
            return HttpResponseBadRequest("Invalid data")
    return HttpResponseBadRequest("Only POST allowed")
