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
]
