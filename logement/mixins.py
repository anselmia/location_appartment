from django.core.exceptions import PermissionDenied
from logement.models import Logement
from django.db.models import Q
from common.views import is_admin
import logging

logger = logging.getLogger(__name__)


class UserHasLogementMixin:
    def dispatch(self, request, *args, **kwargs):
        has_logement = (
            Logement.objects.filter(Q(owner=request.user) | Q(admin=request.user)).exists()
            or request.user.is_owner
            or request.user.is_owner_admin
            or request.user.is_superuser
            or request.user.is_admin
        )

        if not (has_logement or is_admin(request.user)):
            logger.warning(
                f"[Restriction] Accès refusé (UserHasLogementMixin) pour l'utilisateur {getattr(request.user, 'id', '?')} ({getattr(request.user, 'email', '?')})"
            )
            raise PermissionDenied("Vous n'avez pas les droits pour accéder à cette page.")

        return super().dispatch(request, *args, **kwargs)
