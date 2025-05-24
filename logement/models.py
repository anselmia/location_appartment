import os
from datetime import time
from django.db import models
from django.dispatch import receiver
from accounts.models import CustomUser
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP


class City(models.Model):
    name = models.CharField(max_length=150)
    code_postal = models.CharField(max_length=10)

    class Meta:
        unique_together = ("name", "code_postal")

    def __str__(self):
        return f"{self.name} ({self.code_postal})"


class EquipmentType(models.TextChoices):
    COMFORT = "comfort", "Confort & Accessibilité"
    KITCHEN = "kitchen", "Cuisine"
    CONNECTIVITY = "connectivity", "Technologie & Connectivité"
    BED_BATH = "bed_bath", "Chambre & Salle de bain"
    PARKING = "parking", "Stationnement"
    OUTDOOR = "outdoor", "Extérieur"
    CHILDREN = "children", "Équipements pour enfants"
    SECURITY = "security", "Sécurité"
    ENTERTAINMENT = "entertainment", "Divertissement"
    WELLNESS = "wellness", "Bien-être"
    CLEANING = "cleaning", "Entretien"
    CLIMATE = "climate", "Climatisation & Chauffage"
    OTHER = "other", "Autres"


# models.py
class Equipment(models.Model):
    name = models.CharField(max_length=150)
    icon = models.CharField(
        max_length=100, blank=True, help_text="FontAwesome icon class or image name"
    )
    type = models.CharField(
        max_length=20,
        choices=EquipmentType.choices,
        default=EquipmentType.OTHER,
    )

    def __str__(self):
        return self.name


class Logement(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    adresse = models.CharField(max_length=255)
    ville = models.ForeignKey(
        City, related_name="city", on_delete=models.SET_NULL, null=True, blank=True
    )
    statut = models.CharField(
        max_length=20,
        choices=[
            ("open", "Ouvert"),
            ("close", "Fermé"),
        ],
        default="close",
    )

    type = models.CharField(
        max_length=20,
        choices=[
            ("house", "Maison"),
            ("flat", "Appartement"),
            ("room", "Chambre"),
        ],
        default="flat",
    )

    max_traveler = models.IntegerField(default=4)
    nominal_traveler = models.IntegerField(default=4)
    caution = models.IntegerField(default=0)
    fee_per_extra_traveler = models.DecimalField(
        max_digits=6, decimal_places=2, default=0
    )
    cleaning_fee = models.DecimalField(max_digits=6, decimal_places=2, default=49)
    tax = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    tax_max = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    cancelation_period = models.IntegerField(default=15)  # en jours ?
    superficie = models.IntegerField(blank=True, null=True)
    bathrooms = models.IntegerField(default=1)
    bedrooms = models.IntegerField(default=1)
    beds = models.IntegerField(default=1)

    ready_period = models.IntegerField(default=1)  # en jours ?

    entrance_hour_min = models.TimeField(default=time(15, 0))
    entrance_hour_max = models.TimeField(default=time(20, 0))
    leaving_hour = models.TimeField(default=time(11, 0))

    max_days = models.IntegerField(default=60)
    availablity_period = models.IntegerField(default=6)  # en mois ?

    animals = models.BooleanField(default=False)
    smoking = models.BooleanField(default=False)
    owner = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,  # Make it required
        blank=True,
    )

    airbnb_link = models.URLField(blank=True, null=True)
    airbnb_calendar_link = models.URLField(blank=True, null=True)
    booking_link = models.URLField(blank=True, null=True)
    booking_calendar_link = models.URLField(blank=True, null=True)

    equipment = models.ManyToManyField(Equipment, blank=True, related_name="logements")

    map_link = models.URLField(blank=True, null=True, max_length=1000)

    refund_charge = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)

    def __str__(self):
        return self.name

    @property
    def booking_limit(self):
        return timezone.now().date() + timedelta(days=self.ready_period)


class Price(models.Model):
    logement = models.ForeignKey(
        Logement, related_name="night_price", on_delete=models.CASCADE
    )
    date = models.DateField()
    value = models.TextField()

    def __str__(self):
        return f"Prix du {self.date}: {self.value}"


