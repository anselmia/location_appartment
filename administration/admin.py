from django.contrib import admin
from .models import HomePageConfig, Service, Testimonial, Commitment, Entreprise


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 1


class TestimonialInline(admin.TabularInline):
    model = Testimonial
    extra = 1


class CommitmentInline(admin.TabularInline):
    model = Commitment
    extra = 1


admin.site.register(Entreprise)


@admin.register(HomePageConfig)
class HomePageConfigAdmin(admin.ModelAdmin):
    list_display = ("nom", "devise", "primary_color")
