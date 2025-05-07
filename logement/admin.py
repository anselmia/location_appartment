from django.contrib import admin
from .models import (
    Client,
    Logement,
    Photo,
    Reservation,
    booking_booking,
    airbnb_booking,
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
admin.site.register(Client)
admin.site.register(Reservation)
admin.site.register(airbnb_booking)
admin.site.register(booking_booking)
