from django.core.exceptions import PermissionDenied
from activity.models import Activity
from django.db.models import Q
from common.views import is_admin
import logging

logger = logging.getLogger(__name__)


class UserHasActivityMixin:
    def dispatch(self, request, *args, **kwargs):
        has_activity = (
            Activity.objects.filter(Q(owner=request.user)).exists()
            or request.user.is_partner
            or request.user.is_superuser
            or request.user.is_admin
        )

        if not (has_activity or is_admin(request.user)):
            logger.warning(
                f"[Restriction] Accès refusé (UserHasActivityMixin) pour l'utilisateur {getattr(request.user, 'id', '?')} ({getattr(request.user, 'email', '?')})"
            )
            raise PermissionDenied("Vous n'avez pas les droits pour accéder à cette page.")

        return super().dispatch(request, *args, **kwargs)
