import logging

from datetime import timedelta, date

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils import timezone
from django.contrib.auth.tokens import default_token_generator

from common.services.helper_fct import get_entreprise


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

        entreprise = get_entreprise()
        if not entreprise:
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


def send_mail_on_new_activity_reservation(activity, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = get_entreprise()
        if not entreprise:
            return

        # Build context for the email
        email_context = {"reservation": reservation, "activity": activity, "user": user, "entreprise": entreprise}

        # Render email content
        admin_message = render_to_string("email/new_activity_reservation.txt", email_context)

        # Send email to admins
        send_mail(
            subject=f"🆕 Nouvelle Réservation {reservation.code} pour {activity.name}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[activity.owner.email],
            fail_silently=False,  # Raise in dev, log in prod
        )

        logger.info(f"✅ Mail sent for reservation {reservation.code} to admins.")

        # ========== CUSTOMER CONFIRMATION ==========
        if user.email:
            subject = f"Confirmation de votre Réservation {reservation.code} - {activity.name}"
            user_message = render_to_string("email/new_activity_reservation_customer.txt", email_context)

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
                start=target_day,
                status="confirmee",
                pre_checkin_email_sent=False,
            )

            for res in reservations:
                entreprise = get_entreprise()
                if not entreprise:
                    return

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


def send_pre_checkin_activity_reminders():
    try:
        from activity.models import ActivityReservation

        today = date.today()
        for delta in [1, 2, 3]:
            target_day = today + timedelta(days=delta)
            reservations = ActivityReservation.objects.filter(
                start__date=target_day,
                status="confirmee",
                pre_checkin_email_sent=False,
            )

            for res in reservations:
                entreprise = get_entreprise()
                if not entreprise:
                    return

                context = {
                    "reservation": res,
                    "activity": res.activity,
                    "user_contact": res.activity.owner,
                    "entreprise": entreprise,
                }
                subject = f"Votre activité approche - {res.activity.name}"
                message = render_to_string("email/pre_checkin_activity_reminder.txt", context)

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


def send_mail_on_logement_refund(logement, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = get_entreprise()
        if not entreprise:
            return

        # Context for email templates
        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}

        # ===== OWNER AND ADMIN EMAIL =====
        admin_message = render_to_string("email/refund_logement_admin.txt", email_context)

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
            user_message = render_to_string("email/refund_logement_customer.txt", email_context)

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


