from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
    MessageForm,
    ContactForm,
)
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from logement.models import Reservation, Logement
from django.db.models import Q
from .models import Message, CustomUser
from django.core.mail import send_mail
from django.conf import settings


def is_admin(user):
    return user.is_authenticated and user.is_admin


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                "Votre compte a été créé. Vous pouvez maintenant vous connecter.",
            )
            return redirect("accounts:login")
    else:
        form = CustomUserCreationForm()
    return render(request, "accounts/register.html", {"form": form})


def user_login(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Bienvenue {username}!")
                return redirect("logement:home")  # adapt to your homepage view name
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
    today = timezone.now().date()
    reservations = Reservation.objects.filter(user=user).order_by("-start")
    logement = Logement.objects.prefetch_related("photos").first()
    formUser = CustomUserChangeForm(
        name=user.name, last_name=user.last_name, email=user.email, phone=user.phone
    )
    for r in reservations:
        cancel_limit = r.start - timedelta(days=r.logement.cancelation_period)
        r.can_cancel = today < cancel_limit
        r.ended = today > r.end
        r.ongoing = r.start <= today and r.end >= today
        r.coming = r.start > today
    return render(
        request,
        "accounts/dashboard.html",
        {
            "user": user,
            "reservations": reservations,
            "formUser": formUser,
            "logement": logement,
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
            print(form.errors)


@login_required
def messages_view(request):
    admin_user = CustomUser.objects.filter(is_admin=True).first()
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
            send_mail(
                subject=cd["subject"],
                message=f"Message de {cd['name']} ({cd['email']}):\n\n{cd['message']}",
                from_email=cd['email'],
                recipient_list=[admin.email],  # define this in settings
                fail_silently=False,
            )
            messages.success(request, "✅ Message envoyé avec succès.")
            return redirect("logement:home")
    else:
        if request.user.is_authenticated:
            form = ContactForm(name=request.user, email=request.user.email)
        else:
            form = ContactForm()

    return render(request, "accounts/contact.html", {"form": form})


def cgu_view(request):
    return render(request, 'accounts/cgu.html')
