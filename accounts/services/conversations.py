import logging
from django.db.models import Q, Count
from reservation.models import Reservation
from accounts.models import Conversation


logger = logging.getLogger(__name__)


def is_platform_admin(user):
    """
    Return True if the user is a platform admin (superuser or has is_admin attribute set to True).

    Args:
        user (User): The user instance to check.

    Returns:
        bool: True if user is superuser or is_admin, False otherwise.
    """
    return user and (user.is_superuser or getattr(user, "is_admin", False))


def get_reservations_for_conversations_to_start(user):
    """
    Return reservations that the user can start a conversation on.
    - Platform admins see all reservations without a conversation.
    - Regular users see their own reservations, or those where they are logement owner or admin, without a conversation.

    Args:
        user (User): The user requesting reservations.

    Returns:
        QuerySet: Reservations the user can start a conversation on.
    """
    if not user or not user.is_authenticated:
        logger.warning("Anonymous or invalid user tried to fetch reservations.")
        return Reservation.objects.none()

    try:
        if is_platform_admin(user):
            reservations_without_conversation = Reservation.objects.exclude(
                id__in=Conversation.objects.values_list("reservation_id", flat=True)
            )
        else:
            reservations_without_conversation = Reservation.objects.filter(
                Q(user=user) | Q(logement__owner=user) | Q(logement__admin=user)
            ).exclude(id__in=Conversation.objects.values_list("reservation_id", flat=True))

        return reservations_without_conversation.distinct()
    except Exception as e:
        logger.error("Failed to get reservations for user %s: %s", getattr(user, "pk", "unknown"), e)
        return Reservation.objects.none()


def get_conversations(user):
    """
    Return a queryset of conversations for a user, annotated with unread message count.
    - Platform admins see all conversations.
    - Regular users see only conversations they participate in.

    Args:
        user (User): The user requesting conversations.

    Returns:
        QuerySet: Conversations annotated with 'unread_count'.
    """
    if not user or not user.is_authenticated:
        logger.warning("Anonymous or invalid user tried to fetch conversations.")
        return Conversation.objects.none()

    try:
        base_qs = (
            Conversation.objects.all() if is_platform_admin(user) else Conversation.objects.filter(participants=user)
        )
        conversations = base_qs.annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__recipients=user) & ~Q(messages__read_by=user),
            )
        ).order_by("-updated_at")

        return conversations
    except Exception as e:
        logger.error("Failed to get conversations for user %s: %s", getattr(user, "pk", "unknown"), e)
        return Conversation.objects.none()
