from django.core.exceptions import PermissionDenied


def user_is_owner_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Allow admins to bypass the check
        if request.user.is_admin or request.user.is_superuser or request.user.is_owner_admin:
            return view_func(request, *args, **kwargs)

        # If the user is neither the owner nor an admin, raise a PermissionDenied error
        raise PermissionDenied("Vous n'êtes pas authorisé à accéder à cette page.")

    return _wrapped_view

