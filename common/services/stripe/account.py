# accounts/stripe_utils.py

import stripe
import logging

from django.conf import settings

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def get_or_create_stripe_account(user) -> str:
    """
    Check if user has a Stripe account. If not, create one and store the ID.
    Returns the Stripe account ID.
    """
    if user.stripe_account_id:
        return user.stripe_account_id

    try:
        # Create a new Stripe account – Express is common for marketplaces
        account = stripe.Account.create(
            type="express",  # or "custom" depending on your needs
            country="FR",  # Adjust to your marketplace country
            email=user.email,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_type="individual",
        )

        logger.info(f"Stripe account created for user {user.id}: {account.id}")
        return account.id

    except Exception as e:
        logger.info(f"Fail to creat Stripe account for {user}: {e}")
        return None


def get_stripe_account_info(user):
    if not user.stripe_account_id:
        return None
    try:
        return stripe.Account.retrieve(user.stripe_account_id)
    except Exception as e:
        logger.exception(f"Failed to retrieve Stripe account for user {user.id}: {e}")
        return None


def get_reservation_stripe_data(user):
    from logement.models import Reservation

    data = []
    reservations = Reservation.objects.filter(logement__owner=user).select_related(
        "logement"
    )

    for r in reservations:
        payment_intent = refund = None
        if r.stripe_payment_intent_id:
            try:
                payment_intent = stripe.PaymentIntent.retrieve(
                    r.stripe_payment_intent_id
                )
                if payment_intent.latest_charge:
                    charge = stripe.Charge.retrieve(payment_intent.latest_charge)
                    refund = charge.get("refunds", {}).data if charge.refunded else None
            except Exception as e:
                logger.warning(
                    f"Failed to fetch payment data for reservation {r.code}: {e}"
                )
        data.append(
            {
                "reservation": r,
                "payment_intent": payment_intent,
                "refund": refund,
            }
        )
    return data
