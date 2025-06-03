from django.apps import AppConfig


class PaymentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payment"

    def ready(self):
        import payment.signals
        from django_q.models import Schedule
        from django.db.utils import OperationalError, ProgrammingError

        try:
            Schedule.objects.get_or_create(
                name="Sync calendar",
                func="logement.tasks.sync_calendar",
                schedule_type=Schedule.MINUTES,
                minutes=30,
                repeats=-1,
            )

            Schedule.objects.get_or_create(
                name="Transfert Funds",
                func="logement.tasks.transfert_funds",
                schedule_type=Schedule.CRON,
                cron="0 1 * * *",  # At 01:00 AM every day
                repeats=-1,
            )

        except (OperationalError, ProgrammingError):
            pass  # Happens during initial migrate or when DB is not ready
