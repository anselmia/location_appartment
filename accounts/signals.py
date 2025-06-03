import logging
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django_q.tasks import async_task
from .models import Message

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=Message.recipients.through)
def notify_on_recipients_changed(sender, instance, action, pk_set, **kwargs):
    if action != "post_add" or not pk_set:
        return

    for recipient_id in pk_set:
        async_task("accounts.tasks.send_message_notification", instance.id, recipient_id)
        logger.debug(f"Async task queued for message {instance.id} to recipient {recipient_id}")
