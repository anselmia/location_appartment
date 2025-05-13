from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from .views import DailyPriceViewSet

app_name = "administration"

router = DefaultRouter()
router.register(r"prices", DailyPriceViewSet, basename="price")

urlpatterns = [
    path("", views.admin_dashboard, name="dashboard"),
    path("traffic/", views.traffic_dashboard, name="traffic"),
    path("logement/add/", views.add_logement, name="add_logement"),
    path("logement/<int:logement_id>/edit/", views.edit_logement, name="edit_logement"),
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
    path("calendar/", views.calendar, name="calendar"),
    path(
        "logement/discounts/",
        views.manage_discounts,
        name="manage_discounts",
    ),
    path("revenu/<int:logement_id>/", views.economie_view, name="revenu"),
    path("api/revenu/<int:logement_id>/", views.api_economie_data, name="api_revenu"),
]

urlpatterns += router.urls
