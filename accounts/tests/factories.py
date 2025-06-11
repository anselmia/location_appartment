# account/tests/factories.py
import factory
import datetime
from django.utils import timezone
from accounts.models import CustomUser, Conversation, Message
from reservation.models import Reservation
from logement.models import Logement
from administration.models import Entreprise


class EntrepriseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Entreprise

    name = "MyCompany"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "password123")
    phone = factory.Sequence(lambda n: f"+336000000{n:02d}")
    name = "John"
    last_name = "Doe"


class LogementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Logement

    name = factory.Sequence(lambda n: f"Test Apt {n}")
    admin_fee = 0.12
    longitude = 0.0
    latitude = 0.0
    cleaning_fee = 10.0
    owner = factory.SubFactory(UserFactory)  # ✅ This fixes the owner_id error


class ReservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Reservation

    logement = factory.SubFactory(LogementFactory)
    user = factory.SubFactory(UserFactory)
    price = 100.00
    start = factory.LazyFunction(lambda: timezone.now().date())
    end = factory.LazyFunction(lambda: (timezone.now() + datetime.timedelta(days=3)).date())
    guest_adult = 2
    guest_minor = 0
    statut = "confirmee"

    # Add required fields here


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    reservation = factory.SubFactory(ReservationFactory)

    @factory.post_generation
    def participants(self, create, extracted, **kwargs):
        if extracted:
            for user in extracted:
                self.participants.add(user)


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    sender = factory.SubFactory(UserFactory)
    content = "Hello!"
    timestamp = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def recipients(self, create, extracted, **kwargs):
        if extracted:
            for user in extracted:
                self.recipients.add(user)
