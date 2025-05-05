from django.urls import path
from . import views
from django.conf.urls.i18n import set_language

app_name = "logement"

urlpatterns = [
    path("", views.home, name="home"),
    path("i18n/setlang/", set_language, name="set_language"),
    path("reserver/<int:logement_id>/", views.reserver, name="reserver"),
]
