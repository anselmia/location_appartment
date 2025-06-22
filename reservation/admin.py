from django.contrib import admin
from .models import Reservation, booking_booking, airbnb_booking, ActivityReservation


class ReservationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "code",
        "logement",
        "user",
        "start",
        "end",
        "statut",
        "guest_adult",
        "guest_minor",
        "date_reservation",
        "price",
        "tax",
    ]
    list_filter = ["statut", "logement", "start"]
    ordering = ["-date_reservation"]


class ActivityReservationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "code",
        "activity",
        "user",
        "start",
        "end",
        "statut",
        "participants",
        "date_reservation",
        "price",
    ]
    list_filter = ["statut", "activity", "start"]
    ordering = ["-date_reservation"]


admin.site.register(Reservation, ReservationAdmin)
admin.site.register(ActivityReservation, ActivityReservationAdmin)
admin.site.register(airbnb_booking)
admin.site.register(booking_booking)
