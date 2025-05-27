from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
    MessageForm,
    ContactForm,
    CustomPasswordChangeForm,
)
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from logement.models import Reservation
from django.db.models import Q
from .models import Message, CustomUser
from django.core.mail import send_mail
from django.contrib.auth import update_session_auth_hash
from common.decorators import user_has_logement
from common.views import is_stripe_admin
from django.urls import reverse
from django.core.cache import cache
from django_ratelimit.decorators import ratelimit


import logging

logger = logging.getLogger(__name__)


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            logger.info(
                f"Nouvel utilisateur enregistré : {user.username} ({user.email})"
            )
            messages.success(
                request,
                "Votre compte a été créé. Vous pouvez maintenant vous connecter.",
            )
            return redirect("accounts:login")
    else:
        form = CustomUserCreationForm()
    return render(request, "accounts/register.html", {"form": form})


@ratelimit(key="ip", rate="5/m", block=True)
def user_login(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                logger.info(f"Connexion réussie pour {username}")
                messages.success(request, f"Bienvenue {username}!")
                return redirect("logement:home")  # adapt to your homepage view name
            else:
                logger.warning(f"Échec de connexion pour {username}")
        messages.error(request, "Nom d'utilisateur ou mot de passe invalide.")
    else:
        form = AuthenticationForm()
    return render(request, "accounts/login.html", {"form": form})


@login_required
def user_logout(request):
    logout(request)
    messages.info(request, "Vous avez été déconnecté.")
    return redirect("logement:home")


@login_required
def client_dashboard(request):
    user = request.user
    logger.info(f"🔐 Accessing client dashboard for user {user.id} ({user.email})")

    dashboard_link = None
    stripe_account = None
    reservations = []
    code_filter = request.GET.get("code", None)

    try:
        reservations = Reservation.objects.filter(
            user=user, statut__in=["confirmee", "annulee", "terminee"]
        ).order_by("-start")
    except Exception as e:
        logger.exception(f"❌ Failed to load reservations for user {user.id}: {e}")
        messages.error(request, "Impossible de charger vos réservations.")

    # User forms
    formUser = CustomUserChangeForm(instance=user)
    password_form = CustomPasswordChangeForm(user=user, data=request.POST or None)

    # Handle password change securely
    if request.method == "POST" and "change_password" in request.POST:
        if password_form.is_valid():
            try:
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                logger.info(f"🔐 Password changed for user {user.id}")
                messages.success(request, "Mot de passe mis à jour avec succès.")
                return redirect("accounts:dashboard")
            except Exception as e:
                logger.exception(f"❌ Error updating password for user {user.id}: {e}")
                messages.error(
                    request, "Erreur lors de la mise à jour du mot de passe."
                )
        else:
            logger.warning(f"⚠️ Password form invalid for user {user.id}")
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")

    # Stripe integration (only if admin + has account)
    user_is_stripe_admin = is_stripe_admin(user)

    if user_is_stripe_admin and user.stripe_account_id:
        try:
            from common.services.stripe.account import (
                get_stripe_account_info,
                get_stripe_dashboard_link,
            )

            stripe_account = get_stripe_account_info(user)
            if stripe_account:
                dashboard_link = get_stripe_dashboard_link(user)
                logger.info(f"💳 Stripe account loaded for user {user.id}")
            else:
                logger.warning(f"⚠️ No Stripe account data returned for user {user.id}")

        except Exception as e:
            logger.exception(f"❌ Stripe integration failed for user {user.id}: {e}")
            messages.error(
                request,
                "Une erreur est survenue lors du chargement de vos données Stripe.",
            )

    return render(
        request,
        "accounts/dashboard.html",
        {
            "user": user,
            "reservations": reservations,
            "formUser": formUser,
            "password_form": password_form,
            "stripe_account": stripe_account,
            "is_stripe_admin": user_is_stripe_admin,
            "dashboard_link": dashboard_link,
            "code_filter": code_filter,
        },
    )


@login_required
def update_profile(request):
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Profil mis à jour avec succès.")
            return redirect("accounts:dashboard")
        else:
            logger.warning(
                f"Échec de mise à jour du profil pour {request.user.username} : {form.errors}"
            )
            messages.error(
                request, "❌ Une erreur est survenue lors de la mise à jour du profil."
            )
            return redirect("accounts:dashboard")


@login_required
def messages_view(request):
    admin_user = CustomUser.objects.filter(is_admin=True).first()
    if not admin_user:
        messages.error(
            request, "Aucun administrateur n'est défini pour recevoir les messages."
        )
        logger.error("Aucun administrateur trouvé pour gérer les messages.")
        return redirect("logement:home")
    user = request.user

    # Get all messages exchanged with admin
    messages_qs = Message.objects.filter(
        (Q(sender=user) & Q(recipient=admin_user))
        | (Q(sender=admin_user) & Q(recipient=user))
    ).order_by("timestamp")

    form = MessageForm()
    if request.method == "POST":
        form = MessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.sender = user
            message.recipient = admin_user
            message.save()
            return redirect("accounts:messages")

    return render(
        request,
        "accounts/messages.html",
        {
            "messages": messages_qs,
            "form": form,
        },
    )


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)

        if form.is_valid():
            admin = CustomUser.objects.filter(is_admin=True).first()
            cd = form.cleaned_data
            # Optional: send email
            try:
                send_mail(
                    subject=cd["subject"],
                    message=f"Message de {cd['name']} ({cd['email']}):\n\n{cd['message']}",
                    from_email=cd["email"],
                    recipient_list=[admin.email],  # define this in settings
                    fail_silently=False,
                )
                logger.info(f"Message de contact reçu de {cd['name']} ({cd['email']})")
                messages.success(request, "✅ Message envoyé avec succès.")
            except Exception as e:
                logger.error(f"Erreur d'envoi de mail: {e}")
                messages.error(
                    request, "Erreur lors de l'envoi du message. Réessayez plus tard."
                )

            return redirect("logement:home")
    else:
        if request.user.is_authenticated:
            form = ContactForm(name=request.user, email=request.user.email)
        else:
            form = ContactForm()

    return render(request, "accounts/contact.html", {"form": form})


