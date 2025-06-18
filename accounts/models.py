from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator


phone_validator = RegexValidator(
    regex=r"^\+?1?\d{9,15}$",
    message="Le numéro de téléphone n'est pas valide. Veuillez entrer un numéro valide.",
)


class CustomUser(AbstractUser):
    is_admin = models.BooleanField(default=False)
    is_owner = models.BooleanField(default=False)
    is_owner_admin = models.BooleanField(default=False)
    is_partner = models.BooleanField(default=False)
    phone = models.CharField(
        max_length=15,
        validators=[phone_validator],
        unique=True,
        help_text="Numéro au format international, ex: +33612345678",
    )
    last_name = models.CharField(max_length=100, verbose_name="Prénom")
    name = models.CharField(max_length=100, verbose_name="Nom")
    stripe_customer_id = models.CharField(
        max_length=255,
        help_text="Identifiant client Stripe associé pour paiements et impressions de carte.",
        null=True,
        blank=True,
    )
    stripe_account_id = models.CharField(max_length=255, blank=True, null=True)
    last_activity = models.DateTimeField(null=True, blank=True)  # Track the last activity time

    def __str__(self):
        return f"{self.name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.name} {self.last_name}"


class Conversation(models.Model):
    reservation = models.OneToOneField(
        "reservation.Reservation", on_delete=models.CASCADE, related_name="conversation", unique=True
    )
    participants = models.ManyToManyField(CustomUser, related_name="conversations")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Conversation #{self.id} - Réservation {self.reservation_id}"

    class Meta:
        indexes = [
            models.Index(fields=["updated_at"]),
        ]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="sent_messages")
    recipients = models.ManyToManyField(CustomUser, related_name="received_messages")
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    read_by = models.ManyToManyField(CustomUser, related_name="messages_read", blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["sender"]),
        ]
        ordering = ["timestamp"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def is_read_by(self, user):
        return self.read_by.filter(id=user.id).exists()
