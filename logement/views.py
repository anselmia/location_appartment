import json
import logging
import calendar as cal
from decimal import Decimal

from datetime import datetime, timedelta, date
from collections import defaultdict
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.views.generic import TemplateView
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.db.models import Sum
from django.db.models.functions import ExtractYear, ExtractMonth, TruncMonth

from logement.models import (
    Logement,
    Price,
    City,
    Equipment,
    EquipmentType,
    Photo,
    Room,
    CloseDate,
    Discount,
    DiscountType,
)
from logement.services.calendar_service import generate_ical
from logement.services.logement import filter_logements, get_logements, set_price
from logement.services.revenu import get_economie_stats
from logement.forms import LogementForm, DiscountForm
from logement.serializers import DailyPriceSerializer

from payment.services.payment_service import PAYMENT_FEE_VARIABLE

from reservation.models import airbnb_booking, booking_booking
from reservation.services.reservation_service import get_booked_dates
from reservation.services.reservation_service import (
    get_valid_reservations_for_admin,
    get_valid_reservations_in_period,
    get_night_booked_in_period,
)

from logement.decorators import (
    user_has_logement,
    user_is_logement_admin,
)
from logement.mixins import UserHasLogementMixin
from common.services.helper_fct import normalize_decimal_input

logger = logging.getLogger(__name__)


def autocomplete_cities(request):
    q = request.GET.get("q", "")
    try:
        cities = City.objects.filter(name__icontains=q).order_by("name")[:5]
        logger.info(f"Autocomplete for query '{q}', {cities.count()} results")
        return HttpResponse("".join(f"<option value='{c.name}'></option>" for c in cities))
    except Exception as e:
        logger.exception(f"Autocomplete city search failed: {e}")
        return JsonResponse({"error": "Erreur interne serveur"}, status=500)  # ← Add this


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

        photos = logement.photos.all()

        return render(
            request,
            "logement/view_logement.html",
            {
                "logement": logement,
                "rooms": rooms,
                "reserved_dates_start_json": json.dumps(sorted(reserved_dates_start)),
                "reserved_dates_end_json": json.dumps(sorted(reserved_dates_end)),
                "photo_urls": [p.image.url for p in photos],
                "rooms_labels": [p.room.name for p in photos],
                "grouped_equipment": grouped_equipment,
                "EquipmentType": EquipmentType,
                "payment_fee": PAYMENT_FEE_VARIABLE * 100,
            },
        )
    except Exception as e:
        logger.exception(f"Error loading logement detail: {e}")
        raise


@login_required
def get_price_for_date(request, logement_id, date):
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        logement = get_object_or_404(Logement, id=logement_id)
        price = Price.objects.filter(logement=logement, date=parsed_date).first()
        logger.info(f"Price requested for logement {logement_id} on {date}")
        return JsonResponse({"price": str(price.value) if price else str(logement.price)})
    except Logement.DoesNotExist:
        logger.warning(f"Logement {logement_id} not found")
        return JsonResponse({"error": "Logement not found"}, status=404)
    except Exception as e:
        logger.exception(f"Failed to fetch price for date: {e}")
        return JsonResponse({"error": "Erreur interne serveur"}, status=500)


@require_GET
def export_ical(request, code):
    try:
        ics_content = generate_ical(code)
        if ics_content:
            response = HttpResponse(ics_content, content_type="text/calendar")
            response["Content-Disposition"] = f"attachment; filename={code}_calendar.ics"
            return response
        else:
            return HttpResponse("Aucune donnée à exporter", status=204)
    except Exception as e:
        logger.exception(f"Error exporting iCal:  {e}")


@require_GET
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
        raise


@login_required
@user_has_logement
def logement_dashboard(request):
    try:
        logements = get_logements(request.user)
        return render(request, "logement/dashboard.html", {"logements": logements})
    except Exception as e:
        logger.exception(f"Error rendering admin dashboard: {e}")
        raise


