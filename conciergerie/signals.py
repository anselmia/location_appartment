from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Conciergerie


@receiver(post_save, sender=Conciergerie)
def update_user_is_owner_admin(sender, instance, **kwargs):
    user = instance.user
    if instance.validated and not user.is_owner_admin:
        user.is_owner_admin = True
        user.save()
    elif not instance.validated and user.is_owner_admin:
        user.is_owner_admin = False
        user.save()
