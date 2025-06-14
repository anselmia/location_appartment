from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from conciergerie.models import Conciergerie, ConciergerieRequest
from conciergerie.forms import ConciergerieForm
from conciergerie.tasks import send_conciergerie_validation_email
from conciergerie.decorators import user_is_owner_admin

from logement.models import City

from common.decorators import is_admin
from common.services.email_service import (
    send_mail_conciergerie_request_accepted,
    send_mail_conciergerie_request_refused,
)


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

        if not (request.user.is_superuser or request.user.is_admin) and conciergerie.user != request.user:
            messages.error(request, "Accès non autorisé à cette conciergerie.")
            return redirect("accounts:dashboard")

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

    # Pagination
    paginator = Paginator(conciergeries, 20)  # 10 conciergeries par page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "conciergerie/list_conciergeries.html",
        {
            "conciergeries": page_obj,
            "villes": villes,
            "page_obj": page_obj,
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
            for conciergerie in queryset:
                conciergerie.validated = True
                conciergerie.save()
                send_conciergerie_validation_email(conciergerie.id)()
            messages.success(request, f"{queryset.count()} conciergerie(s) validée(s) avec notification.")

        else:
            messages.error(request, "Action non reconnue.")

    return redirect("conciergerie:list_conciergeries")


@is_admin
def conciergerie_detail(request, pk):
    conciergerie = get_object_or_404(Conciergerie, pk=pk)
    return render(request, "conciergerie/detail.html", {"conciergerie": conciergerie})


def customer_conciergerie_list(request):
    conciergeries = Conciergerie.objects.filter(actif=True, validated=True)
    villes = City.objects.all()

    # Optional filtering
    ville_id = request.GET.get("ville")
    if ville_id:
        conciergeries = conciergeries.filter(ville_id=ville_id)

    paginator = Paginator(conciergeries, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "conciergerie/conciergerie_list_customer.html",
        {
            "conciergeries": page_obj,
            "villes": villes,
            "page_obj": page_obj,
        },
    )


def customer_conciergerie_detail(request, pk):
    conciergerie = get_object_or_404(Conciergerie, pk=pk, actif=True, validated=True)
    return render(request, "conciergerie/conciergerie_presentation.html", {"conciergerie": conciergerie})


@login_required
@require_POST
def handle_conciergerie_request(request):
    request_id = request.POST.get("request_id")
    action = request.POST.get("action")
    user = request.user
    if not request_id or not action:
        return JsonResponse({"error": "Missing parameters"}, status=400)
    try:
        req = ConciergerieRequest.objects.get(id=request_id, conciergerie__user=user)
    except ConciergerieRequest.DoesNotExist:
        return JsonResponse({"error": "Demande non trouvée ou non autorisée."}, status=403)
    if req.status != "pending":
        return JsonResponse({"error": "Cette demande a déjà été traitée."}, status=400)
    if action == "accept":
        req.status = "accepted"
        req.logement.admin = user
        req.logement.save()
        req.save()
        # Send email to the logement owner using the new service and template
        if hasattr(req.logement, "owner") and req.logement.owner and hasattr(req.logement.owner, "email"):
            send_mail_conciergerie_request_accepted(req.logement.owner, req.conciergerie, req.logement)
        return JsonResponse({"success": True, "status": "accepted"})
    elif action == "refuse":
        req.status = "rejected"
        req.save()
        # Send email to the logement owner using the new service and template
        if hasattr(req.logement, "owner") and req.logement.owner and hasattr(req.logement.owner, "email"):
            send_mail_conciergerie_request_refused(req.logement.owner, req.conciergerie, req.logement)
        return JsonResponse({"success": True, "status": "rejected"})
    else:
        return JsonResponse({"error": "Action non reconnue."}, status=400)
