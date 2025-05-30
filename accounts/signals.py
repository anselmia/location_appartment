import logging
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import Message

logger = logging.getLogger(__name__)

@receiver(m2m_changed, sender=Message.recipients.through)
def notify_on_recipients_changed(sender, instance, action, pk_set, **kwargs):
    if action != "post_add":
        return

    for recipient in instance.recipients.exclude(email=""):
        try:
            subject = f"Nouveau message de {instance.sender}"
            message = f"""Bonjour {recipient.get_full_name() or recipient.username},

Vous avez reçu un nouveau message concernant la réservation : {instance.conversation.reservation.code}

Message :
{instance.content}

Connectez-vous pour répondre : https://valrose.home-arnaud.ovh/accounts/messages/{instance.conversation.id}/
"""
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=False,
            )
            logger.info(f"Notification envoyée à {recipient.email} pour le message {instance.id}")

        except Exception as e:
            logger.exception(f"Erreur lors de l'envoi de l'email à {recipient.email} pour le message {instance.id}")
