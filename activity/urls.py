from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from activity.views import DailyPriceViewSet, RevenueView

app_name = "activity"

router = DefaultRouter()
router.register(r"prices", DailyPriceViewSet, basename="price")

urlpatterns = [
    path("search/", views.activity_search, name="search"),
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
