from datetime import timedelta
import logging
import inspect
from decimal import Decimal
from arrow import now
from django.db import transaction
from reservation.models import Reservation, ActivityReservation
from payment.services.payment_service import get_refund, get_transfer, get_payment_intent
from huey.contrib.djhuey import periodic_task
from huey import crontab
from django.core.mail import mail_admins

logger = logging.getLogger(__name__)


@periodic_task(crontab(hour=2, minute=0))  # tous les jours à 2h
def transfert_funds():
    from payment.services.payment_service import transfer_funds
    from common.signals import update_last_task_result

    summary = {
        "reservations": {"count": 0, "transferred": 0, "skipped": 0, "errors": []},
        "activity_reservations": {"count": 0, "transferred": 0, "skipped": 0, "errors": []},
    }

    # Standard reservations
    reservations = Reservation.objects.filter(statut="terminee", transferred=False, paid=True)
    summary["reservations"]["count"] = reservations.count()

    for reservation in reservations:
        if reservation.refundable_period_passed:
            try:
                transfer_funds(reservation)
                summary["reservations"]["transferred"] += 1
            except Exception as e:
                summary["reservations"]["errors"].append({"id": reservation.id, "error": str(e)})
        else:
            summary["reservations"]["skipped"] += 1

    # Activity reservations
    reservations = ActivityReservation.objects.filter(statut="terminee", transferred=False, paid=True)
    summary["activity_reservations"]["count"] = reservations.count()

    for reservation in reservations:
        if reservation.refundable_period_passed:
            try:
                transfer_funds(reservation)
                summary["activity_reservations"]["transferred"] += 1
            except Exception as e:
                summary["activity_reservations"]["errors"].append({"id": reservation.id, "error": str(e)})
        else:
            summary["activity_reservations"]["skipped"] += 1
    
    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)

    return summary


@periodic_task(crontab(minute="*"))  # toutes les minutes
def create_reservation_payment_intents():
    from payment.services.payment_service import create_reservation_payment_intents
    from common.signals import update_last_task_result

    today = now().date()
    in_7_days = today + timedelta(days=7)

    summary = {
        "reservations": {"count": 0, "created": 0, "errors": []},
        "activity_reservations": {"count": 0, "created": 0, "errors": []},
    }

    # Standard reservations
    reservations = Reservation.objects.filter(
        statut="confirmee",
        stripe_payment_intent_id=None,
        paid=False,
        start__lte=in_7_days,
        start__gte=today,
    )
    summary["reservations"]["count"] = reservations.count()

    for reservation in reservations:
        try:
            create_reservation_payment_intents(reservation)
            summary["reservations"]["created"] += 1
        except Exception as e:
            summary["reservations"]["errors"].append({"id": reservation.id, "error": str(e)})

    # Activity reservations
    activities = ActivityReservation.objects.filter(
        statut="confirmee",
        stripe_payment_intent_id=None,
        paid=False,
        start__lte=in_7_days,
        start__gte=today,
    )
    summary["activity_reservations"]["count"] = activities.count()

    for activity in activities:
        try:
            create_reservation_payment_intents(activity)
            summary["activity_reservations"]["created"] += 1
        except Exception as e:
            summary["activity_reservations"]["errors"].append({"id": activity.id, "error": str(e)})

    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)

    return summary


@periodic_task(crontab(minute=45))  # toutes les heures à 45 minutes
def capture_payment_intents():
    from payment.services.payment_service import capture_reservation_payment
    from common.signals import update_last_task_result

    today = now().date()
    in_2_days = today + timedelta(days=2)

    summary = {
        "reservations": {"count": 0, "success": 0, "errors": []},
        "activity_reservations": {"count": 0, "success": 0, "errors": []},
    }

    reservations = (
        Reservation.objects.filter(statut="confirmee", paid=False, start__lte=in_2_days, start__gte=today)
        .exclude(stripe_payment_intent_id__isnull=True)
        .exclude(stripe_payment_intent_id__exact="")
    )

    summary["reservations"]["count"] = reservations.count()

    for reservation in reservations:
        try:
            capture_reservation_payment(reservation)
            summary["reservations"]["success"] += 1
        except Exception as e:
            summary["reservations"]["errors"].append({"id": reservation.id, "error": str(e)})

    reservations = (
        ActivityReservation.objects.filter(statut="confirmee", paid=False, start__lte=in_2_days, start__gte=today)
        .exclude(stripe_payment_intent_id__isnull=True)
        .exclude(stripe_payment_intent_id__exact="")
    )
    summary["activity_reservations"]["count"] = reservations.count()

    for reservation in reservations:
        try:
            capture_reservation_payment(reservation)
            summary["activity_reservations"]["success"] += 1
        except Exception as e:
            summary["activity_reservations"]["errors"].append({"id": reservation.id, "error": str(e)})

    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)

    return summary


