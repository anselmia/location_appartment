from django.core.management.base import BaseCommand
from django.db import connection

from reservation.models import Reservation
from activity.models import ActivityReservation, Activity
from payment.models import PaymentTask


class Command(BaseCommand):
    help = "Delete all data from a list of models and reset their IDs"

    def handle(self, *args, **kwargs):
        # List the models you want to clear
        models_to_clear = [
            Reservation,
            PaymentTask,
            ActivityReservation,
            Activity
        ]

        for model in models_to_clear:
            count, _ = model.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} objects from {model.__name__}"))

            # Reset the primary key sequence
            table = model._meta.db_table
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1;")
            elif connection.vendor == "sqlite":
                with connection.cursor() as cursor:
                    cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}';")

        self.stdout.write(self.style.SUCCESS("All specified models have been cleared and their IDs reset."))
