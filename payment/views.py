# -*- coding: utf-8 -*-
"""Views for handling payments, refunds, and Stripe interactions.
This module provides views for processing payments, handling webhooks, and managing payment-related tasks.
"""
import traceback
import logging
import json

from decimal import Decimal, InvalidOperation

from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.core.paginator import Paginator


from reservation.models import Reservation, ActivityReservation, ReservationHistory, ActivityReservationHistory
from reservation.decorators import user_is_reservation_admin, user_has_reservation
from reservation.services.reservation_service import get_reservation_by_code, get_reservation_type

from common.services.stripe.stripe_webhook import handle_stripe_webhook_request
from common.decorators import is_admin
from common.services.network import get_client_ip
from common.services.email_service import (
    send_mail_logement_payment_success,
    send_mail_activity_payment_success,
)

from payment.decorators import is_stripe_admin
from payment.services.payment_service import (
    refund_payment,
    send_stripe_payment_link,
    charge_deposit,
    transfer_funds,
    get_session,
    get_payment_intent,
    verify_payment,
    verify_transfer,
    verify_payment_method,
    verify_deposit_payment,
    verify_refund,
    create_stripe_checkout_session_with_deposit,
    create_stripe_checkout_session_without_deposit,
)
from payment.models import PaymentTask

logger = logging.getLogger(__name__)


@login_required
@user_has_reservation
@require_POST
def save_payment_method(request, code):
    try:
        data = json.loads(request.body)
        payment_method_id = data.get("payment_method")
        reservation = get_reservation_by_code(code)
        reservation.stripe_saved_payment_method_id = payment_method_id
        reservation.save(update_fields=["stripe_saved_payment_method_id"])
        return HttpResponse(status=200)
    except Exception as e:
        logger.exception(f"Erreur lors de la sauvegarde du payment_method Stripe: {e}")
        return HttpResponse(status=400)


@login_required
@user_has_reservation
def payment_method_saved(request, type, code):
    from common.services.email_service import send_mail_on_new_reservation, send_mail_on_new_activity_reservation

    try:
        card_saved = request.GET.get("card_saved")
        if card_saved:
            messages.success(
                request,
                "Votre carte a bien été enregistrée. Aucun paiement n'a encore été effectué. "
                "Le paiement sera prélevé automatiquement 2 jours avant votre arrivée.",
            )
        if type == "logement":
            reservation = Reservation.objects.get(code=code)
            reservation.statut = "confirmee"
            ReservationHistory.objects.create(
                reservation=reservation,
                details=f"Nouvelle réservation {reservation.code} confirmée du {reservation.start} au {reservation.end}.",
            )
            send_mail_on_new_reservation(reservation.logement, reservation, reservation.user)

        elif type == "activity":
            reservation = ActivityReservation.objects.get(code=code)
            ActivityReservationHistory.objects.create(
                reservation=reservation,
                details=f"Nouvelle réservation {reservation.code}  en attente de confirmation du {reservation.start} au {reservation.end}.",
            )
            send_mail_on_new_activity_reservation(reservation.activity, reservation, reservation.user)
        else:
            messages.error(request, "Type de réservation inconnu.")
            return redirect("common:home")

        reservation.save(update_fields=["statut"])

        if type == "logement":
            return render(request, "payment/reservation_logement_success.html", {"reservation": reservation})
        elif type == "activity":
            return render(request, "payment/reservation_activity_success.html", {"reservation": reservation})

    except Reservation.DoesNotExist:
        logger.error(f"Réservation {code} introuvable.")
        messages.error(request, f"Réservation {code} introuvable.")
        return redirect("accounts:dashboard")
    except ActivityReservation.DoesNotExist:
        logger.error(f"activité {code} introuvable.")
        messages.error(request, f"Activité {code} introuvable.")
        return redirect("accounts:dashboard")
    except Exception as e:
        logger.exception(f"Error handling payment success: {e}")
        messages.error(request, "Erreur lors du traitement du paiement.")
        return redirect("accounts:dashboard")