def send_mail_on_activity_refund(activity, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = get_entreprise()
        if not entreprise:
            return

        # Context for email templates
        email_context = {"reservation": reservation, "activity": activity, "user": user, "entreprise": entreprise}

        # ===== OWNER EMAIL =====
        admin_message = render_to_string("email/refund_activity_admin.txt", email_context)

        send_mail(
            subject=f"💸 Remboursement effectué - {activity.name} - Réservation {reservation.code}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[activity.owner.email],
            fail_silently=False,
        )

        logger.info(f"✅ Refund email sent to owners for reservation {reservation.code}.")

        # ===== USER EMAIL =====
        if user.email:
            user_message = render_to_string("email/refund_activity_customer.txt", email_context)

            send_mail(
                subject=f"Remboursement de votre Réservation {reservation.code} - {activity.name}",
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
        entreprise = get_entreprise()
        if not entreprise:
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


def send_mail_on_new_activity_transfer(activity, reservation, user_type):
    try:
        entreprise = get_entreprise()
        if not entreprise:
            return

        # Context for email templates
        user = activity.owner
        amount = reservation.transferred_amount

        email_context = {
            "reservation": reservation,
            "activity": activity,
            "user": user,
            "amount": amount,
            "entreprise": entreprise,
        }

        # ===== ADMIN EMAIL =====
        admin_message = render_to_string("email/transfer_activity_admin.txt", email_context)

        send_mail(
            subject=f"💸 Transfert effectué à {user} - {activity.name} - Réservation {reservation.code}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[activity.owner.email],
            fail_silently=False,
        )

        logger.info(f"✅ Transfer email sent to admins for reservation {reservation.code}.")

        # ===== USER EMAIL =====
        if user.email:
            user_message = render_to_string("email/transfer_activity_user.txt", email_context)

            send_mail(
                subject=f"Transfert des fonds de la Réservation {reservation.code} - {activity.name}",
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
        entreprise = get_entreprise()
        if not entreprise:
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


def send_mail_activity_payment_link(reservation, session):
    try:
        entreprise = get_entreprise()
        if not entreprise:
            return

        # Context for email templates

        email_context = {
            "reservation": reservation,
            "activity": reservation.activity,
            "user": reservation.user,
            "url": session["checkout_session_url"],
            "entreprise": entreprise,
        }

        # ===== Customer EMAIL =====
        message = render_to_string("email/payment_link_activity.txt", email_context)

        send_mail(
            subject=f"Réservation {reservation.code} - Activité {reservation.activity} - Lien de paiement",
            message=message,
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

        entreprise = get_entreprise()
        if not entreprise:
            return

        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}

        # ===== OWNER & ADMIN EMAIL =====
        admin_message = render_to_string("email/payment_failure_admin.txt", email_context)

        send_mail(
            subject=f"💸 Échec de paiement - {logement.name} - Réservation {reservation.code}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=logement.mail_list,
            fail_silently=False,
        )

        logger.info(f"✅ Payment failure email sent to admins for reservation {reservation.code}.")

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


def send_mail_on_activity_payment_failure(activity, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = get_entreprise()
        if not entreprise:
            return

        email_context = {"reservation": reservation, "activity": activity, "user": user, "entreprise": entreprise}

        # ===== OWNER & ADMIN EMAIL =====
        admin_message = render_to_string("email/activity_payment_failure_admin.txt", email_context)

        send_mail(
            subject=f"💸 Échec de paiement - {activity.name} - Réservation {reservation.code}",
            message=admin_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[activity.owner.email],
            fail_silently=False,
        )

        logger.info(f"✅ Payment failure email sent to admins for reservation {reservation.code}.")

        # ===== Customer EMAIL =====
        message = render_to_string("email/activity_payment_failure.txt", email_context)

        # Subject line
        subject = f"❌ Échec de paiement pour votre réservation {reservation.code} - {activity.name}"

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


def send_email_new_message(msg):
    try:
        entreprise = get_entreprise()
        if not entreprise:
            return

        reservation = msg.conversation.reservation
        for user in msg.recipients.all():  # Correction ici
            email_context = {"user": user, "reservation": reservation, "entreprise": entreprise}

            # ===== EMAIL =====
            message = render_to_string("email/new_message.txt", email_context)

            send_mail(
                subject=f"✉️ Nouveau message - Réservation {reservation.code}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[
                    user.email,
                ],
                fail_silently=False,
            )

            logger.info(f"✅ new message email sent to {user.full_name} for reservation {reservation.code}.")

    except Exception as e:
        logger.exception(f"❌ Failed to send new message email for message {msg.id}: {e}")


def send_mail_conciergerie_request_accepted(owner, conciergerie, logement):
    try:
        entreprise = get_entreprise()
        subject = f"Votre demande de conciergerie a été acceptée pour {logement.name}"
        context = {
            "owner": owner,
            "conciergerie": conciergerie,
            "logement": logement,
            "entreprise": entreprise,
        }
        message = render_to_string("email/conciergerie_request_accepted.txt", context)
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [owner.email],
            fail_silently=False,
        )
        logger.info(f"✅ Mail conciergerie accepted sent to {owner.email} for logement {logement.name}")
    except Exception as e:
        logger.exception(f"❌ Failed to send conciergerie accepted mail to {owner.email}: {e}")


def send_mail_conciergerie_request_refused(owner, conciergerie, logement):
    try:
        entreprise = get_entreprise()
        subject = f"Votre demande de conciergerie a été refusée pour {logement.name}"
        context = {
            "owner": owner,
            "conciergerie": conciergerie,
            "logement": logement,
            "entreprise": entreprise,
        }
        message = render_to_string("email/conciergerie_request_refused.txt", context)
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [owner.email],
            fail_silently=False,
        )
        logger.info(f"✅ Mail conciergerie refused sent to {owner.email} for logement {logement.name}")
    except Exception as e:
        logger.exception(f"❌ Failed to send conciergerie refused mail to {owner.email}: {e}")


def send_mail_conciergerie_request_new(conciergerie_user, logement, owner):
    try:
        entreprise = get_entreprise()
        subject = f"Nouvelle demande de gestion pour {logement.name}"
        context = {
            "conciergerie_user": conciergerie_user,
            "logement": logement,
            "owner": owner,
            "entreprise": entreprise,
        }
        message = render_to_string("email/conciergerie_request_new.txt", context)
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [conciergerie_user.email],
            fail_silently=False,
        )
        logger.info(f"✅ Mail new conciergerie request sent to {conciergerie_user.email} for logement {logement.name}")
    except Exception as e:
        logger.exception(f"❌ Failed to send new conciergerie request mail to {conciergerie_user.email}: {e}")


def send_mail_conciergerie_stop_management(owner, conciergerie, logement):
    try:
        entreprise = get_entreprise()
        subject = f"Fin de gestion de votre logement {logement.name} par la conciergerie"
        context = {
            "owner": owner,
            "conciergerie": conciergerie,
            "logement": logement,
            "entreprise": entreprise,
        }
        message = render_to_string("email/conciergerie_stop_management.txt", context)
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [owner.email],
            fail_silently=False,
        )
        logger.info(f"✅ Mail stop management sent to {owner.email} for logement {logement.name}")
    except Exception as e:
        logger.exception(f"❌ Failed to send stop management mail to {owner.email}: {e}")


def send_partner_validation_email(partner):
    try:
        entreprise = get_entreprise()
        subject = f"Validation de votre partenariat avec {entreprise.name}"
        context = {
            "partner": partner,
            "entreprise": entreprise,
        }
        message = render_to_string("email/partner_validation.txt", context)
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [partner.email],
            fail_silently=False,
        )
        logger.info(f"✅ Partner validation email sent to {partner.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send partner validation email to {partner.email}: {e}")


def notify_vendor_new_reservation(reservation):
    try:
        entreprise = get_entreprise()
        context = {
            "reservation": reservation,
            "entreprise": entreprise,
            "espace_partenaire_url": settings.SITE_ADDRESS + "accounts/dashboard/",
            "now": timezone.now(),
        }
        vendor_email = reservation.activity.owner.email
        subject = "Nouvelle demande de réservation d'activité"
        text_content = render_to_string("email/activity_new_reservation.txt", context)
        html_content = render_to_string("email/activity_new_reservation.html", context)
        from django.core.mail import EmailMultiAlternatives

        msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [vendor_email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ New reservation email sent to {vendor_email}")
    except Exception as e:
        logger.exception(f"❌ Failed to notify vendor for new reservation {reservation.id}: {e}")
