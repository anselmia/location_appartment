from datetime import datetime
from administration.models import Entreprise
from django.conf import settings


def entreprise_info(request):
    try:
        entreprise = Entreprise.objects.first()
    except Entreprise.DoesNotExist:
        entreprise = None
    return {
        "entreprise": entreprise,
        "current_year": datetime.now().year,
        "site_address": settings.SITE_ADDRESS,
        "contact_mail": settings.CONTACT_EMAIL,
    }
