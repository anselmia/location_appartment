from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from administration.models import Entreprise
from common.services.helper_fct import ENTREPRISE_CACHE_KEY


@receiver(post_save, sender=Entreprise)
def clear_entreprise_cache(sender, **kwargs):
    cache.delete(ENTREPRISE_CACHE_KEY)