@login_required
def delete_account(request):
    user = request.user

    # Check for ongoing or upcoming reservations
    today = timezone.now().date()
    has_active_reservations = Reservation.objects.filter(
        user=user, statut="confirmee", end__gte=today
    ).exists()

    if has_active_reservations:
        messages.error(
            request,
            "❌ Vous ne pouvez pas supprimer votre compte avec une réservation en cours ou à venir.",
        )
        return redirect("accounts:dashboard")

    # Log out the user before deleting
    logout(request)
    # If allowed, delete user
    user.delete()
    messages.success(request, "✅ Votre compte a été supprimé avec succès.")
    return redirect("logement:home")


@login_required
def create_stripe_account(request):
    user = request.user
    from common.services.network import get_client_ip

    ip = get_client_ip(request)

    key = f"stripe_account_attempts:{user.id}"
    attempts = cache.get(key, 0)

    if attempts >= 3:
        logger.warning(
            f"[Stripe] Limite atteinte pour création Stripe | user={user.username} | ip={ip}"
        )
        messages.error(request, "Trop de tentatives. Réessayez plus tard.")
        return redirect("accounts:dashboard")

    cache.set(key, attempts + 1, timeout=60 * 60)  # 1h

    if user.stripe_account_id:
        logger.info(
            f"[Stripe] Création refusée — compte déjà existant pour {user.username} ({user.email}), IP: {ip}"
        )
        messages.info(request, "Un compte Stripe est déjà associé à votre profil.")
        return redirect("accounts:dashboard")

    try:
        from common.services.stripe.account import create_stripe_connect_account

        refresh_url = request.build_absolute_uri(
            reverse("accounts:create_stripe_account")
        )
        return_url = request.build_absolute_uri(reverse("accounts:dashboard"))

        account, account_link = create_stripe_connect_account(
            user, refresh_url, return_url
        )
        user.stripe_account_id = account.id
        user.save()

        logger.info(
            f"[Stripe] Compte Stripe créé pour {user.username} — ID: {account.id}, IP: {ip}"
        )
        return redirect(account_link.url)

    except Exception as e:
        logger.exception(
            f"[Stripe] Erreur création compte pour {user.username}, IP: {ip} — {e}"
        )
        messages.error(request, "Erreur lors de la création du compte Stripe.")
        return redirect("accounts:dashboard")


@login_required
def update_stripe_account_view(request):
    user = request.user
    from common.services.network import get_client_ip

    ip = get_client_ip(request)

    key = f"stripe_update_account_attempts:{user.id}"
    attempts = cache.get(key, 0)

    if attempts >= 3:
        logger.warning(
            f"[Stripe] Limite atteinte pour mse à jour du compte Stripe | user={user.username} | ip={ip}"
        )
        messages.error(request, "Trop de tentatives. Réessayez plus tard.")
        return redirect("accounts:dashboard")

    cache.set(key, attempts + 1, timeout=60 * 60)  # 1h

    if not user.stripe_account_id:
        logger.warning(
            f"[Stripe] Mise à jour refusée — aucun compte Stripe pour {user.username}, IP: {ip}"
        )
        messages.error(request, "Aucun compte Stripe n'est associé à votre profil.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        try:
            from common.services.stripe.account import update_stripe_account

            update_data = {
                "business_type": "individual",
                "email": user.email,
                "individual": {
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            }

            account = update_stripe_account(user.stripe_account_id, update_data)

            logger.info(
                f"[Stripe] Compte Stripe mis à jour pour {user.username} — ID: {user.stripe_account_id}, IP: {ip}"
            )
            messages.success(request, "Compte Stripe mis à jour.")
            return redirect("accounts:dashboard")

        except Exception as e:
            logger.exception(
                f"[Stripe] Erreur mise à jour pour {user.username}, ID: {user.stripe_account_id}, IP: {ip} — {e}"
            )
            messages.error(request, "Erreur lors de la mise à jour du compte Stripe.")
            return redirect("accounts:dashboard")

    return redirect("accounts:dashboard")
