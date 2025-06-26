from django.db import models
from logement.models import City
from accounts.models import CustomUser
from logement.models import Logement
from django.utils import timezone
from django.core.exceptions import ValidationError


# Create your models here.
class Conciergerie(models.Model):
    # Informations générales
    name = models.CharField("Nom de la conciergerie", max_length=255)
    logo = models.ImageField(upload_to="conciergeries/logos/", blank=True, null=True)
    description = models.TextField("Description", blank=True)
    user = models.ForeignKey(CustomUser, related_name="conciergeries", on_delete=models.CASCADE)

    # Informations de contact
    adresse = models.TextField("Adresse postale")
    code_postal = models.CharField("Code postal", max_length=10)
    ville = models.ForeignKey(City, related_name="conciergeries", on_delete=models.PROTECT)
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
    onboarded = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Conciergerie"
        verbose_name_plural = "Conciergeries"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.siret and (not self.siret.isdigit() or len(self.siret) != 14):
            raise ValidationError({"siret": "Le numéro SIRET doit contenir exactement 14 chiffres."})


class ConciergerieRequest(models.Model):
    logement = models.ForeignKey(Logement, on_delete=models.CASCADE, related_name="conciergerie_requests")
    conciergerie = models.ForeignKey(Conciergerie, on_delete=models.CASCADE, related_name="requests")
    status = models.CharField(
        max_length=20,
        choices=[("pending", "En attente"), ("accepted", "Acceptée"), ("rejected", "Refusée")],
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
