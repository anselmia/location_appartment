import pytest
import io
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from administration.forms import (
    HomePageConfigForm,
    SiteConfigForm,
    ServiceForm,
    TestimonialForm,
    CommitmentForm,
    EntrepriseForm,
)
from administration.tests.factories import HomePageConfigFactory

