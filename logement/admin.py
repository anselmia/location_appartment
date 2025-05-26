from django.contrib import admin
from .models import (
    Logement,
    Photo,
    Reservation,
    booking_booking,
    airbnb_booking,
    Discount,
    DiscountType,
    City,
    Equipment,
)
from django.utils.html import format_html


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 1
    readonly_fields = ["preview"]

    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:100px;">', obj.image.url
            )
        return "Pas d'image"

    preview.short_description = "Aperçu"


class LogementAdmin(admin.ModelAdmin):
    list_display = ["name", "price"]
    inlines = [PhotoInline]


admin.site.register(Logement, LogementAdmin)
admin.site.register(Photo)


class ReservationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "code",
        "logement",
        "user",
        "start",
        "end",
        "statut",
        "guest",
        "date_reservation",
        "price",
        "tax",
    ]
    list_filter = ["statut", "logement", "start"]
    ordering = ["-date_reservation"]


admin.site.register(Reservation, ReservationAdmin)
admin.site.register(City)

admin.site.register(airbnb_booking)
admin.site.register(booking_booking)
admin.site.register(Discount)
admin.site.register(DiscountType)


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "icon"]
    search_fields = ["name"]
