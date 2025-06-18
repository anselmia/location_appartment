import logging
from django.db import models
from django.core.exceptions import ValidationError
from multiselectfield import MultiSelectField
from accounts.models import CustomUser
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from common.services.helper_fct import generate_unique_code
from payment.services.payment_service import get_payment_fee, get_platform_fee, get_fee_waiver
from logement.models import City

logger = logging.getLogger(__name__)


class Partners(models.Model):
    # Informations générales
    name = models.CharField("Nom du partenaire", max_length=255)
    logo = models.ImageField(upload_to="partners/logos/", blank=True, null=True)
    description = models.TextField("Description", blank=True)
    user = models.ForeignKey(CustomUser, related_name="activity_partners", on_delete=models.CASCADE)

    # Informations de contact
    adresse = models.TextField("Adresse postale")
    code_postal = models.CharField("Code postal", max_length=10)
    ville = models.ForeignKey(City, related_name="activity_partners", on_delete=models.PROTECT)
    pays = models.CharField("Pays", max_length=100, default="France")
    telephone = models.CharField("Téléphone", max_length=20)
    email = models.EmailField("Email", unique=True)

    # Informations légales
    forme_juridique = models.CharField("Forme juridique", max_length=100, blank=True)
    siret = models.CharField("Numéro SIRET", max_length=14, blank=True)

    # Représentant légal
    nom_representant = models.CharField("Nom du représentant légal", max_length=255, blank=True)
    email_representant = models.EmailField("Email du représentant", blank=True)
    telephone_representant = models.CharField("Téléphone du représentant", max_length=20, blank=True)

    # Métadonnées
    date_creation = models.DateField("Date de création", default=timezone.now)
    actif = models.BooleanField(default=True)
    validated = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Partenaire"
        verbose_name_plural = "Partenaires"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.siret and (not self.siret.isdigit() or len(self.siret) != 14):
            raise ValidationError({"siret": "Le numéro SIRET doit contenir exactement 14 chiffres."})


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=100, blank=True, help_text="FontAwesome icon class")

    def __str__(self):
        return self.name


DAYS_OF_WEEK = [
    ("monday", "Lundi"),
    ("tuesday", "Mardi"),
    ("wednesday", "Mercredi"),
    ("thursday", "Jeudi"),
    ("friday", "Vendredi"),
    ("saturday", "Samedi"),
    ("sunday", "Dimanche"),
]


class Activity(models.Model):
    owner = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="owned_activities", verbose_name="Propriétaire"
    )
    name = models.CharField("Nom de l'activité", max_length=200)
    start = models.TimeField(
        "Heure de début", help_text="Heure de début de l'activité dans la journée.", default="09:00"
    )
    end = models.TimeField("Heure de fin", help_text="Heure de fin de l'activité dans la journée.", default="18:00")
    code = models.CharField(max_length=20, null=True, unique=True, blank=True)
    days_of_week = MultiSelectField(
        "Jours de la semaine",
        choices=DAYS_OF_WEEK,
        help_text="Jours de la semaine où l'activité est disponible.",
        default=[],
    )
    ready_period = models.PositiveIntegerField(
        "Délai entre deux activités (minutes)",
        default=0,
        null=True,  # <--- add this
        blank=True,  # <--- add this for admin/forms
        help_text="Temps minimum entre deux réservations de cette activité.",
    )
    fixed_slots = models.BooleanField("Horaires Fixes", default=False, help_text="Activité à horaire fixe")
    manual_time_slots = models.TextField(
        "Créneaux horaires personnalisés",
        blank=True,
        null=True,  # <--- add this
        help_text="Entrez chaque créneau horaire sur une ligne séparée, au format HH:MM (ex: 09:00).",
    )
    description = models.TextField("Description de l'activité")
    duration = models.PositiveIntegerField("Durée (minutes)", help_text="Durée totale de l'activité en minutes.")
    location = models.ForeignKey(City, on_delete=models.PROTECT, related_name="activities", verbose_name="Ville")
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="owned_activities", verbose_name="Catégorie"
    )
    nominal_guests = models.PositiveIntegerField(
        "Nombre de participants",
        help_text="Nombre de participants par défaut pour l'activité.",
        default=1,
    )
    fee_per_extra_guest = models.DecimalField(
        "Frais par participant supplémentaire (€)",
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text="Frais supplémentaires pour chaque participant au-delà du nombre nominal.",
    )
    max_participants = models.PositiveIntegerField("Nombre maximum de participants")
    cancelation_period = models.PositiveIntegerField(
        "Délai d'annulation (jours)",
        default=7,
        help_text="Nombre de jours avant le début de l'activité où l'annulation est possible.",
    )
    availability_period = models.PositiveIntegerField(
        "Préavis (jours)", default=1, help_text="Nombre de jours nécessaires à la préparation de l'activité."
    )
    price = models.DecimalField("Prix (€)", max_digits=8, decimal_places=2)
    is_active = models.BooleanField("Activité ouverte ?", default=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            # Ensure uniqueness
            for _ in range(10):  # up to 10 retries
                code = generate_unique_code()
                if not ActivityReservation.objects.filter(code=code).exists():
                    self.code = code
                    break
            else:
                raise ValueError("Could not generate a unique reservation code.")

        super().save(*args, **kwargs)

    def is_activity_admin(self, user):
        return user.is_admin or user == self.owner or user.is_superuser

    @property
    def booking_limit(self):
        return timezone.now().date() + timedelta(days=self.availability_period)


class CloseDate(models.Model):
    activity = models.ForeignKey(Activity, related_name="close_dates", on_delete=models.CASCADE)
    date = models.DateField()

    def __str__(self):
        return f"Nuit du {self.date} fermée"


class ActivityPhoto(models.Model):
    activity = models.ForeignKey(Activity, related_name="photos", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="activities/photos/")
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.activity.name}"


