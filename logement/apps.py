from django.apps import AppConfig
from django_celery_beat.models import PeriodicTask, IntervalSchedule


class LogementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "logement"

    def ready(self):
        # Avoid running this code multiple times (e.g., migrations, shell)
        from django.db.utils import OperationalError, ProgrammingError

        try:
            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=10,
                period=IntervalSchedule.MINUTES,
            )
            PeriodicTask.objects.get_or_create(
                interval=schedule,
                name="Delete expired reservations",
                task="logement.tasks.delete_expired_pending_reservations",
            )

            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=30,
                period=IntervalSchedule.MINUTES,
            )
            PeriodicTask.objects.get_or_create(
                interval=schedule,
                name="Sync calendar",
                task="logement.tasks.sync_calendar",
            )

        except (OperationalError, ProgrammingError):
            pass  # Happens during initial migrate or when DB is not ready
