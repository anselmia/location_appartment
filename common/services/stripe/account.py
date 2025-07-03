# accounts/stripe_utils.py

import stripe
import logging
from datetime import datetime
from django.utils import timezone

from django.conf import settings

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def get_stripe_account_info(user):
    if not user.stripe_account_id:
        return None
    try:
        return stripe.Account.retrieve(user.stripe_account_id)
    except Exception as e:
        logger.exception(f"Failed to retrieve Stripe account for user {user.id}: {e}")
        return None


def get_reservation_stripe_data(user):
    from reservation.models import Reservation

    data = []
    reservations = Reservation.objects.filter(logement__owner=user).select_related("logement")

    for r in reservations:
        payment_intent = refund = None
        # Main payment intent
        if r.stripe_payment_intent_id:
            try:
                payment_intent = stripe.PaymentIntent.retrieve(r.stripe_payment_intent_id)
            except Exception as e:
                logger.warning(f"[Stripe] Error fetching payment intent for {r.code}: {e}")

        if r.stripe_refund_id:
            try:
                refund = stripe.Refund.retrieve(r.stripe_refund_id)

            except Exception as e:
                logger.warning(f"[Stripe] Error fetching refund for {r.code}: {e}")

        # Deposit payment intent
        if r.stripe_deposit_payment_intent_id:
            try:
                deposit_intent = stripe.PaymentIntent.retrieve(r.stripe_deposit_payment_intent_id)
            except Exception as e:
                logger.warning(f"[Stripe] Error fetching deposit intent for {r.code}: {e}")
        data.append(
            {
                "reservation": r,
                "payment_intent": payment_intent,
                "deposit_intent": deposit_intent,
                "refund": refund,
                "refunded_flag": r.refunded,
                "refund_amount": r.refund_amount,
                "stripe_refund_id": r.stripe_refund_id,
                "caution_charged": r.caution_charged,
                "amount_charged": r.amount_charged,
                "saved_payment_method": r.stripe_saved_payment_method_id,
            }
        )
        logger.info(data)
    return data


def get_stripe_dashboard_link(user):
    """
    Crée un lien vers le tableau de bord Stripe Express du propriétaire.
    """
    if not user.stripe_account_id:
        raise ValueError("Aucun compte Stripe associé à l'utilisateur.")

    try:
        login_link = stripe.Account.create_login_link(user.stripe_account_id)
        return login_link.url
    except stripe.error.StripeError as e:
        raise RuntimeError(f"Erreur Stripe : {e.user_message or str(e)}")


def create_stripe_connect_account(user, refresh_url, return_url):
    """
    Creates a Stripe Connect Express account and an onboarding link for the user.
    Returns a tuple: (account, account_link)
    Raises stripe.error.StripeError on failure.
    """

    # Create the Express account
    account = stripe.Account.create(
        type="express",
        country="FR",
        email=user.email,
        business_type="individual",
        capabilities={
            "transfers": {"requested": True},
        },
    )

    # Create the onboarding link
    account_link = stripe.AccountLink.create(
        account=account.id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )

    return account, account_link


def update_stripe_account(account_id, update_data=None):
    """
    Met à jour un compte Stripe avec les données fournies.
    """
    try:
        if update_data:
            account = stripe.Account.modify(account_id, **update_data)
        else:
            account = stripe.Account.retrieve(account_id)
        return account
    except Exception as e:
        logger.error(f"Erreur mise à jour Stripe Account {account_id} : {e}")
        raise


def get_stripe_transactions(user):
    """
    Récupère les transactions Stripe pour un utilisateur donné.
    """
    if not user.stripe_account_id:
        return None

    try:
        transactions = stripe.BalanceTransaction.list(
            limit=100,
            stripe_account=user.stripe_account_id,
        )
        if transactions.data:
            for transaction in transactions.data:
                transaction.amount = transaction.amount / 100.0  # Convert cents to euros
                transaction.created = datetime.fromtimestamp(transaction.created, tz=timezone.get_current_timezone())
        return transactions.data
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des transactions Stripe pour l'utilisateur {user.id}: {e}")
        return None


def get_stripe_balance(user):
    """
    Récupère le solde Stripe pour un utilisateur donné.
    """
    if not user.stripe_account_id:
        return None

    try:
        balance = stripe.Balance.retrieve(stripe_account=user.stripe_account_id)
        return balance
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du solde Stripe pour l'utilisateur {user.id}: {e}")
        return None


def get_stripe_payouts(user):
    """
    Récupère les paiements Stripe pour un utilisateur donné.
    """
    if not user.stripe_account_id:
        return None

    try:
        payouts = stripe.Payout.list(
            limit=100,
            stripe_account=user.stripe_account_id,
        )
        return payouts.data
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des paiements Stripe pour l'utilisateur {user.id}: {e}")
        return None
