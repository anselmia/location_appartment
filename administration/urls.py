from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from .views import DailyPriceViewSet
from .views import FinancialDashboardView, RevenueView

app_name = "administration"

router = DefaultRouter()
router.register(r"prices", DailyPriceViewSet, basename="price")

urlpatterns = [
    path("", views.admin_dashboard, name="dashboard"),
    path("traffic/", views.traffic_dashboard, name="traffic"),
    path("logement/add/", views.manage_logement, name="add_logement"),
    path("logement/<int:logement_id>/", views.manage_logement, name="edit_logement"),
    path("logement/<int:logement_id>/add_room/", views.add_room, name="add_room"),
    path("room/<int:room_id>/delete/", views.delete_room, name="delete_room"),
    path(
        "logement/<int:logement_id>/upload_photos/",
        views.upload_photos,
        name="upload_photos",
    ),
    path(
        "api/change-photo-room/<int:photo_id>/",
        views.change_photo_room,
        name="change_photo_room",
    ),
    path(
        "api/move-photo/<int:photo_id>/<str:direction>/",
        views.move_photo,
        name="move_photo",
    ),
    path("api/delete-photo/<int:photo_id>/", views.delete_photo, name="delete_photo"),
    path(
        "api/delete-all-photos/<int:logement_id>/",
        views.delete_all_photos,
        name="delete_all_photos",
    ),
    path("api/rotate-photos/<int:photo_id>/", views.rotate_photo, name="rotate_photo"),
    path(
        "update-equipment/<int:logement_id>/",
        views.update_equipment,
        name="update_equipment",
    ),
    path("calendar/", views.calendar, name="calendar"),
    path(
        "logement/discounts/<int:logement_id>/",
        views.manage_discounts,
        name="manage_discounts",
    ),
    path(
        "logement/discounts/",
        views.manage_discounts,
        name="manage_discounts",
    ),
    path("revenu/", RevenueView.as_view(), name="revenu"),
    path("api/revenu/<int:logement_id>/", views.api_economie_data, name="api_revenu"),
    path("logs/", views.log_viewer, name="log_viewer"),
    path("api/log-js/", views.js_logger, name="js_logger"),
    path("reservations/", views.reservation_dashboard, name="reservation_dashboard"),
    path("reservations/<str:code>/", views.reservation_detail, name="reservation_detail"),
    path(
        "reservations/<str:code>/cancel/",
        views.cancel_reservation,
        name="cancel_reservation",
    ),
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
        "reservations/<int:logement_id>/",
        views.reservation_dashboard,
        name="reservation_dashboard_by_id",
    ),
    path("gestion-home/", views.homepage_admin_view, name="homepage_admin_view"),
    path("entreprise/", views.edit_entreprise, name="edit_entreprise"),
    path("admin-reservations/", views.manage_reservations, name="manage_reservations"),
    path(
        "transfer-reservation/<str:code>/",
        views.transfer_reservation_payment,
        name="transfer_reservation",
    ),
    path("financial-dashboard/", FinancialDashboardView.as_view(), name="financial_dashboard"),
    path("admin/users/", views.user_update_view, name="user_update_view"),
    path("admin/users/<int:user_id>/edit/", views.user_update_view, name="user_update_view_with_id"),
    path("admin/users/<int:user_id>/delete/", views.user_delete_view, name="user_delete_view"),
]

urlpatterns += router.urls
