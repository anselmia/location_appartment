from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from reservation.models import Reservation
from activity.models import ActivityReservation


def user_is_reservation_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Get the reservation instance from the URL parameter
        code = kwargs["code"]
        reservation = Reservation.objects.filter(code=code).first()
        if not reservation:
            reservation = ActivityReservation.objects.filter(code=code).first()
        if not reservation:
            raise PermissionDenied("Réservation introuvable.")

        # Get the associated logement or activity
        logement = getattr(reservation, "logement", None)
        activity = getattr(reservation, "activity", None)

        # Check if the user is the admin or the owner of the logement/activity
        if (
            (logement and (request.user == logement.owner or request.user == logement.admin))
            or (activity and (request.user == activity.owner))
            or request.user.is_admin
            or request.user.is_superuser
        ):
            return view_func(request, *args, **kwargs)

        raise PermissionDenied("Vous n'êtes pas autorisé à accéder à cette page.")

    return _wrapped_view


def user_is_reservation_customer(view_func):
    def _wrapped_view(request, *args, **kwargs):
        code = kwargs["code"]
        reservation = Reservation.objects.filter(code=code).first()
        if not reservation:
            reservation = ActivityReservation.objects.filter(code=code).first()
        if not reservation:
            raise PermissionDenied("Réservation introuvable.")

        if request.user == reservation.user or request.user.is_admin or request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        raise PermissionDenied("Vous n'êtes pas autorisé à accéder à cette page.")

    return _wrapped_view


def user_has_reservation(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        code = kwargs["code"]
        if (
            Reservation.objects.filter(code=code, user=request.user).exists()
            or ActivityReservation.objects.filter(code=code, user=request.user).exists()
            or request.user.is_superuser
            or request.user.is_admin
        ):
            return view_func(request, *args, **kwargs)

        messages.error(request, "Accès refusé : vous n'avez pas réservé ce logement ou cette activité.")
        return redirect("accounts:dashboard")

    return _wrapped_view
