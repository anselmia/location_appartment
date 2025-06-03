from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from functools import wraps
from reservation.models import Reservation


def user_is_reservation_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Get the reservation instance from the URL parameter
        reservation = get_object_or_404(Reservation, code=kwargs["code"])

        # Get the associated logement
        logement = reservation.logement

        # Check if the user is the admin or the owner of the logement
        if (
            request.user == logement.owner
            or request.user == logement.admin
            or request.user.is_admin
            or request.user.is_superuser
        ):
            return view_func(request, *args, **kwargs)

        # If the user is not authorized, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas autorisé à accéder à cette page.")

    return _wrapped_view


def user_is_reservation_customer(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Get the reservation instance from the URL parameter
        reservation = get_object_or_404(Reservation, code=kwargs["code"])

        # Check if the user is the admin or the owner of the logement
        if request.user == reservation.user or request.user.is_admin or request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        # If the user is not authorized, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas autorisé à accéder à cette page.")

    return _wrapped_view


def user_has_reservation(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        code = kwargs["code"]

        if (
            Reservation.objects.filter(code=code, user=request.user).exists()
            or request.user.is_superuser
            or request.user.is_admin
        ):
            return view_func(request, *args, **kwargs)

        # If the user is not authorized, redirect to dashboard
        messages.error(request, "Accès refusé : vous n'avez pas réservé ce logement.")
        return redirect("accounts:dashboard")

    return _wrapped_view
