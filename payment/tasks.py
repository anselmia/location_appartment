from datetime import timedelta
import logging
from decimal import Decimal
from arrow import now
from django.db import transaction
from reservation.models import Reservation, ActivityReservation
from payment.services.payment_service import get_refund, get_transfer, get_payment_intent
from huey.contrib.djhuey import periodic_task
from huey import crontab
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


@periodic_task(crontab(hour=2, minute=0))  # toutes les jours à 2h
def transfert_funds():
    from payment.services.payment_service import transfer_funds

    reservations = Reservation.objects.filter(statut="terminee")
    for reservation in reservations:
        if reservation.refundable_period_passed and reservation.paid:
            transfer_funds(reservation)

    reservations = ActivityReservation.objects.filter(statut="terminee")
    for reservation in reservations:
        if reservation.refundable_period_passed and reservation.paid:
            transfer_funds(reservation)


@periodic_task(crontab(hour=1, minute=0))  # toutes les jours à 1h
def create_reservation_payment_intents():
    from payment.services.payment_service import create_reservation_payment_intents

    today = now().date()
    in_7_days = today + timedelta(days=7)

    reservations = Reservation.objects.filter(
        statut="confirmee", stripe_payment_intent_id=None, paid=False, start__lte=in_7_days, start__gte=today
    )
    for reservation in reservations:
        create_reservation_payment_intents(reservation)

    activities = ActivityReservation.objects.filter(
        statut="confirmee", stripe_payment_intent_id=None, paid=False, start__lte=in_7_days, start__gte=today
    )
    for activity in activities:
        create_reservation_payment_intents(activity)


@periodic_task(crontab(hour=1, minute=30))  # toutes les jours à 1h30
def capture_payment_intents():
    from payment.services.payment_service import capture_reservation_payment

    today = now().date()
    in_2_days = today + timedelta(days=2)

    reservations = (
        Reservation.objects.filter(statut="confirmee", paid=False, start__lte=in_2_days, start__gte=today)
        .exclude(stripe_payment_intent_id__isnull=True)
        .exclude(stripe_payment_intent_id__exact="")
    )

    for reservation in reservations:
        capture_reservation_payment(reservation)


