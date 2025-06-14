from django.urls import path
from . import views
from .views import FinancialDashboardView

app_name = "administration"

urlpatterns = [
    path("traffic/", views.traffic_dashboard, name="traffic"),
    path("logs/", views.log_viewer, name="log_viewer"),
    path("gestion-home/", views.homepage_admin_view, name="homepage_admin_view"),
    path("entreprise/", views.edit_entreprise, name="edit_entreprise"),
    path("financial-dashboard/", FinancialDashboardView.as_view(), name="financial_dashboard"),
    path("offers/", views.waiver_platform_fee_view, name="offers"),
    path("waivers/", views.waiver_platform_fee_view, name="waiver_platform_fee"),
    path("waivers/<int:waiver_id>/", views.waiver_platform_fee_view, name="edit_waiver_platform_fee"),
    path("waivers/delete/<int:waiver_id>/", views.delete_waiver_platform_fee, name="delete_waiver_platform_fee"),
]
