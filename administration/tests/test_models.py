import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from administration.models import Entreprise, SiteVisit, HomePageConfig, SiteConfig, Service, Testimonial, Commitment


pytestmark = pytest.mark.django_db


def test_entreprise_creation():
    entreprise = Entreprise.objects.create(
        contact_address="123 Rue Exemple",
        contact_phone="0123456789",
        contact_email="contact@example.com",
        name="Exemple SARL",
        facebook="https://facebook.com/exemple",
        linkedin="https://linkedin.com/company/exemple",
        instagram="https://instagram.com/exemple",
        logo=SimpleUploadedFile("logo.jpg", b"file_content"),
    )
    assert entreprise.name == "Exemple SARL"
    assert entreprise.contact_email == "contact@example.com"


def test_site_visit_creation():
    visit = SiteVisit.objects.create(
        ip_address="127.0.0.1", user_agent="TestBrowser", path="/test", timestamp=timezone.now()
    )
    assert visit.ip_address == "127.0.0.1"
    assert visit.user_agent == "TestBrowser"


def test_home_page_config_creation_and_save():
    config = HomePageConfig.objects.create(
        devise="Luxe et Confort",
        description="Bienvenue",
        banner_image=SimpleUploadedFile("banner.jpg", b"image_data"),
        primary_color="#123456",
        font_family="Roboto",
        cta_text="Voir nos logements",
        contact_title="Contactez-nous",
    )
    config.save()
    assert config.pk == 1
    assert str(config) == "Configuration de la page d’accueil"


def test_site_config_creation():
    config = SiteConfig.objects.create(sms=True)
    assert config.sms is True


def test_service_creation_and_str():
    config = HomePageConfig.objects.create()
    service = Service.objects.create(
        config=config,
        icon_class="fas fa-bolt",
        description="Service rapide",
        title="Nettoyage premium",
        background_image=SimpleUploadedFile("bg.jpg", b"bg_data"),
    )
    service.save()
    assert service.pk == 1
    assert str(service) == "Nettoyage premium"


def test_testimonial_str():
    config = HomePageConfig.objects.create()
    testimonial = Testimonial.objects.create(config=config, content="Très bonne expérience ! Je recommande vivement.")
    assert str(testimonial).startswith("Avis: Très bonne")


def test_commitment_str():
    config = HomePageConfig.objects.create()
    commitment = Commitment.objects.create(
        config=config,
        title="Satisfaction",
        text="Nous garantissons une satisfaction totale.",
        background_image=SimpleUploadedFile("bg.jpg", b"img_data"),
    )
    assert str(commitment).startswith("Engagement: Nous garantissons")
