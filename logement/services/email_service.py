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
        send_mail(
            subject=f"🆕 Nouvelle Réservation {reservation.code} pour {logement.name}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=logement.mail_list,
            fail_silently=False,  # Raise in dev, log in prod
        )

        logger.info(f"✅ Mail sent for reservation {reservation.code} to admins.")

        # ========== CUSTOMER CONFIRMATION ==========
        if user.email:
            subject = f"Confirmation de votre Réservation {reservation.code} - {logement.name}"
            user_message = render_to_string("email/new_reservation_customer.txt", email_context)

            send_mail(
                subject=subject,
                message=user_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info(f"✅ Confirmation mail sent to user {user.email} for reservation {reservation.code}")

    except Exception as e:
        logger.exception(f"❌ Failed to send admin mail for reservation {reservation.code}: {e}")


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

        send_mail(
            subject=f"💸 Remboursement effectué - {logement.name} - Réservation {reservation.code}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=logement.mail_list,
            fail_silently=False,
        )

        logger.info(f"✅ Refund email sent to admins for reservation {reservation.code}.")

        # ===== USER EMAIL =====
        if user.email:
            user_message = render_to_string("email/refund_customer.txt", email_context)

            send_mail(
                subject=f"Remboursement de votre Réservation {reservation.code} - {logement.name}",
                message=user_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            logger.info(f"✅ Refund confirmation sent to user {user.email} for reservation {reservation.code}")

    except Exception as e:
        logger.exception(f"❌ Failed to send refund email for reservation {reservation.code}: {e}")


def send_mail_on_new_transfer(logement, reservation, user_type):
    try:
        # Context for email templates
        user = reservation.admin if user_type == "admin" else reservation.owner
        amount = reservation.admin_transferred_amount if user_type == "admin" else reservation.transferred_amount

        email_context = {"reservation": reservation, "logement": logement, "user": user, "amount": amount}

        # ===== ADMIN EMAIL =====
        admin_message = render_to_string("email/transfer_admin.txt", email_context)

        send_mail(
            subject=f"💸 Transfert effectué à {user} - {logement.name} - Réservation {reservation.code}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=logement.mail_list,
            fail_silently=False,
        )

        logger.info(f"✅ Transfer email sent to admins for reservation {reservation.code}.")

        # ===== USER EMAIL =====
        if user.email:
            user_message = render_to_string("email/transfer_user.txt", email_context)

            send_mail(
                subject=f"Transfert des fonds de la Réservation {reservation.code} - {logement.name}",
                message=user_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            logger.info(f"✅ Transfer confirmation sent to user {user.email} for reservation {reservation.code}")

    except Exception as e:
        logger.exception(f"❌ Failed to send transfer email for reservation {reservation.code}: {e}")


def send_mail_payment_link(reservation, session):
    try:
        # Context for email templates

        email_context = {
            "reservation": reservation,
            "logement": reservation.logement,
            "user": reservation.user,
            "url": session["checkout_session_url"],
        }

        # ===== Customer EMAIL =====
        admin_message = render_to_string("email/payment_link.txt", email_context)

        send_mail(
            subject=f"Réservation {reservation.code} - Logement {reservation.logement} - Lien de paiement",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reservation.user.email],
            fail_silently=False,
        )

        logger.info(f"✅ Payment link sent to customer for reservation {reservation.code}.")
    except Exception as e:
        logger.exception(f"❌ Failed to send transfer email for reservation {reservation.code}: {e}")
