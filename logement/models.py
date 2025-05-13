import os
from django.db import models
from django.dispatch import receiver
from accounts.models import CustomUser
from django.urls import reverse


class Logement(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=6, decimal_places=2)
    adresse = models.CharField(max_length=255)
    max_traveler = models.IntegerField(default=4)
    nominal_traveler = models.IntegerField(default=4)
    fee_per_extra_traveler = models.DecimalField(
        max_digits=6, decimal_places=2, default=0
    )
    cleaning_fee = models.DecimalField(max_digits=6, decimal_places=2, default=4)
    tax = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    cancelation_period = models.IntegerField(default=15)
    bedrooms = models.IntegerField(default=1)

    def __str__(self):
        return self.name


class Price(models.Model):
    logement = models.ForeignKey(
        Logement, related_name="night_price", on_delete=models.CASCADE
    )
    date = models.DateField()
    value = models.TextField()

    def __str__(self):
        return f"Prix du {self.date}: {self.value}"


class DiscountType(models.Model):
    name = models.CharField(
        max_length=100, unique=True
    )  # ex: "À la semaine (7+ nuits)"
    description = models.TextField(blank=True)

    # Champs dynamiques selon la logique
    requires_min_nights = models.BooleanField(default=False)
    requires_days_before = models.BooleanField(default=False)
    requires_date_range = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Discount(models.Model):
    logement = models.ForeignKey(
        Logement, on_delete=models.CASCADE, related_name="discounts"
    )
    discount_type = models.ForeignKey(DiscountType, on_delete=models.CASCADE, null=True, blank=True)

    value = models.DecimalField(max_digits=5, decimal_places=2)

    # Valeurs personnalisables selon le type
    min_nights = models.IntegerField(null=True, blank=True)
    days_before = models.IntegerField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('logement', 'discount_type')
        
    def __str__(self):
        return f"{self.discount_type.name} — {self.value} %"


class ExtraCharge(models.Model):
    logement = models.ForeignKey(
        Logement, related_name="extra_charges", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)  # E.g., Cleaning Fee, Extra Guest Fee
    amount = models.DecimalField(
        max_digits=6, decimal_places=2
    )  # The cost of the extra charge
    description = models.TextField(
        blank=True, null=True
    )  # Optional description of the charge
    is_active = models.BooleanField(
        default=True
    )  # Option to deactivate charge if needed

    def __str__(self):
        return f"{self.name} for {self.logement.name}"

    class Meta:
        verbose_name = "Extra Charge"
        verbose_name_plural = "Extra Charges"


class Room(models.Model):
    logement = models.ForeignKey(
        Logement, on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.logement.name}"


class Photo(models.Model):
    logement = models.ForeignKey(
        Logement, on_delete=models.CASCADE, related_name="photos"
    )
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="photos"
    )
    image = models.ImageField(upload_to="logement_images/")
    order = models.IntegerField(default=0)  # Add the order field

    def __str__(self):
        return f"{self.logement.name} - {self.image.name}"

    def save(self, *args, **kwargs):
        # Set order automatically when a new photo is created
        if not self.pk:  # If the photo is being created (not updated)
            max_order = Photo.objects.filter(logement=self.logement).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            self.order = (
                max_order or 0
            ) + 1  # Increment the order, default to 1 if no photos exist
        super().save(*args, **kwargs)


@receiver(models.signals.post_delete, sender=Photo)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    if instance.image:
        if os.path.isfile(instance.image.path):
            os.remove(instance.image.path)


class Reservation(models.Model):
    logement = models.ForeignKey(Logement, on_delete=models.CASCADE)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=False,  # Make it required
        blank=False,
    )
    start = models.DateField()
    end = models.DateField()
    statut = models.CharField(
        max_length=20,
        choices=[
            ("en_attente", "En attente"),
            ("confirmee", "Confirmée"),
            ("annulee", "Annulée"),
        ],
        default="en_attente",
    )
    guest = models.IntegerField()
    date_reservation = models.DateTimeField(auto_now_add=True)
    price = models.FloatField()

    def __str__(self):
        return f"Réservation {self.logement.name} par {self.user.name}"


class airbnb_booking(models.Model):
    logement = models.ForeignKey(Logement, on_delete=models.CASCADE)
    start = models.DateField()
    end = models.DateField()

    def __str__(self):
        return f"Réservation à {self.logement.name} du {self.start} au {self.end}"


class booking_booking(models.Model):
    logement = models.ForeignKey(Logement, on_delete=models.CASCADE)
    start = models.DateField()
    end = models.DateField()

    def __str__(self):
        return f"Réservation à {self.logement.name} du {self.start} au {self.end}"
