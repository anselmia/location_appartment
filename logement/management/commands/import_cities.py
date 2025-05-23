from django.core.management.base import BaseCommand
from logement.models import City

class Command(BaseCommand):
    help = "Importe les 30 principales villes des Alpes-Maritimes (06)"

    def handle(self, *args, **kwargs):
        major_cities = [
            "Nice", "Antibes", "Cannes", "Grasse", "Cagnes-sur-Mer", "Le Cannet",
            "Menton", "Saint-Laurent-du-Var", "Mandelieu-la-Napoule", "Vallauris",
            "Vence", "Beausoleil", "La Trinité", "Roquebrune-Cap-Martin", "Carros",
            "Villeneuve-Loubet", "Valbonne", "Mouans-Sartoux", "Biot", "Contes",
            "Levens", "Pégomas", "La Gaude", "Mougins", "Tourrette-Levens",
            "Villefranche-sur-Mer", "Eze", "Saint-André-de-la-Roche", "Aspremont", "Cap-d'Ail"
        ]

        created = 0
        for name in major_cities:
            city, created_flag = City.objects.update_or_create(
                name=name,
                code_postal="06",  # all are in Alpes-Maritimes
                defaults={},        # no additional updates
            )
            if created_flag:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f"{created} villes majeures des Alpes-Maritimes importées avec succès.")
        )