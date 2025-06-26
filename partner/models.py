import logging

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from logement.models import City
from accounts.models import CustomUser

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
    onboarded = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Partenaire"
        verbose_name_plural = "Partenaires"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.siret and (not self.siret.isdigit() or len(self.siret) != 14):
            raise ValidationError({"siret": "Le numéro SIRET doit contenir exactement 14 chiffres."})

