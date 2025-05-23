from django.core.management.base import BaseCommand
from logement.models import DiscountType


class Command(BaseCommand):
    help = "Initialize common discount types for rental discounts"

    def handle(self, *args, **options):
        discount_definitions = [
            {
                "code": "long_stay",
                "name": "Réduction longue durée",
                "requires_min_nights": True,
            },
            {
                "code": "early_bird",
                "name": "Réservation anticipée (early bird)",
                "requires_days_before": True,
            },
            {
                "code": "last_minute",
                "name": "Réservation de dernière minute",
                "requires_days_before": True,
            },
            {
                "code": "date_range",
                "name": "Réduction pour période définie",
                "requires_date_range": True,
            },
            {
                "code": "fixed_night",
                "name": "Promotion pour durée exacte (ex: 7 nuits)",
                "requires_min_nights": True,
            },
            {
                "code": "seasonal",
                "name": "Réduction saisonnière",
                "requires_date_range": True,
            },
        ]

        created = 0
        for data in discount_definitions:
            obj, created_flag = DiscountType.objects.update_or_create(
                code=data["code"],
                defaults={
                    "name": data["name"],
                    "requires_min_nights": data.get("requires_min_nights", False),
                    "requires_days_before": data.get("requires_days_before", False),
                    "requires_date_range": data.get("requires_date_range", False),
                },
            )
            if created_flag:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f"{created} discount types created or updated.")
        )
