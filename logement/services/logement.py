import logging
import hashlib

from datetime import timedelta, date
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.db.models import Count, Q
from django.utils.dateparse import parse_date

from logement.models import Price, Discount, Logement

from payment.services.payment_service import get_payment_fee

logger = logging.getLogger(__name__)


def get_logements(user):
    try:
        cache_key = f"user_logements_{user.id}"
        logements = cache.get(cache_key)
        if logements:
            return logements

        if user.is_admin or user.is_superuser:
            qs = Logement.objects.all()
        else:
            qs = Logement.objects.filter(Q(owner=user) | Q(admin=user))

        logements = qs.order_by("name")
        cache.set(cache_key, logements, 300)  # 5 minutes
        return logements

    except Exception as e:
        logger.error(f"Error occurred while retrieving reservations: {e}", exc_info=True)
        raise


def filter_logements(
    destination,
    start_date,
    end_date,
    guest_adult,
    guest_minor,
    equipment_ids,
    bedrooms,
    bathrooms,
    smoking,
    animals,
    type,
):
    from reservation.services.reservation_service import get_available_logement_in_period

    key_input = f"{destination}-{start_date}-{end_date}-{guest_adult}-{guest_minor}-{equipment_ids}-{bedrooms}-{bathrooms}-{smoking}-{animals}-{type}"
    cache_key = f"filtered_logements_{hashlib.md5(key_input.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    logements = Logement.objects.prefetch_related("photos").filter(statut="open")

    if destination:
        logements = logements.filter(ville__name__icontains=destination)

    if guest_adult is not None and guest_minor is not None:
        total_guests = int(guest_adult) + int(guest_minor)
        logements = logements.filter(max_traveler__gte=total_guests)

    if start_date and end_date:
        start = parse_date(start_date)
        end = parse_date(end_date)
        if start and end:
            logements = get_available_logement_in_period(start, end, logements)

    if equipment_ids:
        equipment_ids = [int(eid) for eid in equipment_ids]
        logements = logements.annotate(
            matched_equipment_count=Count("equipment", filter=Q(equipment__id__in=equipment_ids), distinct=True)
        ).filter(matched_equipment_count=len(equipment_ids))

    if bedrooms:
        logements = logements.filter(bedrooms__gte=int(bedrooms))

    if bathrooms:
        logements = logements.filter(bathrooms__gte=int(bathrooms))

    if smoking:
        logements = logements.filter(smoking=True)

    if animals:
        logements = logements.filter(animals=True)

    if type:
        logements = logements.filter(type=type)

    cache.set(cache_key, logements, 300)
    return logements


def get_best_discounts(discounts, start_date, end_date):
    try:
        logger.info(f"Fetching best discounts for dates {start_date} to {end_date}.")

        best_min_nights = None
        best_days_before = None
        best_date_range_discounts = []

        nights = (end_date - start_date).days
        today = date.today()
        days_before = (start_date - today).days

        for d in discounts:
            if d.min_nights and nights >= d.min_nights:
                if not best_min_nights or d.min_nights > best_min_nights.min_nights:
                    best_min_nights = d

            if d.days_before_min or d.days_before_max:
                is_valid = True
                if d.days_before_min and days_before < d.days_before_min:
                    is_valid = False
                if d.days_before_max and days_before > d.days_before_max:
                    is_valid = False
                if is_valid:
                    if not best_days_before or ((d.days_before_min or 0) > (best_days_before.days_before_min or 0)):
                        best_days_before = d

            if d.start_date and d.end_date:
                best_date_range_discounts.append(d)

        logger.debug("Best discounts retrieved.")
        return {
            "min_nights": best_min_nights,
            "days_before": best_days_before,
            "date_range": best_date_range_discounts,
        }
    except Exception as e:
        logger.exception(f"Error determining best discounts: {e}")
        return {"min_nights": None, "days_before": None, "date_range": []}


