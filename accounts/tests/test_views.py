import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from django.contrib.messages import get_messages
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from unittest.mock import patch

from accounts.models import Conversation, CustomUser, Message
from accounts.tests.factories import EntrepriseFactory, UserFactory, ReservationFactory, LogementFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def entreprise():
    return EntrepriseFactory()


@pytest.fixture
def user_factory():
    return UserFactory


@pytest.fixture
def reservation_factory():
    return ReservationFactory


@pytest.fixture
def logement_factory():
    return LogementFactory


def test_register_view_get(entreprise):
    client = Client()
    response = client.get(reverse("accounts:register"))
    assert response.status_code == 200
    assert "form" in response.context


def test_register_view_post_valid():
    client = Client()
    data = {
        "username": "testuser",
        "name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "password1": "SuperStrongPass123",
        "password2": "SuperStrongPass123",
        "phone": "+33612345678",
    }
    response = client.post(reverse("accounts:register"), data)
    assert response.status_code == 302
    assert User.objects.filter(username="testuser").exists()


def test_login_view_valid_user(user_factory):
    user = user_factory(password="strongpass123")
    client = Client()
    response = client.post(reverse("accounts:login"), {"username": user.username, "password": "strongpass123"})
    assert response.status_code == 302


def test_login_invalid_password(user_factory):
    user = user_factory(password="correctpass")
    client = Client()
    response = client.post(reverse("accounts:login"), {"username": user.username, "password": "wrongpass"})
    assert response.status_code == 200  # should stay on login page
    assert "form" in response.context


def test_dashboard_requires_login():
    client = Client()
    response = client.get(reverse("accounts:dashboard"))
    assert response.status_code == 302  # redirected to login


def test_dashboard_view_logged_in(user_factory, logement_factory, reservation_factory):
    user = user_factory()
    logement = logement_factory(owner=user)
    reservation_factory(user=user, logement=logement)
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:dashboard"))
    assert response.status_code == 200
    assert "reservations" in response.context


