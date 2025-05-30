import logging
from django.db.models import Q, Count
from logement.models import Reservation
from accounts.models import Conversation


logger = logging.getLogger(__name__)


def get_reservations_for_conversations_to_start(user):
    if user.is_admin or user.is_superuser:
        reservations_without_conversation = Reservation.objects.exclude(
            id__in=Conversation.objects.values_list("reservation_id", flat=True)
        )
    else:
        # Find reservations the user can message on, excluding existing ones
        reservations_without_conversation = Reservation.objects.filter(
            Q(user=user) | Q(logement__owner=user) | Q(logement__admin=user)
        ).exclude(id__in=Conversation.objects.values_list("reservation_id", flat=True))

    return reservations_without_conversation


def get_conversations(user):
    if user.is_admin or user.is_superuser:
        conversations = (
            Conversation.objects.all()
            .annotate(unread_count=Count("messages", filter=Q(messages__read=False, messages__recipients=user)))
            .order_by("-updated_at")
        )
    else:
        conversations = (
            Conversation.objects.filter(Q(participants=user))
            .annotate(unread_count=Count("messages", filter=Q(messages__read=False, messages__recipients=user)))
            .order_by("-updated_at")
        )

    return conversations
