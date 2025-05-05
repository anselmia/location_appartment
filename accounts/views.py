from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import CustomUserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm


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


def user_logout(request):
    logout(request)
    messages.info(request, "Vous avez été déconnecté.")
    return redirect("logement:home")
