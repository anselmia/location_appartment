# signals.py
import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.conf import settings
from activity.models import Activity, Price


logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=Activity)
@receiver([post_save, post_delete], sender=Price)
def clear_activity_related_cache(sender, instance, **kwargs):
    # Déterminer l'ID de l'activité
    if isinstance(instance, Activity):
        activity_id = instance.id
    else:
        activity_id = getattr(instance, "activity_id", None)

    if not activity_id:
        return

    patterns = [
        f"activity_{activity_id}_*",  # prix, disponibilité, etc.
        "user_activities_*",  # vue `get_activity(user)`
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
            if pattern.startswith("activity_"):
                cache.delete(f"activity_{activity_id}_prix")
                cache.delete(f"activity_{activity_id}_dispo")
                logger.info(f"[CACHE] Suppression directe des clés activité pour activity_id={activity_id}")
            elif pattern == "user_activities_*":
                # If you have user_id, you can delete user_activities_{user_id}
                user_id = getattr(instance, "user_id", None)
                if user_id:
                    cache.delete(f"user_activities_{user_id}")
                    logger.info(f"[CACHE] Suppression directe de user_activities_{user_id}")