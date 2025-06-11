import pytest
from django.core.exceptions import ValidationError
from accounts.forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
    ContactForm,
    MessageForm,
    CustomPasswordChangeForm,
    UserAdminUpdateForm,
)
from accounts.models import CustomUser
from accounts.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


@pytest.fixture
def user_factory():
    return UserFactory


def test_custom_user_creation_form_valid():
    form = CustomUserCreationForm(
        data={
            "username": "newuser",
            "name": "Jean",
            "last_name": "Dupont",
            "email": "jean@example.com",
            "phone": "+33612345678",
            "password1": "StrongPassword123!",
            "password2": "StrongPassword123!",
        }
    )
    assert form.is_valid()


def test_custom_user_creation_form_duplicate_fields(user_factory):
    user_factory(username="existing", email="used@example.com", phone="+33611111111")
    form = CustomUserCreationForm(
        data={
            "username": "existing",
            "name": "Jean",
            "last_name": "Dupont",
            "email": "used@example.com",
            "phone": "+33611111111",
            "password1": "StrongPassword123!",
            "password2": "StrongPassword123!",
        }
    )
    assert not form.is_valid()
    assert "email" in form.errors
    assert "username" in form.errors
    assert "phone" in form.errors


def test_custom_user_change_form_phone_conflict(user_factory):
    user1 = user_factory(phone="+33612345678")
    user2 = user_factory()
    form = CustomUserChangeForm(
        data={
            "username": user2.username,
            "name": user2.name,
            "last_name": user2.last_name,
            "email": user2.email,
            "phone": "+33612345678",
        },
        instance=user2,
    )
    assert not form.is_valid()
    assert "phone" in form.errors


def test_contact_form_valid():
    data = {"name": "Alice", "email": "alice@example.com", "subject": "Sujet de test", "message": "Contenu du message"}
    form = ContactForm(data=data)
    assert form.is_valid()


def test_message_form_structure():
    form = MessageForm()
    assert "content" in form.fields
    assert form.fields["content"].widget.attrs["placeholder"] == "Votre message..."


def test_custom_password_change_form_widgets():
    user = CustomUser(username="tester")
    form = CustomPasswordChangeForm(user=user)
    assert "autocomplete" in form.fields["old_password"].widget.attrs


def test_user_admin_update_form_stripe_ids_conflict(user_factory):
    user1 = user_factory(stripe_account_id="acct_abc", stripe_customer_id="cus_xyz")
    user2 = user_factory()
    form = UserAdminUpdateForm(
        data={
            "username": user2.username,
            "name": user2.name,
            "last_name": user2.last_name,
            "email": user2.email,
            "phone": user2.phone,
            "is_admin": True,
            "is_owner": False,
            "is_owner_admin": False,
            "stripe_account_id": "acct_abc",
            "stripe_customer_id": "cus_xyz",
        },
        instance=user2,
    )
    assert not form.is_valid()
    assert "stripe_account_id" in form.errors
    assert "stripe_customer_id" in form.errors


def test_custom_user_creation_form_passwords_do_not_match():
    form = CustomUserCreationForm(
        data={
            "username": "user1",
            "name": "Jean",
            "last_name": "Dupont",
            "email": "test@example.com",
            "phone": "+33612345678",
            "password1": "abc123456",
            "password2": "different123",
        }
    )
    assert not form.is_valid()
    assert "password2" in form.errors


def test_custom_user_creation_form_invalid_email():
    form = CustomUserCreationForm(
        data={
            "username": "user1",
            "name": "Jean",
            "last_name": "Dupont",
            "email": "not-an-email",
            "phone": "+33612345678",
            "password1": "Password123",
            "password2": "Password123",
        }
    )
    assert not form.is_valid()
    assert "email" in form.errors


def test_message_form_empty_content():
    form = MessageForm(data={"content": ""})
    assert not form.is_valid()
    assert "content" in form.errors
