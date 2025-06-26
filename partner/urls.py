from django.urls import path
from . import views

app_name = "partner"


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("add/", views.create_partner, name="create_partner"),
    path("update/", views.update_partner, name="update_partner"),
    path("list/", views.partner_list_customer, name="partner_list_customer"),
    path("<int:pk>/", views.partner_detail, name="partner_detail"),
    path("detail/<int:pk>/", views.partner_customer_detail, name="partner_customer_detail"),
    path("update/<int:pk>/", views.update_partner, name="update_partner"),
    path("list-admin/", views.list_partners, name="list_partners"),
    path("actions/", views.bulk_action, name="bulk_action"),
    path("find/", views.partner_list_customer, name="customer_list"),
]
