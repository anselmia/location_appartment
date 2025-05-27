from django.shortcuts import render
import logging

# Set up a logger for the view
logger = logging.getLogger(__name__)


def is_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False) or user.is_superuser
    )


def is_stripe_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False)
        or user.is_superuser
        or user.is_owner
        or user.is_owner_admin
    )


def cgu_view(request):
    return render(request, "common/cgu.html")


def confidentiality_view(request):
    return render(request, "common/confidentiality.html")


def cgv_view(request):
    return render(request, "common/cgv.html")


def error_view(request, error_message="An unexpected error occurred."):
    """
    Common error view to handle and display errors to the user.
    """
    logger.error(f"Error encountered: {error_message}")  # Log the error

    # Render the error page with the provided error message
    return render(
        request,
        "common/error.html",  # Common error template
        {"error_message": error_message},
    )


def custom_bad_request(request, exception):
    return render(request, "400.html", status=400)


def custom_permission_denied(request, exception):
    return render(request, "403.html", status=403)


def custom_page_not_found(request, exception):
    return render(request, "404.html", status=404)


def custom_server_error(request):
    return render(request, "500.html", status=500)
