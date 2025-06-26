import logging
from typing import Any, Dict, List
from django.utils import timezone
from django.db.models import Sum
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from activity.models import Activity
from reservation.models import ActivityReservationHistory, ActivityReservation
from accounts.models import CustomUser
from reservation.services.reservation_service import (
    get_valid_reservations,
    get_future_reservations,
    get_payment_failed_reservations,
)
from reservation.services.activity import get_activity_reservations_queryset

logger = logging.getLogger(__name__)


def get_activity(user: Any) -> Any:
    """
    Retrieve activities accessible to the user, using caching for efficiency.
    - Admins and superusers see all activities.
    - Regular users see activities where they are owner.
    """
    try:
        cache_key = f"user_activities_{user.id}"
        activities = cache.get(cache_key)
        if activities:
            return activities

        # Determine queryset based on user role
        if user.is_admin or user.is_superuser:
            qs = Activity.objects.all()
        else:
            qs = Activity.objects.filter(owner=user)

        activities = qs.order_by("name")
        cache.set(cache_key, activities, 300)  # Cache for 5 minutes
        return activities
    except Exception as e:
        logger.error(f"Error occurred while retrieving activities: {e}", exc_info=True)
        raise


def get_calendar_context(user):
    activities = get_activity(user)
    if not activities.exists():
        return {"redirect": True}
    return {
        "activities": activities,
        "activities_json": [{"id": a.id, "name": a.name} for a in activities],
    }


def get_activity_statistics(activity_id: int, user: CustomUser) -> Dict[str, Any]:
    """
    Get statistics for a specific activity.
    """
    activity = get_object_or_404(Activity, id=activity_id)
    actual_year = timezone.now().year
    reservations = get_valid_reservations(
        user,
        activity_id,
        obj_type="activity",
        get_queryset_fn=get_activity_reservations_queryset,
        cache_prefix="valid_activity_resa_admin",
        select_related_fields=["user", "activity"],
        prefetch_related_fields=["activity__photos"],
        year=actual_year,
    )
    futur_reservations = get_future_reservations(ActivityReservation, activity)

    stats = {
        "total_bookings": reservations.count(),
        "total_revenue": reservations.aggregate(total=Sum("price"))["total"] or 0,
        "futur_reservations": futur_reservations,
        "failed_reservations": get_payment_failed_reservations(ActivityReservation, activity),
    }

    return stats


def get_activities_overview(user) -> List[Dict[str, Any]]:
    """
    Get an overview of all activities with basic details.
    """
    if user.is_admin or user.is_superuser:
        activities = Activity.objects.all()
    elif user.is_authenticated:
        activities = Activity.objects.filter(owner=user)
    else:
        activities = Activity.objects.none()

    total_bookings = 0
    total_revenue = 0
    all_futur_reservations = []
    total_failed_reservations = []

    for activity in activities:
        stat = get_activity_statistics(activity.id, user)
        total_bookings += stat["total_bookings"]
        total_revenue += stat["total_revenue"]
        all_futur_reservations += list(stat["futur_reservations"])
        total_failed_reservations += list(stat["failed_reservations"])

    stats = {
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "futur_reservations": all_futur_reservations,
        "total_failed_reservations": total_failed_reservations,
        "futur_reservations_count": len(all_futur_reservations),
        "history": ActivityReservationHistory.objects.filter(reservation__activity__owner=user)
        .select_related("reservation")
        .order_by("-date_action")[:10],
    }
    return stats
