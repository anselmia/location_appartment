import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.mail import mail_admins
from django.conf import settings


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
        admin_message = render_to_string("email/new_reservation.txt", email_context)

        # Send email to admins
        mail_admins(
            subject=f"🆕 Nouvelle réservation pour {logement.name}",
            message=admin_message,
            fail_silently=False,  # Raise in dev, log in prod
        )

        logger.info(f"✅ Mail sent for reservation {reservation.id} to admins.")

        # ========== CUSTOMER CONFIRMATION ==========
        if user.email:
            subject = f"Confirmation de votre réservation - {logement.name}"
            user_message = render_to_string(
                "email/new_reservation_customer.txt", email_context
            )

            send_mail(
                subject=subject,
                message=user_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info(
                f"✅ Confirmation mail sent to user {user.email} for reservation {reservation.id}"
            )

    except Exception as e:
        logger.exception(
            f"❌ Failed to send admin mail for reservation {reservation.id}: {e}"
        )


def send_mail_on_refund(logement, reservation, user):
    try:
        # Context for email templates
        email_context = {
            "reservation": reservation,
            "logement": logement,
            "user": user,
        }

        # ===== ADMIN EMAIL =====
        admin_message = render_to_string("email/refund_admin.txt", email_context)

        mail_admins(
            subject=f"💸 Remboursement effectué - {logement.name}",
            message=admin_message,
            fail_silently=False,
        )

        logger.info(f"✅ Refund email sent to admins for reservation {reservation.id}.")

        # ===== USER EMAIL =====
        if user.email:
            user_message = render_to_string("email/refund_customer.txt", email_context)

            send_mail(
                subject=f"Remboursement de votre réservation - {logement.name}",
                message=user_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            logger.info(
                f"✅ Refund confirmation sent to user {user.email} for reservation {reservation.id}"
            )

    except Exception as e:
        logger.exception(
            f"❌ Failed to send refund email for reservation {reservation.id}: {e}"
        )


def send_mail_on_refund_result(reservation, success=True, error_message=None):
    try:
        context = {
            "reservation": reservation,
            "logement": reservation.logement,
            "success": success,
            "error_message": error_message,
        }

        message = render_to_string("email/refund_result.txt", context)

        subject = (
            f"🔁 Remboursement réussi - Réservation {reservation.id}"
            if success
            else f"❗ Échec remboursement - Réservation {reservation.id}"
        )

        mail_admins(subject=subject, message=message, fail_silently=False)

        logger.info(f"✉️ Email sent for refund status of reservation {reservation.id}")
    except Exception as e:
        logger.exception(
            f"❌ Failed to send refund status email for {reservation.id}: {e}"
        )
