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
    phone = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[phone_validator],
        unique=True,
        help_text="Numéro au format international, ex: +33612345678",
    )
    last_name = models.CharField(max_length=100, verbose_name="Prénom")
    name = models.CharField(max_length=100, verbose_name="Nom")
    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Identifiant client Stripe associé pour paiements et impressions de carte.",
    )
    stripe_account_id = models.CharField(max_length=255, blank=True, null=True)
    last_activity = models.DateTimeField(null=True, blank=True)  # Track the last activity time

    def __str__(self):
        return f"{self.name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.name} {self.last_name}"


class Conversation(models.Model):
    reservation = models.OneToOneField("logement.Reservation", on_delete=models.CASCADE, related_name="conversation")
    participants = models.ManyToManyField(CustomUser, related_name="conversations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Conversation #{self.id} - Réservation {self.reservation_id}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="sent_messages")
    recipients = models.ManyToManyField(CustomUser, related_name="received_messages")
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"
