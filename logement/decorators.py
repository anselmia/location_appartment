from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from logement.models import Logement, Room, Photo
from django.db.models import Q


def user_is_logement_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Get the logement instance
        logement_id = kwargs.get("logement_id")
        if not logement_id:
            room_id = kwargs.get("room_id")
            if room_id:
                # If room_id is provided, get the Room instance and then get the associated Logement
                room = get_object_or_404(Room, id=room_id)
                logement_id = room.logement.id
            else:
                photo_id = kwargs.get("photo_id")
                if photo_id:
                    # If photo_id is provided, get the Photo instance and then get the associated Logement
                    photo = get_object_or_404(Photo, id=photo_id)
                    logement_id = photo.logement.id
                else:
                    return view_func(request, *args, **kwargs)

        logement = get_object_or_404(Logement, id=logement_id)

        # Check if the user is an admin or the owner of the logement
        if (
            request.user == logement.owner
            or request.user == logement.admin
            or request.user.is_admin
            or request.user.is_superuser
        ):
            return view_func(request, *args, **kwargs)

        # If the user is neither the owner nor an admin, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas authorisé à accéder à cette page.")

    return _wrapped_view


def user_has_logement(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Allow admins to bypass the check
        if request.user.is_admin:
            return view_func(request, *args, **kwargs)

        # Check if the user is either the owner or an admin of any Logement
        has_logement = (
            Logement.objects.filter(Q(owner=request.user) | Q(admin=request.user)).exists()
            or request.user.is_owner
            or request.user.is_owner_admin
            or request.user.is_superuser
            or request.user.is_admin
        )

        if has_logement:
            return view_func(request, *args, **kwargs)

        # If the user is neither the owner nor an admin, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas authorisé à accéder à cette page.")

    return _wrapped_view
