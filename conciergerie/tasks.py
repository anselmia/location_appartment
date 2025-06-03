from django.core.mail import send_mail
from django.conf import settings


def send_conciergerie_validation_email(conciergerie_id):
    from .models import Conciergerie

    conciergerie = Conciergerie.objects.get(id=conciergerie_id)

    send_mail(
        subject="🎉 Votre conciergerie a été validée !",
        message=f"Bonjour {conciergerie.name},\n\nVotre conciergerie a été validée par l'équipe. Vous pouvez maintenant accéder aux fonctionnalités avancées.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[conciergerie.email],
        fail_silently=False,
    )
