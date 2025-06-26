from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("register/", views.register, name="register"),
    path("register/role/", views.select_role, name="select_role"),
    path("dashboard/", views.client_dashboard, name="dashboard"),
    path("update-profile/", views.update_profile, name="update_profile"),
    path("messages/", views.messages_view, name="messages"),
    path("messages/<int:conversation_id>/", views.messages_view, name="messages_conversation"),
    path("messages/start/", views.start_conversation, name="start_conversation"),
    path("contact/", views.contact_view, name="contact"),
    path("delete-account/", views.delete_account, name="delete_account"),
    path("stripe/create/", views.create_stripe_account, name="create_stripe_account"),
    path(
        "accounts/stripe/update/",
        views.update_stripe_account_view,
        name="update_stripe_account",
    ),
    path("activate/<uid>/<token>/", views.activate, name="activate"),
    path("resend-confirmation/", views.resend_activation_email, name="resend_activation_email"),
    path("users/", views.user_update_view, name="user_update_view"),
    path("users/<int:user_id>/edit/", views.user_update_view, name="user_update_view_with_id"),
    path("users/<int:user_id>/delete/", views.user_delete_view, name="user_delete_view"),
    path(
        "password-reset/",
        views.CustomPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
]