@login_required
@user_has_logement
@user_is_logement_admin
@require_http_methods(["GET", "POST"])
def manage_logement(request, logement_id=None):
    try:
        logement = None
        is_editing = logement_id is not None

        if is_editing:
            logement = get_object_or_404(Logement.objects.prefetch_related("rooms", "photos", "equipment"), id=logement_id)

        form = LogementForm(request.POST or None, instance=logement, user=request.user)

        if request.method == "POST" and form.is_valid():
            logement = form.save()
            if is_editing:
                logger.info(f"Logement {logement.id} updated")
            else:
                logger.info(f"Logement created with ID {logement.id}")
            return redirect("logement:edit_logement", logement.id)

        rooms = logement.rooms.all().order_by("name") if logement else []
        photos = logement.photos.all().order_by("order") if logement else []
        all_equipment = Equipment.objects.all().order_by("name")
        selected_equipment_ids = logement.equipment.values_list("id", flat=True) if logement else []

        grouped_equipment = defaultdict(list)
        for equip in all_equipment:
            grouped_equipment[equip.type].append(equip)

        pricing_fields = [
            ("price", "€"),
            ("fee_per_extra_traveler", "€"),
            ("cleaning_fee", "€"),
            ("caution", "€"),
            ("admin_fee", "%"),
            ("tax", "%"),
            ("tax_max", "€"),
        ]

        timing_fields = [
            ("cancelation_period", "jour(s)"),
            ("ready_period", "jour(s)"),
            ("max_days", "jour(s)"),
            ("availablity_period", "mois"),
        ]

        pricing_bound_fields = [(form[name], unit) for name, unit in pricing_fields]
        timing_bound_fields = [(form[name], unit) for name, unit in timing_fields]

        return render(
            request,
            "logement/edit_logement.html",  # Same template for both
            {
                "form": form,
                "logement": logement,
                "rooms": rooms,
                "photos": photos,
                "grouped_equipment": grouped_equipment,
                "pricing_fields": pricing_bound_fields,
                "timing_fields": timing_bound_fields,
                "selected_equipment_ids": selected_equipment_ids,
                "is_editing": is_editing,
                "equipment_type_choices": EquipmentType.choices,  # if not already passed
            },
        )
    except Exception as e:
        logger.exception(f"Error {'editing' if logement_id else 'adding'} logement: {e}")
        raise


@login_required
@user_is_logement_admin
def add_room(request, logement_id):
    try:
        room_name = request.POST.get("name", "").strip()
        if not room_name:
            messages.error(request, "Nom de pièce invalide.")
            return redirect("logement:edit_logement", logement_id)

        logement = get_object_or_404(Logement, id=logement_id)
        Room.objects.create(name=room_name, logement=logement)
        logger.info(f"Room added to logement {logement_id}")
        return redirect("logement:edit_logement", logement_id)
    except Exception as e:
        logger.exception(f"Error adding room to logement {logement_id}: {e}")
        raise


@login_required
@user_is_logement_admin
@require_POST
def delete_room(request, room_id):
    try:
        room = get_object_or_404(Room, id=room_id)
        logement_id = room.logement.id
        room.delete()
        logger.info(f"Room {room_id} deleted")
        return redirect("logement:edit_logement", logement_id)
    except Exception as e:
        logger.exception(f"Error deleting room {room_id}: {e}")
        raise


MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB


@login_required
@user_is_logement_admin
@require_POST
def upload_photos(request, logement_id):
    try:
        files = request.FILES.getlist("photo")
        for f in files:
            if f.size > MAX_UPLOAD_SIZE:
                messages.error(request, f"Le fichier '{f.name}' dépasse la taille maximale de 2 Mo.")
                return redirect("logement:edit_logement", logement_id=logement_id)
        logement = get_object_or_404(Logement, id=logement_id)
        room_id = request.POST.get("room_id")
        room = get_object_or_404(Room, id=room_id, logement=logement)

        for uploaded_file in files:
            try:
                Photo.objects.create(logement=logement, room=room, image=uploaded_file)
            except Exception as e:
                logger.warning(f"Failed to save photo '{uploaded_file.name}': {e}")

        logger.info(f"Photos uploaded for logement {logement_id} in room {room_id}")
        return redirect("logement:edit_logement", logement_id)
    except Exception as e:
        logger.exception(f"Error uploading photos for logement {logement_id}: {e}")
        raise