class ActivityReservation(models.Model):
    activity = models.ForeignKey(Activity, related_name="reservations", on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="activity_reservations")
    participants = models.PositiveIntegerField(default=1)
    date_reservation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=20,
        choices=[
            ("en_attente", "En attente"),
            ("confirmee", "Confirmée"),
            ("annulee", "Annulée"),
            ("terminee", "Terminée"),
        ],
        default="pending",
    )
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    price = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    payment_fee = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    platform_fee = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    checkout_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    refunded = models.BooleanField(default=False)
    refund_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_refund_id = models.CharField(max_length=100, blank=True, null=True)
    transferred = models.BooleanField(default=False)
    transferred_amount = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    stripe_transfer_id = models.CharField(max_length=100, blank=True, null=True)
    pre_checkin_email_sent = models.BooleanField(default=False)
    comment = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user} - {self.activity} ({self.statut})"

    def save(self, *args, **kwargs):
        if not self.code:
            # Ensure uniqueness
            for _ in range(10):  # up to 10 retries
                code = generate_unique_code()
                if not ActivityReservation.objects.filter(code=code).exists():
                    self.code = code
                    break
            else:
                raise ValueError("Could not generate a unique reservation code.")

        if not self.payment_fee:
            self.payment_fee = get_payment_fee(self.price)

        if self.platform_fee is None:
            platform_fee = get_platform_fee(self.price)
            self.platform_fee = get_fee_waiver(platform_fee, self.activity.owner)

        super().save(*args, **kwargs)

    @property
    def can_cancel(self):
        if self.statut != "confirmee":
            return False
        return True

    @property
    def refundable_period_passed(self):
        cancel_limit = self.start - timedelta(days=self.activity.cancelation_period)
        return timezone.now() > cancel_limit

    @property
    def refundable(self):
        if self.refundable_amount == 0:
            return False
        if self.refunded:
            return False
        if self.refundable_period_passed:
            return False
        if self.transferred:
            return False
        return True

    @property
    def refundable_amount(self):
        """
        Calculates the refundable amount to the guest.

        Formula:
        refundable = price - payment_fee - already_refunded
        """
        try:
            price = Decimal(self.price or "0.00")
            payment_fee = Decimal(self.payment_fee or "0.00")
            refund_amount = Decimal(self.refund_amount or "0.00")

            refundable = price - payment_fee - refund_amount
            refundable = max(Decimal("0.00"), refundable)

            return refundable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            logger.exception(f"❌ Error calculating refundable_amount for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def partial_refundable_amount(self):
        """
        Calculates the partial refundable amount to the guest.

        Formula:
        refundable = price - payment_fee - already_refunded - platform_fee
        """
        try:
            price = Decimal(self.price or "0.00")
            payment_fee = Decimal(self.payment_fee or "0.00")
            refund_amount = Decimal(self.refund_amount or "0.00")
            platform_fee = Decimal(self.platform_fee or "0.00")

            refundable = price - payment_fee - refund_amount - platform_fee
            refundable = max(Decimal("0.00"), refundable)

            return refundable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"❌ Error calculating refundable_amount for reservation {self.id}: {e}")
            return Decimal("0.00")

    @property
    def ended(self):
        return self.statut == "terminee" or (self.statut == "confirmee" and timezone.now() > self.end)

    @property
    def pending(self):
        return self.statut == "en_attente"

    @property
    def ongoing(self):
        today = timezone.now()
        return self.statut == "confirmee" and (self.start <= today <= self.end)

    @property
    def coming(self):
        return self.statut == "confirmee" and (timezone.now() < self.start)

    @property
    def transferable_amount(self):
        """
        Calculates the amount that can be transferred to the owner.

        Formula:
        transferable = price - platform_fee - refund_amount
        """
        try:

            platform_fee = Decimal(self.platform_fee or 0)
            payment_fee = Decimal(self.payment_fee or 0)
            refund = Decimal(self.refund_amount or 0)
            price = Decimal(self.price or 0)

            # Check if logement or owner has offered fees
            amount = price - platform_fee - refund - payment_fee
            amount = max(Decimal("0"), amount)

            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"Error calculating transferable_amount for owner for reservation {self.id}: {e}")
            return Decimal("0.00")


class Price(models.Model):
    activity = models.ForeignKey(Activity, related_name="prices", on_delete=models.CASCADE)
    date = models.DateField()
    value = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return f"Prix du {self.date}: {self.value}"
