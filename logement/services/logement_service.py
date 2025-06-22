import logging
import hashlib
import json
from typing import Any, Dict, List, Optional
from collections import defaultdict

from django.core.cache import cache
from django.db.models import Count, Q
from django.utils.dateparse import parse_date
from django.utils.formats import number_format
from django.urls import reverse
from django.templatetags.static import static

from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

from logement.models import Logement, Equipment, Photo, Room, EquipmentType, City
from logement.forms import LogementForm
from reservation.services.logement import get_booked_dates
from payment.services.payment_service import PAYMENT_FEE_VARIABLE

logger = logging.getLogger(__name__)


def get_logements(user: Any) -> Any:
    """
    Retrieve logements accessible to the user, using caching for efficiency.
    - Admins and superusers see all logements.
    - Regular users see logements where they are owner or admin.
    """
    try:
        cache_key = f"user_logements_{user.id}"
        logements = cache.get(cache_key)
        if logements:
            return logements

        # Determine queryset based on user role
        if user.is_admin or user.is_superuser:
            qs = Logement.objects.all()
        else:
            qs = Logement.objects.filter(Q(owner=user) | Q(admin=user))

        logements = qs.order_by("name")
        cache.set(cache_key, logements, 300)  # Cache for 5 minutes
        return logements
    except Exception as e:
        logger.error(f"Error occurred while retrieving reservations: {e}", exc_info=True)
        raise


def filter_logements(
    destination: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    guest_adult: Optional[int],
    guest_minor: Optional[int],
    equipment_ids: Optional[List[int]],
    bedrooms: Optional[int],
    bathrooms: Optional[int],
    smoking: Optional[bool],
    animals: Optional[bool],
    type: Optional[str],
) -> Any:
    """
    Filter logements based on search criteria, using cache for performance.
    """
    from reservation.services.logement import get_available_logement_in_period

    # Build a unique cache key based on all filter parameters
    key_input = f"{destination}-{start_date}-{end_date}-{guest_adult}-{guest_minor}-{equipment_ids}-{bedrooms}-{bathrooms}-{smoking}-{animals}-{type}"
    cache_key = f"filtered_logements_{hashlib.md5(key_input.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    logements = Logement.objects.prefetch_related("photos").filter(statut="open")

    # Apply filters step by step
    if destination:
        logements = logements.filter(ville__name__icontains=destination)

    if guest_adult is not None and guest_minor is not None:
        total_guests = int(guest_adult) + int(guest_minor)
        logements = logements.filter(max_traveler__gte=total_guests)

    if start_date and end_date:
        start = parse_date(start_date)
        end = parse_date(end_date)
        if not start or not end:
            raise ValueError("Invalid start_date or end_date format")
        logements = get_available_logement_in_period(start, end, logements)

    if equipment_ids:
        equipment_ids = [int(eid) for eid in equipment_ids]
        logements = logements.annotate(
            matched_equipment_count=Count("equipment", filter=Q(equipment__id__in=equipment_ids), distinct=True)
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

    cache.set(cache_key, logements, 300)
    return logements


# Logement form data


def get_logement_form_data(logement: Optional[Logement], user) -> Dict[str, Any]:
    """
    Prepare data for the logement form, including rooms, photos, equipment, and form fields.
    """
    form = LogementForm(instance=logement, user=user)
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
        ("min_booking_days", "jour(s)"),
        ("cancelation_period", "jour(s)"),
        ("ready_period", "jour(s)"),
        ("max_days", "jour(s)"),
        ("availablity_period", "mois"),
    ]
    pricing_bound_fields = [(form[name], unit) for name, unit in pricing_fields]
    timing_bound_fields = [(form[name], unit) for name, unit in timing_fields]
    return {
        "form": form,
        "rooms": rooms,
        "photos": photos,
        "all_equipment": all_equipment,
        "selected_equipment_ids": selected_equipment_ids,
        "grouped_equipment": grouped_equipment,
        "pricing_bound_fields": pricing_bound_fields,
        "timing_bound_fields": timing_bound_fields,
    }


# Room management


def add_room_to_logement(post_data, logement_id: int) -> Dict[str, str]:
    """
    Add a room to a logement.
    """
    room_name = post_data.get("name", "").strip()
    if not room_name:
        return {"success": False, "error": "Nom de pièce invalide."}
    logement = get_object_or_404(Logement, id=logement_id)
    Room.objects.create(name=room_name, logement=logement)
    logger.info(f"Room added to logement {logement_id}")
    return {"success": True}


def delete_room_by_id(room_id: int) -> Dict[str, str]:
    """
    Delete a room by its ID.
    """
    try:
        room = get_object_or_404(Room, id=room_id)
        logement_id = room.logement.id
        room.delete()
        logger.info(f"Room {room_id} deleted")
        return {"success": True, "logement_id": logement_id}
    except Exception as e:
        logger.exception(f"Error deleting room {room_id}: {e}")
        return {"success": False, "error": str(e)}


# Photo management


def upload_photos_to_logement(files, logement_id: int, room_id: int) -> Dict[str, Any]:
    """
    Upload photos to a logement for a specific room.
    """
    MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB
    logement = get_object_or_404(Logement, id=logement_id)
    room = get_object_or_404(Room, id=room_id, logement=logement)
    for f in files:
        if f.size > MAX_UPLOAD_SIZE:
            return {"success": False, "error": f"Le fichier '{f.name}' dépasse la taille maximale de 2 Mo."}
    for uploaded_file in files:
        try:
            Photo.objects.create(logement=logement, room=room, image=uploaded_file)
        except Exception as e:
            logger.warning(f"Failed to save photo '{uploaded_file.name}': {e}")
    logger.info(f"Photos uploaded for logement {logement_id} in room {room_id}")
    return {"success": True}


