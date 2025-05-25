from datetime import datetime, timedelta
import os
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
from logement.forms import DiscountForm, LogementForm
from django.contrib import messages
from .forms import (
    HomePageConfigForm,
    ServiceForm,
    TestimonialForm,
    CommitmentForm,
    EntrepriseForm,
)

from .models import SiteVisit, HomePageConfig, Entreprise
from .serializers import DailyPriceSerializer
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from administration.services.revenu import get_economie_stats
from django.http import JsonResponse, HttpResponseBadRequest
from logement.services.reservation_service import (
    calculate_price,
    get_valid_reservations_for_admin,
    get_reservation_years_and_months,
    mark_reservation_cancelled,
)
from logement.services.logement import get_logements
from common.views import is_admin
from logement.services.payment_service import refund_payment, charge_payment
from decimal import Decimal, InvalidOperation
from administration.services.traffic import get_traffic_dashboard_data
from administration.services.logs import parse_log_file
from common.decorators import (
    user_is_logement_admin,
    user_has_logement,
    user_is_reservation_admin,
)


logger = logging.getLogger(__name__)


@login_required
@user_has_logement
def admin_dashboard(request):
    # Get the logements based on the user
    logements = get_logements(request.user)
    return render(request, "administration/dashboard.html", {"logements": logements})


@login_required
@user_has_logement
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
@user_is_logement_admin
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
@user_is_logement_admin
def add_room(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    Room.objects.create(name=request.POST["name"], logement=logement)
    return redirect("administration:edit_logement", logement_id)


@login_required
@user_is_logement_admin
@require_POST
def delete_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    logement_id = room.logement.id
    room.delete()
    return redirect("administration:edit_logement", logement_id)


@login_required
@user_is_logement_admin
@require_POST
def upload_photos(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)
    room_id = request.POST.get("room_id")
    room = get_object_or_404(Room, id=room_id, logement=logement)

    for uploaded_file in request.FILES.getlist("photo"):
        Photo.objects.create(logement=logement, room=room, image=uploaded_file)

    return redirect("administration:edit_logement", logement_id)


# Change the room of a photo
@login_required
@user_is_logement_admin
@require_POST
def change_photo_room(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id)
    try:
        data = json.loads(request.body)
        room_id = data.get("room_id")
        if not room_id:
            return JsonResponse(
                {"success": False, "error": "Missing room_id"}, status=400
            )

        room = get_object_or_404(Room, id=room_id, logement=photo.logement)
        photo.assign_room(room)
        return JsonResponse({"success": True})

    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)


# Move photo up or down
@login_required
@user_is_logement_admin
@require_POST
def move_photo(request, photo_id, direction):
    photo = get_object_or_404(Photo, id=photo_id)

    success, message = photo.move_in_order(direction)
    if success:
        return JsonResponse({"success": True})
    return JsonResponse({"success": False, "message": message}, status=400)


@login_required
@user_is_logement_admin
@require_http_methods(["DELETE"])
def delete_photo(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id)
    photo.safe_delete()
    return JsonResponse({"success": True})


@login_required
@user_is_logement_admin
@require_POST
def delete_all_photos(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)

    for photo in logement.photos.all():
        photo.safe_delete()

    return JsonResponse({"status": "ok"})


@login_required
@user_is_logement_admin
@require_POST
def rotate_photo(request, photo_id):
    degrees = int(request.POST.get("degrees", 90))
    photo = get_object_or_404(Photo, pk=photo_id)

    photo.rotate(degrees)
    return JsonResponse({"status": "ok", "rotation": photo.rotation})


@login_required
@user_is_logement_admin
def update_equipment(request, logement_id):
    logement = get_object_or_404(Logement, id=logement_id)

    if request.method == "POST":
        equipment_ids = request.POST.getlist("equipment")
        logement.equipment.set(equipment_ids)

    return redirect("administration:edit_logement", logement.id)


@login_required
@user_passes_test(is_admin)
def traffic_dashboard(request):
    period = (
        request.POST.get("period")
        if request.method == "POST"
        else request.GET.get("period", "day")
    )

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