def test_messages_view_get(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:messages"))
    assert response.status_code == 200


def test_messages_conversation_not_found(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:messages_conversation", args=[9999]))
    assert response.status_code == 302  # redirected


def test_start_conversation_valid(user_factory, logement_factory, reservation_factory):
    user = user_factory()
    owner = user_factory()
    logement = logement_factory(owner=owner)
    reservation = reservation_factory(user=user, logement=logement)

    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:start_conversation"), {"reservation_id": reservation.id})
    assert response.status_code == 302
    assert Conversation.objects.filter(reservation=reservation).exists()


def test_start_conversation_unauthorized(user_factory, logement_factory, reservation_factory):
    user = user_factory()
    other_user = user_factory()
    logement = logement_factory(owner=other_user)
    reservation = reservation_factory(user=other_user, logement=logement)

    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:start_conversation"), {"reservation_id": reservation.id})
    assert response.status_code == 302  # redirected
    assert not Conversation.objects.filter(reservation=reservation).exists()


def test_message_view_html(user_factory, reservation_factory, logement_factory):
    user = user_factory()
    logement = logement_factory(owner=user)
    reservation = reservation_factory(user=user, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.add(user)

    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:messages_conversation", args=[conversation.id]))

    assert response.status_code == 200
    assert "active_conversation" in response.context
    assert response.context["active_conversation"] == conversation
    assert response.templates[0].name == "accounts/messages.html"


def test_message_view_ajax(user_factory, reservation_factory, logement_factory):
    user = user_factory()
    logement = logement_factory(owner=user)
    reservation = reservation_factory(user=user, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.add(user)

    client = Client(HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    client.force_login(user)
    response = client.get(reverse("accounts:messages_conversation", args=[conversation.id]))

    assert response.status_code == 200
    assert "active_conversation" in response.context
    assert response.context["active_conversation"] == conversation
    assert response.templates[0].name == "accounts/partials/_conversation.html"


def test_message_view_invalid_conversation(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)

    response = client.get(reverse("accounts:messages_conversation", args=[9999]), follow=True)

    messages_list = list(get_messages(response.wsgi_request))
    assert response.redirect_chain[-1][0].endswith(reverse("accounts:messages"))
    assert any("la conversation n'existe pas" in str(m.message).lower() for m in messages_list)


def test_message_view_unauthorized_access(user_factory, reservation_factory, logement_factory):
    owner = user_factory()
    intruder = user_factory()
    logement = logement_factory(owner=owner)
    reservation = reservation_factory(user=owner, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.add(owner)

    client = Client()
    client.force_login(intruder)

    response = client.get(reverse("accounts:messages_conversation", args=[conversation.id]), follow=True)

    messages_list = list(get_messages(response.wsgi_request))
    assert response.redirect_chain[-1][0].endswith(reverse("accounts:messages"))
    assert any("vous n'avez pas accès" in str(m.message).lower() for m in messages_list)


def test_message_view_post_valid(user_factory, reservation_factory, logement_factory):
    sender = user_factory()
    logement = logement_factory(owner=sender)
    reservation = reservation_factory(user=sender, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.add(sender)

    client = Client()
    client.force_login(sender)

    response = client.post(
        reverse("accounts:messages_conversation", args=[conversation.id]), {"content": "Hello test!"}, follow=True
    )

    assert response.status_code == 200
    assert Message.objects.filter(conversation=conversation, sender=sender, content="Hello test!").exists()


def test_message_view_post_invalid(user_factory, reservation_factory, logement_factory):
    sender = user_factory()
    logement = logement_factory(owner=sender)
    reservation = reservation_factory(user=sender, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.add(sender)

    client = Client()
    client.force_login(sender)

    # Post vide = invalide
    response = client.post(
        reverse("accounts:messages_conversation", args=[conversation.id]), {"content": ""}, follow=True
    )

    assert response.status_code == 200
    assert not Message.objects.filter(conversation=conversation, sender=sender).exists()


def test_message_view_marks_unread_messages_as_read(user_factory, reservation_factory, logement_factory):
    sender = user_factory()
    recipient = user_factory()
    logement = logement_factory(owner=sender)
    reservation = reservation_factory(user=recipient, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.set([sender, recipient])

    # Créer un message envoyé par `sender` à `recipient`
    message = Message.objects.create(conversation=conversation, sender=sender, content="Message non lu")
    message.recipients.add(recipient)

    assert recipient not in message.read_by.all()  # Vérif avant

    # Simuler l'accès à la conversation par le destinataire
    client = Client()
    client.force_login(recipient)
    response = client.get(reverse("accounts:messages_conversation", args=[conversation.id]))

    assert response.status_code == 200

    # Vérifier que le message a été marqué comme lu
    message.refresh_from_db()
    assert recipient in message.read_by.all()


def test_admin_message_is_marked_as_read(user_factory, reservation_factory, logement_factory):
    # Création d'un admin et d'un utilisateur classique
    admin = user_factory(is_admin=True)
    user = user_factory()
    logement = logement_factory(owner=user)
    reservation = reservation_factory(user=user, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.set([user])

    # Admin envoie un message au user
    message = Message.objects.create(conversation=conversation, sender=admin, content="Message de l'admin")
    message.recipients.add(user)

    # Avant consultation : message non lu
    assert user not in message.read_by.all()

    # Le user consulte la conversation
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:messages_conversation", args=[conversation.id]))

    assert response.status_code == 200

    # Le message doit maintenant être marqué comme lu
    message.refresh_from_db()
    assert user in message.read_by.all()


def test_message_post_unauthorized(user_factory, reservation_factory, logement_factory):
    sender = user_factory()
    stranger = user_factory()
    logement = logement_factory(owner=sender)
    reservation = reservation_factory(user=sender, logement=logement)
    conversation = Conversation.objects.create(reservation=reservation)
    conversation.participants.add(sender)

    client = Client()
    client.force_login(stranger)
    response = client.post(reverse("accounts:messages_conversation", args=[conversation.id]), {"content": "Hey!"})
    assert response.status_code == 302


def test_contact_view_get_anonymous():
    client = Client()
    response = client.get(reverse("accounts:contact"))
    assert response.status_code == 200
    assert "form" in response.context


def test_contact_view_post_valid():
    client = Client()
    data = {"name": "Visitor", "email": "visitor@example.com", "subject": "Test", "message": "Hello!"}
    response = client.post(reverse("accounts:contact"), data)
    assert response.status_code == 302


def test_delete_account_no_reservations(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:delete_account"))
    assert response.status_code == 302
    assert not User.objects.filter(id=user.id).exists()


def test_delete_account_with_active_reservation(user_factory, logement_factory, reservation_factory):
    user = user_factory()
    logement = logement_factory(owner=user)
    reservation_factory(user=user, logement=logement, start=timezone.now())
    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:delete_account"))
    assert response.status_code == 302
    assert User.objects.filter(id=user.id).exists()


def test_delete_account_get_should_not_be_allowed(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:delete_account"))
    assert response.status_code == 405
    assert User.objects.filter(id=user.id).exists()


def test_delete_account_post_should_delete_user(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:delete_account"))
    assert response.status_code == 302
    assert not User.objects.filter(id=user.id).exists()


def test_resend_activation_email_existing_user(user_factory):
    user = user_factory(is_active=False)
    client = Client()
    response = client.post(reverse("accounts:resend_activation_email"), {"email": user.email})

    assert response.status_code == 302


def test_resend_activation_email_nonexistent_user(entreprise):
    client = Client()
    response = client.post(reverse("accounts:resend_activation_email"), {"email": "nouser@example.com"})

    # ✅ Assert redirect
    assert response.status_code == 302
    assert response.url == reverse("accounts:resend_activation_email")

    # ✅ Follow redirect to access messages
    response = client.get(response.url)
    messages = list(get_messages(response.wsgi_request))
    assert any("aucun compte" in str(m.message).lower() for m in messages)


def test_update_profile_success(entreprise, user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    data = {
        "username": user.username,
        "email": user.email,
        "phone": "+33101020304",
        "name": user.name,
        "last_name": user.last_name,
    }
    response = client.post(reverse("accounts:update_profile"), data)
    messages = list(get_messages(response.wsgi_request))
    user.refresh_from_db()
    assert any("profil mis à jour avec succès" in str(m.message).lower() for m in messages)
    assert response.status_code == 302
    assert user.phone == "+33101020304"


def test_update_profile_invalid_data(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:update_profile"), {"email": "not-an-email"})
    messages_list = list(get_messages(response.wsgi_request))
    assert any("une erreur est survenue" in str(m.message).lower() for m in messages_list)


def test_user_update_view_get_and_post(admin_user, user_factory):
    user = user_factory()
    client = Client()
    client.force_login(admin_user)

    # GET view
    response = client.get(reverse("accounts:user_update_view_with_id", args=[user.id]))
    assert response.status_code == 200
    assert "form" in response.context

    # POST update
    response = client.post(
        reverse("accounts:user_update_view_with_id", args=[user.id]),
        {
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "name": user.name,
            "last_name": "NewLast",
        },
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_user_delete_view(admin_user, user_factory):
    target_user = user_factory()
    client = Client()
    client.force_login(admin_user)
    response = client.post(reverse("accounts:user_delete_view", args=[target_user.id]))
    assert response.status_code == 302
    assert not CustomUser.objects.filter(id=target_user.id).exists()


def test_logout(user_factory):
    user = user_factory()
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:logout"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_activate_valid_token(user_factory):
    user = user_factory(is_active=False)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    client = Client()
    response = client.get(reverse("accounts:activate", args=[uid, token]))
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.is_active


@pytest.mark.django_db
def test_activate_invalid_token(user_factory):
    user = user_factory(is_active=False)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = "invalid-token"

    client = Client()
    response = client.get(reverse("accounts:activate", args=[uid, token]))
    assert response.status_code == 302
    user.refresh_from_db()
    assert not user.is_active


@patch("common.services.stripe.account.create_stripe_connect_account")
def test_create_stripe_account(mock_create, user_factory):
    mock_create.return_value = (
        type("StripeAccount", (), {"id": "acct_test"}),
        type("AccountLink", (), {"url": "/redirect-url"}),
    )
    user = user_factory(stripe_account_id="", email="test@example.com")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:create_stripe_account"))
    assert response.status_code == 302


@patch("common.services.stripe.account.update_stripe_account")
def test_update_stripe_account_view(mock_update, user_factory):
    user = user_factory(stripe_account_id="acct_test", email="test@example.com")
    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:update_stripe_account"))
    assert response.status_code == 302


def test_create_stripe_account_no_email(user_factory):
    user = user_factory(email="")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:create_stripe_account"))
    assert response.status_code == 302
