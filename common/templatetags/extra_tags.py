from django import template

register = template.Library()


FRENCH_MONTHS = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre",
}


@register.filter
def get_month_name(month_number):
    try:
        return FRENCH_MONTHS[int(month_number)]
    except (ValueError, KeyError):
        return f"Mois {month_number}"


@register.filter
def to_month_range(value):
    return range(1, 13)


@register.filter
def cents_to_euros(value):
    try:
        return float(value) / 100
    except (ValueError, TypeError):
        return 0.00


@register.filter
def get(dict_obj, key):
    if isinstance(dict_obj, dict):
        return dict_obj.get(key, [])
    return []


@register.filter
def replace(value, args):
    old, new = args.split(",")
    return value.replace(old, new)


@register.filter
def duration_hm(minutes):
    minutes = int(minutes or 0)
    hours = minutes // 60
    mins = minutes % 60
    if hours and mins:
        return f"{hours}h {mins}min"
    elif hours:
        return f"{hours}h"
    else:
        return f"{mins}min"


@register.filter
def is_dict(value):
    return isinstance(value, dict)


@register.filter
def is_list(value):
    return isinstance(value, list)