@login_required
@user_has_logement
def calendar(request):
    try:
        # Get the logements based on the user
        logements = get_logements(request.user)

        # Return the rendered page with logements data
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

    except Exception as e:
        # Log the error with the exception details
        logger.error(f"Error occurred in calendar view: {e}", exc_info=True)

        # Optionally, return a safe error page with a user-friendly message
        return render(
            request,
            "common/error.html",  # Reuse the error template from the common app
            {
                "error_message": "Une erreur est survenue en essayant d'accéder au calendrier"
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
@user_has_logement
def manage_discounts(request):
    # Get the logements based on the user
    logements = get_logements(request.user)

    logement_id = request.GET.get("logement_id") or request.POST.get("logement_id")
    logement = (
        get_object_or_404(Logement, id=logement_id)
        if logement_id
        else logements.first()
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
                        "all_logements": logements,
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
            "all_logements": logements,
            "form": DiscountForm(),
        },
    )


@login_required
@user_has_logement
@require_http_methods(["GET", "POST"])
def economie_view(request):
    # Get the logements based on the user
    logements = get_logements(request.user)

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

    data = get_economie_stats(logement_id=logement_id, year=year, month=month)
    return JsonResponse(data)


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
            {
                "error_message": "Une erreur est survenue en récupérant les réservations."
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
@user_is_reservation_admin
def reservation_detail(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    return render(
        request, "administration/reservation_detail.html", {"reservation": reservation}
    )


@login_required
@user_is_reservation_admin
@require_POST
def cancel_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    if reservation.statut != "annulee":
        mark_reservation_cancelled(reservation)
        messages.success(request, "Réservation annulée avec succès.")
    else:
        messages.warning(request, "La réservation est déjà annulée.")
    return redirect("administration:reservation_detail", pk=pk)


@login_required
@user_is_reservation_admin
@require_POST
def refund_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    if not reservation.refunded:
        try:
            amount_in_cents = int(reservation.refundable_amount * 100)

            refund = refund_payment(reservation, amount_in_cents)

            messages.success(
                request,
                f"Une demande de remboursement de {reservation.refundable_amount:.2f} € a été effectuée avec succès.",
            )
        except Exception as e:
            messages.error(request, f"Erreur de remboursement Stripe : {e}")
            logger.exception("Stripe refund failed")
    else:
        messages.warning(request, "Cette réservation a déjà été remboursée.")

    return redirect("administration:reservation_detail", pk=pk)


@login_required
@user_is_reservation_admin
@require_POST
def refund_partially_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    if reservation.refunded:
        messages.warning(request, "Cette réservation a déjà été remboursée.")
        return redirect("administration:reservation_detail", pk=pk)

    try:
        amount_str = request.POST.get("refund_amount")
        refund_amount = Decimal(amount_str)

        if refund_amount <= 0 or refund_amount > reservation.price:
            messages.error(
                request,
                "Montant invalide. Il doit être supérieur à 0 et inférieur ou égal au montant total.",
            )
            return redirect("administration:reservation_detail", pk=pk)

        amount_in_cents = int(refund_amount * 100)
        refund = refund_payment(reservation, amount_in_cents)

        messages.success(
            request,
            f"Remboursement partiel de {refund_amount:.2f} € effectué avec succès.",
        )

    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Montant de remboursement invalide.")
    except Exception as e:
        messages.error(request, f"Erreur de remboursement Stripe : {e}")
        logger.exception("Stripe refund failed")

    return redirect("administration:reservation_detail", pk=pk)


@login_required
@user_is_reservation_admin
@require_POST
def charge_deposit(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    try:
        amount = Decimal(request.POST.get("deposit_amount"))

        if amount <= 0:
            messages.error(request, "Le montant doit être supérieur à 0.")
            return redirect("administration:reservation_detail", pk=pk)

        logement_caution = getattr(reservation.logement, "caution", None)
        if logement_caution is not None and amount > reservation.chargeable_deposit:
            messages.error(
                request,
                f"Le montant de la caution ({amount:.2f} €) dépasse la limite autorisée pour ce logement ({logement_caution:.2f} €).",
            )
            return redirect("administration:reservation_detail", pk=pk)

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

    return redirect("administration:reservation_detail", pk=pk)
