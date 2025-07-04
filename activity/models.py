import logging
from datetime import timedelta
from multiselectfield import MultiSelectField
from django.db.models import Avg
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone

from common.services.helper_fct import generate_unique_code
from logement.models import City
from accounts.models import CustomUser
from partner.models import Partners

logger = logging.getLogger(__name__)


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
    detail = models.TextField("Détails de l'activité")
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
                if not Activity.objects.filter(code=code).exists():
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

    @property
    def partner(self):
        return get_object_or_404(Partners, user=self.owner)

    @property
    def rating(self):
        """Return the average stars for this activity (float, 0 if no ratings)."""
        avg = self.rankings.aggregate(avg=Avg("stars"))["avg"]
        return round(avg or 0, 2)

    @property
    def review_count(self):
        """Return the number of ratings for this activity."""
        return self.rankings.count()

    @property
    def ranking_comments(self):
        """
        Returns a queryset of all non-empty comments from rankings for this activity.
        """
        return self.rankings.exclude(comment__isnull=True).exclude(comment__exact="").values_list("comment", flat=True)


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


class Price(models.Model):
    activity = models.ForeignKey(Activity, related_name="prices", on_delete=models.CASCADE)
    date = models.DateField()
    value = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return f"Prix du {self.date}: {self.value}"


class ActivityRating(models.Model):
    reservation = models.OneToOneField("reservation.ActivityReservation", on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="rankings")
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE)
    stars = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
