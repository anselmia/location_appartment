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
]
