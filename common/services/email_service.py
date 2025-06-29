import logging

from datetime import timedelta, date

from django.template.loader import render_to_string
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils import timezone
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.core.mail import mail_admins
from common.services.helper_fct import get_entreprise


logger = logging.getLogger(__name__)


def send_mail_new_account_validation(user, current_site):
    try:
        subject = "Confirmez votre adresse email"
        email_context = {
            "user": user,
            "domain": current_site,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
            "entreprise": get_entreprise(),
        }
        message_txt = render_to_string("email/confirmation_email.txt", email_context)
        message_html = render_to_string("email/confirmation_email.html", email_context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"📧 Validation email sent to {user.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send account validation email to {user.email}: {e}")


def resend_confirmation_email(user, current_site):
    try:
        subject = "Confirmez votre adresse email"
        email_context = {
            "user": user,
            "domain": current_site,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
            "entreprise": get_entreprise(),
        }
        message_txt = render_to_string("email/confirmation_email.txt", email_context)
        message_html = render_to_string("email/confirmation_email.html", email_context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
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
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/new_reservation.txt", email_context)
        admin_message_html = render_to_string("email/new_reservation_admin.html", email_context)
        subject_admin = f"🆕 Nouvelle Réservation {reservation.code} pour {logement.name}"
        admin_emails = logement.mail_list
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, admin_emails)
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Mail sent for reservation {reservation.code} to admins.")

        # ========== CUSTOMER CONFIRMATION ==========
        if user.email:
            subject = f"Confirmation de votre Réservation {reservation.code} - {logement.name}"
            user_message_txt = render_to_string("email/new_reservation_customer.txt", email_context)
            user_message_html = render_to_string("email/new_reservation_customer.html", email_context)
            msg_user = EmailMultiAlternatives(subject, user_message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
            msg_user.attach_alternative(user_message_html, "text/html")
            msg_user.send(fail_silently=False)
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

        email_context = {"reservation": reservation, "activity": activity, "user": user, "entreprise": entreprise}
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/new_activity_reservation.txt", email_context)
        admin_message_html = render_to_string("email/activity_new_reservation.html", email_context)
        subject_admin = f"🆕 Nouvelle Réservation {reservation.code} pour {activity.name}"
        admin_email = activity.owner.email
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, [admin_email])
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Mail sent for reservation {reservation.code} to admins.")

        # ========== CUSTOMER CONFIRMATION ==========
        if user.email:
            subject = f"Confirmation de votre Réservation {reservation.code} - {activity.name}"
            user_message_txt = render_to_string("email/new_activity_reservation_customer.txt", email_context)
            user_message_html = render_to_string("email/new_activity_reservation_customer.html", email_context)
            msg_user = EmailMultiAlternatives(subject, user_message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
            msg_user.attach_alternative(user_message_html, "text/html")
            msg_user.send(fail_silently=False)
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
                statut="confirmee",
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
                message_txt = render_to_string("email/pre_checkin_reminder.txt", context)
                message_html = render_to_string("email/pre_checkin_reminder.html", context)
                msg = EmailMultiAlternatives(
                    subject,
                    message_txt,
                    settings.DEFAULT_FROM_EMAIL,
                    [res.user.email],
                )
                msg.attach_alternative(message_html, "text/html")
                msg.send(fail_silently=False)

                res.pre_checkin_email_sent = True
                res.save()
                logger.info(f"📧 Pre-checkin reminder sent for reservation {res.code}")
    except Exception as e:
        logger.exception(f"❌ Error during pre-checkin reminders: {e}")


def send_pre_checkin_activity_reminders():
    try:
        from reservation.models import ActivityReservation

        today = date.today()
        for delta in [1, 2, 3]:
            target_day = today + timedelta(days=delta)
            reservations = ActivityReservation.objects.filter(
                start__date=target_day,
                statut="confirmee",
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
                message_txt = render_to_string("email/pre_checkin_activity_reminder.txt", context)
                message_html = render_to_string("email/pre_checkin_activity_reminder.html", context)
                msg = EmailMultiAlternatives(
                    subject,
                    message_txt,
                    settings.DEFAULT_FROM_EMAIL,
                    [res.user.email],
                )
                msg.attach_alternative(message_html, "text/html")
                msg.send(fail_silently=False)

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

        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/refund_logement_admin.txt", email_context)
        admin_message_html = render_to_string("email/refund_logement_admin.html", email_context)
        subject_admin = f"💸 Remboursement effectué - {logement.name} - Réservation {reservation.code}"
        admin_emails = logement.mail_list
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, admin_emails)
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Refund email sent to admins for reservation {reservation.code}.")

        # User email (HTML + plain)
        if user.email:
            user_message_txt = render_to_string("email/refund_logement_customer.txt", email_context)
            user_message_html = render_to_string("email/refund_logement_customer.html", email_context)
            msg_user = EmailMultiAlternatives(
                f"Remboursement de votre Réservation {reservation.code} - {logement.name}",
                user_message_txt,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg_user.attach_alternative(user_message_html, "text/html")
            msg_user.send(fail_silently=False)
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

        email_context = {"reservation": reservation, "activity": activity, "user": user, "entreprise": entreprise}
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/refund_activity_admin.txt", email_context)
        admin_message_html = render_to_string("email/refund_activity_admin.html", email_context)
        subject_admin = f"💸 Remboursement effectué - {activity.name} - Réservation {reservation.code}"
        admin_email = activity.owner.email
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, [admin_email])
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Refund email sent to owners for reservation {reservation.code}.")

        # User email (HTML + plain)
        if user.email:
            user_message_txt = render_to_string("email/refund_activity_customer.txt", email_context)
            user_message_html = render_to_string("email/refund_activity_customer.html", email_context)
            msg_user = EmailMultiAlternatives(
                f"Remboursement de votre Réservation {reservation.code} - {activity.name}",
                user_message_txt,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg_user.attach_alternative(user_message_html, "text/html")
            msg_user.send(fail_silently=False)
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
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/transfer_admin.txt", email_context)
        admin_message_html = render_to_string("email/transfer_admin.html", email_context)
        subject_admin = f"💸 Transfert effectué à {user} - {logement.name} - Réservation {reservation.code}"
        admin_emails = logement.mail_list
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, admin_emails)
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Transfer email sent to admins for reservation {reservation.code}.")

        # User email (HTML + plain)
        if user.email:
            user_message_txt = render_to_string("email/transfer_user.txt", email_context)
            user_message_html = render_to_string("email/transfer_user.html", email_context)
            msg_user = EmailMultiAlternatives(
                f"Transfert des fonds de la Réservation {reservation.code} - {logement.name}",
                user_message_txt,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg_user.attach_alternative(user_message_html, "text/html")
            msg_user.send(fail_silently=False)
            logger.info(f"✅ Transfer confirmation sent to user {user.email} for reservation {reservation.code}")
    except Exception as e:
        logger.exception(f"❌ Failed to send transfer email for reservation {reservation.code}: {e}")


def send_mail_on_new_activity_transfer(activity, reservation, user_type):
    try:
        entreprise = get_entreprise()
        if not entreprise:
            return
        user = activity.owner
        amount = reservation.transferred_amount
        email_context = {
            "reservation": reservation,
            "activity": activity,
            "user": user,
            "amount": amount,
            "entreprise": entreprise,
        }
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/transfer_activity_admin.txt", email_context)
        admin_message_html = render_to_string("email/transfer_activity_admin.html", email_context)
        subject_admin = f"💸 Transfert effectué à {user} - {activity.name} - Réservation {reservation.code}"
        admin_email = activity.owner.email
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, [admin_email])
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Transfer email sent to admins for reservation {reservation.code}.")

        # User email (HTML + plain)
        if user.email:
            user_message_txt = render_to_string("email/transfer_activity_user.txt", email_context)
            user_message_html = render_to_string("email/transfer_activity_user.html", email_context)
            msg_user = EmailMultiAlternatives(
                f"Transfert des fonds de la Réservation {reservation.code} - {activity.name}",
                user_message_txt,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg_user.attach_alternative(user_message_html, "text/html")
            msg_user.send(fail_silently=False)
            logger.info(f"✅ Transfer confirmation sent to user {user.email} for reservation {reservation.code}")
    except Exception as e:
        logger.exception(f"❌ Failed to send transfer email for reservation {reservation.code}: {e}")


def send_mail_payment_link(reservation):
    try:
        entreprise = get_entreprise()
        if not entreprise:
            return
        email_context = {
            "reservation": reservation,
            "logement": reservation.logement,
            "user": reservation.user,
            "url": f"{settings.SITE_ADDRESS}/payment/pay/{reservation.code}/",
            "entreprise": entreprise,
        }
        subject = f"Réservation {reservation.code} - Logement {reservation.logement.name} - Lien de paiement"
        message_txt = render_to_string("email/payment_link.txt", email_context)
        message_html = render_to_string("email/payment_link.html", email_context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [reservation.user.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Payment link sent to customer for reservation {reservation.code}.")
    except Exception as e:
        logger.exception(f"❌ Failed to send transfer email for reservation {reservation.code}: {e}")


def send_mail_activity_payment_link(reservation):
    try:
        entreprise = get_entreprise()
        if not entreprise:
            return
        email_context = {
            "reservation": reservation,
            "activity": reservation.activity,
            "user": reservation.user,
            "url": f"{settings.SITE_ADDRESS}/payment/pay/{reservation.code}/",
            "entreprise": entreprise,
        }
        subject = f"Réservation {reservation.code} - Activité {reservation.activity.name} - Lien de paiement"
        message_txt = render_to_string("email/payment_link_activity.txt", email_context)
        message_html = render_to_string("email/payment_link_activity.html", email_context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [reservation.user.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Payment link sent to customer for reservation {reservation.code}.")
    except Exception as e:
        logger.exception(f"❌ Failed to send transfer email for reservation {reservation.code}: {e}")


def send_mail_logement_payment_success(logement, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = get_entreprise()
        if not entreprise:
            return

        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/payment_success_admin.txt", email_context)
        admin_message_html = render_to_string("email/payment_success_admin.html", email_context)
        subject_admin = f"✅ Paiement reçu - {logement.name} - Réservation {reservation.code}"
        admin_emails = logement.mail_list
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, admin_emails)
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Payment success email sent to admins for reservation {reservation.code}.")

        # Customer email (HTML + plain)
        if user.email:
            message_txt = render_to_string("email/payment_success.txt", email_context)
            message_html = render_to_string("email/payment_success.html", email_context)
            subject = f"✅ Paiement reçu pour votre réservation {reservation.code} - {logement.name}"
            msg_user = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
            msg_user.attach_alternative(message_html, "text/html")
            msg_user.send(fail_silently=False)
            logger.info(f"📧 Payment success email sent to {user.email} for reservation {reservation.code}.")

    except Exception as e:
        logger.exception(f"❌ Failed to send payment success email for reservation {reservation.code}: {e}")


def send_mail_activity_payment_success(activity, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = get_entreprise()
        if not entreprise:
            return

        email_context = {"reservation": reservation, "activity": activity, "user": user, "entreprise": entreprise}
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/payment_success_activity_admin.txt", email_context)
        admin_message_html = render_to_string("email/payment_success_activity_admin.html", email_context)
        subject_admin = f"✅ Paiement reçu - {activity.name} - Réservation {reservation.code}"
        admin_emails = [activity.owner.email]
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, admin_emails)
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Payment success email sent to admins for reservation {reservation.code}.")

        # Customer email (HTML + plain)
        if user.email:
            message_txt = render_to_string("email/payment_success_activity.txt", email_context)
            message_html = render_to_string("email/payment_success_activity.html", email_context)
            subject = f"✅ Paiement reçu pour votre réservation {reservation.code} - {activity.name}"
            msg_user = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
            msg_user.attach_alternative(message_html, "text/html")
            msg_user.send(fail_silently=False)
            logger.info(f"📧 Payment success email sent to {user.email} for reservation {reservation.code}.")

    except Exception as e:
        logger.exception(f"❌ Failed to send payment success email for reservation {reservation.code}: {e}")


def send_mail_on_payment_failure(logement, reservation, user):
    try:
        if not user or not getattr(user, "email", None):
            logger.warning(f"No valid user email for reservation {reservation.code}")
            return

        entreprise = get_entreprise()
        if not entreprise:
            return

        email_context = {"reservation": reservation, "logement": logement, "user": user, "entreprise": entreprise}
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # Admin/owner email (HTML + plain)
        admin_message_txt = render_to_string("email/payment_failure_admin.txt", email_context)
        admin_message_html = render_to_string("email/payment_failure_admin.html", email_context)
        subject_admin = f"💸 Échec de paiement - {logement.name} - Réservation {reservation.code}"
        admin_emails = logement.mail_list
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, admin_emails)
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Payment failure email sent to admins for reservation {reservation.code}.")

        # Customer email (HTML + plain)
        if user.email:
            message_txt = render_to_string("email/payment_failure.txt", email_context)
            message_html = render_to_string("email/payment_failure.html", email_context)
            subject = f"❌ Échec de paiement pour votre réservation {reservation.code} - {logement.name}"
            msg_user = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
            msg_user.attach_alternative(message_html, "text/html")
            msg_user.send(fail_silently=False)
            logger.info(f"📧 Payment failure email sent to {user.email} for reservation {reservation.code}.")

        mail_admins(
            subject=f"❌ Échec de paiement pour la réservation {reservation.code} - {logement.name}",
            message=admin_message_txt,
            fail_silently=False,
        )
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
        # Add espace_partenaire_url if needed
        if hasattr(settings, "SITE_ADDRESS"):
            email_context["espace_partenaire_url"] = settings.SITE_ADDRESS + "/accounts/dashboard/"
        else:
            email_context["espace_partenaire_url"] = "#"
        email_context["now"] = timezone.now()

        # ===== OWNER EMAIL =====
        admin_message_txt = render_to_string("email/activity_payment_failure_admin.txt", email_context)
        admin_message_html = render_to_string("email/activity_payment_failure_admin.html", email_context)
        subject_admin = f"💸 Échec de paiement - {activity.name} - Réservation {reservation.code}"
        admin_email = activity.owner.email
        msg = EmailMultiAlternatives(subject_admin, admin_message_txt, settings.DEFAULT_FROM_EMAIL, [admin_email])
        msg.attach_alternative(admin_message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Payment failure email sent to admins for reservation {reservation.code}.")

        # ===== Customer EMAIL (HTML + plain) =====
        if user.email:
            message_txt = render_to_string("email/activity_payment_failure.txt", email_context)
            message_html = render_to_string("email/activity_payment_failure.html", email_context)
            subject = f"❌ Échec de paiement pour votre réservation {reservation.code} - {activity.name}"
            msg_user = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
            msg_user.attach_alternative(message_html, "text/html")
            msg_user.send(fail_silently=False)
            logger.info(f"📧 Payment failure email sent to {user.email} for reservation {reservation.code}.")

        mail_admins(
            subject=f"❌ Échec de paiement pour la réservation {reservation.code} - {activity.name}",
            message=admin_message_txt,
            fail_silently=False,
        )
    except Exception as e:
        logger.exception(f"❌ Failed to send payment failure email for reservation {reservation.code}: {e}")


def send_message_notification_email(message, recipient):
    try:
        subject = f"Nouveau message de {message.sender}"
        context = {
            "recipient": recipient,
            "message": message,
            "reservation": message.conversation.reservation,
            "site_address": settings.SITE_ADDRESS,
        }
        body_txt = render_to_string("email/message_notification.txt", context)
        body_html = render_to_string("email/message_notification.html", context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_txt,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
        )
        msg.attach_alternative(body_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Notification envoyée à {recipient.email} pour le message {message.id}")
    except Exception:
        logger.exception(
            f"Échec de la notification pour message {getattr(message, 'id', '?')} à utilisateur {getattr(recipient, 'id', '?')}"
        )


def send_contact_email_notification(cd):
    try:
        context = {
            "name": cd["name"],
            "email": cd["email"],
            "message": cd["message"],
            "subject": cd["subject"],
        }
        subject = cd["subject"]
        body_txt = render_to_string("email/contact_notification.txt", context)
        body_html = render_to_string("email/contact_notification.html", context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_txt,
            from_email=cd["email"],
            to=[settings.CONTACT_EMAIL],
        )
        msg.attach_alternative(body_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Contact email sent from {cd['email']} to {settings.CONTACT_EMAIL}")
    except Exception as e:
        logger.exception(f"Erreur d'envoi email de contact: {e}")


def send_email_new_message(msg):
    try:
        entreprise = get_entreprise()
        if not entreprise:
            return
        reservation = msg.conversation.reservation
        for user in msg.recipients.all():
            email_context = {"user": user, "reservation": reservation, "entreprise": entreprise}
            subject = f"✉️ Nouveau message - Réservation {reservation.code}"
            message_txt = render_to_string("email/new_message.txt", email_context)
            message_html = render_to_string("email/new_message.html", email_context)
            m = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [user.email])
            m.attach_alternative(message_html, "text/html")
            m.send(fail_silently=False)
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
        message_txt = render_to_string("email/conciergerie_request_accepted.txt", context)
        message_html = render_to_string("email/conciergerie_request_accepted.html", context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [owner.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
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
        message_txt = render_to_string("email/conciergerie_request_refused.txt", context)
        message_html = render_to_string("email/conciergerie_request_refused.html", context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [owner.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
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
        message_txt = render_to_string("email/conciergerie_request_new.txt", context)
        message_html = render_to_string("email/conciergerie_request_new.html", context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [conciergerie_user.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
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
        message_txt = render_to_string("email/conciergerie_stop_management.txt", context)
        message_html = render_to_string("email/conciergerie_stop_management.html", context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [owner.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
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
        message_txt = render_to_string("email/partner_validation.txt", context)
        message_html = render_to_string("email/partner_validation.html", context)
        msg = EmailMultiAlternatives(subject, message_txt, settings.DEFAULT_FROM_EMAIL, [partner.email])
        msg.attach_alternative(message_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ Partner validation email sent to {partner.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send partner validation email to {partner.email}: {e}")


def notify_vendor_new_reservation(reservation):
    try:
        entreprise = get_entreprise()
        context = {
            "reservation": reservation,
            "entreprise": entreprise,
            "espace_partenaire_url": settings.SITE_ADDRESS + "/accounts/dashboard/",
            "now": timezone.now(),
        }
        vendor_email = reservation.activity.owner.email
        subject = "Nouvelle demande de réservation d'activité"
        text_content = render_to_string("email/activity_new_reservation.txt", context)
        html_content = render_to_string("email/activity_new_reservation.html", context)

        msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [vendor_email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"✅ New reservation email sent to {vendor_email}")
    except Exception as e:
        logger.exception(f"❌ Failed to notify vendor for new reservation {reservation.id}: {e}")


def send_conciergerie_validation_email_notification(conciergerie):
    try:
        subject = "🎉 Votre conciergerie a été validée !"
        context = {
            "conciergerie": conciergerie,
            "entreprise": get_entreprise(),
        }
        body_txt = render_to_string("email/conciergerie_validation.txt", context)
        body_html = render_to_string("email/conciergerie_validation.html", context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_txt,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[conciergerie.email],
        )
        msg.attach_alternative(body_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Validation email sent to conciergerie {conciergerie.email}")
    except Exception as e:
        logger.exception(f"Erreur d'envoi email de validation conciergerie: {e}")


def send_admin_conciergerie_validation_email_notification(conciergerie):
    try:
        subject = "Nouvelle conciergerie en attente de validation"
        context = {
            "conciergerie": conciergerie,
            "entreprise": get_entreprise(),
        }
        mail_admins(
            subject=subject,
            message=render_to_string("email/admin_conciergerie_validation.txt", context),
            fail_silently=False,
        )
        logger.info(f"Admin validation email sent for conciergerie {conciergerie.name}")
    except Exception as e:
        logger.exception(f"Erreur d'envoi email de validation admin conciergerie: {e}")


def send_admin_partner_validation_email_notification(partner):
    try:
        subject = "Nouveau partenaire en attente de validation"
        context = {
            "partner": partner,
            "entreprise": get_entreprise(),
        }
        mail_admins(
            subject=subject,
            message=render_to_string("email/admin_partner_validation.txt", context),
            fail_silently=False,
        )
        logger.info(f"Admin validation email sent for partner {partner.name}")
    except Exception as e:
        logger.exception(f"Erreur d'envoi email de validation admin partenaire: {e}")


def send_mail_on_manual_payment_intent_failure(reservation):
    try:
        subject = "Échec de la création du paiement"
        context = {
            "reservation": reservation,
            "entreprise": get_entreprise(),
        }
        body_txt = render_to_string("email/manual_payment_intent_failure.txt", context)
        body_html = render_to_string("email/manual_payment_intent_failure.html", context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_txt,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reservation.user.email],
        )
        msg.attach_alternative(body_html, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Email sent to user {reservation.user.email} about manual payment intent failure")
    except Exception as e:
        logger.exception(f"Error sending email about manual payment intent failure: {e}")
