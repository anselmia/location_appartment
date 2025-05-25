import stripe
import logging
from django.conf import settings
from logement.models import Reservation
from logement.services.email_service import (
    send_mail_on_new_reservation,
    send_mail_on_refund,
)
from common.services.stripe.stripe_event import (
    StripeCheckoutSessionEventData,
    StripeChargeEventData,
    StripePaymentIntentEventData,
)
from decimal import Decimal


logger = logging.getLogger(__name__)
# Set up Stripe with the secret key
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def create_stripe_checkout_session(reservation, success_url, cancel_url):
    try:
        logger.info(
            f"Creating Stripe checkout session for reservation {reservation.id}."
        )

        session = stripe.checkout.Session.create(
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
        logger.info(
            f"Checkout session created successfully for reservation {reservation.id}. Session ID: {session.id}"
        )
        return session
    except Exception as e:
        logger.exception(f"Erreur Stripe: {e}")
        raise


def user_has_saved_card(stripe_customer_id):
    try:
        logger.info(
            f"Checking for saved cards for Stripe customer {stripe_customer_id}."
        )
        payment_methods = stripe.PaymentMethod.list(
            customer=stripe_customer_id, type="card"
        )
        has_saved_cards = len(payment_methods.data) > 0
        logger.debug(f"Saved cards found: {has_saved_cards}")
        return has_saved_cards
    except Exception as e:
        logger.exception(f"❌ Failed to check saved cards: {e}")
        return False


def create_stripe_checkout_session_with_deposit(reservation, success_url, cancel_url):
    try:
        logger.info(
            f"Creating Stripe checkout session with deposit for reservation {reservation.id}."
        )

        # Ensure the user has a Stripe customer ID
        customer_id = create_stripe_customer_if_not_exists(reservation.user)

        if customer_id:
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
                "payment_intent_data": {"setup_future_usage": "off_session"},
                "payment_method_options": {
                    "card": {"setup_future_usage": "off_session"}
                },
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"reservation_id": reservation.id},
            }

            checkout_session = stripe.checkout.Session.create(**session_args)
            logger.info(
                f"Checkout session with deposit created successfully for reservation {reservation.id}."
            )
            logger.debug(
                f"Session created: {checkout_session.id}, URL: {checkout_session.url}"
            )
            return {
                "checkout_session_url": checkout_session.url,
                "session_id": checkout_session.id,
            }
        else:
            logger.warning(
                f"No customer ID returned from Stripe for user {reservation.user.id}."
            )
            raise Exception("Customer ID creation failed.")
    except Exception as e:
        logger.exception(f"Erreur Stripe: {e}")
        raise


def create_stripe_customer_if_not_exists(user):
    customer_id = None

    if not user.stripe_customer_id:
        try:
            logger.info(f"Creating Stripe customer for user {user.id}.")
            customer = stripe.Customer.create(
                email=user.email,
                name=user.name,
            )
            user.stripe_customer_id = customer.id
            user.save()
            customer_id = customer.id
            logger.info(f"Stripe customer created for user {user.id}.")

            if not customer_id:
                logger.error(
                    f"Failed to create or retrieve Stripe customer for user {user.id} {user.username}"
                )
                raise Exception("Failed to create or retrieve Stripe customer.")

        except Exception as e:
            logger.exception(
                f"Failed to create Stripe customer for user {user.id}: {e}"
            )
            raise

    return user.stripe_customer_id


def refund_payment(reservation, amount_cents=None):
    try:
        logger.info(f"Initiating refund for reservation {reservation.id}.")

        params = {
            "payment_intent": reservation.stripe_payment_intent_id,
            "metadata": {"reservation_id": reservation.id},
        }
        if amount_cents is not None:
            amount_cents = int(
                amount_cents
            )  # Convert to integer (removes decimal places)
            params["amount"] = amount_cents

        refund = stripe.Refund.create(**params)
        logger.info(
            f"Refund successfully processed for reservation {reservation.id}. Refund ID: {refund.id}"
        )
        return refund
    except stripe.error.StripeError as e:
        logger.exception(f"Stripe refund error: {e}")
        raise Exception(f"Refund failed for reservation {reservation.id}. Error: {e}")


def handle_charge_refunded(data: StripeChargeEventData):
    try:
        reservation_id = data.object.metadata.get("reservation_id")
        if not reservation_id:
            logger.warning("⚠️ No reservation_id found in the refund event metadata.")
            return

        logger.info(f"🔔 Handling charge.refunded for reservation {reservation_id}")

        reservation = Reservation.objects.get(id=reservation_id)

        amount = data.object.amount
        if amount:
            refunded_amount = amount / 100  # Convert to euros
            refund_id = data.object.id

            reservation.refunded = True
            refunded_amount_decimal = Decimal(refunded_amount)

            # Ensure reservation.refund_amount is a Decimal (if it isn't already)
            if not isinstance(reservation.refund_amount, Decimal):
                reservation.refund_amount = Decimal(reservation.refund_amount)

            reservation.refund_amount += refunded_amount_decimal
            reservation.stripe_refund_id = refund_id
            reservation.save()

            currency = (
                data.object.currency or "eur"
            )  # Default to "eur" if no currency provided
            logger.info(
                f"💶 Refund ID: {refund_id}, Amount: {refunded_amount:.2f} {currency.upper()}"
            )

            try:
                send_mail_on_refund(reservation.logement, reservation, reservation.user)
            except Exception as e:
                logger.exception(f"❌ Error sending refund email: {e}")
        else:
            logger.warning("⚠️ No refund amount found in the webhook event.")
    except Reservation.DoesNotExist:
        logger.warning(f"⚠️ Reservation {reservation_id} not found.")
    except Exception as e:
        logger.exception(f"❌ Unexpected error handling charge.refunded: {e}")
        raise


