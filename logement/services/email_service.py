import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.mail import mail_admins


logger = logging.getLogger(__name__)


def send_mail_on_new_reservation(logement, reservation, user):
    try:
        # Build context for the email
        email_context = {
            "reservation": reservation,
            "logement": logement,
            "user": user,
        }

        # Render email content
        email_message = render_to_string("email/new_reservation.txt", email_context)

        # Send email to admins
        mail_admins(
            subject=f"🆕 Nouvelle réservation pour {logement.name}",
            message=email_message,
            fail_silently=False,  # Raise in dev, log in prod
        )

        logger.info(f"✅ Mail sent for reservation {reservation.id} to admins.")

    except Exception as e:
        logger.exception(
            f"❌ Failed to send admin mail for reservation {reservation.id}: {e}"
        )
