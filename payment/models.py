from django.db import models
from django.utils import timezone


# Create your models here.
class PaymentTask(models.Model):
    TASK_TYPES = [
        ("transfer_owner", "Transfer to Owner"),
        ("transfer_admin", "Transfer to Admin"),
        ("charge_deposit", "Charge Deposit"),
        ("refund", "Refund"),
    ]

    reservation = models.ForeignKey("reservation.Reservation", on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=TASK_TYPES)
    status = models.CharField(max_length=20, choices=[("success", "Success"), ("failed", "Failed")], default="failed")

    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    def mark_success(self):
        self.status = "success"
        self.updated_at = timezone.now()
        self.save(update_fields=["status", "updated_at"])

    def mark_failure(self, error):
        self.status = "failed"
        self.error = str(error)
        self.updated_at = timezone.now()
        self.save(update_fields=["status", "error", "updated_at"])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["reservation", "type"], name="unique_task_type_per_reservation")]
