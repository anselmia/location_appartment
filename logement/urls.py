from django.urls import path
from . import views
from django.conf.urls.i18n import set_language

app_name = "logement"

urlpatterns = [
    path("", views.home, name="home"),
    path("logement/<int:logement_id>/", views.view_logement, name="view_logement"),
    path('cities/', views.autocomplete_cities, name='autocomplete_cities'),
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
        "api/check_booking_input/<int:logement_id>/",
        views.check_booking_input,
        name="check_booking_input",
    ),
    path(
        "payment/success/<str:code>/",
        views.payment_success,
        name="payment_success",
    ),
    path(
        "payment/cancel/<str:code>/",
        views.payment_cancel,
        name="payment_cancel",
    ),
    path(
        "cancel-booking/<str:code>/",
        views.cancel_booking,
        name="cancel_booking",
    ),
    path('api/export/ical/<str:code>/', views.export_ical, name='export-ical'),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path('search/', views.logement_search, name='logement_search'),
]