def handle_payment_intent_succeeded(data: StripePaymentIntentEventData):
    metadata = data.object.metadata or {}
    payment_type = metadata.get("type")

    if not payment_type:
        logger.warning("⚠️ No 'type' metadata found in payment intent.")
        return

    if payment_type == "deposit":
        payment_intent_id = data.object.id
        reservation_id = metadata.get("reservation_id")
        amount = data.object.amount_received / 100  # Convert to euros

        logger.info(
            f"✅ Deposit received: {amount:.2f} € via PaymentIntent {payment_intent_id}"
        )

        if reservation_id:
            try:
                reservation = Reservation.objects.get(pk=reservation_id)
                reservation.caution_charged = True

                caution_charged_decimal = Decimal(amount)

                # Ensure reservation.refund_amount is a Decimal (if it isn't already)
                if not isinstance(reservation.amount_charged, Decimal):
                    reservation.amount_charged = Decimal(reservation.amount_charged)

                reservation.amount_charged += caution_charged_decimal
                reservation.stripe_deposit_payment_intent_id = payment_intent_id
                reservation.save()
                logger.info(
                    f"🏠 Caution charge confirmed for reservation {reservation.pk}, amount: {amount:.2f} €"
                )
            except Reservation.DoesNotExist:
                logger.warning(f"⚠️ Reservation {reservation_id} not found.")
        else:
            logger.warning("⚠️ No reservation_id provided in metadata.")
    else:
        logger.info("ℹ️ Payment type is not 'deposit', skipping deposit handling.")


def handle_payment_failed(data: StripePaymentIntentEventData):
    # Extract customer_id, payment_intent_id, and failure_reason
    customer_id = (
        data.customer
    )  # This is directly available in the structured event data
    payment_intent_id = data.id  # Access payment intent ID directly
    failure_reason = data.failure_message  # Extract failure reason if available

    if not customer_id:
        logger.warning("⚠️ No customer ID found in failed payment event.")
        return

    # Log the payment failure event
    logger.warning(
        f"⚠️ Payment failed for customer {customer_id}, PaymentIntent {payment_intent_id}. Failure reason: {failure_reason}. Event Data: {data}"
    )

    # Additional logging based on the failure reason (if available)
    if failure_reason:
        logger.warning(f"💥 Payment failure reason: {failure_reason}")


def handle_checkout_session_completed(data: StripeCheckoutSessionEventData):
    try:
        # Extracting reservation_id and payment_intent from the structured event data
        reservation_id = data.object.metadata.get("reservation_id")
        payment_intent_id = data.object.payment_intent
        logger.info(
            f"🔔 Handling checkout.session.completed for reservation {reservation_id}"
        )

        # Attempting to retrieve the reservation from the database
        reservation = Reservation.objects.get(id=reservation_id)

        # Check if the reservation is already confirmed
        if reservation.statut != "confirmee":
            try:
                # Retrieve PaymentIntent and payment method information from Stripe
                intent = stripe.PaymentIntent.retrieve(
                    payment_intent_id, expand=["payment_method"]
                )
                payment_method = intent.payment_method

                # Validate if payment method exists
                if not payment_method:
                    raise ValueError(
                        f"No payment method found on PaymentIntent {payment_intent_id}"
                    )

                # Save the payment method if not already saved
                if not reservation.stripe_saved_payment_method_id:
                    reservation.stripe_saved_payment_method_id = payment_method.id
                    logger.info(
                        f"💾 Saved payment method {payment_method.id} for reservation {reservation.id}"
                    )

            except Exception as e:
                logger.exception(
                    f"❌ Failed to retrieve or validate payment method: {e}"
                )
                raise

            # Update reservation with payment intent and mark it as confirmed
            reservation.stripe_payment_intent_id = payment_intent_id
            reservation.statut = "confirmee"
            reservation.save()
            logger.info(f"✅ Reservation {reservation.id} confirmed")

            # Send confirmation email to the user and admins
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


def charge_payment(
    saved_payment_method_id, amount_cents, customer_id, reservation, currency="eur"
):
    try:
        if not saved_payment_method_id:
            raise ValueError("Missing saved payment method ID.")

        if not customer_id:
            raise ValueError(
                "Customer ID is required to charge a saved payment method."
            )

        # Check if the PaymentMethod is already attached to the Customer
        payment_method = stripe.PaymentMethod.retrieve(saved_payment_method_id)

        # If not attached, attach the PaymentMethod to the customer
        if payment_method.customer != customer_id:
            logger.info(
                f"Attaching PaymentMethod {saved_payment_method_id} to Customer {customer_id}."
            )
            stripe.PaymentMethod.attach(saved_payment_method_id, customer=customer_id)

        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            customer=customer_id,
            payment_method=payment_method.id,
            confirm=True,
            off_session=True,
            description=f"Charge sur caution location {reservation.logement.name}",
            metadata={"type": "deposit", "reservation_id": str(reservation.id)},
        )
        logger.info(
            f"Charge payment of {amount_cents} cents successful for reservation {reservation.id}."
        )
        return intent

    except stripe.error.CardError as e:
        logger.error(f"Carte refusée : {e.user_message}")
        raise

    except stripe.error.StripeError as e:
        logger.exception("Erreur Stripe inattendue : %s", str(e))
        raise

    except Exception as e:
        logger.exception("Erreur interne lors du chargement du paiement : %s", str(e))
        raise


def create_bank_account():
    # stripe.createToken(
    #    country: 'US',
    #    currency: 'usd',
    #    routing_number: '110000000',
    #    account_number: '000123456789',
    #    account_holder_name: 'Jenny Rosen',
    #    account_holder_type: 'individual',
    # )
    pass
