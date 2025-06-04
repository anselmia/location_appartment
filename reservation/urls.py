from django.urls import path
from . import views

app_name = "reservation"

urlpatterns = [
    path("book/<int:logement_id>/", views.book, name="book"),
    path(
        "api/check_availability/<int:logement_id>/",
        views.check_availability,
        name="check_availability",
    ),
    path(
        "check_booking_input/<int:logement_id>/",
        views.check_booking_input,
        name="check_booking_input",
    ),
    path(
        "cancel-booking/<str:code>/",
        views.cancel_booking,
        name="cancel_booking",
    ),
    path("admin-reservations/", views.manage_reservations, name="manage_reservations"),
    path(
        "details/<str:code>/",
        views.customer_reservation_detail,
        name="customer_reservation_detail",
    ),
    path("", views.reservation_dashboard, name="reservation_dashboard"),
    path(
        "<int:logement_id>/",
        views.reservation_dashboard,
        name="reservation_dashboard_by_id",
    ),
    path("<str:code>/", views.reservation_detail, name="reservation_detail"),
    path(
        "<str:code>/cancel/",
        views.cancel_reservation,
        name="cancel_reservation",
    ),
]
