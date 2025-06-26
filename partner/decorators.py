import logging

from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


# Decorator to check if the user is a partner
def user_is_partner(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Allow admins to bypass the check
        if request.user.is_admin or request.user.is_superuser or request.user.is_partner:
            return view_func(request, *args, **kwargs)

        logger.warning(
            f"[Restriction] Accès refusé (partner) pour l'utilisateur {request.user.id} ({request.user.email})"
        )
        # If the user is neither the owner nor an admin, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas authorisé à accéder à cette page.")

    return _wrapped_view


def user_has_valid_partner(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Allow admins to bypass the check
        if request.user.is_admin or request.user.is_superuser or request.user.has_valid_partners:
            return view_func(request, *args, **kwargs)

        logger.warning(
            f"[Restriction] Accès refusé (valid_partner) pour l'utilisateur {request.user.id} ({request.user.email})"
        )
        # If the user is neither the owner nor an admin, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas authorisé à accéder à cette page.")

    return _wrapped_view
