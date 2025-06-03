from django.contrib import admin

# Register your models here.
from conciergerie.models import Conciergerie


@admin.register(Conciergerie)
class ConciergerieAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "ville", "actif", "validated")
    list_filter = ("actif", "validated", "ville")
    search_fields = ("name", "email", "siret")
