import logging
from django.conf import settings

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
        "user_logements_*",  # vue `get_logements(user)`
        "filtered_logements_*",  # vue `filter_logements(...)`
    ]

    cache_backend = settings.CACHES["default"]["BACKEND"]
    is_redis = "redis" in cache_backend.lower()

    for pattern in patterns:
        if is_redis:
            try:
                cache.delete_pattern(pattern)
                logger.debug(f"[CACHE] delete_pattern utilisé pour : {pattern}")
            except Exception as e:
                logger.warning(f"[CACHE] Erreur lors de delete_pattern pour {pattern}: {e}")
        else:
            # LocMemCache, Memcached, etc. do not support pattern deletion
            # Delete most common keys explicitly for dev
            if pattern.startswith("logement_"):
                cache.delete(f"logement_{logement_id}_prix")
                cache.delete(f"logement_{logement_id}_dispo")
                logger.info(f"[CACHE] Suppression directe des clés logement pour logement_id={logement_id}")
            elif pattern == "user_logements_*":
                # If you have user_id, you can delete user_logements_{user_id}
                user_id = getattr(instance, "user_id", None)
                if user_id:
                    cache.delete(f"user_logements_{user_id}")
                    logger.info(f"[CACHE] Suppression directe de user_logements_{user_id}")
            elif pattern == "filtered_logements_*":
                # Not possible to know all keys, so just log
                logger.info("[CACHE] Impossible de supprimer filtered_logements_* sans pattern support")
