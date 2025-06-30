import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from partner.forms import PartnerForm
from partner.models import Partners
from partner.decorators import user_is_partner
from partner.services.partner import get_partner_system_messages
from logement.models import City

from common.decorators import is_admin
from common.services.email_service import (
    send_partner_validation_email,
    send_admin_partner_validation_email_notification,
)

from activity.services.activity import get_activities_overview

logger = logging.getLogger(__name__)


@login_required
@user_is_partner
def dashboard(request):
    """
    Tableau de bord partenaire :
    - Accessible uniquement si l'utilisateur est partenaire, admin ou superuser.
    - Sinon, redirige avec un message d'info.
    """
    try:
        user = request.user
        partner = Partners.objects.filter(user=user).first()
        if not partner:
            messages.info(request, "Vous n'avez pas encore de compte partenaire. Veuillez en créer un.")
            return redirect("partner:create_partner")

        # Onboarding message la première fois
        if not partner.onboarded:
            show_onboarding = True
            partner.onboarded = True
            partner.save()
        else:
            show_onboarding = False

        activity_stats = get_activities_overview(user)

        messages_systems = get_partner_system_messages(user)

        context = {
            "total_revenue": activity_stats["total_revenue"],
            "futur_reservations": activity_stats["futur_reservations"],
            "futur_reservations_count": activity_stats["futur_reservations_count"],
            "failed_reservations": activity_stats["total_failed_reservations"],
            "history": activity_stats["history"],
            "show_onboarding": show_onboarding,
            "messages_systems": messages_systems,
        }

        return render(request, "partner/dashboard.html", context)
    except Partners.DoesNotExist:
        messages.error(request, "Vous n'avez pas encore de compte partenaire. Veuillez en créer un.")
        return redirect("partner:create_partner")
    except Exception as e:
        logger.error(f"Erreur lors de l'accès au tableau de bord partenaire : {e}")
        messages.error(request, "Une erreur est survenue lors du chargement du tableau de bord.")
        raise


@login_required
@user_is_partner
def create_partner(request):
    if request.method == "POST":
        form = PartnerForm(request.POST, request.FILES)
        if form.is_valid():
            partner = form.save(commit=False)
            partner.user = request.user  # ← assignation ici
            partner.save()
            send_admin_partner_validation_email_notification(partner)
            messages.success(
                request,
                "Votre compte partenaire est en attente de validation. Vous recevrez un email de confirmation une fois validé par notre équipe !",
            )
            return redirect("accounts:dashboard")  # ou autre URL
        else:
            messages.error(request, "Merci de corriger les erreurs dans le formulaire.")
    else:
        form = PartnerForm()

    return render(request, "partner/create_partner.html", {"form": form, "is_edit": False})


@login_required
@user_is_partner
def update_partner(request, pk=None):
    try:
        if pk:
            partner = Partners.objects.get(id=pk)
        else:
            partner = Partners.objects.get(user=request.user)

        if not (request.user.is_superuser or request.user.is_admin) and partner.user != request.user:
            messages.error(request, "Accès non autorisé à ce partenaire.")
            return redirect("accounts:dashboard")

    except Partners.DoesNotExist:
        messages.error(request, "Vous n'avez pas encore de compte partenaire à modifier.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = PartnerForm(request.POST, request.FILES, instance=partner)
        if form.is_valid():
            form.save()
            messages.success(request, "Compte mis à jour avec succès.")
            if request.user.is_admin or request.user.is_superuser:
                return redirect("partner:list_partners")
            else:
                return redirect("accounts:dashboard")  # ou un dashboard
        else:
            messages.error(request, "Merci de corriger les erreurs dans le formulaire.")
    else:
        form = PartnerForm(instance=partner)

    return render(request, "partner/create_partner.html", {"form": form, "is_edit": True})


@login_required
@is_admin
def list_partners(request):
    partners = Partners.objects.all()
    villes = City.objects.all()

    # Filtres
    ville_id = request.GET.get("ville")
    validated = request.GET.get("validated")

    if ville_id:
        partners = partners.filter(ville_id=ville_id)
    if validated:
        partners = partners.filter(validated=True)

    # Pagination
    paginator = Paginator(partners, 20)  # 20 partenaires par page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "partner/list_partners.html",
        {
            "partners": page_obj,
            "villes": villes,
            "page_obj": page_obj,
        },
    )


def partner_list_customer(request):
    ville_id = request.GET.get("ville")
    partners = Partners.objects.filter(actif=True, validated=True)
    if ville_id:
        partners = partners.filter(ville_id=ville_id)
    partners = partners.order_by("name")

    # Pagination (9 par page)
    paginator = Paginator(partners, 9)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Liste des villes ayant au moins un partenaire
    villes = City.objects.filter(activity_partners__isnull=False).distinct()

    context = {
        "partners": page_obj.object_list,
        "page_obj": page_obj,
        "villes": villes,
    }
    return render(request, "partner/partner_list_customer.html", context)


@login_required
@is_admin
def partner_detail(request, pk):
    partner = get_object_or_404(Partners, pk=pk)
    return render(request, "partner/partner_detail.html", {"partner": partner})


def partner_customer_detail(request, pk):
    partner = get_object_or_404(Partners, pk=pk)
    return render(request, "partner/partner_customer_card.html", {"partner": partner})


@is_admin
def bulk_action(request):
    if request.method == "POST":
        ids = request.POST.getlist("selected_ids")
        action = request.POST.get("action")

        if not ids:
            messages.warning(request, "Aucun partenaire sélectionné.")
            return redirect("partner:list_partners")

        queryset = Partners.objects.filter(id__in=ids)

        if action == "delete":
            count = queryset.count()
            queryset.delete()
            messages.success(request, f"{count} partenaire(s) supprimé(s).")

        elif action == "validate":
            for partner in queryset:
                partner.validated = True
                partner.save()
                send_partner_validation_email(partner)
            messages.success(request, f"{queryset.count()} partenaire(s) validé(s) avec notification.")

        else:
            messages.error(request, "Action non reconnue.")

    return redirect("partner:list_partners")
