#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

env = os.environ.get("DJANGO_ENV", "dev").lower()
if env == "prod":
    settings_module = "location_site.production"
else:
    settings_module = "location_site.development"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)


def main():
    """Run administrative tasks."""
    try:
        from django.core.management import execute_from_command_line

        execute_from_command_line(sys.argv)
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc


if __name__ == "__main__":
    main()
