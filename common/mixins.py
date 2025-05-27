from django.core.exceptions import PermissionDenied


class AdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, "is_admin", False):
            raise PermissionDenied(
                "Vous n'avez pas les droits pour accéder à cette page."
            )
        return super().dispatch(request, *args, **kwargs)
