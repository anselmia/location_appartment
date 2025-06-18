import logging
from typing import Any

from django.core.cache import cache
from activity.models import Activity

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