@login_required
@user_is_logement_admin
@require_POST
def change_photo_room(request, photo_id):
    try:
        photo = get_object_or_404(Photo, id=photo_id)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

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
        return redirect("logement:edit_logement", logement.id)
    except Exception as e:
        logger.exception(f"Error updating equipment for logement {logement_id}: {e}")
        raise


@login_required
@user_has_logement
def calendar(request):
    try:
        logements = get_logements(request.user)

        if not logements.exists():
            messages.info(request, "Vous devez ajouter un logement avant d’accéder au tableau de revenus.")
            return redirect("logement:dashboard")

        return render(
            request,
            "logement/calendar.html",
            {
                "logements": logements,
                "logements_json": [{"id": l.id, "name": l.name, "calendar_link": l.calendar_link} for l in logements],
            },
        )
    except Exception as e:
        logger.error(f"Error occurred in calendar view: {e}", exc_info=True)
        raise


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

            logement = get_object_or_404(Logement, id=logement_id)
            default_price = logement.price

            start = datetime.fromisoformat(start_str).date()
            end = datetime.fromisoformat(end_str).date()

            custom_prices = Price.objects.filter(logement_id=logement_id, date__range=(start, end))
            price_map = {p.date: p.value for p in custom_prices}

            closed_date = CloseDate.objects.filter(logement_id=logement_id, date__range=(start, end))
            statut_map = {p.date: 0 for p in closed_date}

            daily_data = [
                {
                    "date": (start + timedelta(days=i)).isoformat(),
                    "price": price_map.get(start + timedelta(days=i), str(default_price)),
                    "statut": 0 if (start + timedelta(days=i)) in statut_map else 1,
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
                for b in get_valid_reservations_in_period(logement_id, start, end)
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

            closed_days = [{"date": c.date.isoformat()} for c in closed_date]

            return Response(
                {
                    "data": daily_data,
                    "data_bookings": data_bookings,
                    "airbnb_bookings": airbnb_bookings,
                    "booking_bookings": booking_bookings,
                    "closed_days": closed_days,
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
            price = float(request.data.get("price"))
            statut = int(request.data.get("statut"))

            if not price or price <= 0:
                return Response({"error": "Le prix doit être supérieur à 0."}, status=400)

            if not all([logement_id, start, end]):
                return Response({"error": "Missing required parameters."}, status=400)

            for i in range((end - start).days + 1):
                day = start + timedelta(days=i)
                Price.objects.update_or_create(logement_id=logement_id, date=day, defaults={"value": price})

                if statut == 0:
                    # Mark as closed
                    CloseDate.objects.get_or_create(logement_id=logement_id, date=day)
                else:
                    # Ensure it's marked open (remove CloseDate if exists)
                    CloseDate.objects.filter(logement_id=logement_id, date=day).delete()

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

            logement = get_object_or_404(Logement, id=logement_id)
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()

            price_data = set_price(logement, start, end, guestCount, base_price)

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


@login_required
@user_has_logement
def manage_discounts(request):
    try:
        logements = get_logements(request.user)
        logement_id = request.GET.get("logement_id") or request.POST.get("logement_id")
        logement = get_object_or_404(Logement, id=logement_id) if logement_id else logements.first()

        if not logement:
            messages.info(request, "Vous devez ajouter un logement avant d’accéder au tableau de revenus.")
            return redirect("logement:dashboard")

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
                        "logement/discounts.html",
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
                        "logement/discounts.html",
                        {
                            "logement": logement,
                            "discounts": discounts,
                            "discount_types": discount_types,
                            "all_logements": logements,
                            "form": form,
                        },
                    )

            return redirect(f"{reverse('logement:manage_discounts')}?logement_id={logement.id}")

        return render(
            request,
            "logement/discounts.html",
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
        raise


class RevenueView(LoginRequiredMixin, UserHasLogementMixin, TemplateView):
    template_name = "logement/revenu.html"

    def dispatch(self, request, *args, **kwargs):
        logements = get_logements(request.user)

        if not logements.exists():
            messages.info(request, "Vous devez ajouter un logement avant d’accéder au tableau de revenus.")
            return redirect("logement:dashboard")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        logements = get_logements(self.request.user)

        year = self.request.GET.get("year")
        month = self.request.GET.get("month")
        logement_id = self.request.GET.get("logement_id")

        if logement_id == "" or logement_id is None:
            logement_id = None
        else:
            logement_id = int(logement_id)

        reservations = get_valid_reservations_for_admin(self.request.user)

        all_years = reservations.annotate(year=ExtractYear("start")).values("year").distinct().order_by("year")
        all_years = [y["year"] for y in all_years]

        selected_year = int(year) if year and year.isdigit() else max(all_years, default=datetime.now().year)

        all_months = (
            reservations.filter(start__year=selected_year)
            .annotate(month=ExtractMonth("start"))
            .values("month")
            .distinct()
            .order_by("month")
        )
        all_months = [m["month"] for m in all_months]
        selected_month = int(month) if month and month.isdigit() else max(all_months, default=datetime.now().month)

        reservations = get_valid_reservations_for_admin(self.request.user, logement_id, selected_year, selected_month)

        brut_revenue = reservations.aggregate(Sum("price"))["price__sum"] or Decimal("0.00")
        total_refunds = reservations.aggregate(Sum("refund_amount"))["refund_amount__sum"] or Decimal("0.00")
        platform_earnings = reservations.aggregate(Sum("platform_fee"))["platform_fee__sum"] or Decimal("0.00")
        total_payment_fee = reservations.aggregate(Sum("payment_fee"))["payment_fee__sum"] or Decimal("0.00")
        tax = reservations.aggregate(Sum("tax"))["tax__sum"] or Decimal("0.00")
        total_revenu = brut_revenue - total_refunds - platform_earnings - total_payment_fee

        total_reservations = reservations.count()
        average_price = brut_revenue / total_reservations if total_reservations else Decimal("0.00")

        nights_in_month = cal.monthrange(selected_year, selected_month)[1]
        # Dates du mois sélectionné
        month_start = date(selected_year, selected_month, 1)
        last_day = cal.monthrange(selected_year, selected_month)[1]
        month_end = date(selected_year, selected_month, last_day)

        # Calcul des nuitées réservées sur cette période
        reserved_nights = get_night_booked_in_period(logements, logement_id, month_start, month_end)

        occupancy_rate = (
            round((reserved_nights / (nights_in_month * (logements.count() if not logement_id else 1))) * 100, 1)
            if nights_in_month
            else 0
        )

        context.update(
            {
                "logement_id": logement_id,
                "logements": logements,
                "selected_year": selected_year,
                "available_years": all_years,
                "selected_month": selected_month,
                "available_months": all_months,
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
                "occupancy_rate": occupancy_rate,
                "days_booked": reserved_nights,
            }
        )

        reservations = get_valid_reservations_for_admin(self.request.user, logement_id, selected_year)

        # Group and aggregate by month
        monthly_data = (
            reservations.annotate(month=TruncMonth("start"))
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
        monthly_manual_data = defaultdict(
            lambda: {
                "admin_transfer": 0,
                "owner_transfer": 0,
            }
        )

        # Compute manually
        for reservation in reservations:
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


def api_economie_data(request, logement_id):
    try:
        year = int(request.GET.get("year", datetime.now().year))
        month = request.GET.get("month", "all")
        data = get_economie_stats(logement_id=logement_id, year=year, month=month)
        return JsonResponse(data)
    except Exception as e:
        logger.exception(f"Erreur dans api_economie_data: {e}")
        return JsonResponse({"error": "Erreur interne serveur"}, status=500)
