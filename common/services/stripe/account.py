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
