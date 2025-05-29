import logging
import json
import openai
from openai import OpenAI, RateLimitError

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render
from django.http import JsonResponse

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


@csrf_exempt
@require_POST
def chatbot_api(request):
    data = json.loads(request.body)
    user_input = data.get("message")

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un assistant intelligent, professionnel et chaleureux dédié à un site de location de logements courte durée avec services de conciergerie haut de gamme. "
                        "Le site permet aux visiteurs de réserver des appartements, maisons ou chambres avec des services inclus, comme l’accueil personnalisé, le ménage, les transferts ou des expériences locales sur mesure, lorsque le bien est géré par une conciergerie.\n\n"
                        "La plateforme s'adresse aussi bien aux voyageurs qu'aux propriétaires et conciergeries souhaitant mettre leurs biens en location.\n\n"
                        "Les utilisateurs peuvent :\n"
                        "- Rechercher un logement selon des critères précis (lieu, dates, nombre de voyageurs, services, prix, équipements, etc.)\n"
                        "- Les Réservations sont instantanées\n"
                        "- Consulter les disponibilités en temps réel et réserver en ligne de manière sécurisée via Stripe (paiement, acompte, caution, facture)\n"
                        "- Créer et gérer leur compte (profil, historique de réservations, messages, paiements...)\n"
                        "- Accéder à des services personnalisés : transferts, ménage, paniers d’accueil, expériences exclusives\n\n"
                        "Les propriétaires ou conciergeries peuvent :\n"
                        "- Ajouter et gérer leurs biens via un espace dédié\n"
                        "- Configurer précisément les prix, le calendrier, les conditions d’annulation, les frais, les promotions et les règles du logement\n"
                        "- Suivre les paiements, cautions, remboursements et revenus par logement\n"
                        "- transfert des fonds automatiques sur leur compte\n"
                        "- Le service client doit être assuré par la concergerie ou le propriétaire mais nous gérons les problèmes côtés plateforme sur demande\n"
                        "- Déléguer ou gérer eux-mêmes certains aspects (photos, services, relation client...)\n\n"
                        "Tu es chargé de répondre clairement et efficacement à toute question liée au fonctionnement du site, aux réservations, à la gestion des comptes, aux paiements ou aux services proposés. "
                        "Si une question est floue ou manque d'informations, demande poliment des précisions. Utilise un ton professionnel, rassurant et accessible."
                    ),
                },
                {"role": "user", "content": user_input},
            ],
        )
        answer = response.choices[0].message.content
        return JsonResponse({"response": answer})

    except RateLimitError:
        return JsonResponse(
            {"error": "Le service est momentanément saturé. Veuillez réessayer dans un instant."}, status=429
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
