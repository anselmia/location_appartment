from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone
from django.contrib.sessions.models import Session
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from accounts.models import CustomUser
from administration.models import (
    SiteVisit,
)  # Assuming you have a SiteVisit model for tracking visits


def get_online_users():
    """
    Returns the number of online authenticated users based on activity within the last 5 minutes.
    """
    now = timezone.now()
    online_threshold = now - timedelta(minutes=5)
    online_users = CustomUser.objects.filter(last_activity__gte=online_threshold)
    return online_users.count()


def get_connected_users():
    """
    Returns the number of authenticated users currently logged in.
    """
    return CustomUser.objects.filter(is_authenticated=True).count()


def get_online_visitors():
    """
    Returns the number of online visitors (non-authenticated users) based on active sessions within the last 5 minutes.
    """
    now = timezone.now()
    online_threshold = now - timedelta(minutes=5)
    online_visitors = Session.objects.filter(
        expire_date__gte=online_threshold,
        session_key__in=Session.objects.all().values_list("session_key", flat=True),
    ).exclude(
        session_data__icontains="user_id"
    )  # Exclude authenticated users
    return online_visitors.count()


def get_traffic_data(period="day"):
    """
    Returns the traffic data (visits) for the selected period (day, week, month).
    """
    now = timezone.now()
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

    # Convert datetime to string using isoformat
    labels = [
        (
            v["period"].date().isoformat()
            if isinstance(v["period"], timezone.datetime)
            else str(v["period"])
        )
        for v in visits_qs
    ]
    data = [v["count"] for v in visits_qs]

    return labels, data


def get_visits_count(since_days=30):
    """
    Returns the total number of visits in the last `since_days` days.
    """
    now = timezone.now()
    since = now - timedelta(days=since_days)
    return SiteVisit.objects.filter(timestamp__gte=since).count()


def get_unique_visitors_count(since_days=30):
    """
    Returns the number of unique visitors based on IP addresses in the last `since_days` days.
    """
    now = timezone.now()
    since = now - timedelta(days=since_days)
    return (
        SiteVisit.objects.filter(timestamp__gte=since)
        .values("ip_address")
        .distinct()
        .count()
    )


def get_recent_logs(limit=20):
    """
    Returns the most recent logs.
    """
    return SiteVisit.objects.order_by("-timestamp")[:limit]


def clear_user_cache(user_id):
    # Clear the cache related to the user when session expires
    cache.delete(f"user_{user_id}_data")  # Modify according to your cache key structure


def clear_inactive_sessions():
    inactive_threshold = timezone.now() - timedelta(
        minutes=30
    )  # 30 minutes of inactivity
    Session.objects.filter(expire_date__lte=inactive_threshold).delete()
