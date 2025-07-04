import logging
from .models import Message, CustomUser
from huey.contrib.djhuey import task
from common.services import email_service

logger = logging.getLogger(__name__)


@task()
def send_message_notification(message_id, recipient_id):
    try:
        message = Message.objects.select_related("conversation__reservation", "sender").get(id=message_id)
        recipient = CustomUser.objects.get(id=recipient_id)

        if not recipient.email:
            logger.warning(f"Recipient {recipient_id} has no email; skipping.")
            return

        email_service.send_message_notification_email(message, recipient)
    except Exception:
        logger.error(f"Échec de la notification pour message {message_id} à utilisateur {recipient_id}")


@task()
def send_contact_email(cd):
    try:
        email_service.send_contact_email_notification(cd)
    except Exception as e:
        logger.error(f"Erreur d'envoi email de contact: {e}")
