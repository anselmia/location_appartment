# -*- coding: utf-8 -*-
"""Views for handling payments, refunds, and Stripe interactions.
This module provides views for processing payments, handling webhooks, and managing payment-related tasks.
"""

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

from activity.models import Activity
from reservation.models import Reservation, ActivityReservation
from reservation.decorators import user_is_reservation_admin, user_has_reservation
from reservation.services.reservation_service import get_reservation_by_code

from logement.models import Logement

from common.services.stripe.stripe_webhook import handle_stripe_webhook_request
from common.decorators import is_admin
from common.services.network import get_client_ip

from payment.decorators import is_stripe_admin
from payment.services.payment_service import (
    refund_payment,
    send_stripe_payment_link,
    charge_deposit,
    transfer_funds,
    get_session,
    verify_payment,
    get_reservation_type,
    verify_transfer,
)
from payment.models import PaymentTask

logger = logging.getLogger(__name__)


@login_required
@user_has_reservation
def payment_success(request, type, code):
    try:
        session_id = request.GET.get("session_id")
        if not session_id:
            messages.error(request, "Session ID manquant.")
            if type == "activity":
                return redirect("reservation:book_activity", pk=1)
            else:
                return redirect("reservation:book_logement", pk=1)

        session = get_session(session_id)
        if not session:
            messages.error(request, "Session invalide.")
            if type == "activity":
                return redirect("reservation:book_activity", pk=1)
            else:
                return redirect("reservation:book_logement", pk=1)

        payment_intent_id = session.payment_intent

        if type == "logement":
            reservation = Reservation.objects.get(code=code)
            reservation.statut = "confirmee"
        elif type == "activity":
            reservation = ActivityReservation.objects.get(code=code)
        else:
            messages.error(request, "Type de réservation inconnu.")
            return redirect("common:home")

        reservation.stripe_payment_intent_id = payment_intent_id
        reservation.save(update_fields=["statut", "stripe_payment_intent_id"])

        if type == "logement":
            return render(request, "payment/payment_logement_success.html", {"reservation": reservation})
        elif type == "activity":
            return render(request, "payment/payment_activity_success.html", {"reservation": reservation})

    except Reservation.DoesNotExist:
        messages.error(request, f"Réservation {code} introuvable.")
        return redirect("reservation:book_logement", pk=1)
    except ActivityReservation.DoesNotExist:
        messages.error(request, f"Réservation activité {code} introuvable.")
        return redirect("reservation:book_activity", pk=1)
    except Exception as e:
        logger.exception(f"Error handling payment success: {e}")
        messages.error(request, "Erreur lors du traitement du paiement.")
        if type == "activity":
            return redirect("reservation:book_activity", pk=1)
        else:
            return redirect("reservation:book_logement", pk=1)


@login_required
@user_has_reservation
def payment_cancel(request, type, code):
    try:
        messages.info(
            request,
            "Votre paiement a été annulé. Vous pouvez modifier ou reprogrammer votre réservation.",
        )
        if type == "logement":
            reservation = get_object_or_404(Reservation, code=code)
            logement = get_object_or_404(Logement, id=reservation.logement.id)

            query_params = urlencode(
                {
                    "start": reservation.start.isoformat(),
                    "end": reservation.end.isoformat(),
                    "adults": reservation.guest_adult,
                    "minors": reservation.guest_minor,
                    "code": reservation.code,
                }
            )

            # Delete the reservation
            reservation.delete()

            return redirect(f"{reverse('reservation:book_logement', args=[logement.id])}?{query_params}")
        elif type == "activity":
            reservation = get_object_or_404(ActivityReservation, code=code)
            activity = get_object_or_404(Activity, id=reservation.activity.id)

            query_params = urlencode(
                {
                    "start": reservation.start.isoformat(),
                    "guest": reservation.participants,
                    "code": reservation.code,
                }
            )

            # Delete the reservation
            reservation.delete()

            return redirect(f"{reverse('reservation:book_activity', args=[activity.id])}?{query_params}")

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
        reservation = get_reservation_by_code(code)
        reservation_type = get_reservation_type(reservation)
        send_stripe_payment_link(reservation, request)  # Your helper function
        messages.success(request, f"Lien de paiement envoyé à {reservation.user.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send payment link for {code}: {e}")
        messages.error(request, "Erreur lors de l'envoi du lien.")

    if reservation_type == "activity":
        return redirect("reservation:activity_reservation_detail", code=code)
    else:
        return redirect("reservation:_logement_reservation_detail", code=code)