@login_required
@user_has_reservation
def payment_success(request, type, code):
    try:
        session_id = request.GET.get("session_id")
        if not session_id:
            messages.error(request, "Session ID manquant. Veuillez contacter un administrateur")
            return redirect("accounts:dashboard")

        # Verify the session
        session = get_session(session_id)
        if not session:
            messages.error(request, "Session Stripe introuvable. Veuillez contacter un administrateur.")
            return redirect("accounts:dashboard")

        payment_intent_id = session.payment_intent
        payment_intent = get_payment_intent(payment_intent_id)
        if not payment_intent:
            messages.error(request, "Intent de paiement introuvable. Veuillez contacter un administrateur.")
            return redirect("accounts:dashboard")

        amount_paid = payment_intent.amount / 100  # Montant en euros

        if type == "logement":
            reservation = Reservation.objects.get(code=code)
            reservation.statut = "confirmee"
            reservation.paid = True
            reservation.stripe_payment_intent_id = payment_intent_id
            reservation.stripe_saved_payment_method_id = payment_intent.payment_method.id
            reservation.save(
                update_fields=["paid", "stripe_payment_intent_id", "stripe_saved_payment_method_id", "statut"]
            )
            send_mail_logement_payment_success(reservation.logement, reservation, reservation.user)
            ReservationHistory.objects.create(
                reservation=reservation,
                details=f"Paiement manuel de {amount_paid}€ pour la réservation {reservation.code} confirmée du {reservation.start} au {reservation.end}.",
            )
        elif type == "activity":
            reservation = ActivityReservation.objects.get(code=code)
            reservation.statut = "confirmee"
            reservation.paid = True
            reservation.stripe_payment_intent_id = payment_intent_id
            reservation.stripe_saved_payment_method_id = payment_intent.payment_method.id
            reservation.save(
                update_fields=["paid", "stripe_payment_intent_id", "stripe_saved_payment_method_id", "statut"]
            )
            send_mail_activity_payment_success(reservation.activity, reservation, reservation.user)
            ActivityReservationHistory.objects.create(
                reservation=reservation,
                details=f"Paiement manuel de {amount_paid}€ pour la réservation {reservation.code} confirmée du {reservation.start} au {reservation.end}.",
            )
        else:
            messages.error(request, "Type de réservation inconnu.")
            return redirect("accounts:dashboard")

        if type == "logement":
            return render(request, "payment/payment_logement_success.html", {"reservation": reservation})
        elif type == "activity":
            return render(request, "payment/payment_activity_success.html", {"reservation": reservation})

    except Reservation.DoesNotExist:
        messages.error(request, f"Réservation {code} introuvable.")
        return redirect("accounts:dashboard")
    except ActivityReservation.DoesNotExist:
        messages.error(request, f"Réservation activité {code} introuvable.")
        return redirect("accounts:dashboard")
    except Exception as e:
        logger.error(f"Error handling payment success: {e}\n{traceback.format_exc()}")
        messages.error(request, "Erreur lors du traitement du paiement.")
        return redirect("accounts:dashboard")


@login_required
@user_has_reservation
def payment_cancel(request, type, code):
    try:
        messages.info(
            request,
            "Votre paiement a été annulé. Contactez le support si nécessaire.",
        )
        return redirect("accounts:dashboard")

    except Exception as e:
        logger.exception(f"Error handling payment cancellation: {e}")
        messages.error(request, "Une erreur est survenue.")
        return redirect("accounts:dashboard")


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
        send_stripe_payment_link(reservation)  # Your helper function
        messages.success(request, f"Lien de paiement envoyé à {reservation.user.email}")
    except Exception as e:
        logger.exception(f"❌ Failed to send payment link for {code}: {e}")
        messages.error(request, "Erreur lors de l'envoi du lien.")

    if reservation_type == "activity":
        return redirect("reservation:activity_reservation_detail", code=code)
    else:
        return redirect("reservation:logement_reservation_detail", code=code)


@login_required
@user_has_reservation
def start_payment(request, code):
    reservation = get_reservation_by_code(code)
    reservation_type = get_reservation_type(reservation)
    try:
        if reservation_type == "logement":
            if not reservation.paid and reservation.statut in ["confirmee", "echec_paiement"]:
                # Create a Stripe session for the deposit payment
                session = create_stripe_checkout_session_with_deposit(reservation, request)
                return redirect(session["checkout_session_url"])
            else:
                messages.error(request, "Cette réservation est déjà payée ou n'est pas éligible pour un paiement.")
                return redirect("accounts:dashboard")
        elif reservation_type == "activity":
            if not reservation.paid and reservation.statut in ["confirmee", "echec_paiement"]:
                # Create a Stripe session for the activity payment
                session = create_stripe_checkout_session_without_deposit(reservation, request)
                return redirect(session["checkout_session_url"])
            else:
                messages.error(
                    request, "Cette réservation d'activité est déjà payée ou n'est pas éligible pour un paiement."
                )
                return redirect("accounts:dashboard")
    except Exception as e:
        logger.exception(f"Erreur lors de la création de la session Stripe pour {reservation.code}: {e}")
        messages.error(request, "Impossible de démarrer le paiement Stripe.")
        if reservation_type == "activity":
            return redirect("reservation:customer_activity_reservation_detail", code=code)
        else:
            return redirect("reservation:customer_logement_reservation_detail", code=code)


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
    try:
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
            reservation_ids = [r.id for r in Reservation.objects.filter(code__icontains=code)]
            activity_ids = [ar.id for ar in ActivityReservation.objects.filter(code__icontains=code)]
            all_ids = reservation_ids + activity_ids
            if all_ids:
                tasks = tasks.filter(object_id__in=all_ids)
                # Exclude tasks whose content_object is None (dangling generic relation)
                tasks = [t for t in tasks if getattr(t, 'content_type', None) is not None]
            else:
                tasks = tasks.none()

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
    except Exception as e:
        logger.exception(f"Erreur lors de l'affichage des tâches de paiement : {e}")
        raise

