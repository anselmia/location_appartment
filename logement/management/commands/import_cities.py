from django.core.management.base import BaseCommand
from logement.models import City


class Command(BaseCommand):
    help = "Importe les 30 principales villes des Alpes-Maritimes (06)"

    def handle(self, *args, **kwargs):

        major_cities = [
            ("Nice", True, "06"),
            ("Antibes", False, "06"),
            ("Cannes", False, "06"),
            ("Grasse", False, "06"),
            ("Cagnes-sur-Mer", False, "06"),
            ("Le Cannet", False, "06"),
            ("Menton", True, "06"),
            ("Saint-Laurent-du-Var", False, "06"),
            ("Mandelieu-la-Napoule", False, "06"),
            ("Vallauris", False, "06"),
            ("Vence", False, "06"),
            ("Beausoleil", False, "06"),
            ("La Trinité", False, "06"),
            ("Roquebrune-Cap-Martin", True, "06"),
            ("Carros", False, "06"),
            ("Villeneuve-Loubet", False, "06"),
            ("Valbonne", False, "06"),
            ("Mouans-Sartoux", False, "06"),
            ("Biot", False, "06"),
            ("Contes", False, "06"),
            ("Levens", False, "06"),
            ("Pégomas", False, "06"),
            ("La Gaude", False, "06"),
            ("Mougins", False, "06"),
            ("Tourrette-Levens", False, "06"),
            ("Villefranche-sur-Mer", True, "06"),
            ("Eze", False, "06"),
            ("Saint-André-de-la-Roche", False, "06"),
            ("Aspremont", False, "06"),
            ("Cap-d'Ail", False, "06"),
            ("Bairols", False, "06"),
            ("Beaulieu-sur-Mer", False, "06"),
            ("Belvédère", False, "06"),
            ("Bonson", False, "06"),
            ("Castagniers", False, "06"),
            ("Clans", False, "06"),
            ("Châteauneuf-Villevieille", False, "06"),
            ("Colomars", False, "06"),
            ("Drap", False, "06"),
            ("Duranus", False, "06"),
            ("Falicon", False, "06"),
            ("Gattières", False, "06"),
            ("Gilette", False, "06"),
            ("Ilonse", False, "06"),
            ("Isola", False, "06"),
            ("La Bollène-Vésubie", False, "06"),
            ("La Roquette-sur-Var", False, "06"),
            ("La Tour-sur-Tinée", False, "06"),
            ("Lantosque", False, "06"),
            ("Le Broc", False, "06"),
            ("Marie", False, "06"),
            ("Rimplas", False, "06"),
            ("Roquebillière", False, "06"),
            ("Roubion", False, "06"),
            ("Roure", False, "06"),
            ("Saint-Blaise", False, "06"),
            ("Saint-Dalmas-le-Selvage", False, "06"),
            ("Saint-Étienne-de-Tinée", False, "06"),
            ("Saint-Jean-Cap-Ferrat", False, "06"),
            ("Saint-Jeannet", False, "06"),
            ("Saint-Martin-du-Var", False, "06"),
            ("Saint-Martin-Vésubie", False, "06"),
            ("Saint-Sauveur-sur-Tinée", False, "06"),
            ("Tournefort", False, "06"),
            ("Utelle", False, "06"),
            ("Valdeblore", False, "06"),
            ("Venanson", False, "06"),
            # Villes supplémentaires avec obligation
            ("Saint-Paul-de-Vence", True, "06"),
            ("Marseille", True, "13"),
            ("Aix-en-Provence", True, "13"),
            ("Cassis", True, "13"),
            ("Istres", True, "13"),
            ("Martigues", True, "13"),
            ("Port-Saint-Louis-du-Rhône", True, "13"),
            ("Saint-Cannat", True, "13"),
            ("Les Baux-de-Provence", True, "13"),
            ("Saintes-Maries-de-la-Mer", True, "13"),
            ("Bandol", True, "83"),
            ("Le Castellet", True, "83"),
            ("Roquebrune-sur-Argens", True, "83"),
            ("Saint-Cyr-sur-Mer", True, "83"),
            ("La Croix-Valmer", True, "83"),
            ("La Londe-les-Maures", True, "83"),
            ("Saint-Tropez", True, "83"),
        ]

        created = 0
        for name, registration, department in major_cities:
            city, created_flag = City.objects.update_or_create(
                name=name,
                registration=registration,
                code_postal=department,
                defaults={},
            )
            if created_flag:
                created += 1

        self.stdout.write(self.style.SUCCESS(f"{created} villes majeures des Alpes-Maritimes importées avec succès."))
