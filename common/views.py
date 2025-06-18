import logging
import json
from openai import OpenAI, RateLimitError, AuthenticationError, APIError, Timeout
from datetime import date

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import render
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages

from logement.models import Logement
from common.services.email_service import send_mail_contact
from administration.models import HomePageConfig
from accounts.forms import ContactForm


logger = logging.getLogger(__name__)
client = OpenAI(api_key=settings.OPENAI_KEY)


def is_admin(user):
    return user.is_authenticated and (getattr(user, "is_admin", False) or user.is_superuser)


def home(request):
    try:
        config = HomePageConfig.objects.prefetch_related("services", "testimonials", "commitments").first()
        logements = Logement.objects.prefetch_related("photos").filter(statut="open")

        if request.method == "POST":
            form = ContactForm(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                try:
                    send_mail_contact(cd)
                    messages.success(request, "✅ Message envoyé avec succès.")
                    return redirect("common:home")
                except Exception as e:
                    logger.error(f"Erreur d'envoi de mail: {e}")
                    messages.error(request, "❌ Une erreur est survenue lors de l'envoi du message.")
        else:
            initial_data = {
                "name": request.user.full_name or request.user.username if request.user.is_authenticated else "",
                "email": request.user.email if request.user.is_authenticated else "",
            }

            form = ContactForm(**initial_data)

        return render(
            request,
            "home.html",
            {
                "logements": logements,
                "config": config,
                "contact_form": form,
            },
        )
    except Exception as e:
        logger.exception(f"Error rendering homepage: {e}")
        raise


@require_GET
def cgu_view(request):
    return render(request, "common/cgu.html")


@require_GET
def confidentiality_view(request):
    return render(request, "common/confidentiality.html")


@require_GET
def cgv_view(request):
    return render(request, "common/cgv.html")


@require_GET
def join_owner(request):
    return render(request, "common/join_owner.html")


@require_GET
def join_user(request):
    return render(request, "common/join_user.html")


@require_GET
def custom_bad_request(request, exception):
    return render(request, "400.html", status=400)


@require_GET
def custom_permission_denied(request, exception):
    return render(request, "403.html", status=403)


@require_GET
def custom_page_not_found(request, exception):
    return render(request, "404.html", status=404)


@require_GET
def custom_server_error(request):
    return render(request, "500.html", status=500)


MAX_MESSAGES_PER_DAY = 5


@csrf_exempt
@require_POST
def chatbot_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Requête JSON invalide."}, status=400)

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
    except AuthenticationError:
        return JsonResponse({"error": "Clé API invalide."}, status=403)
    except Timeout:
        return JsonResponse({"error": "Temps d’attente dépassé. Réessayez."}, status=504)
    except APIError:
        logger.exception("OpenAI APIError")
        return JsonResponse({"error": "Erreur côté serveur IA"}, status=502)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def js_logger(request):
    logger = logging.getLogger("frontend")
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            level = data.get("level", "info").lower()
            message = data.get("message", "")
            meta = data.get("meta", {})

            # Format message with metadata
            formatted_msg = f"[JS] {message} | Meta: {meta}"

            if level == "debug":
                logger.debug(formatted_msg)
            elif level == "info":
                logger.info(formatted_msg)
            elif level == "warning":
                logger.warning(formatted_msg)
            elif level == "error":
                logger.error(formatted_msg)
            elif level == "critical":
                logger.critical(formatted_msg)
            else:
                logger.info(formatted_msg)

            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception(f"Failed to log JS message: {e}")
            return HttpResponseBadRequest("Invalid data")
    return JsonResponse({"error": "Méthode non autorisée"}, status=400)
