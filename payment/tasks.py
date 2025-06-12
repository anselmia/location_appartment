import logging
from decimal import Decimal
from django.db import transaction
from reservation.models import Reservation
from payment.services.payment_service import get_refund, get_transfer
from huey.contrib.djhuey import periodic_task
from huey import crontab
from django.core.mail import mail_admins

logger = logging.getLogger(__name__)


@periodic_task(crontab(hour=2, minute=0))  # toutes les jours à 2h
def transfert_funds():
    from payment.services.payment_service import charge_reservation

    reservations = Reservation.objects.filter(statut="confirmee")
    for reservation in reservations:
        if reservation.refundable_period_passed:
            charge_reservation(reservation)


@periodic_task(crontab(hour=3, minute=30))  # toutes les jours à 3h30
def check_stripe_integrity():
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
                        mail_admins(
                            subject=f"[Refund Integrity] Invalid refund amount for reservation {resa.code}",
                            message=f"Refund {refund.id} for reservation {resa.code} has invalid amount: {amount} {currency}.",
                        )
                        continue

                    refunded_amount = Decimal(amount) / 100
                    current_refund = Decimal(resa.refund_amount or 0)

                    # Update reservation
                    resa.refund_amount = current_refund + refunded_amount
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
    logger.info("Transfer and refund integrity check completed.")
    return "Transfer and refund integrity check completed."
