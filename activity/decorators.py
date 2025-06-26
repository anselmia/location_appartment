import logging

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from activity.models import Activity

logger = logging.getLogger(__name__)


def user_is_activity_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Get the activity instance
        activity_id = kwargs.get("activity_id")
        if not activity_id:
            return view_func(request, *args, **kwargs)

        activity = get_object_or_404(Activity, id=activity_id)

        # Check if the user is an admin or the owner of the activity
        if request.user == activity.owner or request.user.is_admin or request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        logger.warning(
            f"[Restriction] Accès refusé à l'activité {activity_id} (admin) pour l'utilisateur {request.user.id} ({request.user.email})"
        )
        # If the user is neither the owner nor an admin, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas authorisé à accéder à cette page.")

    return _wrapped_view


def user_has_activity(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Allow admins to bypass the check
        if request.user.is_admin:
            return view_func(request, *args, **kwargs)

        # Check if the user is either the owner or an admin of any Activity
        has_activity = (
            Activity.objects.filter(owner=request.user).exists()
            or request.user.is_partner
            or request.user.is_superuser
            or request.user.is_admin
        )

        if has_activity:
            return view_func(request, *args, **kwargs)

        logger.warning(
            f"[Restriction] Accès refusé (has_activity) pour l'utilisateur {request.user.id} ({request.user.email})"
        )
        # If the user is neither the owner nor an admin, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas authorisé à accéder à cette page.")

    return _wrapped_view
