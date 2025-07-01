import random
import string
import time
import logging
import json

from django.core.paginator import Paginator, Page
from django.db.models import QuerySet
from django.core.cache import cache
from administration.models import Entreprise

from datetime import datetime
from django.http import HttpRequest
from django.http import QueryDict

logger = logging.getLogger(__name__)


def generate_unique_code(length=8):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def normalize_decimal_input(data):
    if isinstance(data, QueryDict):
        data = data.copy()
    if "value" in data:
        data["value"] = data["value"].replace(",", ".")
    return data


def is_ajax(request: HttpRequest):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def date_to_timestamp(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(time.mktime(dt.timetuple()))


ENTREPRISE_CACHE_KEY = "entreprise_instance"
ENTREPRISE_CACHE_TIMEOUT = 60 * 60  # 1 hour


def get_entreprise(force_refresh=False):
    """
    Returns the first Entreprise instance, using cache.
    If none is found, logs a warning.

    :param force_refresh: Invalidate and reload from DB
    :return: Entreprise instance or None
    """
    if not force_refresh:
        entreprise = cache.get(ENTREPRISE_CACHE_KEY)
        if entreprise:
            return entreprise

    entreprise = Entreprise.objects.first()
    if entreprise:
        cache.set(ENTREPRISE_CACHE_KEY, entreprise, ENTREPRISE_CACHE_TIMEOUT)
    else:
        logger.warning("⚠️ Aucune configuration Entreprise trouvée.")

    return entreprise


def paginate_queryset(queryset: QuerySet, request: HttpRequest, per_page: int = 20) -> Page:
    """
    Paginate a queryset for the given request.
    """
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


def pretty_json(val):
    try:
        return json.dumps(json.loads(val), indent=2, ensure_ascii=False)
    except Exception:
        return val


def parse_json_field(val):
    try:
        return json.loads(val)
    except Exception:
        return val
