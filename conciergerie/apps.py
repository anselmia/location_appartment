from django.apps import AppConfig


class ConciergerieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "conciergerie"

    def ready(self):
        import conciergerie.signals  # ← important
