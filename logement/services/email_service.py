from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.mail import mail_admins


def send_mail_on_new_reservation(logement, reservation, user):
    # Build context for the email
    email_context = {
        "reservation": reservation,
        "logement": logement,
        "user": user,
    }

    # Optional: Render an HTML email template (or create `emails/new_reservation.txt`)
    email_message = render_to_string("email/new_reservation.txt", email_context)

    mail_admins(
        subject=f"🆕 Nouvelle réservation pour {logement.name}",
        message=email_message,
        fail_silently=False,
    )
