from datetime import datetime, timedelta
import os
import re
import logging
import json
from django.http import QueryDict
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models.functions import ExtractYear, ExtractMonth
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
    Equipment,
)
from logement.forms import DiscountForm
from django.contrib import messages
from .forms import (
    LogementForm,
    HomePageConfigForm,
    ServiceForm,
    TestimonialForm,
    CommitmentForm,
    EntrepriseForm,
)
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.db.models import Count
from .models import SiteVisit, HomePageConfig, Entreprise
from .serializers import DailyPriceSerializer
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, F
from calendar import month_name
from django.http import JsonResponse, HttpResponseBadRequest
from logement.services.reservation_service import calculate_price
from common.views import is_admin
from logement.services.payment_service import refund_payment


logger = logging.getLogger(__name__)


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
    logement = get_object_or_404(
        Logement.objects.prefetch_related(
            "photos", "equipment"
        ),  # Include .equipment if it's a ManyToMany
        id=logement_id,
    )
    rooms = logement.rooms.all().order_by("name")
    photos = logement.photos.all().order_by("order")

    if request.method == "POST":
        form = LogementForm(request.POST, instance=logement)
        if form.is_valid():
            form.save()
    else:
        form = LogementForm(instance=logement)

    # Get selected equipment IDs
    selected_equipment_ids = logement.equipment.values_list("id", flat=True)

    return render(
        request,
        "administration/edit_logement.html",
        {
            "form": form,
            "logement": logement,
            "rooms": rooms,
            "photos": photos,
            "all_equipment": Equipment.objects.all(),
            "selected_equipment_ids": selected_equipment_ids,
        },
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
    data = json.loads(request.body)  # <- THIS IS REQUIRED for JSON body
    room_id = data.get("room_id")

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
    logement_photos = list(
        Photo.objects.filter(logement=photo.logement).order_by("order")
    )

    if len(logement_photos) < 2:
        return JsonResponse(
            {"success": False, "message": "Pas assez de photos."}, status=400
        )

    index = next((i for i, p in enumerate(logement_photos) if p.id == photo.id), None)
    if index is None:
        return JsonResponse(
            {"success": False, "message": "Photo introuvable."}, status=404
        )

    if direction == "up":
        swap_index = (index - 1) % len(logement_photos)
    elif direction == "down":
        swap_index = (index + 1) % len(logement_photos)
    else:
        return JsonResponse(
            {"success": False, "message": "Direction invalide."}, status=400
        )

    other_photo = logement_photos[swap_index]
    photo.order, other_photo.order = other_photo.order, photo.order
    photo.save()
    other_photo.save()

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
@require_POST
def delete_all_photos(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    logement.photos.all().delete()
    return JsonResponse({"status": "ok"})


@login_required
@user_passes_test(is_admin)
@require_POST
def rotate_photo(request, photo_id):
    degrees = int(request.POST.get("degrees", 90))
    try:
        photo = Photo.objects.get(pk=photo_id)
        photo.rotation = (photo.rotation - degrees) % 360
        photo.save()
        return JsonResponse({"status": "ok", "rotation": photo.rotation})
    except Photo.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Photo not found"}, status=404
        )


@login_required
@user_passes_test(is_admin)
def update_equipment(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)

    if request.method == "POST":
        equipment_ids = request.POST.getlist("equipment")
        logement.equipment.set(equipment_ids)

    return redirect("administration:edit_logement", logement.id)


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
    logements = Logement.objects.prefetch_related("photos").all()
    return render(
        request,
        "administration/calendar.html",
        {
            "logements": logements,
            "logements_json": json.dumps(
                [{"id": l.id, "name": l.name} for l in logements]
            ),
        },
    )


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
        details[f"Total {price_data['number_of_nights']} Nuit(s)"] = (
            f"{round(price_data['total_base_price'], 2)} €"
        )

        if price_data["TotalextraGuestFee"] != 0:
            details["Voyageur(s) supplémentaire(s)"] = (
                f"+ {round(price_data['TotalextraGuestFee'], 2)} €"
            )

        for key, value in price_data["discount_totals"].items():
            details[f"Réduction {key}"] = f"- {round(value, 2)} €"

        details["Frais de ménage"] = f"+ {round(logement.cleaning_fee, 2)} €"
        details["Taxe de séjour"] = f"+ {round(price_data['taxAmount'], 2)} €"

        return Response(
            {
                "final_price": round(price_data["total_price"], 2),
                "tax": round(price_data["taxAmount"], 2),
                "details": details,  # Send the total discount for each discount type
            }
        )


def normalize_decimal_input(data):
    if isinstance(data, QueryDict):
        data = data.copy()
    if "value" in data:
        data["value"] = data["value"].replace(",", ".")
    return data


@login_required
@user_passes_test(is_admin)
def manage_discounts(request):
    all_logements = Logement.objects.all()
    logement_id = request.GET.get("logement_id") or request.POST.get("logement_id")
    logement = (
        get_object_or_404(Logement, id=logement_id)
        if logement_id
        else all_logements.first()
    )

    if not logement:
        messages.error(request, "Aucun logement trouvé.")
        return redirect("administration:dashboard")

    discounts = Discount.objects.filter(logement=logement)
    discount_types = DiscountType.objects.all()

    if request.method == "POST":
        post_data = normalize_decimal_input(request.POST)
        action = post_data.get("action")

        if action == "delete":
            Discount.objects.filter(
                id=post_data["discount_id"], logement=logement
            ).delete()
            messages.success(request, "Réduction supprimée avec succès.")

        elif action == "update":
            instance = get_object_or_404(
                Discount, id=post_data["discount_id"], logement=logement
            )
            form = DiscountForm(post_data, instance=instance)
            if form.is_valid():
                form.save()
                messages.success(request, "Réduction mise à jour.")
            else:
                messages.error(request, "Erreur lors de la mise à jour.")
                return render(
                    request,
                    "administration/discounts.html",
                    {
                        "logement": logement,
                        "discounts": discounts,
                        "discount_types": discount_types,
                        "all_logements": all_logements,
                        "form": form,
                    },
                )

        else:  # create
            form = DiscountForm(post_data)
            if form.is_valid():
                new_discount = form.save(commit=False)
                new_discount.logement = logement
                new_discount.save()
                messages.success(request, "Réduction ajoutée.")
            else:
                messages.error(request, "Erreur lors de la création.")
                return render(
                    request,
                    "administration/discounts.html",
                    {
                        "logement": logement,
                        "discounts": discounts,
                        "discount_types": discount_types,
                        "all_logements": all_logements,
                        "form": form,
                    },
                )

        return redirect(
            f"{reverse('administration:manage_discounts')}?logement_id={logement.id}"
        )

    return render(
        request,
        "administration/discounts.html",
        {
            "logement": logement,
            "discounts": discounts,
            "discount_types": discount_types,
            "all_logements": all_logements,
            "form": DiscountForm(),
        },
    )


@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET", "POST"])
def economie_view(request):
    logements = Logement.objects.all()
    selected_logement_id = (
        request.POST.get("logement_id") or logements.first().id if logements else None
    )

    current_year = datetime.now().year
    years = list(
        Reservation.objects.filter(logement_id=selected_logement_id)
        .dates("start", "year")
        .values_list("start__year", flat=True)
        .distinct()
    ) or [current_year]

    return render(
        request,
        "administration/revenu.html",
        {
            "logement_id": int(selected_logement_id),
            "logements": logements,
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


@login_required
@user_passes_test(is_admin)
def reservation_dashboard(request, logement_id=None):
    if logement_id:
        logement = get_object_or_404(
            Logement.objects.prefetch_related("photos"), id=logement_id
        )
        base_qs = Reservation.objects.filter(logement=logement)
    else:
        base_qs = Reservation.objects.all()

    base_qs = (
        base_qs.exclude(statut="en_attente")
        .order_by("-start")
        .select_related("user", "logement")
        .prefetch_related("logement__photos")
    )

    # Filter by year and month (from query params)
    year = request.GET.get("year")
    month = request.GET.get("month")
    if year:
        base_qs = base_qs.annotate(res_year=ExtractYear("start")).filter(res_year=year)
    if month:
        base_qs = base_qs.annotate(res_month=ExtractMonth("start")).filter(
            res_month=month
        )

    # For dropdowns: list all available years and months
    years = (
        Reservation.objects.annotate(y=ExtractYear("start"))
        .values_list("y", flat=True)
        .distinct()
        .order_by("y")
    )
    months = (
        Reservation.objects.annotate(m=ExtractMonth("start"))
        .values_list("m", flat=True)
        .distinct()
        .order_by("m")
    )

    return render(
        request,
        "administration/reservations.html",
        {
            "reservations": base_qs,
            "available_years": years,
            "available_months": months,
            "current_year": year,
            "current_month": month,
        },
    )


@login_required
@user_passes_test(is_admin)
def homepage_admin_view(request):
    config = HomePageConfig.objects.first() or HomePageConfig.objects.create()

    service_form = ServiceForm()
    testimonial_form = TestimonialForm()
    commitment_form = CommitmentForm()
    main_form = HomePageConfigForm(instance=config)

    if request.method == "POST":
        # DELETE actions
        if "delete_service_id" in request.POST:
            config.services.filter(id=request.POST["delete_service_id"]).delete()
        elif "delete_testimonial_id" in request.POST:
            config.testimonials.filter(
                id=request.POST["delete_testimonial_id"]
            ).delete()
        elif "delete_commitment_id" in request.POST:
            config.commitments.filter(id=request.POST["delete_commitment_id"]).delete()

        # ADD actions
        elif "add_service" in request.POST:
            service_form = ServiceForm(request.POST, request.FILES)
            if service_form.is_valid():
                instance = service_form.save(commit=False)
                instance.config = config
                instance.save()
        elif "add_testimonial" in request.POST:
            testimonial_form = TestimonialForm(request.POST)
            if testimonial_form.is_valid():
                instance = testimonial_form.save(commit=False)
                instance.config = config
                instance.save()
        elif "add_commitment" in request.POST:
            commitment_form = CommitmentForm(request.POST, request.FILES)
            if commitment_form.is_valid():
                instance = commitment_form.save(commit=False)
                instance.config = config
                instance.save()

        # UPDATE config form
        else:
            main_form = HomePageConfigForm(request.POST, request.FILES, instance=config)
            if main_form.is_valid():
                main_form.save()

    context = {
        "form": main_form,
        "config": config,
        "services": config.services.all(),
        "testimonials": config.testimonials.all(),
        "commitments": config.commitments.all(),
        "service_form": service_form,
        "testimonial_form": testimonial_form,
        "commitment_form": commitment_form,
    }
    return render(request, "administration/base_site.html", context)


@login_required
@user_passes_test(is_admin)
def edit_entreprise(request):
    entreprise = Entreprise.objects.first()
    if request.method == "POST":
        form = EntrepriseForm(request.POST, request.FILES, instance=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "Les informations ont été mises à jour.")
    else:
        form = EntrepriseForm(instance=entreprise)

    return render(request, "administration/edit_entreprise.html", {"form": form})


@login_required
@user_passes_test(is_admin)
def reservation_detail(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    return render(
        request, "administration/reservation_detail.html", {"reservation": reservation}
    )


@login_required
@user_passes_test(is_admin)
@require_POST
def cancel_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    if reservation.statut != "annulee":
        reservation.statut = "annulee"
        reservation.save()
        messages.success(request, "Réservation annulée avec succès.")
    else:
        messages.warning(request, "La réservation est déjà annulée.")
    return redirect("administration:reservation_detail", pk=pk)


@login_required
@user_passes_test(is_admin)
@require_POST
def refund_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    if not reservation.refunded:
        try:
            refund_fee = reservation.price * 0.01
            total_to_refund = reservation.price - refund_fee
            amount_in_cents = int(total_to_refund * 100)

            refund = refund_payment(reservation.payment_intent_id, amount_in_cents)

            messages.success(
                request,
                f"Remboursement de {total_to_refund:.2f} € effectué avec succès.",
            )
        except Exception as e:
            messages.error(request, f"Erreur de remboursement Stripe : {e}")
            logger.exception("Stripe refund failed")
    else:
        messages.warning(request, "Remboursement non possible.")

    return redirect("administration:reservation_detail", pk=pk)
