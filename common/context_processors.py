from datetime import datetime
from administration.models import Entreprise
from django.conf import settings


def entreprise_info(request):
    from payment.services.payment_service import PAYMENT_FEE_VARIABLE
    try:
        from common.services.helper_fct import get_entreprise
        entreprise = get_entreprise()
    except Entreprise.DoesNotExist:
        entreprise = None
    return {
        "entreprise": entreprise,
        "current_year": datetime.now().year,
        "site_address": settings.SITE_ADDRESS,
        "contact_mail": settings.CONTACT_EMAIL,
        "payment_fee_variable": PAYMENT_FEE_VARIABLE,
    }
