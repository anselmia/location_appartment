import stripe
import logging
from django.conf import settings
from logement.models import Reservation
from logement.services.email_service import (
    send_mail_on_new_reservation,
    send_mail_on_refund,
)


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
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {"reservation_id": reservation.id},
            }

            # Request card to be saved if no card is saved yet
            if not user_has_saved_card(customer_id):
                session_args["payment_intent_data"] = {
                    "setup_future_usage": "off_session"
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
        except Exception as e:
            logger.exception(
                f"Failed to create Stripe customer for user {user.id}: {e}"
            )
            raise

    if not customer_id:
        logger.error(
            f"Failed to create or retrieve Stripe customer for user {user.id} {user.username}"
        )
        raise Exception("Failed to create or retrieve Stripe customer.")

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
            logger.warning("⚠️ No refund data found in webhook event.")

    except Reservation.DoesNotExist:
        logger.warning(f"⚠️ Reservation {reservation_id} not found.")
    except Exception as e:
        logger.exception(f"❌ Unexpected error handling charge.refunded: {e}")
        raise


def handle_payment_intent_succeeded(data):
    metadata = data.get("metadata", {})
    payment_type = metadata.get("type")

    if not payment_type:
        logger.warning("No 'type' metadata found in payment intent.")
        return

    if payment_type == "deposit":
        payment_intent_id = data.get("id")
        reservation_id = metadata.get("reservation_id")
        amount = data.get("amount_received") / 100

        logger.info(
            f"✅ Dépôt reçu: {amount:.2f} € via PaymentIntent {payment_intent_id}"
        )

        if reservation_id:
            try:
                reservation = Reservation.objects.get(pk=reservation_id)
                reservation.caution_charged = True
                reservation.amount_charged += amount
                reservation.stripe_deposit_payment_intent_id = payment_intent_id
                reservation.save()
                logger.info(
                    f"🏠 Confirmation de charge sur Caution enregistrée pour réservation {reservation.pk}, montant: {amount:.2f}"
                )
            except Reservation.DoesNotExist:
                logger.warning(f"⚠️ Réservation introuvable pour ID: {reservation_id}")
        else:
            logger.warning("⚠️ Aucun reservation_id fourni dans les metadata.")


def handle_payment_failed(data):
    customer_id = data.get("customer")
    logger.warning(f"⚠️ Paiement échoué pour client Stripe {customer_id}: {data}")


def handle_checkout_session_completed(data):
    reservation_id = data["metadata"].get("reservation_id")
    payment_intent_id = data.get("payment_intent")
    logger.info(
        f"🔔 Handling checkout.session.completed for reservation {reservation_id}"
    )

    try:
        reservation = Reservation.objects.get(id=reservation_id)

        if reservation.statut != "confirmee":
            try:
                intent = stripe.PaymentIntent.retrieve(
                    payment_intent_id, expand=["payment_method"]
                )
                payment_method = intent.payment_method

                if not payment_method:
                    raise ValueError(
                        f"No payment method found on PaymentIntent {payment_intent_id}"
                    )

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

        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            customer=customer_id,
            payment_method=saved_payment_method_id,
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
