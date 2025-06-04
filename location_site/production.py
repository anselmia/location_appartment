from .base import *  # start from base settings

import os
import logging
from pathlib import Path
from dotenv import load_dotenv


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))

SITE_ADDRESS = "https://www.bnbazure.fr/"
DOMAIN = "bnbazure.fr"

# SECURITY SETTINGS
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

logging.getLogger("django.security.DisallowedHost").setLevel(logging.CRITICAL)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

# DATABASE SETTINGS (PostgreSQL Example)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# STATIC & MEDIA FILES
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Cookies

# Sessions
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True  # JS can't access session cookie
SESSION_COOKIE_SAMESITE = "Lax"  # Prevents CSRF between sites
SESSION_SAVE_EVERY_REQUEST = True

# Optional: custom cookie for consent (readable from server)
COOKIE_CONSENT_NAME = "cookie_consent"

# SECURITY HARDENING
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

CSRF_TRUSTED_ORIGINS = [
    "https://www.bnbazure.fr",
    "https://bnbazure.fr",
]

LOG_DIR = "/var/log/location_app/"

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
            "when": "midnight",  # Rotate daily
            "backupCount": 14,  # Keep 14 days of logs
            "formatter": "verbose",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "formatter": "verbose",
        },
        "null": {
            "class": "logging.NullHandler",
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
        "logement.tasks": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security.DisallowedHost": {
            "handlers": ["null"],
            "propagate": False,
            "level": "CRITICAL",
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

ADMINS = [("Arnaud Anselmi", "anselmi.arnaud@yahoo.fr")]
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "localhost"
EMAIL_PORT = 25
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = "noreply@bnbazure.fr"
CONTACT_EMAIL = "contact@bnbazure.fr"
