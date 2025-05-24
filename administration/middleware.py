from .models import SiteVisit
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import logout
from django.core.cache import cache
from administration.services.traffic import clear_user_cache, clear_inactive_sessions


class TrafficLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.user.is_staff and not request.path.startswith("/admin"):
            SiteVisit.objects.create(
                ip_address=request.META.get("REMOTE_ADDR", ""),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                path=request.path,
            )
        return response


class UpdateUserActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Update last activity for the authenticated user
        if request.user.is_authenticated:
            request.user.last_activity = timezone.now()
            request.user.save()

        return response


class SessionTimeoutMiddleware:
    """
    Middleware to handle session timeout and cache clearing
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get the current time and session last activity
        now = timezone.now()

        # Retrieve the last_activity from the session, ensuring it's a datetime object
        last_activity_str = request.session.get("last_activity")
        last_activity = (
            timezone.datetime.fromisoformat(last_activity_str)
            if last_activity_str
            else None
        )

        # If the session has not been set or the session has expired
        if last_activity and (
            now - last_activity > timedelta(seconds=3600)
        ):  # 1 hour timeout
            # Clear the user session and cache
            if request.user.is_authenticated:
                logout(request)
                # Optionally, clear cache related to the user
                clear_user_cache(request.user.id)

        # Update session activity time to track user interaction
        if request.user.is_authenticated:
            request.session["last_activity"] = (
                now.isoformat()
            )  # Store the activity as a string (ISO format)

        clear_inactive_sessions()

        response = self.get_response(request)
        return response
