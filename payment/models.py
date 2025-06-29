from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.mail import mail_admins

# Create your models here.
class PaymentTask(models.Model):
    TASK_TYPES = [
        ("transfer_owner", "Transfer to Owner"),
        ("transfer_admin", "Transfer to Admin"),
        ("charge_deposit", "Charge Deposit"),
        ("refund", "Refund"),
        ("checkout", "Check Out"),
        ("capture", "Capture Payment"),
        ("create_manual_payment_intent", "Create Manual Payment Intent"),
        ("create_setup_intent", "Create Setup Intent"),
    ]

    # Generic relation to Reservation or ActivityReservation
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    reservation = GenericForeignKey("content_type", "object_id")

    type = models.CharField(max_length=32, choices=TASK_TYPES)
    status = models.CharField(max_length=20, choices=[("success", "Success"), ("failed", "Failed")], default="failed")

    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    task_id = models.CharField(max_length=50)

    def mark_success(self, id):
        self.status = "success"
        self.updated_at = timezone.now()
        self.task_id = id
        self.save(update_fields=["status", "updated_at"])

    def mark_failure(self, error, id=None):
        self.status = "failed"
        self.error = str(error)
        self.updated_at = timezone.now()
        self.task_id = id
        self.save(update_fields=["status", "error", "updated_at"])
        mail_admins(
            "Payment Task Failure",
            f"Task {self.type} for reservation {self.reservation.code} failed with error: {error}",
            fail_silently=False,
        )

    @property
    def reservation_type(self):
        if self.reservation:
            return self.reservation.__class__.__name__
        return ""

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "type"], name="unique_task_type_per_reservation"
            )
        ]
