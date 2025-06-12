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


@pytest.fixture
def homepageconfig():
    return HomePageConfigFactory()


@pytest.fixture
def valid_image_file():
    image = Image.new("RGB", (100, 100), color="blue")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)
    return SimpleUploadedFile("test.jpg", buffer.read(), content_type="image/jpeg")


@pytest.mark.django_db
def test_homepage_config_form_valid(valid_image_file):
    form = HomePageConfigForm(
        data={
            "description": "Test",
            "devise": "Slogan",
            "cta_text": "Découvrez",
            "primary_color": "#123456",
            "font_family": "Arial",
            "contact_title": "Contact",
        },
        files={"banner_image": valid_image_file},
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_site_config_form_valid():
    assert SiteConfigForm(data={"sms": True}).is_valid()
    assert SiteConfigForm(data={"sms": False}).is_valid()


@pytest.mark.django_db
def test_service_form_valid(valid_image_file):
    form = ServiceForm(
        data={
            "title": "WiFi",
            "icon_class": "fa-wifi",
            "description": "High speed internet",
        },
        files={"background_image": valid_image_file},
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_testimonial_form_valid_and_invalid():
    form_valid = TestimonialForm(data={"content": "Amazing!"})
    form_invalid = TestimonialForm(data={})
    assert form_valid.is_valid()
    assert not form_invalid.is_valid()
    assert "content" in form_invalid.errors


@pytest.mark.django_db
def test_commitment_form_valid(valid_image_file):
    form = CommitmentForm(
        data={
            "title": "Sustainable",
            "text": "We care about the planet.",
        },
        files={"background_image": valid_image_file},
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_entreprise_form_valid_and_invalid(valid_image_file):
    valid_data = {
        "name": "MyCompany",
        "contact_address": "1 rue abc",
        "contact_phone": "0123456789",
        "contact_email": "contact@mycompany.com",
        "facebook": "https://facebook.com/mycompany",
        "instagram": "https://instagram.com/mycompany",
        "linkedin": "https://linkedin.com/company/mycompany",
    }
    form_valid = EntrepriseForm(data=valid_data, files={"logo": valid_image_file})
    assert form_valid.is_valid()

    invalid_data = valid_data.copy()
    invalid_data["contact_email"] = ""
    form_invalid = EntrepriseForm(data=invalid_data)
    assert not form_invalid.is_valid()
    assert "contact_email" in form_invalid.errors
