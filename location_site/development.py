from .base import *  # start from base settings

import os
from pathlib import Path
from dotenv import load_dotenv

SITE_ADDRESS=""
DOMAIN=""
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

STATIC_URL = "/staticfiles/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LOG_DIR = os.path.join(BASE_DIR, "Logs")

# Create the log directory if it doesn't exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)
    # Optional: set permissions
    os.chmod(LOG_DIR, 0o755)

# LOGGING
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} ({module}.{funcName}:{lineno}) {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "django.log"),
            "when": "W0",  # Rotate weekly
            "backupCount": 365,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file", "mail_admins"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["file"],
            "level": "ERROR",  # Set to DEBUG to log SQL
            "propagate": False,
        },
        "myapp": {  # replace with your actual app name
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "frontend": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

CONTACT_EMAIL= ""
