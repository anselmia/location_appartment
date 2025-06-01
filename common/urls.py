from django.urls import path
from . import views

app_name = "common"

urlpatterns = [
    path("", views.home, name="home"),
    path("cgu/", views.cgu_view, name="cgu"),
    path("politique-de-confidenialité/", views.confidentiality_view, name="confidentiality"),
    path("CGV/", views.cgv_view, name="cgv"),
    path("chatbot/api/", views.chatbot_api, name="chatbot_api"),
]