@login_required
@user_is_reservation_admin
@require_POST
def refund_reservation(request, code):
    try:
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
    except (InvalidOperation, TypeError, ValueError):
        logger.error("Invalid refund amount")
        messages.error(request, "Montant de remboursement invalide.")
    except Exception as e:
        messages.error(request, f"Erreur lors du remboursement : {e}")
        logger.exception("Error processing refund")

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
        logger.exception("Invalid refund amount")
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
        logger.exception("Invalid deposit amount")
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
    try:
        reservation = get_reservation_by_code(code)
        if not reservation:
            messages.error(request, "Réservation introuvable.")
            return redirect(request.META.get("HTTP_REFERER", "/"))

        paid, message = verify_payment(reservation)

        if paid:
            messages.success(request, message)
        else:
            messages.warning(request, message)
    except Exception as e:
        logger.error(f"Error verifying payment for reservation {code}: {e}")
        messages.error(request, "Erreur lors de la vérification du paiement.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
@user_is_reservation_admin
@require_POST
def verify_transfer_view(request, code):
    """
    View to verify the Stripe Transfer status for a reservation (logement or activity).
    """
    try:
        reservation = get_reservation_by_code(code)
        if not reservation:
            messages.error(request, "Réservation introuvable.")
            return redirect(request.META.get("HTTP_REFERER", "/"))

        success, message = verify_transfer(reservation)

        if success:
            messages.success(request, message)
        else:
            messages.warning(request, message)
    except Exception as e:
        logger.error(f"Error verifying transfer for reservation {code}: {e}")
        messages.error(request, "Erreur lors de la vérification du transfert.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
@user_is_reservation_admin
@require_POST
def verify_payment_method_view(request, code):
    """
    View to verify the Stripe Payment method used for a reservation (logement or activity).
    """
    try:
        reservation = get_reservation_by_code(code)
        if not reservation:
            messages.error(request, "Réservation introuvable.")
            return redirect(request.META.get("HTTP_REFERER", "/"))

        success, message = verify_payment_method(reservation)

        if success:
            messages.success(request, message)
        else:
            messages.warning(request, message)
    except Exception as e:
        logger.error(f"Error verifying payment method for reservation {code}: {e}")
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
@user_is_reservation_admin
@require_POST
def verify_deposit_payment_view(request, code):
    """
    View to verify the Stripe Paymment intent for deposit used for a reservation (logement or activity).
    """
    try:
        # Retrieve the reservation by code
        reservation = get_reservation_by_code(code)
        if not reservation:
            messages.error(request, "Réservation introuvable.")
            return redirect(request.META.get("HTTP_REFERER", "/"))

        success, message = verify_deposit_payment(reservation)

        if success:
            messages.success(request, message)
        else:
            messages.warning(request, message)
    except Exception as e:
        logger.error(f"Error verifying deposit payment for reservation {code}: {e}")
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
@user_is_reservation_admin
@require_POST
def verify_refund_view(request, code):
    """
    View to verify the Stripe Paymment intent for deposit used for a reservation (logement or activity).
    """
    try:
        reservation = get_reservation_by_code(code)
        if not reservation:
            messages.error(request, "Réservation introuvable.")
            return redirect(request.META.get("HTTP_REFERER", "/"))

        success, message = verify_refund(reservation)

        if success:
            messages.success(request, message)
        else:
            messages.warning(request, message)
    except Exception as e:
        logger.error(f"Error verifying refund for reservation {code}: {e}")

    return redirect(request.META.get("HTTP_REFERER", "/"))
