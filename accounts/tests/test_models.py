# account/tests/test_models.py
import pytest
from accounts.tests.factories import UserFactory, ConversationFactory, MessageFactory

pytestmark = pytest.mark.django_db


def test_user_full_name():
    user = UserFactory(name="Alice", last_name="Smith")
    assert user.full_name == "Alice Smith"


def test_user_phone_validation():
    user = UserFactory(phone="+33612345678")
    assert user.phone.startswith("+336")


def test_admin_user_flags():
    admin = UserFactory(is_admin=True, is_owner=True, is_owner_admin=True)
    assert admin.is_admin
    assert admin.is_owner
    assert admin.is_owner_admin


def test_duplicate_phone_fails():
    UserFactory(phone="+33699999999")
    with pytest.raises(Exception):
        UserFactory(phone="+33699999999")  # Should fail


def test_conversation_str():
    conv = ConversationFactory()
    assert str(conv) == f"Conversation #{conv.id} - Réservation {conv.reservation_id}"


def test_conversation_participants():
    user1 = UserFactory()
    user2 = UserFactory()
    conv = ConversationFactory(participants=[user1, user2])
    assert conv.participants.count() == 2


# ✅ Conversation: Multiple participants
def test_conversation_with_participants():
    user1 = UserFactory()
    user2 = UserFactory()
    conv = ConversationFactory()
    conv.participants.add(user1, user2)
    assert conv.participants.count() == 2
    assert user1 in conv.participants.all()


# ✅ Message: Unread by default
def test_message_unread_by_default():
    user = UserFactory()
    msg = MessageFactory()
    assert not msg.is_read_by(user)


def test_message_multiple_recipients():
    sender = UserFactory()
    recipient1 = UserFactory()
    recipient2 = UserFactory()
    msg = MessageFactory(sender=sender)
    msg.recipients.set([recipient1, recipient2])
    assert msg.recipients.count() == 2


# ✅ Message: Read logic works after adding
def test_message_mark_as_read():
    user = UserFactory()
    msg = MessageFactory()
    msg.read_by.add(user)
    assert msg.is_read_by(user)


def test_message_ordering():
    m1 = MessageFactory()
    m2 = MessageFactory(conversation=m1.conversation)
    assert list(m1.conversation.messages.all()) == sorted(m1.conversation.messages.all(), key=lambda m: m.timestamp)


def test_message_read_logic():
    user = UserFactory()
    msg = MessageFactory()
    msg.read_by.add(user)
    assert msg.is_read_by(user)


def test_message_recipients():
    user1 = UserFactory()
    user2 = UserFactory()
    msg = MessageFactory(recipients=[user1, user2])
    assert msg.recipients.count() == 2
    assert not msg.is_read_by(user1)
