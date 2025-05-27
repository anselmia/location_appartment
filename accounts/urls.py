from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", views.user_logout, name="logout"),
    path("register/", views.register, name="register"),
    path("dashboard/", views.client_dashboard, name="dashboard"),
    path("update-profile/", views.update_profile, name="update_profile"),
    path("messages/", views.messages_view, name="messages"),
    path("contact/", views.contact_view, name="contact"),
    path("delete-account/", views.delete_account, name="delete_account"),
    path("stripe/create/", views.create_stripe_account, name="create_stripe_account"),
    path(
        "accounts/stripe/update/",
        views.update_stripe_account_view,
        name="update_stripe_account",
    ),
]