@login_required
@is_admin
def transfer_reservation_payment(request, code):
    reservation = get_reservation_by_code(code)
    reservation_type = get_reservation_type(reservation)
    try:
        transfer_funds(reservation)

        messages.success(request, f"Transfert effectué pour {reservation.code}.")
    except Exception as e:
        messages.error(request, f"Erreur lors du transfert : {str(e)}")
        logger.exception(f"❌ Failed to transfer funds for {code}: {e}")
    if reservation_type == "activity":
        return redirect("reservation:manage_activity_reservations")
    else:
        return redirect("reservation:manage_logement_reservations")


def payment_task_list(request):
    tasks = PaymentTask.objects.select_related().order_by("-updated_at")

    # Filter logic
    task_type = request.GET.get("type")
    status = request.GET.get("status")
    code = request.GET.get("code")

    if task_type:
        tasks = tasks.filter(type=task_type)
    if status:
        tasks = tasks.filter(status=status)
    if code:
        tasks = tasks.filter(
            object_id__in=[r.id for r in Reservation.objects.filter(code__icontains=code)]
            + [ar.id for ar in ActivityReservation.objects.filter(code__icontains=code)]
        )

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
    reservation = get_reservation_by_code(code)
    reservation_type = get_reservation_type(reservation)

    key = f"refund_attempts_{code}:{user.id}"
    attempts = cache.get(key, 0)

    if attempts >= 5:
        ip = get_client_ip(request)
        logger.warning(f"[Stripe] Trop de tentatives de remboursement | user={user.username} | ip={ip}")
        messages.error(request, "Trop de tentatives de remboursement. Réessayez plus tard.")
        if reservation_type == "activity":
            return redirect("reservation:activity_reservation_dashboard")
        elif reservation_type == "logement":
            return redirect("reservation:logement_reservation_dashboard")

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

    if reservation_type == "activity":
        return redirect("reservation:activity_reservation_detail", code=code)
    else:
        return redirect("reservation:logement_reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def refund_partially_reservation(request, code):
    reservation = get_reservation_by_code(code)
    reservation_type = get_reservation_type(reservation)
    if reservation.refunded:
        messages.warning(request, "Cette réservation a déjà été remboursée.")
        if reservation_type == "activity":
            return redirect("reservation:activity_reservation_detail", code=code)
        else:
            return redirect("reservation:logement_reservation_detail", code=code)

    try:
        amount_str = request.POST.get("refund_amount")
        refund_amount = Decimal(amount_str)

        if refund_amount <= 0 or refund_amount > reservation.price:
            messages.error(
                request,
                "Montant invalide. Il doit être supérieur à 0 et inférieur ou égal au montant total.",
            )
            if reservation_type == "activity":
                return redirect("reservation:activity_reservation_detail", code=code)
            else:
                return redirect("reservation:logement_reservation_detail", code=code)

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

    if reservation_type == "activity":
        return redirect("reservation:activity_reservation_detail", code=code)
    else:
        return redirect("reservation:logement_reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def charge_deposit_view(request, code):
    reservation = get_object_or_404(Reservation, code=code)

    try:
        amount = Decimal(request.POST.get("deposit_amount"))

        if amount <= 0:
            messages.error(request, "Le montant doit être supérieur à 0.")
            return redirect("reservation:logement_reservation_detail", code=code)

        logement_caution = getattr(reservation.logement, "caution", None)
        if logement_caution is not None and amount > reservation.chargeable_deposit:
            messages.error(
                request,
                f"Le montant de la caution ({amount:.2f} €) dépasse la limite autorisée pour ce logement ({logement_caution:.2f} €).",
            )
            return redirect("reservation:logement_reservation_detail", code=code)

        amount_in_cents = int(amount * 100)

        charge_result = charge_deposit(
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

    return redirect("reservation:logement_reservation_detail", code=code)


@login_required
@user_is_reservation_admin
@require_POST
def verify_payment_view(request, code):
    """
    View to verify the Stripe PaymentIntent status for a reservation (logement or activity).
    """

    reservation = get_reservation_by_code(code)
    if not reservation:
        messages.error(request, "Réservation introuvable.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    paid, message = verify_payment(reservation)

    if paid:
        messages.success(request, message)
    else:
        messages.warning(request, message)

    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
@user_is_reservation_admin
@require_POST
def verify_transfer_view(request, code):
    """
    View to verify the Stripe Transfer status for a reservation (logement or activity).
    """
    reservation = get_reservation_by_code(code)
    if not reservation:
        messages.error(request, "Réservation introuvable.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    success, message = verify_transfer(reservation)

    if success:
        messages.success(request, message)
    else:
        messages.warning(request, message)

    return redirect(request.META.get("HTTP_REFERER", "/"))
