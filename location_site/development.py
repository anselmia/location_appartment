from .base import *  # start from base settings

import os
from pathlib import Path
from dotenv import load_dotenv


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(os.path.join(BASE_DIR, ".env"))

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "unsafe-default-secret-key"
)  # Set securely in env

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

STATICFILES_DIRS = [os.path.join(BASE_DIR, "logement/static")]


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
