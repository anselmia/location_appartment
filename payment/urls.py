from django.urls import path
from . import views

app_name = "payment"

urlpatterns = [
    path(
        "success/<str:type>/<str:code>/",
        views.payment_success,
        name="payment_success",
    ),
    path(
        "cancel/<str:type>/<str:code>/",
        views.payment_cancel,
        name="payment_cancel",
    ),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path(
        "reservations/<str:code>/refund/",
        views.refund_reservation,
        name="refund_reservation",
    ),
    path(
        "reservations/<str:code>/refund-partially/",
        views.refund_partially_reservation,
        name="refund_partially_reservation",
    ),
    path(
        "reservations/<str:code>/charge-deposit/",
        views.charge_deposit,
        name="charge_deposit",
    ),
    path(
        "transfer-reservation/<str:code>/",
        views.transfer_reservation_payment,
        name="transfer_reservation",
    ),
    path("admin/payment-tasks/", views.payment_task_list, name="payment_tasks"),
]