def change_photo_room_service(photo_id: int, request_body: bytes) -> Dict:
    """
    Change the room associated with a photo.
    """
    try:
        photo = get_object_or_404(Photo, id=photo_id)
        try:
            import json

            data = json.loads(request_body)
        except (json.JSONDecodeError, ValueError):
            return {"success": False, "error": "Invalid JSON", "status": 400}
        room_id = data.get("room_id")
        if not room_id:
            return {"success": False, "error": "Room ID is required", "status": 400}
        room = get_object_or_404(Room, id=room_id)
        photo.room = room
        photo.save()
        logger.info(f"Photo {photo_id} assigned to room {room_id}")
        return {"success": True}
    except Exception as e:
        logger.exception(f"Error changing photo room: {e}")
        return {"success": False, "error": str(e)}


# Search


def get_logement_search_context(request) -> Dict:
    """
    Prepare context for the logement search.
    """
    # Setup
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

    # Query parameters
    page_number = int(request.GET.get("page", 1) or 1)
    destination = request.GET.get("destination") or None
    start_date = request.GET.get("start_date") or None
    end_date = request.GET.get("end_date") or None
    guest_adult = int(request.GET.get("guest_adult") or 0)
    guest_minor = int(request.GET.get("guest_minor") or 0)
    equipment_ids = request.GET.getlist("equipments") or []
    bedrooms = int(request.GET.get("bedrooms") or 0)
    bathrooms = int(request.GET.get("bathrooms") or 0)
    smoking = request.GET.get("is_smoking_allowed") == "1"
    animals = request.GET.get("is_pets_allowed") == "1"
    type = request.GET.get("type") or None

    # Filtering
    logements = filter_logements(
        destination,
        start_date,
        end_date,
        guest_adult,
        guest_minor,
        equipment_ids,
        bedrooms,
        bathrooms,
        smoking,
        animals,
        type,
    )

    paginator = Paginator(logements, 9)
    page_obj = paginator.get_page(page_number)

    selected_equipment_ids = [str(eid) for eid in equipment_ids]
    guest_adult = int(guest_adult) if guest_adult and str(guest_adult).isdigit() else 1
    guest_minor = int(guest_minor) if guest_minor and str(guest_minor).isdigit() else 0

    logger.info(f"🔎 Search returned {page_obj.paginator.count} logements")

    # JSON data for logements with coordinates
    all_logements_json = json.dumps(
        [
            {
                "id": l.id,
                "name": l.name,
                "lat": float(str(l.latitude).replace(",", ".")),
                "lng": float(str(l.longitude).replace(",", ".")),
                "price": number_format(l.price, decimal_pos=2, use_l10n=False) if l.price else "0.00",
                "url": reverse("logement:view_logement", args=[l.id]),
                "book_url": reverse("reservation:book_logement", args=[l.id]),
                "image": (l.photos.first().image_webp.url if l.photos.first() else static("logement/img/no-photo.jpg")),
                "city": l.ville.name if l.ville else "",
                "max_traveler": l.max_traveler,
            }
            for l in logements
            if l.latitude and l.longitude
        ]
    )

    context = {
        "logements": page_obj,
        "equipments": equipments,
        "destination": destination,
        "guest_adult": guest_adult,
        "guest_minor": guest_minor,
        "page_obj": page_obj,
        "selected_equipment_ids": selected_equipment_ids,
        "number_range": number_range,
        "types": types,
        "selected_type": type,
        "all_logements": all_logements_json,
    }
    return context


# Dashboard


def get_logement_dashboard_context(user, request) -> Dict:
    """
    Prepare context for the logement dashboard.
    """
    logements = get_logements(user)
    paginator = Paginator(logements, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "logements": page_obj,
        "page_obj": page_obj,
    }
    return context


# Detail


def get_logement_detail_context(logement_id: int, user) -> dict:
    """
    Get the context for a specific logement's detail page.
    """
    logement = get_object_or_404(Logement.objects.prefetch_related("photos"), id=logement_id)
    rooms = logement.rooms.all()
    grouped_equipment = defaultdict(list)
    for equip in logement.equipment.all():
        grouped_equipment[equip.type].append(equip)
    reserved_dates_start, reserved_dates_end = get_booked_dates(logement, user)
    photos = logement.photos.all()
    context = {
        "logement": logement,
        "rooms": rooms,
        "reserved_dates_start_json": json.dumps(sorted(reserved_dates_start)),
        "reserved_dates_end_json": json.dumps(sorted(reserved_dates_end)),
        "photo_urls": [p.image.url for p in photos],
        "rooms_labels": [p.room.name for p in photos],
        "grouped_equipment": grouped_equipment,
        "EquipmentType": EquipmentType,
        "payment_fee": PAYMENT_FEE_VARIABLE * 100,
    }
    return context


# Equipment


def update_logement_equipment(logement_id: int, equipment_ids: List[int]) -> bool:
    """
    Update the equipment for a logement.
    """
    logement = get_object_or_404(Logement, id=logement_id)
    logement.equipment.set(equipment_ids)
    logger.info(f"Updated equipment for logement {logement_id}")
    return True


# Autocomplete


def autocomplete_cities_service(query: str):
    """
    Autocomplete city names based on a query.
    """
    try:
        cities = City.objects.filter(name__icontains=query).order_by("name")[:5]
        logger.info(f"Autocomplete for query '{query}', {cities.count()} results")
        return {"success": True, "options": "".join(f"<option value='{c.name}'></option>" for c in cities)}
    except Exception as e:
        logger.exception(f"Autocomplete city search failed: {e}")
        return {"success": False, "error": "Erreur interne serveur"}
