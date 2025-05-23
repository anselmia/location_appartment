import stripe
import logging
from django.conf import settings


from logement.models import (
    Reservation,
)

from logement.services.email_service import (
    send_mail_on_new_reservation,
    send_mail_on_refund,
)


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


def user_has_saved_card(stripe_customer_id):
    try:
        payment_methods = stripe.PaymentMethod.list(
            customer=stripe_customer_id, type="card"
        )
        return len(payment_methods.data) > 0
    except Exception as e:
        logger.exception(f"❌ Failed to check saved cards: {e}")
        return False


def create_stripe_checkout_session_with_deposit(reservation, success_url, cancel_url):
    try:
        # Ensure the user has a Stripe customer ID
        customer_id = create_stripe_customer_if_not_exists(reservation.user)

        if customer_id:
            # Create the Stripe Checkout session
            session_args = {
                "payment_method_types": ["card"],
                "mode": "payment",
                "customer": customer_id,
                "line_items": [
                    {
                        "price_data": {
                            "currency": "eur",
                            "product_data": {
                                "name": f"Réservation - {reservation.logement.name}",
                            },
                            "unit_amount": int(reservation.price * 100),
                        },
                        "quantity": 1,
                    }
                ],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"reservation_id": reservation.id},
            }

            # ✅ Only request card to be saved if none is saved yet
            if not user_has_saved_card(customer_id):
                session_args["payment_intent_data"] = {
                    "setup_future_usage": "off_session"
                }

            try:
                checkout_session = stripe.checkout.Session.create(**session_args)
            except Exception as e:
                logger.exception(f"Erreur Stripe: {e}")
                raise

            return {
                "checkout_session_url": checkout_session.url,
                "session_id": checkout_session.id,
            }
        else:
            logger.exception("No customer ID returned from Stripe")
            raise

    except Exception as e:
        logger.exception(f"Erreur Stripe: {e}")
        raise


def create_stripe_customer_if_not_exists(user):
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.name,
        )
        user.stripe_customer_id = customer.id
        user.save()
    return user.stripe_customer_id


def refund_payment(payment_intent_id, amount_cents=None):
    try:
        params = {"payment_intent": payment_intent_id}
        if amount_cents is not None:
            params["amount"] = amount_cents

        return stripe.Refund.create(**params)
    except stripe.error.StripeError as e:
        logger.exception(f"Stripe refund error: {e}")
        raise


def handle_charge_refunded(data):
    reservation_id = data["metadata"].get("reservation_id")
    logger.info(f"🔔 Handling charge.refunded for reservation {reservation_id}")

    try:
        reservation = Reservation.objects.get(id=reservation_id)

        # Get refunded amount from the charge object
        refunds = data.get("refunds", {}).get("data", [])
        if refunds:
            latest_refund = refunds[-1]  # If multiple refunds, get the last one
            refunded_amount = latest_refund["amount"] / 100  # convert to euros
            refund_id = latest_refund["id"]

            reservation.refunded = True
            reservation.refund_amount += refunded_amount
            reservation.statut = "annulee"
            reservation.stripe_refund_id = refund_id
            reservation.save()

            currency = latest_refund.get("currency", "eur").upper()
            logger.info(
                f"💶 Refund ID: {refund_id}, Amount: {refunded_amount:.2f} {currency}"
            )

            try:
                send_mail_on_refund(reservation.logement, reservation, reservation.user)
            except Exception as e:
                logger.exception(f"❌ Error sending refund email: {e}")
        else:
            refunded_amount = None
            logger.warning("⚠️ No refund data found in webhook event.")

    except Reservation.DoesNotExist:
        logger.warning(f"⚠️ Reservation {reservation_id} not found.")
    except Exception as e:
        logger.exception(
            f"❌ Unexpected error handling checkout.session.completed: {e}"
        )
        raise


def handle_payment_failed(data):
    logger.warning(f"❌ Payment failed for intent {data['id']}.")


def handle_checkout_session_completed(data):
    reservation_id = data["metadata"].get("reservation_id")
    payment_intent_id = data.get("payment_intent")
    logger.info(
        f"🔔 Handling checkout.session.completed for reservation {reservation_id}"
    )

    try:
        reservation = Reservation.objects.get(id=reservation_id)

        if reservation.statut != "confirmee":
            # Retrieve the full payment intent including attached method
            try:
                intent = stripe.PaymentIntent.retrieve(
                    payment_intent_id, expand=["payment_method"]
                )
                payment_method = intent.payment_method

                if not payment_method:
                    raise ValueError(
                        f"No payment method found on PaymentIntent {payment_intent_id}"
                    )

                # Save payment method if not already saved
                if not reservation.stripe_saved_payment_method_id:
                    reservation.stripe_saved_payment_method_id = payment_method.id
                    logger.info(
                        f"💾 Saved payment method {payment_method.id} for reservation {reservation.id}"
                    )

            except Exception as e:
                logger.exception(
                    f"❌ Failed to retrieve or validate payment method: {e}"
                )
                raise  # re-raise to avoid falsely confirming

            # Save payment and confirm reservation
            reservation.stripe_payment_intent_id = payment_intent_id
            reservation.statut = "confirmee"
            reservation.save()
            logger.info(f"✅ Reservation {reservation.id} confirmed")

            try:
                send_mail_on_new_reservation(
                    reservation.logement, reservation, reservation.user
                )
            except Exception as e:
                logger.exception(f"❌ Error sending confirmation email: {e}")

        else:
            logger.info(f"ℹ️ Reservation {reservation.id} already confirmed.")

    except Reservation.DoesNotExist:
        logger.warning(f"⚠️ Reservation {reservation_id} not found.")
    except Exception as e:
        logger.exception(
            f"❌ Unexpected error handling checkout.session.completed: {e}"
        )
        raise
