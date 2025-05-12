from django.urls import path
from . import views
from django.conf.urls.i18n import set_language

app_name = "logement"

urlpatterns = [
    path("", views.home, name="home"),
    path("i18n/setlang/", set_language, name="set_language"),
    path("book/<int:logement_id>/", views.book, name="book"),
    path(
        "api/get_price/<int:logement_id>/<str:date>/",
        views.get_price_for_date,
        name="get_price_for_date",
    ),
    path(
        "api/check_availability/<int:logement_id>/",
        views.check_availability,
        name="check_availability",
    ),
    path(
        "create-checkout-session/",
        views.create_checkout_session,
        name="create_checkout_session",
    ),
    path(
        "payment/success/<int:reservation_id>/",
        views.payment_success,
        name="payment_success",
    ),
    path(
        "payment/cancel/<int:reservation_id>/",
        views.payment_cancel,
        name="payment_cancel",
    ),
    path(
        "cancel-booking/<int:reservation_id>/",
        views.cancel_booking,
        name="cancel_booking",
    ),
]
