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
        views.charge_deposit_view,
        name="charge_deposit",
    ),
    path(
        "transfer-reservation/<str:code>/",
        views.transfer_reservation_payment,
        name="transfer_reservation",
    ),
    path("admin/payment-tasks/", views.payment_task_list, name="payment_tasks"),
    path(
        "verify-checkout/<str:code>/",
        views.verify_payment_view,
        name="verify_payment",
    ),
    path(
        "verify-transfer/<str:code>/",
        views.verify_transfer_view,
        name="verify_transfer",
    ),
    path(
        "verify-payment-method/<str:code>/",
        views.verify_payment_method_view,
        name="verify_payment_method",
    ),
    path(
        "verify-deposit-payment/<str:code>/",
        views.verify_deposit_payment_view,
        name="verify_deposit_payment",
    ),
    path(
        "verify-refund/<str:code>/",
        views.verify_refund_view,
        name="verify_refund",
    )
]
