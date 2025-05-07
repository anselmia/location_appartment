"""
ASGI config for location_site project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Choose settings module based on DJANGO_ENV variable in .env
env = os.environ.get("DJANGO_ENV", "dev").lower()
if env == "prod":
    settings_module = "location_site.production"
else:
    settings_module = "location_site.development"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

application = get_asgi_application()
