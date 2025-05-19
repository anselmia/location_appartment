import stripe
import logging
from django.conf import settings
from logement.models import Reservation
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone


logger = logging.getLogger(__name__)
# Set up Stripe with the secret key
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def create_stripe_checkout_session(reservation, success_url, cancel_url):
    try:
        return stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": f"Reservation for {reservation.logement.name}",
                        },
                        "unit_amount": int(reservation.price * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"reservation_id": reservation.id},
        )
    except Exception as e:
        logger.exception(f"Erreur Stripe: {e}")
        raise


def refund_payment(payment_intent_id):
    try:
        return stripe.Refund.create(payment_intent=payment_intent_id)
    except stripe.error.StripeError as e:
        logger.exception(f"Stripe refund error: {e}")
        raise


def handle_charge_refunded(data):
    logger.info(f"🔁 Charge {data['id']} refunded.")


def handle_payment_failed(data):
    logger.warning(f"❌ Payment failed for intent {data['id']}.")
