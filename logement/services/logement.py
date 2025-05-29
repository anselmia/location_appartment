import logging
from django.db.models import Q
from logement.models import Logement
import logging

from datetime import datetime

from django.core.paginator import Paginator
from django.db.models import Count, Q
from logement.services.reservation_service import get_available_logement_in_period
from logement.models import (
    Logement,
)

logger = logging.getLogger(__name__)


def get_logements(user):
    try:
        if user.is_admin:
            # Admin users can see all reservations
            qs = Logement.objects.all()
        else:
            # Non-admin users: filter logements where the user is either the owner or an admin
            qs = Logement.objects.filter(Q(owner=user) | Q(admin=user))

        return qs.order_by("name")

    except Exception as e:
        # Log the error and raise an exception
        logger.error(
            f"Error occurred while retrieving reservations: {e}", exc_info=True
        )
        # Optionally, you can re-raise the error or return a safe result, depending on the use case
        raise


def filter_logements(request):
    page_number = request.GET.get("page", 1)
    destination = request.GET.get("destination", "").strip()
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    guests = request.GET.get("guests")
    equipment_ids = request.GET.getlist("equipments")
    bedrooms = request.GET.get("bedrooms")
    bathrooms = request.GET.get("bathrooms")
    smoking = request.GET.get("is_smoking_allowed") == "1"
    animals = request.GET.get("is_pets_allowed") == "1"
    type = request.GET.get("type")

    logements = Logement.objects.prefetch_related("photos").filter(statut="open")

    if destination:
        logements = logements.filter(ville__name__icontains=destination)

    if guests:
        logements = logements.filter(max_traveler__gte=int(guests))

    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        logements = get_available_logement_in_period(start, end, logements)

    if equipment_ids:
        equipment_ids = [int(eid) for eid in equipment_ids]
        logements = logements.annotate(
            matched_equipment_count=Count(
                "equipment", filter=Q(equipment__id__in=equipment_ids), distinct=True
            )
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

    paginator = Paginator(logements, 9)
    page_obj = paginator.get_page(page_number)

    return page_obj, equipment_ids, guests, type