class DiscountType(models.Model):
    code = models.CharField(max_length=50, unique=True, default="")
    name = models.CharField(max_length=100, default="")
    requires_min_nights = models.BooleanField(default=False)
    requires_days_before = models.BooleanField(default=False)
    requires_date_range = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Discount(models.Model):
    logement = models.ForeignKey(
        Logement, on_delete=models.CASCADE, related_name="discounts", null=False
    )
    discount_type = models.ForeignKey(
        DiscountType, on_delete=models.CASCADE, related_name="discounts", null=False
    )

    name = models.CharField(max_length=100, default="")
    value = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="En pourcentage"
    )

    # Conditions
    min_nights = models.IntegerField(
        null=True, blank=True, help_text="Durée minimale du séjour"
    )
    exact_nights = models.IntegerField(
        null=True, blank=True, help_text="Appliqué uniquement pour cette durée exacte"
    )
    days_before_min = models.IntegerField(
        null=True,
        blank=True,
        help_text="Réservation au moins X jours avant (early bird)",
    )
    days_before_max = models.IntegerField(
        null=True,
        blank=True,
        help_text="Réservation moins de X jours avant (last minute)",
    )
    start_date = models.DateField(
        null=True, blank=True, help_text="Date de début d'application"
    )
    end_date = models.DateField(
        null=True, blank=True, help_text="Date de fin d'application"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("logement", "discount_type", "name")

    def __str__(self):
        return f"{self.name} — {self.value}%"


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


def upload_to(instance, filename):
    return f"logement_images/{filename}"


ROTATION_CHOICES = [
    (0, "0°"),
    (90, "90°"),
    (180, "180°"),
    (270, "270°"),
]


class Photo(models.Model):
    logement = models.ForeignKey(
        Logement, on_delete=models.CASCADE, related_name="photos"
    )
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="photos"
    )
    image = models.ImageField(upload_to=upload_to)
    image_webp = models.ImageField(
        upload_to="logement_images/webp/", blank=True, null=True, editable=False
    )
    order = models.IntegerField(default=0)  # Add the order field
    rotation = models.IntegerField(choices=ROTATION_CHOICES, default=0)

    def __str__(self):
        return f"{self.logement.name} - {self.image.name}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_rotation = None
        old_image_path = None

        if not is_new:
            old = Photo.objects.get(pk=self.pk)
            old_rotation = old.rotation
            old_image_path = (
                old.image.path
                if old.image and old.image.name != self.image.name
                else None
            )

        # If the photo is being created, set initial order
        if is_new:
            max_order = Photo.objects.filter(logement=self.logement).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            self.order = (max_order or 0) + 1

        super().save(*args, **kwargs)  # Save original image to get path

        should_rebuild_webp = False

        # 1. New image or image changed
        if is_new or old_image_path:
            should_rebuild_webp = True

        # 2. Rotation changed
        elif old_rotation is not None and self.rotation != old_rotation:
            should_rebuild_webp = True

        if should_rebuild_webp and self.image:
            try:
                img = Image.open(self.image.path).convert("RGB")

                if self.rotation:
                    img = img.rotate(self.rotation, expand=True)

                buffer = BytesIO()
                img.save(buffer, format="WEBP", quality=85)
                buffer.seek(0)

                filename = (
                    os.path.splitext(os.path.basename(self.image.name))[0] + ".webp"
                )
                self.image_webp.save(filename, ContentFile(buffer.read()), save=False)
                super().save(update_fields=["image_webp"])  # Save only webp
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(
                    f"Error generating WebP for photo {self.pk}: {e}"
                )

    class Meta:
        ordering = ["order"]  # 👈 Always sort by `order`


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
            ("terminee", "Terminée"),
        ],
        default="en_attente",
    )
    guest = models.IntegerField()
    date_reservation = models.DateTimeField(default=timezone.now)
    price = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_saved_payment_method_id = models.CharField(
        max_length=255, null=True, blank=True
    )
    refunded = models.BooleanField(default=False)
    refund_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_refund_id = models.CharField(max_length=100, blank=True, null=True)
    caution_charged = models.BooleanField(default=False)
    amount_charged = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_deposit_payment_intent_id = models.CharField(
        max_length=100, blank=True, null=True
    )

    def __str__(self):
        return f"Réservation {self.logement.name} par {self.user.name}"

    @property
    def can_cancel(self):
        if self.statut != "confirmee":
            return False
        return True

    @property
    def refundable(self):
        if self.statut != "confirmee":
            return False
        if self.refunded:
            return False
        cancel_limit = self.start - timedelta(days=self.logement.cancelation_period)
        return timezone.now().date() < cancel_limit

    @property
    def refundable_amount(self):
        # Calculate the refundable amount
        __refundable_amount = max(
            self.price
            - (
                self.price * (self.logement.refund_charge / Decimal("100"))
                - self.refund_amount
            ),
            Decimal("0"),  # Ensure we return 0 if the result is negative
        )

        # Round the result to 2 decimal places
        __refundable_amount = __refundable_amount.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return __refundable_amount

    @property
    def ended(self):
        return self.statut == "terminee" or (
            self.statut == "confirmee" and timezone.now().date() > self.end
        )

    @property
    def ongoing(self):
        today = timezone.now().date()
        return self.statut == "confirmee" and (self.start <= today <= self.end)

    @property
    def coming(self):
        return self.statut == "confirmee" and (timezone.now().date() < self.start)

    @property
    def chargeable_deposit(self):
        caution = Decimal(
            self.logement.caution or 0
        )  # Ensure it is treated as a Decimal
        charged = Decimal(self.amount_charged or 0)  # Ensure it is treated as a Decimal
        result = max(Decimal("0"), caution - charged)

        # Round the result to 2 decimal places
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
