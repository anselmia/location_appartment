from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class CustomUser(AbstractUser):
    is_admin = models.BooleanField(default=False)
    phone = models.CharField(
        max_length=15, blank=True, null=True
    )  # Adjust max_length as per your requirement
    last_name = models.CharField(max_length=100)  # Surname (Last name)
    name = models.CharField(max_length=100)  # First name (Given name)

    def __str__(self):
        return self.username


class Message(models.Model):
    sender = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="sent_messages"
    )
    recipient = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="received_messages"
    )
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["timestamp"]
