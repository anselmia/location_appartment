import pytest
from django.test import Client
from accounts.services.conversations import (
    get_reservations_for_conversations_to_start,
    get_conversations,
)
from accounts.tests.factories import UserFactory, ReservationFactory, ConversationFactory, MessageFactory


@pytest.fixture
def user_factory():
    return UserFactory


@pytest.fixture
def client_logged():
    client = Client()
    client.force_login(UserFactory)
    return client


@pytest.mark.django_db
def test_get_reservations_anonymous():
    assert get_reservations_for_conversations_to_start(None).count() == 0


@pytest.mark.django_db
def test_get_reservations_platform_admin():
    admin = UserFactory(is_admin=True)
    reservations = ReservationFactory.create_batch(3)
    # Attach one reservation to a conversation
    ConversationFactory(reservation=reservations[0])

    results = get_reservations_for_conversations_to_start(admin)
    assert reservations[0] not in results
    assert set(results) == set(reservations[1:])


@pytest.mark.django_db
def test_get_reservations_normal_user_participant():
    user = UserFactory()
    guest_res = ReservationFactory(user=user)
    owner_res = ReservationFactory(logement__owner=user)
    admin_res = ReservationFactory(logement__admin=user)
    other_res = ReservationFactory()
    # Create conversations for some
    ConversationFactory(reservation=owner_res)

    results = get_reservations_for_conversations_to_start(user)
    assert guest_res in results
    assert admin_res in results
    assert owner_res not in results
    assert other_res not in results


@pytest.mark.django_db
def test_get_reservations_invalid_user():
    class FakeUser:
        is_authenticated = False

    assert get_reservations_for_conversations_to_start(FakeUser()).count() == 0


@pytest.mark.django_db
def test_get_conversations_anonymous():
    assert get_conversations(None).count() == 0


@pytest.mark.django_db
def test_get_conversations_platform_admin():
    admin = UserFactory(is_admin=True)
    conv1 = ConversationFactory()
    conv2 = ConversationFactory()
    assert set(get_conversations(admin)) == {conv1, conv2}


@pytest.mark.django_db
def test_get_conversations_normal_user():
    user = UserFactory()
    conv1 = ConversationFactory(participants=[user])
    ConversationFactory()
    assert list(get_conversations(user)) == [conv1]


@pytest.mark.django_db
def test_unread_message_count():
    user = UserFactory()
    other = UserFactory()
    conv = ConversationFactory(participants=[user, other])
    MessageFactory(conversation=conv, recipients=[user])  # Unread
    msg2 = MessageFactory(conversation=conv, recipients=[user])
    msg2.read_by.set([user])
    result = get_conversations(user).first()
    assert result.unread_count == 1


@pytest.mark.django_db
def test_conversations_ordered_by_updated_at():
    user = UserFactory()
    conv_old = ConversationFactory(participants=[user], updated_at="2024-01-01")
    conv_new = ConversationFactory(participants=[user], updated_at="2025-01-01")
    conversations = list(get_conversations(user))
    assert conversations == [conv_new, conv_old]


@pytest.mark.django_db
def test_get_conversations_handles_failure(monkeypatch):
    def broken_filter(*args, **kwargs):
        raise Exception("Database error")

    monkeypatch.setattr("accounts.services.conversations.Conversation.objects.annotate", broken_filter)
    user = UserFactory()
    assert get_conversations(user).count() == 0


@pytest.mark.django_db
def test_get_reservations_handles_failure(monkeypatch):
    def broken_query(*args, **kwargs):
        raise Exception("DB broken")

    monkeypatch.setattr("accounts.services.conversations.Reservation.objects.exclude", broken_query)
    user = UserFactory()
    assert get_reservations_for_conversations_to_start(user).count() == 0
