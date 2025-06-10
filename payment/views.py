import time
import logging

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.core.paginator import Paginator

from reservation.models import Reservation
from reservation.decorators import user_is_reservation_admin, user_has_reservation

from logement.models import Logement

from common.services.stripe.stripe_webhook import handle_stripe_webhook_request
from common.decorators import is_admin
from common.services.network import get_client_ip

from payment.decorators import is_stripe_admin
from payment.services.payment_service import (
    refund_payment,
    send_stripe_payment_link,
    charge_payment,
    charge_reservation,
)
from payment.models import PaymentTask

logger = logging.getLogger(__name__)


# Create your views here.
@login_required
@user_has_reservation
def payment_success(request, code):
    try:
        reservation = Reservation.objects.get(code=code)

        # Wait up to 3 seconds for the reservation to be confirmed
        max_wait = 3  # seconds
        interval = 0.5  # seconds
        waited = 0

        while reservation.statut != "confirmee" and waited < max_wait:
            time.sleep(interval)
            waited += interval
            reservation.refresh_from_db()

        if reservation.statut != "confirmee":
            messages.warning(
                request,
                "Votre paiement semble incomplet ou non encore confirmé. Veuillez vérifier plus tard ou contacter l’assistance.",
            )
        return render(request, "payment/payment_success.html", {"reservation": reservation})
    except Reservation.DoesNotExist:
        messages.error(request, f"Réservation {code} introuvable.")
        return redirect("reservation:book", logement_id=1)
    except Exception as e:
        logger.exception(f"Error handling payment success: {e}")


@login_required
@user_has_reservation
def payment_cancel(request, code):
    try:
        reservation = get_object_or_404(Reservation, code=code)
        logement = Logement.objects.prefetch_related("photos").first()
        messages.info(
            request,
            "Votre paiement a été annulé. Vous pouvez modifier ou reprogrammer votre réservation.",
        )
        query_params = urlencode(
            {
                "start": reservation.start.isoformat(),
                "end": reservation.end.isoformat(),
                "adults": reservation.guest_adult,
                "minors": reservation.guest_minor,
                "code": reservation.code,
            }
        )
        return redirect(f"{reverse('logement:book', args=[logement.id])}?{query_params}")
    except Exception as e:
        logger.exception(f"Error handling payment cancellation: {e}")
        messages.error(request, "Une erreur est survenue.")
        return redirect("common:home")


@csrf_exempt
def stripe_webhook(request):
    handle_stripe_webhook_request(request)
    return HttpResponse(status=200)


@require_POST
@login_required
@is_stripe_admin
def send_payment_link(request, code):
    try:
        reservation = Reservation.objects.get(code=code)
        send_stripe_payment_link(reservation, request)  # Your helper function
        messages.success(request, f"Lien de paiement envoyé à {reservation.user.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send payment link for {code}: {e}")
        messages.error(request, "Erreur lors de l'envoi du lien.")
    return redirect("reservation:reservation_detail", code=code)


@login_required
@is_admin
def transfer_reservation_payment(request, code):
    reservation = get_object_or_404(Reservation, code=code, transferred=False)

    try:
        charge_reservation(reservation)

        messages.success(request, f"Transfert effectué pour {reservation.code}.")
    except Exception as e:
        messages.error(request, f"Erreur lors du transfert : {str(e)}")

    return redirect("reservation:manage_reservations")


def payment_task_list(request):
    tasks = PaymentTask.objects.select_related("reservation", "reservation__logement").order_by("-updated_at")

    # Filter logic
    task_type = request.GET.get("type")
    status = request.GET.get("status")
    code = request.GET.get("code")

    if task_type:
        tasks = tasks.filter(type=task_type)
    if status:
        tasks = tasks.filter(status=status)
    if code:
        tasks = tasks.filter(reservation__code__icontains=code)

    # Pagination
    paginator = Paginator(tasks, 20)  # 20 tâches par page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "tasks": page_obj,
        "types": PaymentTask.TASK_TYPES,
        "page_obj": page_obj,
    }

    return render(request, "payment/payment_tasks.html", context)