@periodic_task(crontab(hour=4, minute=0))  # toutes les jours à 4h
def check_stripe_integrity():
    from payment.services.payment_service import send_stripe_payment_link

    ##### RESERVATIONS #####
    from reservation.models import Reservation

    ##### REFUNDS #####
    problematic = Reservation.objects.filter(refunded=True).filter(
        refund_amount__isnull=True
    ) | Reservation.objects.filter(refunded=True, refund_amount=0)

    for resa in problematic:
        try:
            refund = get_refund(resa.stripe_refund_id)
            if refund:
                with transaction.atomic():
                    amount = refund.amount
                    currency = refund.currency or "eur"

                    if not amount or amount <= 0:
                        logger.warning(f"⚠️ Invalid or missing refund amount for event {refund.id}")
                        EmailMessage(
                            subject=f"[Refund Integrity] Invalid refund amount for reservation {resa.code}",
                            message=f"Refund {refund.id} for reservation {resa.code} has invalid amount: {amount} {currency}.",
                        )
                        continue

                    refunded_amount = Decimal(amount) / 100

                    # Update reservation
                    resa.refund_amount = refunded_amount
                    if refund.metadata and refund.metadata.get("refund") == "full":
                        resa.platform_fee = Decimal("0.00")
                        resa.tax = Decimal("0.00")
                        resa.statut = "annulee"

                    resa.save(update_fields=["refund_amount", "platform_fee", "tax", "statut", "stripe_refund_id"])
                    logger.info(
                        f"Reservation {resa.code}: refund info updated from Stripe (amount={refunded_amount}, id={refund.id})"
                    )
            else:
                logger.warning(
                    f"Reservation {resa.code}: No refund found on Stripe for refund_id {resa.stripe_refund_id}"
                )
                mail_admins(
                    subject=f"[Refund Integrity] No refund found for reservation {resa.code}",
                    message=f"No refund found on Stripe for reservation {resa.code} (refund_id={resa.stripe_refund_id}).",
                )
        except Exception as e:
            logger.error(f"Error checking refund for reservation {resa.code}: {e}")
            mail_admins(
                subject=f"[Refund Integrity] Error for reservation {resa.code}",
                message=f"Error checking refund for reservation {resa.code}: {e}",
            )

    ##### TRANSFERS #####
    problematic = (
        Reservation.objects.filter(transferred=True).filter(transferred_amount__isnull=True)
        | Reservation.objects.filter(transferred=True, transferred_amount=0)
        | Reservation.objects.filter(admin_transferred=True, admin_transferred_amount__isnull=True)
        | Reservation.objects.filter(admin_transferred=True, admin_transferred_amount=0)
    )

    for resa in problematic:
        try:
            transfer = get_transfer(resa.stripe_transfer_id)
            if transfer:
                transfer_user = transfer.metadata.get("transfer")
                if not transfer_user:
                    logger.warning("⚠️ No reservation user found in the transfer event metadata.")
                    return
                with transaction.atomic():
                    amount = transfer.amount
                    if not amount or amount <= 0:
                        logger.warning(f"⚠️ Invalid or missing transfer amount for event {transfer.id}")
                        mail_admins(
                            subject=f"[Transfer Integrity] Invalid transfer amount for reservation {resa.code}",
                            message=f"Transfer {transfer.id} for reservation {resa.code} has invalid amount: {amount}",
                        )
                        continue

                    transferred_amount = Decimal(amount) / 100

                    if transfer_user == "owner":
                        resa.transferred_amount = transferred_amount
                        resa.save(update_fields=["transferred_amount"])
                        logger.info(
                            f"Reservation {resa.code}: transfer to owner info updated from Stripe (amount={resa.transferred_amount}, id={transfer.id})"
                        )
                    elif transfer_user == "admin":
                        resa.admin_transferred_amount = transferred_amount
                        resa.save(update_fields=["admin_transferred_amount"])
                        logger.info(
                            f"Reservation {resa.code}: transfer to admin info updated from Stripe (amount={resa.admin_transferred_amount}, id={transfer.id})"
                        )
            else:
                logger.warning(
                    f"Reservation {resa.code}: No transfer found on Stripe for transfer_id {resa.stripe_transfer_id}"
                )
                mail_admins(
                    subject=f"[Transfer Integrity] No transfer found for reservation {resa.code}",
                    message=f"No transfer found on Stripe for reservation {resa.code} (transfer_id={resa.stripe_transfer_id}).",
                )
        except Exception as e:
            logger.error(f"Error checking transfer for reservation {resa.code}: {e}")
            mail_admins(
                subject=f"[Transfer Integrity] Error for reservation {resa.code}",
                message=f"Error checking transfer for reservation {resa.code}: {e}",
            )
            continue

    ##### DEPOSIT #####
    problematic = Reservation.objects.filter(caution_charged=True).filter(
        amount_charged__isnull=True
    ) | Reservation.objects.filter(caution_charged=True, amount_charged=0)

    for resa in problematic:
        try:
            if resa.stripe_deposit_payment_intent_id:
                deposit = get_payment_intent(resa.stripe_deposit_payment_intent_id)
                if deposit:
                    with transaction.atomic():
                        amount = deposit.amount
                        if not amount or amount <= 0:
                            logger.warning(f"⚠️ Invalid or missing deposit amount for event {deposit.id}")
                            mail_admins(
                                subject=f"[Deposit Integrity] Invalid deposit amount for reservation {resa.code}",
                                message=f"Deposit {deposit.id} for reservation {resa.code} has invalid amount: {amount}",
                            )
                            continue

                        deposited_amount = Decimal(amount) / 100

                        # Update reservation
                        resa.amount_charged = deposited_amount
                        resa.save(update_fields=["amount_charged"])
                        logger.info(
                            f"Reservation {resa.code}: deposit info updated from Stripe (amount={deposited_amount}, id={deposit.id})"
                        )
                else:
                    logger.warning(
                        f"Reservation {resa.code}: No deposit found on Stripe for deposit_id {resa.stripe_deposit_payment_intent_id}"
                    )
                    mail_admins(
                        subject=f"[Deposit Integrity] No deposit amount found for reservation {resa.code}",
                        message=f"No deposit amount found on Stripe for reservation {resa.code} (deposit_id={resa.stripe_deposit_payment_intent_id}).",
                    )
            else:
                logger.warning(f"Reservation {resa.code}: No stripe_deposit_payment_intent_id found.")
        except Exception as e:
            logger.error(f"Error checking deposit for reservation {resa.code}: {e}")
            mail_admins(
                subject=f"[Deposit Integrity] Error for reservation {resa.code}",
                message=f"Error checking deposit for reservation {resa.code}: {e}",
            )

    ##### BOOKING #####
    problematic = Reservation.objects.filter(statut="echec_paiement")

    for resa in problematic:
        try:
            send_stripe_payment_link(resa)

            logger.info(f"Reservation {resa.code}: sending payment link for failed payment")
            mail_admins(
                subject=f"[Payment Integrity] No payment found for reservation {resa.code}",
                message=f"No payment found on Stripe for reservation {resa.code}.",
            )
        except Exception as e:
            logger.error(f"Error checking payment for reservation {resa.code}: {e}")
            mail_admins(
                subject=f"[Payment Integrity] Error for reservation {resa.code}",
                message=f"Error checking payment for reservation {resa.code}: {e}",
            )

    ##### ACTIVITY RESERVATIONS #####
    from reservation.models import ActivityReservation

    ##### REFUNDS #####
    problematic = ActivityReservation.objects.filter(refunded=True).filter(
        refund_amount__isnull=True
    ) | ActivityReservation.objects.filter(refunded=True, refund_amount=0)

    for resa in problematic:
        try:
            refund = get_refund(resa.stripe_refund_id)
            if refund:
                with transaction.atomic():
                    amount = refund.amount
                    currency = refund.currency or "eur"

                    if not amount or amount <= 0:
                        logger.warning(f"⚠️ Invalid or missing refund amount for event {refund.id}")
                        mail_admins(
                            subject=f"[Refund Integrity] Invalid refund amount for reservation {resa.code}",
                            message=f"Refund {refund.id} for reservation {resa.code} has invalid amount: {amount} {currency}.",
                        )
                        continue

                    refunded_amount = Decimal(amount) / 100

                    # Update reservation
                    resa.refund_amount = refunded_amount
                    if refund.metadata and refund.metadata.get("refund") == "full":
                        resa.platform_fee = Decimal("0.00")
                        resa.tax = Decimal("0.00")
                        resa.statut = "annulee"

                    resa.save(update_fields=["refund_amount", "platform_fee", "tax", "statut", "stripe_refund_id"])
                    logger.info(
                        f"Reservation {resa.code}: refund info updated from Stripe (amount={refunded_amount}, id={refund.id})"
                    )
            else:
                logger.warning(
                    f"Reservation {resa.code}: No refund found on Stripe for refund_id {resa.stripe_refund_id}"
                )
                mail_admins(
                    subject=f"[Refund Integrity] No refund found for reservation {resa.code}",
                    message=f"No refund found on Stripe for reservation {resa.code} (refund_id={resa.stripe_refund_id}).",
                )
        except Exception as e:
            logger.error(f"Error checking refund for reservation {resa.code}: {e}")
            mail_admins(
                subject=f"[Refund Integrity] Error for reservation {resa.code}",
                message=f"Error checking refund for reservation {resa.code}: {e}",
            )

    ##### TRANSFERS #####
    problematic = ActivityReservation.objects.filter(transferred=True).filter(
        transferred_amount__isnull=True
    ) | ActivityReservation.objects.filter(transferred=True, transferred_amount=0)

    for resa in problematic:
        try:
            transfer = get_transfer(resa.stripe_transfer_id)
            if transfer:
                transfer_user = transfer.metadata.get("transfer")
                if not transfer_user:
                    logger.warning("⚠️ No reservation user found in the transfer event metadata.")
                    return
                with transaction.atomic():
                    amount = transfer.amount
                    if not amount or amount <= 0:
                        logger.warning(f"⚠️ Invalid or missing transfer amount for event {transfer.id}")
                        mail_admins(
                            subject=f"[Transfer Integrity] Invalid transfer amount for reservation {resa.code}",
                            message=f"Transfer {transfer.id} for reservation {resa.code} has invalid amount: {amount}",
                        )
                        continue

                    transferred_amount = Decimal(amount) / 100

                    if transfer_user == "owner":
                        resa.transferred_amount = transferred_amount
                        resa.save(update_fields=["transferred_amount"])
                        logger.info(
                            f"Reservation {resa.code}: transfer to owner info updated from Stripe (amount={resa.transferred_amount}, id={transfer.id})"
                        )

            else:
                logger.warning(
                    f"Reservation {resa.code}: No transfer found on Stripe for transfer_id {resa.stripe_transfer_id}"
                )
                mail_admins(
                    subject=f"[Transfer Integrity] No transfer found for reservation {resa.code}",
                    message=f"No transfer found on Stripe for reservation {resa.code} (transfer_id={resa.stripe_transfer_id}).",
                )
        except Exception as e:
            logger.error(f"Error checking transfer for reservation {resa.code}: {e}")
            mail_admins(
                subject=f"[Transfer Integrity] Error for reservation {resa.code}",
                message=f"Error checking transfer for reservation {resa.code}: {e}",
            )
            continue

    ##### BOOKING #####
    problematic = ActivityReservation.objects.filter(statut="echec_paiement")

    for resa in problematic:
        try:
            send_stripe_payment_link(resa)

            logger.info(f"Reservation {resa.code}: sending payment link for failed payment")
            mail_admins(
                subject=f"[Payment Integrity] No payment found for reservation {resa.code}",
                message=f"No payment found on Stripe for reservation {resa.code}.",
            )
        except Exception as e:
            logger.error(f"Error checking payment for reservation {resa.code}: {e}")
            mail_admins(
                subject=f"[Payment Integrity] Error for reservation {resa.code}",
                message=f"Error checking payment for reservation {resa.code}: {e}",
            )

    logger.info("Stripe integrity check completed.")
    return "Stripe integrity check completed."
