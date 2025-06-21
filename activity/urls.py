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
    path("reservations/", views.reservation_dashboard, name="reservation_dashboard"),
    path("admin-reservations/", views.manage_reservations, name="manage_reservations"),
    path("discounts/", views.manage_discounts, name="manage_discounts"),
    path("book/<int:pk>/", views.book, name="book"),
    path("slots/<int:pk>/", views.activity_slots, name="activity_slots"),
    path(
        "check_booking_input/<int:activity_id>/",
        views.check_booking_input,
        name="check_booking_input",
    ),
    path("not-available-dates/<int:pk>/", views.not_available_dates, name="not_available_dates"),
    path(
        "reservation/<str:code>/validate/",
        views.validate_reservation,
        name="validate_reservation",
    ),
    path(
        "details/<str:code>/",
        views.customer_reservation_detail,
        name="customer_reservation_detail",
    ),
    path(
        "cancel-booking/<str:code>/",
        views.cancel_booking,
        name="cancel_booking",
    ),
    path("revenu/", RevenueView.as_view(), name="revenu"),
]

# Add router URLs BEFORE catch-all patterns
urlpatterns += router.urls

# Catch-all patterns LAST
urlpatterns += [
    path("<str:code>/", views.reservation_detail, name="reservation_detail"),
    path("<str:code>/cancel/", views.cancel_reservation, name="cancel_reservation"),
]
