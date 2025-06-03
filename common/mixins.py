from django.core.exceptions import PermissionDenied
from django import forms


class AdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not (getattr(request.user, "is_admin", False) or request.user.is_superuser):
            raise PermissionDenied("Vous n'avez pas les droits pour accéder à cette page.")
        return super().dispatch(request, *args, **kwargs)


class BootstrapFormMixin:
    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-control"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()