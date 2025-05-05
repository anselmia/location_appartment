import os
from django.db import models
from django.dispatch import receiver


class Client(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    telephone = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.name} ({self.email})"


class Logement(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    prix_par_nuit = models.DecimalField(max_digits=6, decimal_places=2)
    adresse = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Room(models.Model):
    logement = models.ForeignKey(
        Logement, on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.image.name}"


class Photo(models.Model):
    logement = models.ForeignKey(
        Logement, on_delete=models.CASCADE, related_name="photos"
    )
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="photos"
    )
    image = models.ImageField(upload_to="logement_images/")

    def __str__(self):
        return f"{self.logement.name} - {self.image.name}"


@receiver(models.signals.post_delete, sender=Photo)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    if instance.image:
        if os.path.isfile(instance.image.path):
            os.remove(instance.image.path)


class Reservation(models.Model):
    logement = models.ForeignKey(Logement, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    date_debut = models.DateField()
    date_fin = models.DateField()
    statut = models.CharField(
        max_length=20,
        choices=[
            ("en_attente", "En attente"),
            ("confirmee", "Confirmée"),
            ("annulee", "Annulée"),
        ],
        default="en_attente",
    )
    date_reservation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Réservation {self.logement.name} par {self.client.name}"