@login_required
@user_is_reservation_admin
@require_POST
def refund_reservation(request, code):
    user = request.user
    reservation = get_object_or_404(Reservation, code=code)

    key = f"refund_attempts_{code}:{user.id}"
    attempts = cache.get(key, 0)

    if attempts >= 5:
        ip = get_client_ip(request)
        logger.warning(f"[Stripe] Trop de tentatives de remboursement | user={user.username} | ip={ip}")
        messages.error(request, "Trop de tentatives de remboursement. Réessayez plus tard.")
        return redirect("reservation:reservation_dashboard")

    cache.set(key, attempts + 1, timeout=60 * 10)  # 10 minutes

    if not reservation.refunded:
        try:
            amount_in_cents = int(reservation.refundable_amount * 100)

            refund = refund_payment(reservation, refund="full", amount_cents=amount_in_cents)

            messages.success(
                request,
                f"Une demande de remboursement de {reservation.refundable_amount:.2f} € a été effectuée avec succès.",
            )
        except Exception as e:
            messages.error(request, f"Erreur de remboursement Stripe : {e}")
            logger.exception("Stripe refund failed")
    else:
        messages.warning(request, "Cette réservation a déjà été remboursée.")

    return redirect("reservation:reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def refund_partially_reservation(request, code):
    reservation = get_object_or_404(Reservation, code=code)

    if reservation.refunded:
        messages.warning(request, "Cette réservation a déjà été remboursée.")
        return redirect("reservation:reservation_detail", code=code)

    try:
        amount_str = request.POST.get("refund_amount")
        refund_amount = Decimal(amount_str)

        if refund_amount <= 0 or refund_amount > reservation.price:
            messages.error(
                request,
                "Montant invalide. Il doit être supérieur à 0 et inférieur ou égal au montant total.",
            )
            return redirect("reservation:reservation_detail", code=code)

        amount_in_cents = int(refund_amount * 100)
        refund = refund_payment(reservation, refund="partial", amount_cents=amount_in_cents)

        messages.success(
            request,
            f"Remboursement partiel de {refund_amount:.2f} € effectué avec succès.",
        )

    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Montant de remboursement invalide.")
    except Exception as e:
        messages.error(request, f"Erreur de remboursement Stripe : {e}")
        logger.exception("Stripe refund failed")

    return redirect("reservation:reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def charge_deposit(request, code):
    reservation = get_object_or_404(Reservation, code=code)

    try:
        amount = Decimal(request.POST.get("deposit_amount"))

        if amount <= 0:
            messages.error(request, "Le montant doit être supérieur à 0.")
            return redirect("reservation:reservation_detail", code=code)

        logement_caution = getattr(reservation.logement, "caution", None)
        if logement_caution is not None and amount > reservation.chargeable_deposit:
            messages.error(
                request,
                f"Le montant de la caution ({amount:.2f} €) dépasse la limite autorisée pour ce logement ({logement_caution:.2f} €).",
            )
            return redirect("reservation:reservation_detail", code=code)

        amount_in_cents = int(amount * 100)

        charge_result = charge_payment(
            reservation.stripe_saved_payment_method_id,
            amount_in_cents,
            reservation.user.stripe_customer_id,
            reservation,
        )

        if charge_result:
            messages.success(request, f"Caution de {amount:.2f} € chargée avec succès.")
        else:
            messages.error(request, "Erreur lors du paiement de la caution.")

    except (InvalidOperation, ValueError, TypeError):
        messages.error(request, "Montant invalide.")
    except Exception as e:
        messages.error(request, f"Erreur lors du chargement Stripe : {e}")
        logger.exception("Stripe deposit charge failed")

    return redirect("reservation:reservation_detail", code=code)