def apply_discounts(base_price, current_day, discounts_by_type):
    try:
        logger.debug(f"Applying discounts to price {base_price} for date {current_day}.")

        base_price = Decimal(str(base_price)) if not isinstance(base_price, Decimal) else base_price
        discount_applied = []

        for key in ["min_nights", "days_before"]:
            d = discounts_by_type.get(key)
            if d:
                try:
                    value = Decimal(str(d.value))
                    discount = (base_price * value) / Decimal("100")
                    base_price -= discount
                    discount_applied.append((d.name, discount))
                    logger.debug(f"Applied {d.name}: -{discount:.2f}")
                except (InvalidOperation, TypeError) as e:
                    logger.warning(f"Invalid discount value for {d.name}: {d.value} – {e}")

        for d in discounts_by_type.get("date_range", []):
            if d.start_date <= current_day <= d.end_date:
                try:
                    value = Decimal(str(d.value))
                    discount = (base_price * value) / Decimal("100")
                    base_price -= discount
                    discount_applied.append((d.name, discount))
                    logger.debug(f"Applied {d.name}: -{discount:.2f}")
                except (InvalidOperation, TypeError) as e:
                    logger.warning(f"Invalid discount value for {d.name}: {d.value} – {e}")

        return base_price, discount_applied
    except Exception as e:
        logger.exception(f"Error applying discounts on {current_day} with base {base_price}: {e}")
        raise


def set_price(logement, start, end, guest_adult, guest_minor, base_price=None):
    try:
        key = f"logement_{logement.id}_price_{start}_{end}_{guest_adult}_{guest_minor}_{base_price}"
        cached_result = cache.get(key)
        if cached_result:
            return cached_result

        nights = (end - start).days or 1
        default_price = Decimal(str(logement.price))
        base_price = Decimal(str(base_price)) if base_price else None

        custom_prices = Price.objects.filter(logement_id=logement.id, date__range=(start, end))
        price_map = {p.date: Decimal(str(p.value)) for p in custom_prices}

        discounts = Discount.objects.filter(logement=logement, is_active=True)
        best_discounts = get_best_discounts(discounts, start, end)

        total_base = Decimal("0.00")
        total_discount_amount = Decimal("0.00")
        discount_breakdown = {}

        for day in range(nights):
            current_day = start + timedelta(days=day)
            daily_price = base_price if base_price else price_map.get(current_day, default_price)
            total_base += daily_price

            final_price, discounts_today = apply_discounts(daily_price, current_day, best_discounts)
            for name, amount in discounts_today:
                discount_breakdown[name] = discount_breakdown.get(name, Decimal("0.00")) + amount
                total_discount_amount += amount

        total_price = total_base - total_discount_amount

        total_guests = guest_adult + guest_minor
        extra_guests = max(total_guests - logement.nominal_traveler, 0)
        extra_fee = Decimal(str(logement.fee_per_extra_traveler)) * extra_guests * nights
        total_price += extra_fee

        per_night = total_price / nights
        tax_cap = Decimal(str(logement.tax_max))
        guest_decimal = Decimal(str(guest_adult))
        tax_rate = min((Decimal(str(logement.tax)) / 100) * (per_night / guest_decimal), tax_cap)
        taxAmount = tax_rate * guest_decimal * nights

        total_price += Decimal(str(logement.cleaning_fee)) + taxAmount
        payment_fee = get_payment_fee(total_price)
        total_price += Decimal(str(payment_fee))

        result = {
            "number_of_nights": nights,
            "total_base_price": total_base,
            "TotalextraGuestFee": extra_fee,
            "discount_totals": discount_breakdown,
            "taxAmount": taxAmount,
            "payment_fee": payment_fee,
            "total_price": total_price,
        }
        cache.set(key, result, 300)  # 5 min
        return result
    except Exception as e:
        logger.exception(f"Error calculating price: {e}")
        raise
