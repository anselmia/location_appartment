import logging
import json
import openai
from openai import OpenAI, RateLimitError
from datetime import date

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render
from django.http import JsonResponse
from django.urls import reverse

logger = logging.getLogger(__name__)
client = OpenAI(api_key=settings.OPENAI_KEY)


# Set up a logger for the view
logger = logging.getLogger(__name__)


def is_admin(user):
    return user.is_authenticated and (getattr(user, "is_admin", False) or user.is_superuser)


def is_stripe_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False) or user.is_superuser or user.is_owner or user.is_owner_admin
    )


def cgu_view(request):
    return render(request, "common/cgu.html")


def confidentiality_view(request):
    return render(request, "common/confidentiality.html")


def cgv_view(request):
    return render(request, "common/cgv.html")


def error_view(request, error_message="An unexpected error occurred."):
    """
    Common error view to handle and display errors to the user.
    """
    logger.error(f"Error encountered: {error_message}")  # Log the error

    # Render the error page with the provided error message
    return render(
        request,
        "common/error.html",  # Common error template
        {"error_message": error_message},
    )


def custom_bad_request(request, exception):
    return render(request, "400.html", status=400)


def custom_permission_denied(request, exception):
    return render(request, "403.html", status=403)


def custom_page_not_found(request, exception):
    return render(request, "404.html", status=404)


def custom_server_error(request):
    return render(request, "500.html", status=500)


MAX_MESSAGES_PER_DAY = 5


@csrf_exempt
@require_POST
def chatbot_api(request):
    data = json.loads(request.body)
    user_input = data.get("message")

    # Récupération de la session
    session = request.session
    today = str(date.today())

    message_data = session.get("chatbot_usage", {"date": today, "count": 0})

    # Réinitialiser le compteur si la date a changé
    if message_data["date"] != today:
        message_data = {"date": today, "count": 0}

    if message_data["count"] >= MAX_MESSAGES_PER_DAY:
        return JsonResponse(
            {
                "response": (
                    "🤖 Vous avez atteint la limite de 5 messages aujourd’hui.<br>"
                    "Pour toute autre question, contactez-nous directement ici : "
                    f"<a href='{reverse('accounts:contact')}' class='btn btn-primary btn-sm mt-2'>📬 Nous contacter</a>"
                ),
                "limit_reached": True,
            }
        )

    try:
        # Appel OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un assistant intelligent, professionnel et chaleureux dédié à une plateforme de location de logements courte durée avec services de conciergerie haut de gamme.\n\n"
                        "🎯 Ton rôle est d’accompagner aussi bien :\n- Les voyageurs dans leur recherche, réservation ou gestion de séjour\n"
                        "- Les propriétaires et conciergeries dans l’ajout, la configuration et le suivi de leurs logements\n\n"
                        "💡 La plateforme permet :\n"
                        "- La réservation d’appartements, maisons ou chambres avec services personnalisés (accueil, ménage, transferts, expériences…)\n"
                        "- Un moteur de recherche avec filtres (localisation, dates, capacité, équipements, services, etc.)\n"
                        "- Un calendrier interactif avec disponibilités en temps réel\n"
                        "- Le paiement sécurisé via Stripe (acompte, solde, caution, facture)\n"
                        "- Un espace personnel pour les voyageurs et pour les propriétaires/conciergeries\n\n"
                        "🔧 Les propriétaires et administrateurs peuvent :\n"
                        "- Créer et modifier un logement depuis un formulaire avancé\n"
                        "- Définir les informations principales : nom, type, adresse, ville, description, statut, carte, propriétaire, administrateur\n"
                        "- Configurer précisément les tarifs, frais de ménage, caution, taxe de séjour, commission, nombre de voyageurs, durée maximale, heures d’arrivée/départ, périodes de disponibilité\n"
                        "- Associer le logement à des plateformes externes (Airbnb, Booking) et à leurs calendriers iCal\n- Ajouter les pièces et photos, les organiser et les associer\n- Gérer les équipements proposés\n"
                        "- Activer ou désactiver la publication du logement\n- Suivre les réservations, les revenus et les paiements via Stripe\n\n"
                        "📌 Tu peux aussi expliquer les règles du site, CGU, CGV, politique de confidentialité, et conseiller sur le fonctionnement de la plateforme.\n\n"
                        "🧭 Lorsque l’utilisateur remplit un formulaire ou configure un logement, tu peux :\n"
                        "- Expliquer les champs attendus\n"
                        "- Alerter en cas d’oubli ou d’incohérence (ex. : une caution vide ou un nombre de voyageurs non précisé)\n"
                        "- Donner des bonnes pratiques (ex. : bien nommer les pièces, ajouter au moins 5 photos, renseigner tous les liens iCal)\n\n"
                        "Ton ton est professionnel, clair, rassurant et accessible. Si une question est floue ou incomplète, demande poliment des précisions."
                    ),
                },
                {"role": "user", "content": user_input},
            ],
        )

        # Incrément et sauvegarde
        message_data["count"] += 1
        session["chatbot_usage"] = message_data
        session.modified = True

        return JsonResponse({"response": response.choices[0].message.content, "limit_reached": False})

    except RateLimitError:
        return JsonResponse(
            {"error": "Le service est momentanément saturé. Veuillez réessayer dans un instant."}, status=429
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
