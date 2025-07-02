from django.urls import path
from .views import (
    create_conciergerie,
    update_conciergerie,
    delete_conciergerie,
    list_conciergeries,
    bulk_action,
    conciergerie_detail,
    customer_conciergerie_list,
    customer_conciergerie_detail,
    handle_conciergerie_request,
    dashboard,
)

app_name = "conciergerie"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("add/", create_conciergerie, name="create_conciergerie"),
    path("update/", update_conciergerie, name="update_conciergerie"),
    path("delete/<int:pk>/", delete_conciergerie, name="delete_conciergerie"),
    path("update/<int:pk>/", update_conciergerie, name="update_conciergerie"),
    path("list", list_conciergeries, name="list_conciergeries"),
    path("actions/", bulk_action, name="bulk_action"),
    path("detail/<int:pk>/", conciergerie_detail, name="detail"),
    path("trouver/", customer_conciergerie_list, name="customer_list"),
    path("detail-view/<int:pk>/", customer_conciergerie_detail, name="conciergerie_detail"),
    path("api/handle-request/", handle_conciergerie_request, name="handle_request"),
]
