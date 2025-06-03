import random
import string
from django.http import HttpRequest
from django.http import QueryDict


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
