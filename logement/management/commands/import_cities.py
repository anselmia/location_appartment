import csv
from django.core.management.base import BaseCommand
from logement.models import City


class Command(BaseCommand):
    help = "Importe les communes depuis le fichier CSV de l'INSEE"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Chemin vers le fichier CSV")

    def handle(self, *args, **kwargs):
        csv_file = kwargs["csv_file"]
        with open(csv_file, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file, delimiter=",", quotechar='"')
            print("Colonnes détectées :", reader.fieldnames)
            count = 0
            for row in reader:
                name = row["NCCENR"].title()
                code_postal = row["DEP"]

                city, _ = City.objects.update_or_create(
                    name=name,
                    code_postal=code_postal,
                    defaults={},  # rien à mettre à jour
                )
                self.stdout.write(
                    self.style.SUCCESS(f"{city.name} importées avec succès.")
                )
                count += 1
            self.stdout.write(
                self.style.SUCCESS(f"{count} villes importées avec succès.")
            )
