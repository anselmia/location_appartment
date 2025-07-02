from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from django.conf.urls.i18n import set_language
from logement.views import DailyPriceViewSet
from .views import RevenueView

app_name = "logement"

router = DefaultRouter()
router.register(r"prices", DailyPriceViewSet, basename="price")

urlpatterns = [
    path("<int:logement_id>/", views.view_logement, name="view_logement"),
    path("cities/", views.autocomplete_cities, name="autocomplete_cities"),
    path("i18n/setlang/", set_language, name="set_language"),
    path("api/export/ical/<str:code>/", views.export_ical, name="export-ical"),
    path("search/", views.logement_search, name="logement_search"),
    path("add/", views.manage_logement, name="add_logement"),
    path("edit/<int:logement_id>/", views.manage_logement, name="edit_logement"),
    path("edit/<int:logement_id>/add_room/", views.add_room, name="add_room"),
    path("delete/<int:pk>/", views.delete_logement, name="delete_logement"),
    path("room/<int:room_id>/delete/", views.delete_room, name="delete_room"),
    path(
        "edit/<int:logement_id>/upload_photos/",
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
        "discounts/<int:logement_id>/",
        views.manage_discounts,
        name="manage_discounts",
    ),
    path(
        "discounts/",
        views.manage_discounts,
        name="manage_discounts",
    ),
    path("revenu/", RevenueView.as_view(), name="revenu"),
    path("api/revenu/<int:logement_id>/", views.api_economie_data, name="api_revenu"),
    path("dashboard/", views.logement_dashboard, name="dashboard"),
    path("<int:logement_id>/sync/airbnb/", views.sync_airbnb_calendar_view, name="sync_airbnb_calendar"),
    path("<int:logement_id>/sync/booking/", views.sync_booking_calendar_view, name="sync_booking_calendar"),
    path("api/stop-managing-logement/", views.stop_managing_logement, name="stop_managing_logement"),
    path("dash/", views.dashboard, name="dash"),
]

urlpatterns += router.urls
