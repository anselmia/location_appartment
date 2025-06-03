import logging
from django.core.mail import send_mail
from django.conf import settings
from .models import Message, CustomUser

logger = logging.getLogger(__name__)


def send_message_notification(message_id, recipient_id):
    try:
        message = Message.objects.select_related("conversation__reservation", "sender").get(id=message_id)
        recipient = CustomUser.objects.get(id=recipient_id)

        if not recipient.email:
            logger.warning(f"Recipient {recipient_id} has no email; skipping.")
            return

        subject = f"Nouveau message de {message.sender}"
        body = f"""Bonjour {recipient.get_full_name() or recipient.username},

Vous avez reçu un nouveau message concernant la réservation : {message.conversation.reservation.code}

Message :
{message.content}

Connectez-vous pour répondre : {settings.SITE_ADDRESS}/accounts/messages/{message.conversation.id}/
"""

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient.email],
            fail_silently=False,
        )

        logger.info(f"Notification envoyée à {recipient.email} pour le message {message.id}")
    except Exception:
        logger.exception(f"Échec de la notification pour message {message_id} à utilisateur {recipient_id}")


def send_contact_email(cd):
    try:
        send_mail(
            subject=cd["subject"],
            message=f"Message de {cd['name']} ({cd['email']}):\n\n{cd['message']}",
            from_email=cd["email"],
            recipient_list=[settings.CONTACT_EMAIL],
            fail_silently=False,
        )
    except Exception as e:
        logger.exception(f"Erreur d'envoi email de contact: {e}")
