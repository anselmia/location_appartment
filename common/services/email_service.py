import logging

from datetime import timedelta, date

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator

from administration.models import Entreprise


logger = logging.getLogger(__name__)


def send_mail_new_account_validation(user, current_site):
    try:
        subject = "Confirmez votre adresse email"
        email_context = {
            "user": user,
            "domain": current_site.domain,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
        message = render_to_string("email/confirmation_email.txt", email_context)

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        logger.info(f"📧 Validation email sent to {user.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send account validation email to {user.email}: {e}")


def resend_confirmation_email(user, current_site):
    try:
        subject = "Confirmez votre adresse email"
        email_context = {
            "user": user,
            "domain": current_site.domain,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
        message = render_to_string("email/confirmation_email.txt", email_context)

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        logger.info(f"🔁 Confirmation email resent to {user.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to resend confirmation email to {user.email}: {e}")


def send_mail_on_new_reservation(logement, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = Entreprise.objects.first()
        if not entreprise:
            logger.warning("No Entreprise config found, emails may lack branding info.")
            return

        # Build context for the email
        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}

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


def send_pre_checkin_reminders():
    try:
        from reservation.models import Reservation

        today = date.today()
        for delta in [1, 2, 3]:
            target_day = today + timedelta(days=delta)
            reservations = Reservation.objects.filter(
                checkin_date=target_day,
                status="confirmee",
                pre_checkin_email_sent=False,
            )

            for res in reservations:
                entreprise = Entreprise.objects.first()
                if not entreprise:
                    logger.warning("No Entreprise config found, emails may lack branding info.")
                    continue

                context = {
                    "reservation": res,
                    "logement": res.logement,
                    "user_contact": res.logement.admin if res.logement.admin else res.logement.owner,
                    "entreprise": entreprise,
                }
                subject = f"Votre séjour approche - {res.logement.name}"
                message = render_to_string("email/pre_checkin_reminder.txt", context)

                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [res.user.email],
                    fail_silently=False,
                )

                res.pre_checkin_email_sent = True
                res.save()
                logger.info(f"📧 Pre-checkin reminder sent for reservation {res.code}")
    except Exception as e:
        logger.exception(f"❌ Error during pre-checkin reminders: {e}")


def send_mail_on_refund(logement, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = Entreprise.objects.first()
        if not entreprise:
            logger.warning("No Entreprise config found, emails may lack branding info.")
            return

        # Context for email templates
        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}

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
        entreprise = Entreprise.objects.first()
        if not entreprise:
            logger.warning("No Entreprise config found, emails may lack branding info.")
            return

        # Context for email templates
        user = logement.admin if user_type == "admin" else logement.owner
        amount = reservation.admin_transferred_amount if user_type == "admin" else reservation.transferred_amount

        email_context = {
            "reservation": reservation,
            "logement": logement,
            "user": user,
            "amount": amount,
            "entreprise": entreprise,
        }

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
        entreprise = Entreprise.objects.first()
        if not entreprise:
            logger.warning("No Entreprise config found, emails may lack branding info.")
            return

        # Context for email templates

        email_context = {
            "reservation": reservation,
            "logement": reservation.logement,
            "user": reservation.user,
            "url": session["checkout_session_url"],
            "entreprise": entreprise,
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


def send_mail_on_payment_failure(logement, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = Entreprise.objects.first()
        if not entreprise:
            logger.warning("No Entreprise config found, emails may lack branding info.")
            return

        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}

        # ===== ADMIN EMAIL =====
        admin_message = render_to_string("email/payment_failure_admin.txt", email_context)

        send_mail(
            subject=f"💸 Échec de paiement - {logement.name} - Réservation {reservation.code}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=logement.mail_list,
            fail_silently=False,
        )

        logger.info(f"✅ Refund email sent to admins for reservation {reservation.code}.")

        # ===== Customer EMAIL =====
        message = render_to_string("email/payment_failure.txt", email_context)

        # Subject line
        subject = f"❌ Échec de paiement pour votre réservation {reservation.code} - {logement.name}"

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        logger.info(f"📧 Payment failure email sent to {user.email} for reservation {reservation.code}.")

    except Exception as e:
        logger.exception(f"❌ Failed to send payment failure email for reservation {reservation.code}: {e}")


def send_mail_contact(cd):
    try:
        logger.info(f"📨 Tentative d'envoi de message de contact: nom={cd['name']}, email={cd['email']}")

        send_mail(
            subject="Contact depuis le site",
            message=f"Message de {cd['name']} ({cd['email']}):\n\n{cd['message']}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.CONTACT_EMAIL],
            fail_silently=False,
        )

        logger.info(f"✅ Message de contact envoyé avec succès: nom={cd['name']}, email={cd['email']}")
    except Exception as e:
        logger.error(f"❌ Erreur d'envoi de message de contact: nom={cd.get('name')} — erreur: {e}")
        raise
