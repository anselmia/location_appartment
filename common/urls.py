from django.urls import path
from . import views

app_name = "common"

urlpatterns = [
    path("cgu/", views.cgu_view, name="cgu"),
    path("politique-de-confidenialité/", views.confidentiality_view, name="confidentiality"),
    path("CGV/", views.cgv_view, name="cgv"),

]
