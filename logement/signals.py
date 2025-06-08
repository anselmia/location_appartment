import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from logement.models import Logement, Discount, Price
from django.core.cache import cache

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=Logement)
@receiver([post_save, post_delete], sender=Discount)
@receiver([post_save, post_delete], sender=Price)
def clear_logement_related_cache(sender, instance, **kwargs):
    # Déterminer l'ID du logement
    if isinstance(instance, Logement):
        logement_id = instance.id
    else:
        logement_id = getattr(instance, "logement_id", None)

    if not logement_id:
        return

    patterns = [
        f"logement_{logement_id}_*",  # prix, disponibilité, etc.
        f"user_logements_*",  # vue `get_logements(user)`
        f"filtered_logements_*",  # vue `filter_logements(...)`
    ]

    for pattern in patterns:
        try:
            keys = cache.keys(pattern)
            for key in keys:
                cache.delete(key)
                logger.debug(f"[CACHE] Clé supprimée : {key}")
        except Exception as e:
            logger.warning(f"[CACHE] Erreur lors de la suppression des clés pour pattern {pattern}: {e}")
