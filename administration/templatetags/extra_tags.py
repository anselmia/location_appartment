from django import template
import calendar

register = template.Library()

@register.filter
def get_month_name(month_number):
    return calendar.month_name[int(month_number)]

@register.filter
def to_month_range(value):
    return range(1, 13)