@periodic_task(crontab(hour=4, minute=0))  # tous les jours à 4h
def check_stripe_integrity():
    from payment.services.payment_service import send_stripe_payment_link
    from common.signals import update_last_task_result
    summary = {
        "reservations": {
            "refunds": {"checked": 0, "updated": 0, "errors": []},
            "transfers": {"checked": 0, "updated": 0, "errors": []},
            "deposits": {"checked": 0, "updated": 0, "errors": []},
            "bookings": {"checked": 0, "sent": 0, "errors": []},
        },
        "activity_reservations": {
            "refunds": {"checked": 0, "updated": 0, "errors": []},
            "transfers": {"checked": 0, "updated": 0, "errors": []},
            "bookings": {"checked": 0, "sent": 0, "errors": []},
        },
    }

    ##### RESERVATION REFUNDS #####
    problematic = Reservation.objects.filter(refunded=True).filter(
        refund_amount__isnull=True
    ) | Reservation.objects.filter(refunded=True, refund_amount=0)

    for resa in problematic:
        summary["reservations"]["refunds"]["checked"] += 1
        try:
            refund = get_refund(resa.stripe_refund_id)
            if refund:
                with transaction.atomic():
                    amount = refund.amount
                    currency = refund.currency or "eur"

                    if not amount or amount <= 0:
                        mail_admins(
                            subject=f"[Refund Integrity] Invalid refund amount for reservation {resa.code}",
                            message=f"Refund {refund.id} for reservation {resa.code} has invalid amount: {amount} {currency}.",
                        )
                        continue

                    refunded_amount = Decimal(amount) / 100
                    resa.refund_amount = refunded_amount

                    if refund.metadata and refund.metadata.get("refund") == "full":
                        resa.platform_fee = Decimal("0.00")
                        resa.tax = Decimal("0.00")
                        resa.statut = "annulee"

                    resa.save(update_fields=["refund_amount", "platform_fee", "tax", "statut", "stripe_refund_id"])
                    summary["reservations"]["refunds"]["updated"] += 1
            else:
                mail_admins(
                    subject=f"[Refund Integrity] No refund found for reservation {resa.code}",
                    message=f"No refund found on Stripe for reservation {resa.code} (refund_id={resa.stripe_refund_id}).",
                )
        except Exception as e:
            summary["reservations"]["refunds"]["errors"].append(f"{resa.code}: {str(e)}")

    ##### RESERVATION TRANSFERS #####
    problematic = (
        Reservation.objects.filter(transferred=True, transferred_amount__isnull=True)
        | Reservation.objects.filter(transferred=True, transferred_amount=0)
        | Reservation.objects.filter(admin_transferred=True, admin_transferred_amount__isnull=True)
        | Reservation.objects.filter(admin_transferred=True, admin_transferred_amount=0)
    )

    for resa in problematic:
        summary["reservations"]["transfers"]["checked"] += 1
        try:
            transfer = get_transfer(resa.stripe_transfer_id)
            if transfer:
                transfer_user = transfer.metadata.get("transfer")
                if not transfer_user:
                    continue

                with transaction.atomic():
                    amount = transfer.amount
                    if not amount or amount <= 0:
                        mail_admins(
                            subject=f"[Transfer Integrity] Invalid transfer amount for reservation {resa.code}",
                            message=f"Transfer {transfer.id} for reservation {resa.code} has invalid amount: {amount}",
                        )
                        continue

                    transferred_amount = Decimal(amount) / 100

                    if transfer_user == "owner":
                        resa.transferred_amount = transferred_amount
                        resa.save(update_fields=["transferred_amount"])
                    elif transfer_user == "admin":
                        resa.admin_transferred_amount = transferred_amount
                        resa.save(update_fields=["admin_transferred_amount"])

                    summary["reservations"]["transfers"]["updated"] += 1
            else:
                mail_admins(
                    subject=f"[Transfer Integrity] No transfer found for reservation {resa.code}",
                    message=f"No transfer found on Stripe for reservation {resa.code} (transfer_id={resa.stripe_transfer_id}).",
                )
        except Exception as e:
            summary["reservations"]["transfers"]["errors"].append(f"{resa.code}: {str(e)}")

    ##### RESERVATION DEPOSITS #####
    problematic = Reservation.objects.filter(caution_charged=True).filter(
        amount_charged__isnull=True
    ) | Reservation.objects.filter(caution_charged=True, amount_charged=0)

    for resa in problematic:
        summary["reservations"]["deposits"]["checked"] += 1
        try:
            if resa.stripe_deposit_payment_intent_id:
                deposit = get_payment_intent(resa.stripe_deposit_payment_intent_id)
                if deposit:
                    with transaction.atomic():
                        amount = deposit.amount
                        if not amount or amount <= 0:
                            mail_admins(
                                subject=f"[Deposit Integrity] Invalid deposit amount for reservation {resa.code}",
                                message=f"Deposit {deposit.id} for reservation {resa.code} has invalid amount: {amount}",
                            )
                            continue

                        deposited_amount = Decimal(amount) / 100
                        resa.amount_charged = deposited_amount
                        resa.save(update_fields=["amount_charged"])
                        summary["reservations"]["deposits"]["updated"] += 1
                else:
                    mail_admins(
                        subject=f"[Deposit Integrity] No deposit found for reservation {resa.code}",
                        message=f"No deposit found on Stripe for reservation {resa.code} (id={resa.stripe_deposit_payment_intent_id})",
                    )
        except Exception as e:
            summary["reservations"]["deposits"]["errors"].append(f"{resa.code}: {str(e)}")

    ##### RESERVATION BOOKING FAILURES #####
    problematic = Reservation.objects.filter(statut="echec_paiement")

    for resa in problematic:
        summary["reservations"]["bookings"]["checked"] += 1
        try:
            send_stripe_payment_link(resa)
            summary["reservations"]["bookings"]["sent"] += 1
            mail_admins(
                subject=f"[Payment Integrity] No payment found for reservation {resa.code}",
                message=f"No payment found on Stripe for reservation {resa.code}. Link resent.",
            )
        except Exception as e:
            summary["reservations"]["bookings"]["errors"].append(f"{resa.code}: {str(e)}")

    ##### ACTIVITY REFUNDS #####
    problematic = ActivityReservation.objects.filter(refunded=True).filter(
        refund_amount__isnull=True
    ) | ActivityReservation.objects.filter(refunded=True, refund_amount=0)

    for resa in problematic:
        summary["activity_reservations"]["refunds"]["checked"] += 1
        try:
            refund = get_refund(resa.stripe_refund_id)
            if refund:
                with transaction.atomic():
                    amount = refund.amount
                    currency = refund.currency or "eur"

                    if not amount or amount <= 0:
                        mail_admins(
                            subject=f"[Refund Integrity] Invalid refund amount for activity reservation {resa.code}",
                            message=f"Refund {refund.id} for reservation {resa.code} has invalid amount: {amount} {currency}.",
                        )
                        continue

                    refunded_amount = Decimal(amount) / 100
                    resa.refund_amount = refunded_amount

                    if refund.metadata and refund.metadata.get("refund") == "full":
                        resa.platform_fee = Decimal("0.00")
                        resa.tax = Decimal("0.00")
                        resa.statut = "annulee"

                    resa.save(update_fields=["refund_amount", "platform_fee", "tax", "statut", "stripe_refund_id"])
                    summary["activity_reservations"]["refunds"]["updated"] += 1
            else:
                mail_admins(
                    subject=f"[Refund Integrity] No refund found for activity reservation {resa.code}",
                    message=f"No refund found on Stripe for activity reservation {resa.code} (refund_id={resa.stripe_refund_id}).",
                )
        except Exception as e:
            summary["activity_reservations"]["refunds"]["errors"].append(f"{resa.code}: {str(e)}")

    ##### ACTIVITY TRANSFERS #####
    problematic = ActivityReservation.objects.filter(transferred=True).filter(
        transferred_amount__isnull=True
    ) | ActivityReservation.objects.filter(transferred=True, transferred_amount=0)

    for resa in problematic:
        summary["activity_reservations"]["transfers"]["checked"] += 1
        try:
            transfer = get_transfer(resa.stripe_transfer_id)
            if transfer:
                transfer_user = transfer.metadata.get("transfer")
                if not transfer_user:
                    continue

                with transaction.atomic():
                    amount = transfer.amount
                    if not amount or amount <= 0:
                        mail_admins(
                            subject=f"[Transfer Integrity] Invalid transfer amount for activity reservation {resa.code}",
                            message=f"Transfer {transfer.id} for reservation {resa.code} has invalid amount: {amount}",
                        )
                        continue

                    transferred_amount = Decimal(amount) / 100

                    if transfer_user == "owner":
                        resa.transferred_amount = transferred_amount
                        resa.save(update_fields=["transferred_amount"])
                        summary["activity_reservations"]["transfers"]["updated"] += 1
            else:
                mail_admins(
                    subject=f"[Transfer Integrity] No transfer found for activity reservation {resa.code}",
                    message=f"No transfer found on Stripe for reservation {resa.code} (transfer_id={resa.stripe_transfer_id}).",
                )
        except Exception as e:
            summary["activity_reservations"]["transfers"]["errors"].append(f"{resa.code}: {str(e)}")

    ##### ACTIVITY BOOKING FAILURES #####
    problematic = ActivityReservation.objects.filter(statut="echec_paiement")

    for resa in problematic:
        summary["activity_reservations"]["bookings"]["checked"] += 1
        try:
            send_stripe_payment_link(resa)
            summary["activity_reservations"]["bookings"]["sent"] += 1
            mail_admins(
                subject=f"[Payment Integrity] No payment found for activity reservation {resa.code}",
                message=f"No payment found on Stripe for activity reservation {resa.code}. Link resent.",
            )
        except Exception as e:
            summary["activity_reservations"]["bookings"]["errors"].append(f"{resa.code}: {str(e)}")

    name = inspect.currentframe().f_code.co_name
    update_last_task_result(name, summary)

    return summary
