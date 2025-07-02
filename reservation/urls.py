from django.urls import path
from . import views

app_name = "reservation"

urlpatterns = [
    path("logement/<int:pk>/", views.book_logement, name="book_logement"),
    path("activity/<int:pk>/", views.book_activity, name="book_activity"),
    path("slots/<int:pk>/", views.activity_slots, name="activity_slots"),
    path(
        "api/check_availability/<int:logement_id>/",
        views.check_availability,
        name="check_availability",
    ),
    path(
        "check-logement-input/<int:logement_id>/",
        views.check_logement_booking_input,
        name="check_logement_booking_input",
    ),
    path(
        "check-activity-input/<int:activity_id>/",
        views.check_activity_booking_input,
        name="check_activity_booking_input",
    ),
    path(
        "user-cancel-logement/<str:code>/",
        views.customer_cancel_logement_booking,
        name="customer_cancel_logement_booking",
    ),
    path(
        "user-cancel-activity/<str:code>/",
        views.customer_cancel_activity_booking,
        name="customer_cancel_activity_booking",
    ),
    path("admin-logement/", views.manage_logement_reservations, name="manage_logement_reservations"),
    path("admin-activity/", views.manage_activity_reservations, name="manage_activity_reservations"),
    path(
        "logement-details/<str:code>/",
        views.customer_logement_reservation_detail,
        name="customer_logement_reservation_detail",
    ),
    path(
        "activity-details/<str:code>/",
        views.customer_activity_reservation_detail,
        name="customer_activity_reservation_detail",
    ),
    path("logements/", views.logement_reservation_dashboard, name="logement_reservation_dashboard"),
    path("activities/", views.activity_reservation_dashboard, name="activity_reservation_dashboard"),
    path("logement-detail/<str:code>/", views.logement_reservation_detail, name="logement_reservation_detail"),
    path("activity-detail/<str:code>/", views.activity_reservation_detail, name="activity_reservation_detail"),
    path(
        "cancel-activity/<str:code>/",
        views.cancel_activity_reservation,
        name="cancel_activity_reservation",
    ),
    path(
        "cancel-logement/<str:code>/", views.cancel_logement_reservation, name="cancel_logement_reservation"
    ),
    path(
        "owner-cancel-activity/<str:code>/",
        views.owner_cancel_activity_reservation,
        name="owner_cancel_activity_reservation",
    ),
    path(
        "owner-cancel-logement/<str:code>/", views.owner_cancel_logement_booking, name="owner_cancel_logement_booking"
    ),
    path(
        "validate-activity/<str:code>/",
        views.validate_activity_reservation,
        name="validate_activity_reservation",
    ),
    path("not-available-dates/<int:pk>/", views.activity_not_available_dates, name="activity_not_available_dates"),
    path('toggle-paid/<str:code>/', views.toggle_paid, name='toggle_paid')
]
