import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from administration.models import Entreprise, SiteVisit, HomePageConfig, SiteConfig, Service, Testimonial, Commitment


pytestmark = pytest.mark.django_db


