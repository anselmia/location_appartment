import json
import logging
import os
import calendar as cal

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import stripe

from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.db.models import Sum, Q
from django.db.models.functions import ExtractYear, ExtractMonth, TruncMonth
from django.http import (
    HttpResponseBadRequest,
    JsonResponse,
    QueryDict,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import TemplateView

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

# App imports
from common.decorators import (
    user_has_logement,
    user_is_logement_admin,
    user_is_reservation_admin,
)
from common.mixins import AdminRequiredMixin, UserHasLogementMixin
from common.views import is_admin, is_stripe_admin

from logement.forms import DiscountForm, LogementForm
from logement.models import (
    Discount,
    DiscountType,
    Equipment,
    Logement,
    Photo,
    Price,
    Reservation,
    Room,
    airbnb_booking,
    booking_booking,
)
from logement.services.logement import get_logements
from logement.services.payment_service import (
    charge_payment,
    charge_reservation,
    refund_payment,
    send_stripe_payment_link,
)
from logement.services.reservation_service import (
    calculate_price,
    get_reservation_years_and_months,
    get_valid_reservations_for_admin,
    mark_reservation_cancelled,
)

from administration.services.logs import parse_log_file
from administration.services.revenu import get_economie_stats
from administration.services.traffic import get_traffic_dashboard_data

from .forms import (
    CommitmentForm,
    EntrepriseForm,
    HomePageConfigForm,
    ServiceForm,
    TestimonialForm,
)
from .models import Entreprise, HomePageConfig
from .serializers import DailyPriceSerializer


stripe.api_key = settings.STRIPE_PRIVATE_KEY

logger = logging.getLogger(__name__)


@login_required
@user_has_logement
def admin_dashboard(request):
    try:
        logements = get_logements(request.user)
        return render(request, "administration/dashboard.html", {"logements": logements})
    except Exception as e:
        logger.exception(f"Error rendering admin dashboard: {e}")


@login_required
@user_has_logement
def add_logement(request):
    try:
        if request.method == "POST":
            form = LogementForm(request.POST)
            if form.is_valid():
                logement = form.save()
                logger.info(f"Logement added with ID {logement.id}")
                return redirect("administration:edit_logement", logement.id)
        else:
            form = LogementForm()

        return render(request, "administration/add_logement.html", {"form": form})
    except Exception as e:
        logger.exception(f"Error adding logement: {e}")


@login_required
@user_is_logement_admin
def edit_logement(request, logement_id):
    try:
        logement = get_object_or_404(Logement.objects.prefetch_related("photos", "equipment"), id=logement_id)
        rooms = logement.rooms.all().order_by("name")
        photos = logement.photos.all().order_by("order")

        if request.method == "POST":
            form = LogementForm(request.POST, instance=logement)
            if form.is_valid():
                form.save()
                logger.info(f"Logement {logement_id} updated")
        else:
            form = LogementForm(instance=logement)

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
    except Exception as e:
        logger.exception(f"Error editing logement {logement_id}: {e}")


@login_required
@user_is_logement_admin
def add_room(request, logement_id):
    try:
        logement = get_object_or_404(Logement, id=logement_id)
        Room.objects.create(name=request.POST["name"], logement=logement)
        logger.info(f"Room added to logement {logement_id}")
        return redirect("administration:edit_logement", logement_id)
    except Exception as e:
        logger.exception(f"Error adding room to logement {logement_id}: {e}")


@login_required
@user_is_logement_admin
@require_POST
def delete_room(request, room_id):
    try:
        room = get_object_or_404(Room, id=room_id)
        logement_id = room.logement.id
        room.delete()
        logger.info(f"Room {room_id} deleted")
        return redirect("administration:edit_logement", logement_id)
    except Exception as e:
        logger.exception(f"Error deleting room {room_id}: {e}")


@login_required
@user_is_logement_admin
@require_POST
def upload_photos(request, logement_id):
    try:
        logement = get_object_or_404(Logement, id=logement_id)
        room_id = request.POST.get("room_id")
        room = get_object_or_404(Room, id=room_id, logement=logement)

        for uploaded_file in request.FILES.getlist("photo"):
            Photo.objects.create(logement=logement, room=room, image=uploaded_file)

        logger.info(f"Photos uploaded for logement {logement_id} in room {room_id}")
        return redirect("administration:edit_logement", logement_id)
    except Exception as e:
        logger.exception(f"Error uploading photos for logement {logement_id}: {e}")


@login_required
@user_is_logement_admin
@require_POST
def change_photo_room(request, photo_id):
    try:
        photo = get_object_or_404(Photo, id=photo_id)
        data = json.loads(request.body)
        room_id = data.get("room_id")

        if not room_id:
            return JsonResponse({"success": False, "error": "Missing room_id"}, status=400)

        room = get_object_or_404(Room, id=room_id, logement=photo.logement)
        photo.assign_room(room)

        logger.info(f"Photo {photo_id} moved to room {room_id}")
        return JsonResponse({"success": True})

    except (json.JSONDecodeError, ValueError):
        logger.warning(f"Invalid JSON in request to change photo room for photo {photo_id}")
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception:
        logger.exception(f"Error changing photo room for photo {photo_id}")
        return JsonResponse({"success": False, "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
@require_POST
def move_photo(request, photo_id, direction):
    try:
        photo = get_object_or_404(Photo, id=photo_id)
        success, message = photo.move_in_order(direction)
        if success:
            logger.info(f"Photo {photo_id} moved {direction}")
            return JsonResponse({"success": True})
        logger.warning(f"Failed to move photo {photo_id}: {message}")
        return JsonResponse({"success": False, "message": message}, status=400)
    except Exception as e:
        logger.exception(f"Error moving photo {photo_id}: {e}")
        return JsonResponse({"success": False, "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
@require_http_methods(["DELETE"])
def delete_photo(request, photo_id):
    try:
        photo = get_object_or_404(Photo, id=photo_id)
        photo.safe_delete()
        logger.info(f"Photo {photo_id} deleted")
        return JsonResponse({"success": True})
    except Exception as e:
        logger.exception(f"Error deleting photo {photo_id}: {e}")
        return JsonResponse({"success": False, "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
@require_POST
def delete_all_photos(request, logement_id):
    try:
        logement = get_object_or_404(Logement, id=logement_id)
        for photo in logement.photos.all():
            photo.safe_delete()
        logger.info(f"All photos deleted for logement {logement_id}")
        return JsonResponse({"status": "ok"})
    except Exception as e:
        logger.exception(f"Error deleting all photos for logement {logement_id}: {e}")
        return JsonResponse({"status": "error", "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
@require_POST
def rotate_photo(request, photo_id):
    try:
        degrees = int(request.POST.get("degrees", 90))
        photo = get_object_or_404(Photo, pk=photo_id)
        photo.rotate(degrees)
        logger.info(f"Photo {photo_id} rotated by {degrees} degrees")
        return JsonResponse({"status": "ok", "rotation": photo.rotation})
    except Exception as e:
        logger.exception(f"Error rotating photo {photo_id}: {e}")
        return JsonResponse({"status": "error", "error": "Erreur interne serveur"}, status=500)


@login_required
@user_is_logement_admin
def update_equipment(request, logement_id):
    try:
        logement = get_object_or_404(Logement, id=logement_id)
        if request.method == "POST":
            equipment_ids = request.POST.getlist("equipment")
            logement.equipment.set(equipment_ids)
            logger.info(f"Updated equipment for logement {logement_id}")
        return redirect("administration:edit_logement", logement.id)
    except Exception as e:
        logger.exception(f"Error updating equipment for logement {logement_id}: {e}")


@login_required
@user_passes_test(is_admin)
def traffic_dashboard(request):
    try:
        period = request.POST.get("period") if request.method == "POST" else request.GET.get("period", "day")

        stats = get_traffic_dashboard_data(period=period)

        if request.method == "POST":
            return JsonResponse(stats)

        return render(
            request,
            "administration/traffic.html",
            {
                "online_visitors": stats["online_visitors"],
                "online_users": stats["online_users"],
                "labels": json.dumps(stats["labels"]),
                "data": json.dumps(stats["data"]),
                "total_visits": stats["total_visits"],
                "unique_visitors": stats["unique_visitors"],
                "recent_logs": stats["recent_logs"],
                "selected_period": period,
            },
        )
    except Exception as e:
        logger.exception(f"Error loading traffic dashboard: {e}")


@login_required
@user_has_logement
def calendar(request):
    try:
        logements = get_logements(request.user)
        return render(
            request,
            "administration/calendar.html",
            {
                "logements": logements,
                "logements_json": [{"id": l.id, "name": l.name, "calendar_link": l.calendar_link} for l in logements],
            },
        )
    except Exception as e:
        logger.error(f"Error occurred in calendar view: {e}", exc_info=True)
        return render(
            request,
            "common/error.html",
            {"error_message": "Une erreur est survenue en essayant d'accéder au calendrier"},
        )


class DailyPriceViewSet(viewsets.ModelViewSet):
    serializer_class = DailyPriceSerializer

    def get_queryset(self):
        logement_id = self.request.query_params.get("logement_id")
        return Price.objects.filter(logement_id=logement_id)

    def list(self, request, *args, **kwargs):
        try:
            logement_id = request.query_params.get("logement_id")
            start_str = request.query_params.get("start")
            end_str = request.query_params.get("end")

            if not logement_id:
                return Response({"error": "Missing logement_id"}, status=400)

            logement = Logement.objects.get(id=logement_id)
            default_price = logement.price

            start = datetime.fromisoformat(start_str).date()
            end = datetime.fromisoformat(end_str).date()

            custom_prices = Price.objects.filter(logement_id=logement_id, date__range=(start, end))
            price_map = {p.date: p.value for p in custom_prices}

            daily_prices = [
                {
                    "date": (start + timedelta(days=i)).isoformat(),
                    "value": price_map.get(start + timedelta(days=i), str(default_price)),
                }
                for i in range((end - start).days + 1)
            ]

            data_bookings = [
                {
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),
                    "name": b.user.name,
                    "guests": b.guest,
                    "total_price": str(b.price),
                }
                for b in Reservation.objects.filter(
                    logement_id=logement_id,
                    start__lte=end,
                    end__gte=start,
                    statut="confirmee",
                )
            ]

            airbnb_bookings = [
                {
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),
                    "name": "Airbnb",
                }
                for b in airbnb_booking.objects.filter(logement_id=logement_id, start__lte=end, end__gte=start)
            ]

            booking_bookings = [
                {
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),
                    "name": "Booking",
                }
                for b in booking_booking.objects.filter(logement_id=logement_id, start__lte=end, end__gte=start)
            ]

            return Response(
                {
                    "data": daily_prices,
                    "data_bookings": data_bookings,
                    "airbnb_bookings": airbnb_bookings,
                    "booking_bookings": booking_bookings,
                }
            )
        except Exception as e:
            logger.exception(f"Error fetching daily prices: {e}")
            return Response({"error": "Erreur interne serveur"}, status=500)

    def perform_create(self, serializer):
        try:
            serializer.save()
        except Exception as e:
            logger.exception(f"Error creating price: {e}")
            raise

    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        try:
            logement_id = request.data.get("logement_id")
            start = datetime.strptime(request.data["start"], "%Y-%m-%d").date()
            end = datetime.strptime(request.data["end"], "%Y-%m-%d").date()
            value = float(request.data.get("value"))

            if not all([logement_id, start, end, value]):
                return Response({"error": "Missing required parameters."}, status=400)

            for i in range((end - start).days + 1):
                day = start + timedelta(days=i)
                Price.objects.update_or_create(logement_id=logement_id, date=day, defaults={"value": value})

            logger.info(f"Bulk prices updated for logement {logement_id}")
            return Response({"status": "updated"})
        except Exception as e:
            logger.exception(f"Error in bulk_update: {e}")
            return Response({"error": "Erreur interne serveur"}, status=500)

    @action(detail=False, methods=["post"])
    def calculate_price(self, request):
        try:
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

            details = {
                f"Total {price_data['number_of_nights']} Nuit(s)": f"{round(price_data['total_base_price'], 2)} €"
            }

            if price_data["TotalextraGuestFee"] != 0:
                details["Voyageur(s) supplémentaire(s)"] = f"+ {round(price_data['TotalextraGuestFee'], 2)} €"

            for key, value in price_data["discount_totals"].items():
                details[f"Réduction {key}"] = f"- {round(value, 2)} €"

            details["Frais de ménage"] = f"+ {round(logement.cleaning_fee, 2)} €"
            details["Taxe de séjour"] = f"+ {round(price_data['taxAmount'], 2)} €"

            details["Frais de transaction"] = f"+ {round(price_data['payment_fee'], 2)} €"

            return Response(
                {
                    "final_price": round(price_data["total_price"], 2),
                    "tax": round(price_data["taxAmount"], 2),
                    "details": details,
                }
            )
        except Exception as e:
            logger.exception(f"Error calculating price: {e}")
            return Response({"error": "Erreur interne serveur"}, status=500)


def normalize_decimal_input(data):
    if isinstance(data, QueryDict):
        data = data.copy()
    if "value" in data:
        data["value"] = data["value"].replace(",", ".")
    return data


@login_required
@user_has_logement
def manage_discounts(request):
    try:
        logements = get_logements(request.user)
        logement_id = request.GET.get("logement_id") or request.POST.get("logement_id")
        logement = get_object_or_404(Logement, id=logement_id) if logement_id else logements.first()

        if not logement:
            messages.error(request, "Aucun logement trouvé.")
            return redirect("administration:dashboard")

        discounts = Discount.objects.filter(logement=logement)
        discount_types = DiscountType.objects.all()

        if request.method == "POST":
            post_data = normalize_decimal_input(request.POST)
            action = post_data.get("action")

            if action == "delete":
                Discount.objects.filter(id=post_data["discount_id"], logement=logement).delete()
                messages.success(request, "Réduction supprimée avec succès.")

            elif action == "update":
                instance = get_object_or_404(Discount, id=post_data["discount_id"], logement=logement)
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
                            "all_logements": logements,
                            "form": form,
                        },
                    )
            else:
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
                            "all_logements": logements,
                            "form": form,
                        },
                    )

            return redirect(f"{reverse('administration:manage_discounts')}?logement_id={logement.id}")

        return render(
            request,
            "administration/discounts.html",
            {
                "logement": logement,
                "discounts": discounts,
                "discount_types": discount_types,
                "all_logements": logements,
                "form": DiscountForm(),
            },
        )
    except Exception as e:
        logger.exception(f"Error managing discounts: {e}")


def api_economie_data(request, logement_id):
    try:
        year = int(request.GET.get("year", datetime.now().year))
        month = request.GET.get("month", "all")
        data = get_economie_stats(logement_id=logement_id, year=year, month=month)
        return JsonResponse(data)
    except Exception as e:
        logger.exception(f"Erreur dans api_economie_data: {e}")
        return JsonResponse({"error": "Erreur interne serveur"}, status=500)


@login_required
@user_passes_test(is_admin)
def log_viewer(request):
    log_file_path = os.path.join(settings.LOG_DIR, "django.log")
    selected_level = request.GET.get("level")
    selected_logger = request.GET.get("logger")
    query = request.GET.get("query", "").strip().lower()

    try:
        logs, all_loggers = parse_log_file(
            path=log_file_path,
            level=selected_level,
            logger_filter=selected_logger,
            query=query,
        )
    except Exception as e:
        logger.exception(f"Erreur lors de la lecture du fichier de log: {e}")
        logs = []
        all_loggers = []

    return render(
        request,
        "administration/log_viewer.html",
        {
            "logs": logs,
            "loggers": sorted(all_loggers),
            "levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "selected_level": selected_level,
            "query": query,
        },
    )


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
@user_has_logement
def reservation_dashboard(request, logement_id=None):
    try:
        year = request.GET.get("year")
        month = request.GET.get("month")

        reservations = get_valid_reservations_for_admin(
            user=request.user,
            logement_id=logement_id,
            year=year,
            month=month,
        )

        years, months = get_reservation_years_and_months()

        return render(
            request,
            "administration/reservations.html",
            {
                "reservations": reservations,
                "available_years": years,
                "available_months": months,
                "current_year": year,
                "current_month": month,
            },
        )

    except Exception as e:
        logger.error(f"Error in reservation_dashboard: {e}", exc_info=True)
        return render(
            request,
            "common/error.html",
            {"error_message": "Une erreur est survenue en récupérant les réservations."},
        )


@login_required
@user_passes_test(is_admin)
def homepage_admin_view(request):
    try:
        config = HomePageConfig.objects.first() or HomePageConfig.objects.create()
        service_form = ServiceForm()
        testimonial_form = TestimonialForm()
        commitment_form = CommitmentForm()
        main_form = HomePageConfigForm(instance=config)

        if request.method == "POST":
            if "delete_service_id" in request.POST:
                config.services.filter(id=request.POST["delete_service_id"]).delete()
            elif "delete_testimonial_id" in request.POST:
                config.testimonials.filter(id=request.POST["delete_testimonial_id"]).delete()
            elif "delete_commitment_id" in request.POST:
                config.commitments.filter(id=request.POST["delete_commitment_id"]).delete()
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
    except Exception as e:
        logger.exception(f"Erreur dans homepage_admin_view: {e}")
        return render(request, "common/error.html", {"error_message": "Erreur interne serveur"})


@login_required
@user_passes_test(is_admin)
def edit_entreprise(request):
    try:
        entreprise = Entreprise.objects.first()
        if request.method == "POST":
            form = EntrepriseForm(request.POST, request.FILES, instance=entreprise)
            if form.is_valid():
                form.save()
                messages.success(request, "Les informations ont été mises à jour.")
        else:
            form = EntrepriseForm(instance=entreprise)

        return render(request, "administration/edit_entreprise.html", {"form": form})
    except Exception as e:
        logger.exception(f"Erreur dans edit_entreprise: {e}")
        return render(request, "common/error.html", {"error_message": "Erreur interne serveur"})


@login_required
@user_is_reservation_admin
def reservation_detail(request, code):
    reservation = get_object_or_404(Reservation, code=code)
    return render(request, "administration/reservation_detail.html", {"reservation": reservation})


@login_required
@user_is_reservation_admin
@require_POST
def cancel_reservation(request, code):
    reservation = get_object_or_404(Reservation, code=code)
    if reservation.statut != "annulee":
        mark_reservation_cancelled(reservation)
        messages.success(request, "Réservation annulée avec succès.")
    else:
        messages.warning(request, "La réservation est déjà annulée.")
    return redirect("administration:reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def refund_reservation(request, code):
    user = request.user
    reservation = get_object_or_404(Reservation, code=code)

    key = f"refund_attempts_{code}:{user.id}"
    attempts = cache.get(key, 0)

    if attempts >= 5:
        logger.warning(f"[Stripe] Trop de tentatives de remboursement | user={user.username} | ip={ip}")
        messages.error(request, "Trop de tentatives de remboursement. Réessayez plus tard.")
        return redirect("administration:reservation_dashboard")

    cache.set(key, attempts + 1, timeout=60 * 10)  # 10 minutes

    if not reservation.refunded:
        try:
            amount_in_cents = int(reservation.refundable_amount * 100)

            refund = refund_payment(reservation, refund="full", amount_cents=amount_in_cents)

            messages.success(
                request,
                f"Une demande de remboursement de {reservation.refundable_amount:.2f} € a été effectuée avec succès.",
            )
        except Exception as e:
            messages.error(request, f"Erreur de remboursement Stripe : {e}")
            logger.exception("Stripe refund failed")
    else:
        messages.warning(request, "Cette réservation a déjà été remboursée.")

    return redirect("administration:reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def refund_partially_reservation(request, code):
    reservation = get_object_or_404(Reservation, code=code)

    if reservation.refunded:
        messages.warning(request, "Cette réservation a déjà été remboursée.")
        return redirect("administration:reservation_detail", code=code)

    try:
        amount_str = request.POST.get("refund_amount")
        refund_amount = Decimal(amount_str)

        if refund_amount <= 0 or refund_amount > reservation.price:
            messages.error(
                request,
                "Montant invalide. Il doit être supérieur à 0 et inférieur ou égal au montant total.",
            )
            return redirect("administration:reservation_detail", code=code)

        amount_in_cents = int(refund_amount * 100)
        refund = refund_payment(reservation, refund="partial", amount_cents=amount_in_cents)

        messages.success(
            request,
            f"Remboursement partiel de {refund_amount:.2f} € effectué avec succès.",
        )

    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Montant de remboursement invalide.")
    except Exception as e:
        messages.error(request, f"Erreur de remboursement Stripe : {e}")
        logger.exception("Stripe refund failed")

    return redirect("administration:reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def charge_deposit(request, code):
    reservation = get_object_or_404(Reservation, code=code)

    try:
        amount = Decimal(request.POST.get("deposit_amount"))

        if amount <= 0:
            messages.error(request, "Le montant doit être supérieur à 0.")
            return redirect("administration:reservation_detail", code=code)

        logement_caution = getattr(reservation.logement, "caution", None)
        if logement_caution is not None and amount > reservation.chargeable_deposit:
            messages.error(
                request,
                f"Le montant de la caution ({amount:.2f} €) dépasse la limite autorisée pour ce logement ({logement_caution:.2f} €).",
            )
            return redirect("administration:reservation_detail", code=code)

        amount_in_cents = int(amount * 100)

        charge_result = charge_payment(
            reservation.stripe_saved_payment_method_id,
            amount_in_cents,
            reservation.user.stripe_customer_id,
            reservation,
        )

        if charge_result:
            messages.success(request, f"Caution de {amount:.2f} € chargée avec succès.")
        else:
            messages.error(request, "Erreur lors du paiement de la caution.")

    except (InvalidOperation, ValueError, TypeError):
        messages.error(request, "Montant invalide.")
    except Exception as e:
        messages.error(request, f"Erreur lors du chargement Stripe : {e}")
        logger.exception("Stripe deposit charge failed")

    return redirect("administration:reservation_detail", code=code)


@login_required
@user_passes_test(is_admin)
def manage_reservations(request):
    query = request.GET.get("q")
    reservations = Reservation.objects.select_related("logement", "user").exclude(statut="en_attente")

    if query:
        reservations = reservations.filter(code__icontains=query)

    reservations = reservations.order_by("-date_reservation")[:50]

    context = {
        "reservations": reservations,
        "query": query,
    }
    return render(request, "administration/manage_reservations.html", context)


@login_required
@user_passes_test(is_admin)
def transfer_reservation_payment(request, code):
    reservation = get_object_or_404(Reservation, code=code, transferred=False)

    try:
        charge_reservation(reservation)

        messages.success(request, f"Transfert effectué pour {reservation.code}.")
    except Exception as e:
        messages.error(request, f"Erreur lors du transfert : {str(e)}")

    return redirect("administration:manage_reservations")


class FinancialDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "administration/financial_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        year = self.request.GET.get("year")
        all_years = (
            Reservation.objects.filter(statut="confirmee")
            .annotate(year=ExtractYear("start"))
            .values_list("year", flat=True)
            .distinct()
        )
        selected_year = int(year) if year and year.isdigit() else max(all_years, default=datetime.now().year)

        reservations = Reservation.objects.filter(start__year=selected_year).exclude(statut="en_attente")

        monthly_data = (
            reservations.filter(date_reservation__year=selected_year)
            .annotate(month=ExtractMonth("date_reservation"))
            .values("month")
            .annotate(total=Sum("platform_fee"))
            .order_by("month")
        )

        brut_revenue = reservations.aggregate(Sum("price"))["price__sum"] or Decimal("0.00")
        total_refunds = reservations.aggregate(Sum("refund_amount"))["refund_amount__sum"] or Decimal("0.00")
        total_revenu = brut_revenue - total_refunds

        total_reservations = reservations.count()
        average_price = brut_revenue / total_reservations

        # Fill all 12 months, even if 0
        monthly_revenue = [0] * 12
        for entry in monthly_data:
            month_index = entry["month"] - 1
            monthly_revenue[month_index] = float(entry["month"])

        context.update(
            {
                "selected_year": selected_year,
                "monthly_revenue": monthly_revenue,
                "available_years": sorted(all_years),
                "total_revenue": total_revenu,
                "platform_earnings": reservations.aggregate(Sum("platform_fee"))["platform_fee__sum"]
                or Decimal("0.00"),
                "total_payment_fee": reservations.aggregate(Sum("payment_fee"))["payment_fee__sum"] or Decimal("0.00"),
                "total_deposits": reservations.aggregate(Sum("amount_charged"))["amount_charged__sum"]
                or Decimal("0.00"),
                "total_refunds": total_refunds,
                "total_reservations": total_reservations,
                "average_price": average_price,
                "reservations": reservations.order_by("-date_reservation")[:100],
            }
        )

        try:
            balance = stripe.Balance.retrieve()
            context["stripe_balance_available"] = balance["available"][0]["amount"] / 100
            context["stripe_balance_pending"] = balance["pending"][0]["amount"] / 100
        except Exception:
            context["stripe_balance_available"] = None
            context["stripe_balance_pending"] = None

        return context


class RevenueView(LoginRequiredMixin, UserHasLogementMixin, TemplateView):
    template_name = "administration/revenu.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        logements = get_logements(self.request.user)

        year = self.request.GET.get("year")
        month = self.request.GET.get("month")
        logement_id = self.request.GET.get("logement_id")

        if logement_id == "" or logement_id is None:
            logement_id = None

        all_years = (
            Reservation.objects.filter(Q(statut="confirmee") | Q(statut="terminee"))
            .annotate(year=ExtractYear("start"))
            .values_list("year", flat=True)
            .distinct()
        )
        selected_year = int(year) if year and year.isdigit() else max(all_years, default=datetime.now().year)

        all_months = (
            Reservation.objects.filter(Q(statut="confirmee") | Q(statut="terminee"))
            .annotate(month=ExtractMonth("start"))
            .values_list("month", flat=True)
            .distinct()
        )
        selected_month = int(month) if month and month.isdigit() else max(all_months, default=datetime.now().month)

        reservations = get_valid_reservations_for_admin(self.request.user, logement_id, year, month)

        brut_revenue = reservations.aggregate(Sum("price"))["price__sum"] or Decimal("0.00")
        total_refunds = reservations.aggregate(Sum("refund_amount"))["refund_amount__sum"] or Decimal("0.00")
        platform_earnings = reservations.aggregate(Sum("platform_fee"))["platform_fee__sum"] or Decimal("0.00")
        total_payment_fee = reservations.aggregate(Sum("payment_fee"))["payment_fee__sum"] or Decimal("0.00")
        tax = reservations.aggregate(Sum("tax"))["tax__sum"] or Decimal("0.00")
        total_revenu = brut_revenue - total_refunds - platform_earnings - total_payment_fee - tax

        total_reservations = reservations.count()
        average_price = brut_revenue / total_reservations if total_reservations else Decimal("0.00")
        context.update(
            {
                "logement_id": logement_id,
                "logements": logements,
                "selected_year": selected_year,
                "available_years": sorted(all_years),
                "selected_month": selected_month,
                "available_months": sorted(all_months),
                "total_revenue": total_revenu,
                "platform_earnings": platform_earnings or Decimal("0.00"),
                "tax": tax,
                "total_payment_fee": total_payment_fee,
                "total_deposits": reservations.aggregate(Sum("amount_charged"))["amount_charged__sum"]
                or Decimal("0.00"),
                "total_refunds": total_refunds,
                "total_reservations": total_reservations,
                "average_price": average_price,
                "reservations": reservations.order_by("-date_reservation")[:100],
            }
        )

        # Group and aggregate by month
        monthly_data = (
            Reservation.objects.filter(
                Q(statut="confirmee") | Q(statut="terminee"),
                start__year=selected_year,
            )
            .annotate(month=TruncMonth("start"))
            .values("month")
            .annotate(
                brut=Sum("price"),
                refunds=Sum("refund_amount"),
                fees=Sum("payment_fee"),
                platform=Sum("platform_fee"),
                tax=Sum("tax"),
            )
            .order_by("month")
        )

        # Compute admin_fees manually
        monthly_manual_data = defaultdict(lambda: {
            "admin_transfer": 0,
            "owner_transfer": 0,
        })

        # Compute manually
        for reservation in Reservation.objects.filter(
            Q(statut="confirmee") | Q(statut="terminee"),
            start__year=selected_year,
        ):
            month = reservation.start.replace(day=1)
            monthly_manual_data[month]["admin_transfer"] += reservation.admin_transferable_amount or 0
            monthly_manual_data[month]["owner_transfer"] += reservation.transferable_amount - reservation.tax or 0

        # Merge into final monthly data list
        final_monthly_data = []
        for row in monthly_data:
            month = row["month"]
            manual_data = monthly_manual_data.get(month, {"admin_transfer": 0, "owner_transfer": 0})
            row["admin_transfer"] = manual_data["admin_transfer"]
            row["owner_transfer"] = manual_data["owner_transfer"]
            final_monthly_data.append(row)

        monthly_chart = defaultdict(
            lambda: {
                "revenue_brut": Decimal("0.00"),
                "revenue_net": Decimal("0.00"),
                "admin_revenue": Decimal("0.00"),
                "refunds": Decimal("0.00"),
                "payment_fee": Decimal("0.00"),
                "platform_fee": Decimal("0.00"),
                "tax": Decimal("0.00"),
            }
        )

        for item in monthly_data:
            month_key = item["month"].month
            monthly_chart[month_key]["revenue_brut"] = item["brut"] or Decimal("0.00")
            monthly_chart[month_key]["revenue_net"] = item["owner_transfer"] or Decimal("0.00")
            monthly_chart[month_key]["admin_revenue"] = item["admin_transfer"] or Decimal("0.00")
            monthly_chart[month_key]["refunds"] = item["refunds"] or Decimal("0.00")
            monthly_chart[month_key]["payment_fee"] = item["fees"] or Decimal("0.00")
            monthly_chart[month_key]["platform_fee"] = item["platform"] or Decimal("0.00")
            monthly_chart[month_key]["tax"] = item["tax"] or Decimal("0.00")

        chart_labels = [cal.month_abbr[m] for m in range(1, 13)]
        revenue_brut_data = [float(monthly_chart[m]["revenue_brut"]) for m in range(1, 13)]
        revenue_net_data = [float(monthly_chart[m]["revenue_net"]) for m in range(1, 13)]
        admin_revenue_data = [float(monthly_chart[m]["admin_revenue"]) for m in range(1, 13)]
        refunds_data = [float(monthly_chart[m]["refunds"]) for m in range(1, 13)]
        payment_fee_data = [float(monthly_chart[m]["payment_fee"]) for m in range(1, 13)]
        platform_fee_data = [float(monthly_chart[m]["platform_fee"]) for m in range(1, 13)]
        tax_data = [float(monthly_chart[m]["tax"]) for m in range(1, 13)]

        context.update(
            {
                "chart_labels": chart_labels,
                "revenue_brut_data": revenue_brut_data,
                "revenue_net_data": revenue_net_data,
                "admin_revenue_data": admin_revenue_data,
                "refunds_data": refunds_data,
                "payment_fee_data": payment_fee_data,
                "platform_fee_data": platform_fee_data,
                "tax_data": tax_data,
            }
        )

        return context


@require_POST
@login_required
@user_passes_test(is_stripe_admin)
def send_payment_link(request, code):
    try:
        reservation = Reservation.objects.get(code=code)
        send_stripe_payment_link(reservation)  # Your helper function
        messages.success(request, f"Lien de paiement envoyé à {reservation.user.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send payment link for {code}: {e}")
        messages.error(request, "Erreur lors de l'envoi du lien.")
    return redirect("administration:reservation_detail", code=code)


@login_required
@user_passes_test(is_admin)
def user_update_view(request, user_id=None):
    from accounts.models import CustomUser
    from administration.forms import UserAdminUpdateForm

    all_users = CustomUser.objects.all().order_by("username")

    # Fallback to query parameter if not provided in path
    if not user_id:
        user_id = request.GET.get("user_id")
        if user_id:
            return redirect("administration:user_update_view_with_id", user_id=user_id)

    # If still no ID, redirect to first user
    if not user_id and all_users.exists():
        return redirect("administration:user_update_view_with_id", user_id=all_users.first().id)

    selected_user = get_object_or_404(CustomUser, id=user_id)

    if request.method == "POST":
        form = UserAdminUpdateForm(request.POST, instance=selected_user)
        if form.is_valid():
            form.save()
            return redirect("administration:user_update_view_with_id", user_id=selected_user.id)
    else:
        form = UserAdminUpdateForm(instance=selected_user)

    return render(
        request,
        "administration/manage_users.html",
        {
            "form": form,
            "title": f"Modifier l'utilisateur : {selected_user.username}",
            "all_users": all_users,
            "selected_user": selected_user,
        },
    )


@login_required
@user_passes_test(is_admin)
def user_delete_view(request, user_id):
    from accounts.models import CustomUser

    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == "POST":
        user.delete()
        messages.success(request, "Utilisateur supprimé avec succès.")
        return redirect("administration:user_update_view")
    return redirect("administration:user_update_view_with_id", user_id=user_id)
