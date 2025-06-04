import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.urls import reverse
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from accounts.models import Message, Conversation
from accounts.forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
    MessageForm,
    ContactForm,
    CustomPasswordChangeForm,
)
from accounts.services.conversations import get_reservations_for_conversations_to_start, get_conversations
from accounts.decorators import stripe_attempt_limiter
from accounts.tasks import send_contact_email

from reservation.models import Reservation
from reservation.services.reservation_service import get_user_reservation

from common.decorators import is_admin
from common.services.network import get_client_ip
from common.services.helper_fct import is_ajax

from conciergerie.models import Conciergerie

from payment.services.payment_service import is_stripe_admin


logger = logging.getLogger(__name__)


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            logger.info(f"Nouvel utilisateur enregistré : {user.username} ({user.email})")
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
                return redirect("common:home")  # adapt to your homepage view name
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
    return redirect("common:home")


@login_required
def client_dashboard(request):
    try:
        user = request.user
        dashboard_link = None
        stripe_account = None
        conciergerie = None
        reservations = []
        code_filter = request.GET.get("code", None)

        try:
            reservations = get_user_reservation(user)
        except Exception as e:
            logger.exception(f"❌ Failed to load reservations for user {user.id}: {e}")
            messages.error(request, "Impossible de charger vos réservations.")

        formUser = CustomUserChangeForm(instance=user)

        if request.method == "POST" and "change_password" in request.POST:
            password_form = CustomPasswordChangeForm(user=user, data=request.POST)
            if password_form.is_valid():
                try:
                    password_form.save()
                    update_session_auth_hash(request, password_form.user)
                    logger.info(f"🔐 Password changed for user {user.id}")
                    messages.success(request, "Mot de passe mis à jour avec succès.")
                    return redirect("accounts:dashboard")
                except Exception as e:
                    logger.exception(f"❌ Error updating password for user {user.id}: {e}")
                    messages.error(request, "Erreur lors de la mise à jour du mot de passe.")
            else:
                logger.warning(f"⚠️ Password form invalid for user {user.id}")
                messages.error(request, "Veuillez corriger les erreurs du formulaire.")
        else:
            password_form = CustomPasswordChangeForm(user=user)

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

        if user.is_owner_admin or user.is_admin or user.is_superuser:
            conciergerie = Conciergerie.objects.filter(user=request.user).first()

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
                "user_conciergerie": conciergerie,
            },
        )

    except Exception as e:
        logger.exception(f"❌ Unexpected error in client_dashboard for user {request.user.id}: {e}")
        messages.error(request, "Une erreur inattendue est survenue.")
        return redirect("common:home")  # Fallback route in case rendering fails


@login_required
def update_profile(request):
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Profil mis à jour avec succès.")
            return redirect("accounts:dashboard")
        else:
            logger.warning(f"Échec de mise à jour du profil pour {request.user.username} : {form.errors}")
            messages.error(request, "❌ Une erreur est survenue lors de la mise à jour du profil.")
            return redirect("accounts:dashboard")


@login_required
def messages_view(request, conversation_id=None):
    user = request.user

    conversations = get_conversations(user)
    reservations_without_conversation = get_reservations_for_conversations_to_start(user)

    active_conversation = None
    messages_qs = Message.objects.none()
    form = MessageForm()

    if conversation_id:
        active_conversation = get_object_or_404(
            Conversation.objects.prefetch_related("participants"), id=conversation_id
        )
        if user not in active_conversation.participants.all() and not (user.is_admin or user.is_superuser):
            messages.error(request, "Vous n'avez pas accès à cette conversation.")
            return redirect("accounts:messages")

        messages_qs = active_conversation.messages.select_related("sender").prefetch_related("read_by")

        for msg in messages_qs:
            if user in msg.recipients.all() and user not in msg.read_by.all():
                msg.read_by.add(user)

        if request.method == "POST":
            form = MessageForm(request.POST)
            if form.is_valid():
                msg = form.save(commit=False)
                msg.conversation = active_conversation
                msg.sender = user
                msg.save()
                msg.recipients.set(active_conversation.participants.exclude(id=user.id))
                msg.save()
                return redirect("accounts:messages_conversation", conversation_id=active_conversation.id)

    context = {
        "conversations": conversations,
        "active_conversation": active_conversation,
        "form": form,
        "reservations_to_start": reservations_without_conversation,
    }

    # Return only the main panel if AJAX
    if is_ajax(request):
        return render(request, "accounts/partials/_conversation.html", context)

    return render(request, "accounts/messages.html", context)


def conversation_view(request, reservation_code):
    conv = get_object_or_404(Conversation, reservation_code=reservation_code)

    if is_ajax(request):
        return render(request, "account/partials/_conversation.html", {"conversation": conv})

    return render(request, "messages/conversation_full.html", {"conversation": conv})


