import os
from dotenv import load_dotenv
from pathlib import Path
from celery import Celery

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

env = os.environ.get("DJANGO_ENV", "dev").lower()
if env == "prod":
    settings_module = "location_site.production"
else:
    settings_module = "location_site.development"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

app = Celery("location_site")
app.conf.timezone = 'Europe/Paris'
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
