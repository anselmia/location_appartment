from django.core.management.base import BaseCommand
from activity.models import Category

# Liste concise de grandes familles d'activités touristiques (max 20)
categories = [
    {"name": "Visites guidées & Culture", "icon": "fas fa-landmark"},
    {"name": "Sports & Aventure", "icon": "fas fa-hiking"},
    {"name": "Bien-être & Spa", "icon": "fas fa-spa"},
    {"name": "Gastronomie & Dégustation", "icon": "fas fa-utensils"},
    {"name": "Nature & Découverte", "icon": "fas fa-leaf"},
    {"name": "Activités nautiques", "icon": "fas fa-water"},
    {"name": "Sorties en famille", "icon": "fas fa-child"},
    {"name": "Spectacles & Événements", "icon": "fas fa-theater-masks"},
    {"name": "Artisanat & Ateliers", "icon": "fas fa-paint-brush"},
    {"name": "Excursions & Randonnées", "icon": "fas fa-mountain"},
    {"name": "Vie nocturne & Bars", "icon": "fas fa-cocktail"},
    {"name": "Shopping & Marchés", "icon": "fas fa-shopping-bag"},
    {"name": "Parcs & Loisirs", "icon": "fas fa-tree"},
    {"name": "Patrimoine & Histoire", "icon": "fas fa-monument"},
    {"name": "Photographie & Création", "icon": "fas fa-camera-retro"},
    {"name": "Musées & Expositions", "icon": "fas fa-university"},
    {"name": "Animaux & Ferme", "icon": "fas fa-dog"},
    {"name": "Jeux & Escape Game", "icon": "fas fa-puzzle-piece"},
    {"name": "Cours & Initiations", "icon": "fas fa-chalkboard-teacher"},
]


class Command(BaseCommand):
    help = "Importe une liste de catégories d'activités."

    def handle(self, *args, **kwargs):
        created_list = []
        for cat in categories:
            obj, created = Category.objects.get_or_create(name=cat["name"])
            obj.icon = cat["icon"]
            obj.save()
            created_list.append(obj)
        self.stdout.write(
            self.style.SUCCESS(f"✔️ {len(created_list)} catégories importées : {[c.name for c in created_list]}")
        )
