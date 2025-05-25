import logging
from django.db.models import Q
from logement.models import Logement


logger = logging.getLogger(__name__)


def get_logements(user):
    try:
        if user.is_admin:
            # Admin users can see all reservations
            qs = Logement.objects.all()
        else:
            # Non-admin users: filter logements where the user is either the owner or an admin
            qs = Logement.objects.filter(Q(owner=user) | Q(admins=user))

        return qs

    except Exception as e:
        # Log the error and raise an exception
        logger.error(
            f"Error occurred while retrieving reservations: {e}", exc_info=True
        )
        # Optionally, you can re-raise the error or return a safe result, depending on the use case
        raise
