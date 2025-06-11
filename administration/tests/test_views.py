import pytest
import logging
from django.urls import reverse
from django.contrib.messages import get_messages
from django.test import Client
from datetime import datetime

from administration.models import HomePageConfig, Service, Testimonial, SiteConfig, Commitment
from administration.forms import HomePageConfigForm
from administration.tests.factories import UserAdminFactory, ReservationFactory, EntrepriseFactory

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.django_db


@pytest.fixture
def user_factory():
    return UserAdminFactory


@pytest.fixture
def reservation_factory():
    return ReservationFactory


@pytest.fixture
def entreprise():
    return EntrepriseFactory()


@pytest.fixture
def client_admin(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


def test_traffic_dashboard_view_admin(admin_user):
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("administration:traffic"))
    assert response.status_code == 200
    assert "total_visits" in response.context


def test_traffic_dashboard_ajax(admin_user):
    client = Client(HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    client.force_login(admin_user)
    response = client.post(reverse("administration:traffic"), {"period": "month"})
    assert response.status_code == 200
    assert response.json().get("online_visitors") is not None


def test_log_viewer_access(entreprise, admin_user):
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("administration:log_viewer"))
    assert response.status_code == 200
    assert "logs" in response.context


def test_homepage_admin_get(entreprise, admin_user):
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("administration:homepage_admin_view"))
    assert response.status_code == 200
    assert "form" in response.context


def test_homepage_admin_add_service(entreprise, admin_user):
    config = HomePageConfig.objects.create()
    client = Client()
    client.force_login(admin_user)
    response = client.post(
        reverse("administration:homepage_admin_view"),
        {
            "add_service": "",
            "title": "WiFi gratuit",
            "icon_class": "fas fa-wifi",
            "description": "Connexion gratuite",
        },
    )
    assert response.status_code == 302
    assert Service.objects.filter(title="WiFi gratuit").exists()


def test_homepage_admin_add_testimonial(entreprise, admin_user):
    config = HomePageConfig.objects.create()
    client = Client()
    client.force_login(admin_user)
    response = client.post(
        reverse("administration:homepage_admin_view"),
        {"add_testimonial": "", "content": "Super séjour !"},
    )
    assert response.status_code == 302
    assert Testimonial.objects.filter(content__contains="séjour").exists()


def test_edit_entreprise_view_get(entreprise, admin_user):
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("administration:edit_entreprise"))
    assert response.status_code == 200
    assert "form" in response.context


def test_edit_entreprise_view_post(entreprise, admin_user):
    client = Client()
    client.force_login(admin_user)
    response = client.post(
        reverse("administration:edit_entreprise"),
        {"name": "Nouvelle Entreprise", "contact_email": "test@ex.com"},
        follow=True,
    )
    assert response.status_code == 200
    assert "mises à jour" in [m.message for m in get_messages(response.wsgi_request)][0].lower()


def test_financial_dashboard(entreprise, admin_user, reservation_factory):
    current_year = datetime.now().year
    reservation_factory.create_batch(3, statut="confirmee", start=f"{current_year}-06-01", price=500)
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("administration:financial_dashboard"))
    assert response.status_code == 200
    assert "total_revenue" in response.context


def test_traffic_dashboard_get_admin(client_admin):
    url = reverse("administration:traffic")
    response = client_admin.get(url)
    assert response.status_code == 200

    # Vérifie que les variables sont bien dans le contexte
    assert "total_visits" in response.context
    assert "recent_logs" in response.context

    assert isinstance(response.context["total_visits"], int)
    assert isinstance(response.context["recent_logs"], list)


def test_traffic_dashboard_post_admin(client_admin):
    url = reverse("administration:traffic")
    response = client_admin.post(url, {"period": "month"})
    assert response.status_code == 200
    json = response.json()
    assert "labels" in json and "data" in json


def test_log_viewer(client_admin, settings):
    logger.info("2025-06-11 12:00:00,000 INFO root This is a test log entry")
    url = reverse("administration:log_viewer")
    response = client_admin.get(url)
    assert response.status_code == 200
    # Confirm log appears in the parsed logs
    logs = response.context["logs"]
    assert any("test log entry" in log["message"].lower() for log in logs)


def test_homepage_admin_view_get(client_admin):
    url = reverse("administration:homepage_admin_view")
    response = client_admin.get(url)
    assert response.status_code == 200
    assert isinstance(response.context["form"], HomePageConfigForm)


def test_add_service(client_admin):
    url = reverse("administration:homepage_admin_view")
    HomePageConfig.objects.get_or_create(id=1)
    data = {
        "add_service": "1",
        "title": "Service Test",
        "icon_class": "fas fa-check",
        "description": "Test service description",
    }
    response = client_admin.post(url, data)
    assert response.status_code == 302
    assert Service.objects.filter(title="Service Test").exists()


def test_delete_service(client_admin):
    config = HomePageConfig.objects.get_or_create(id=1)[0]
    service = Service.objects.create(config=config, title="To delete")
    url = reverse("administration:homepage_admin_view")
    response = client_admin.post(url, {"delete_service_id": service.id})
    assert response.status_code == 302
    assert not Service.objects.filter(id=service.id).exists()


def test_add_testimonial(client_admin):
    HomePageConfig.objects.get_or_create(id=1)
    url = reverse("administration:homepage_admin_view")
    response = client_admin.post(url, {"add_testimonial": "1", "content": "Excellent !"})
    assert response.status_code == 302
    assert Testimonial.objects.filter(content__icontains="Excellent").exists()


def test_add_commitment(client_admin):
    HomePageConfig.objects.get_or_create(id=1)
    url = reverse("administration:homepage_admin_view")
    response = client_admin.post(
        url,
        {
            "add_commitment": "1",
            "title": "Sécurité",
            "text": "Nous garantissons votre sécurité",
        },
    )
    assert response.status_code == 302
    assert Commitment.objects.filter(title="Sécurité").exists()


def test_update_site_config(client_admin):
    SiteConfig.objects.create()
    url = reverse("administration:homepage_admin_view")
    response = client_admin.post(url, {"update_site_config": "1", "sms": "on"})
    assert response.status_code == 302
    assert SiteConfig.objects.first().sms


def test_edit_entreprise_get(client_admin):
    url = reverse("administration:edit_entreprise")
    response = client_admin.get(url)
    assert response.status_code == 200
    assert b"form" in response.content or response.context["form"]


def test_edit_entreprise_post(client_admin):
    url = reverse("administration:edit_entreprise")
    data = {
        "name": "My Entreprise",
        "contact_email": "admin@example.com",
        "contact_phone": "+33600000000",
    }
    response = client_admin.post(url, data)
    assert response.status_code == 302


def test_financial_dashboard_context(client_admin, reservation_factory):
    # Create 2 reservations
    reservation_factory(price=200, platform_fee=20, statut="confirmee")
    reservation_factory(price=300, platform_fee=30, statut="annulee")
    url = reverse("administration:financial_dashboard")
    response = client_admin.get(url)
    assert response.status_code == 200
    ctx = response.context
    assert ctx["total_revenue"] >= 0
    assert isinstance(ctx["monthly_revenue"], list)
    assert "daily_revenue" in ctx
