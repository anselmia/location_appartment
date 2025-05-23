from datetime import datetime
from administration.models import Entreprise


def entreprise_info(request):
    try:
        entreprise = Entreprise.objects.first()
    except Entreprise.DoesNotExist:
        entreprise = None
    return {
        "entreprise": entreprise,
        "current_year": datetime.now().year,
    }
