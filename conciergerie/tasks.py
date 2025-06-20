from huey.contrib.djhuey import task
from django.conf import settings
from common.services import email_service


@task()
def send_conciergerie_validation_email(conciergerie_id):
    from .models import Conciergerie

    conciergerie = Conciergerie.objects.get(id=conciergerie_id)
    email_service.send_conciergerie_validation_email_notification(conciergerie)