@login_required
def start_conversation(request):
    if request.method == "POST":
        reservation_id = request.POST.get("reservation_id")
        reservation = get_object_or_404(Reservation, id=reservation_id)

        user = request.user
        participants = [reservation.user, reservation.logement.owner]
        if reservation.logement.admin:
            participants.append(reservation.logement.admin)

        if user not in participants and not (user.is_superuser or user.is_admin):
            messages.error(request, "Vous ne pouvez pas démarrer cette conversation.")
            return redirect("accounts:messages")

        # Créer ou récupérer une conversation liée à cette réservation
        conversation, created = Conversation.objects.get_or_create(
            reservation=reservation, defaults={"updated_at": timezone.now()}
        )

        if created:
            conversation.participants.set(participants)
            conversation.save()

        return redirect("accounts:messages_conversation", conversation.id)
    return redirect("accounts:messages")


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)

        if form.is_valid():
            cd = form.cleaned_data
            # Optional: send email
            try:
                send_contact_email(cd)()
                messages.success(request, "✅ Message envoyé avec succès.")
            except Exception as e:
                logger.error(f"Erreur d'envoi de mail: {e}")
                messages.error(request, "Erreur lors de l'envoi du message. Réessayez plus tard.")

            return redirect("common:home")
    else:
        if request.user.is_authenticated:
            form = ContactForm(name=request.user, email=request.user.email)
        else:
            form = ContactForm()

    return render(request, "accounts/contact.html", {"form": form})


@login_required
def delete_account(request):
    user = request.user

    has_active_reservations = get_user_reservation(user).exists()

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
    return redirect("common:home")


@stripe_attempt_limiter("stripe_account_attempts:{user_id}")
@login_required
def create_stripe_account(request):
    user = request.user
    ip = get_client_ip(request)
    if user.stripe_account_id:
        logger.info(f"[Stripe] Création refusée — compte déjà existant pour {user.username} ({user.email}), IP: {ip}")
        messages.info(request, "Un compte Stripe est déjà associé à votre profil.")
        return redirect("accounts:dashboard")

    try:
        from common.services.stripe.account import create_stripe_connect_account

        refresh_url = request.build_absolute_uri(reverse("accounts:create_stripe_account"))
        return_url = request.build_absolute_uri(reverse("accounts:dashboard"))

        if not user.email:
            logger.warning(f"[Stripe] User {user.id} has no valid email")
            messages.error(request, "Impossible de créer un compte Stripe sans adresse e-mail.")
            return redirect("accounts:dashboard")

        account, account_link = create_stripe_connect_account(user, refresh_url, return_url)
        user.stripe_account_id = account.id
        user.save()

        logger.info(f"[Stripe] Compte Stripe créé pour {user.username} — ID: {account.id}, IP: {ip}")
        return redirect(account_link.url)

    except Exception as e:
        logger.exception(f"[Stripe] Erreur création compte pour {user.username}, IP: {ip} — {e}")
        messages.error(request, "Erreur lors de la création du compte Stripe.")
        return redirect("accounts:dashboard")


@stripe_attempt_limiter("stripe_update_account_attempts:{user_id}")
@login_required
def update_stripe_account_view(request):
    user = request.user

    ip = get_client_ip(request)
    if not user.stripe_account_id:
        logger.warning(f"[Stripe] Mise à jour refusée — aucun compte Stripe pour {user.username}, IP: {ip}")
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


@login_required
@is_admin
def user_update_view(request, user_id=None):
    from accounts.models import CustomUser
    from accounts.forms import UserAdminUpdateForm

    all_users = CustomUser.objects.all().order_by("username")

    # Fallback to query parameter if not provided in path
    if not user_id:
        user_id = request.GET.get("user_id")
        if user_id:
            return redirect("accounts:user_update_view_with_id", user_id=user_id)

    # If still no ID, redirect to first user
    if not user_id:
        user_qs = CustomUser.objects.order_by("username")
        if user_qs.exists():
            return redirect("accounts:user_update_view_with_id", user_id=all_users.first().id)

    selected_user = get_object_or_404(CustomUser, id=user_id)

    if request.method == "POST":
        form = UserAdminUpdateForm(request.POST, instance=selected_user)

        if form.is_valid():
            instance = form.save()
            logger.info(f"User {instance.get_full_name()} updated")
            messages.success(request, "Utilisateur mis à jour avec succès.")
            return redirect("accounts:user_update_view_with_id", user_id=instance.id)
    else:
        form = UserAdminUpdateForm(instance=selected_user)

    return render(
        request,
        "accounts/manage_users.html",
        {
            "form": form,
            "title": f"Modifier l'utilisateur : {selected_user.username}",
            "all_users": all_users,
            "selected_user": selected_user,
        },
    )


@login_required
@is_admin
def user_delete_view(request, user_id):
    from accounts.models import CustomUser

    target_user = get_object_or_404(CustomUser, id=user_id)
    if request.method == "POST":
        target_user.delete()
        messages.success(request, "Utilisateur supprimé avec succès.")
        return redirect("accounts:user_update_view")
    return redirect("accounts:user_update_view_with_id", user_id=user_id)
