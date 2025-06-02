from django.urls import path
from .views import create_conciergerie, update_conciergerie, list_conciergeries, bulk_action, conciergerie_detail

app_name = "conciergerie"

urlpatterns = [
    path("add/", create_conciergerie, name="create_conciergerie"),
    path("update/", update_conciergerie, name="update_conciergerie"),
    path("update/<int:pk>/", update_conciergerie, name="update_conciergerie"),
    path("", list_conciergeries, name="list_conciergeries"),
    path('actions/', bulk_action, name='bulk_action'),
    path('detail/<int:pk>/', conciergerie_detail, name='detail'),
]
