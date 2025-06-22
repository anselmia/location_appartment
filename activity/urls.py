from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from activity.views import DailyPriceViewSet, RevenueView

app_name = "activity"

router = DefaultRouter()
router.register(r"prices", DailyPriceViewSet, basename="price")

urlpatterns = [
    path("add/partner/", views.create_partner, name="create_partner"),
    path("update/partner", views.update_partner, name="update_partner"),
    path("search/", views.activity_search, name="search"),
    path("partners/", views.partner_list_customer, name="partner_list_customer"),
    path("partner/<int:pk>/", views.partner_detail, name="partner_detail"),
    path("partner-card/<int:pk>/", views.partner_customer_detail, name="partner_customer_detail"),
    path("partner/update/<int:pk>/", views.update_partner, name="update_partner"),
    path("partners-admin", views.list_partners, name="list_partners"),
    path("partner/actions/", views.bulk_action, name="bulk_action"),
    path("partner/find/", views.partner_list_customer, name="customer_list"),
    path("add/", views.create_activity, name="create_activity"),
    path("detail/<int:pk>/", views.detail, name="detail"),
    path("update/<int:pk>/", views.update_activity, name="update_activity"),
    path("dashboard/", views.activity_dashboard, name="activity_dashboard"),
    path("calendar/", views.activity_calendar, name="activity_calendar"), 
    path("discounts/", views.manage_discounts, name="manage_discounts"),
    path("revenu/", RevenueView.as_view(), name="revenu"),
]

# Add router URLs BEFORE catch-all patterns
urlpatterns += router.urls
