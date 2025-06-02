from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Conciergerie
from .forms import ConciergerieForm
from logement.models import City
from .decorators import user_is_owner_admin
from common.decorators import is_admin


@login_required
def create_conciergerie(request):
    if request.method == "POST":
        form = ConciergerieForm(request.POST, request.FILES)
        if form.is_valid():
            conciergerie = form.save(commit=False)
            conciergerie.user = request.user  # ← assignation ici
            conciergerie.save()
            messages.success(request, "Conciergerie créée avec succès.")
            return redirect("accounts:dashboard")  # ou autre URL
        else:
            messages.error(request, "Merci de corriger les erreurs dans le formulaire.")
    else:
        form = ConciergerieForm()

    return render(request, "conciergerie/create_conciergerie.html", {"form": form, "is_edit": False})


@user_is_owner_admin
@login_required
def update_conciergerie(request, pk=None):
    try:
        if pk:
            conciergerie = Conciergerie.objects.get(id=pk)
        else:
            conciergerie = Conciergerie.objects.get(user=request.user)
    except Conciergerie.DoesNotExist:
        messages.error(request, "Vous n'avez pas encore de conciergerie à modifier.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = ConciergerieForm(request.POST, request.FILES, instance=conciergerie)
        if form.is_valid():
            form.save()
            messages.success(request, "Conciergerie mise à jour avec succès.")
            if request.user.is_admin or request.user.is_superuser:
                return redirect("conciergerie:list_conciergeries")
            else:
                return redirect("accounts:dashboard")  # ou un dashboard
        else:
            messages.error(request, "Merci de corriger les erreurs dans le formulaire.")
    else:
        form = ConciergerieForm(instance=conciergerie)

    return render(request, "conciergerie/create_conciergerie.html", {"form": form, "is_edit": True})


@is_admin
def list_conciergeries(request):
    conciergeries = Conciergerie.objects.all()
    villes = City.objects.all()

    # Filtres
    ville_id = request.GET.get("ville")
    validated = request.GET.get("validated")

    if ville_id:
        conciergeries = conciergeries.filter(ville_id=ville_id)
    if validated:
        conciergeries = conciergeries.filter(validated=True)

    return render(
        request,
        "conciergerie/list_conciergeries.html",
        {
            "conciergeries": conciergeries,
            "villes": villes,
        },
    )


@is_admin
def bulk_action(request):
    if request.method == "POST":
        ids = request.POST.getlist("selected_ids")
        action = request.POST.get("action")

        if not ids:
            messages.warning(request, "Aucune conciergerie sélectionnée.")
            return redirect("conciergerie:list_conciergeries")

        queryset = Conciergerie.objects.filter(id__in=ids)

        if action == "delete":
            count = queryset.count()
            queryset.delete()
            messages.success(request, f"{count} conciergerie(s) supprimée(s).")

        elif action == "validate":
            updated = queryset.update(validated=True)
            messages.success(request, f"{updated} conciergerie(s) validée(s).")

        else:
            messages.error(request, "Action non reconnue.")

    return redirect("conciergerie:list_conciergeries")


@is_admin
def conciergerie_detail(request, pk):
    conciergerie = get_object_or_404(Conciergerie, pk=pk)
    return render(request, "conciergerie/detail.html", {"conciergerie": conciergerie})
