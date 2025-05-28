import stripe
import logging
from django.urls import reverse
from django.conf import settings

from logement.services.email_service import send_mail_on_new_reservation, send_mail_on_refund, send_mail_on_new_transfer
from common.services.stripe.stripe_event import (
    StripeCheckoutSessionEventData,
    StripeChargeEventData,
    StripePaymentIntentEventData,
    StripeTransferEventData,
)
from decimal import Decimal, ROUND_UP, ROUND_HALF_UP


logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_PRIVATE_KEY
PLATFORM_FEE = 0.05
PAYMENT_FEE_VARIABLE = 0.025
PAYMENT_FEE_FIX = 0.25


def get_payment_fee(price):
    # Convert all constants to Decimal FIRST
    variable_fee = Decimal(str(PAYMENT_FEE_VARIABLE))
    fixed_fee = Decimal(str(PAYMENT_FEE_FIX))

    # Ensure price is Decimal
    price = Decimal(price)

    fee = (variable_fee * price) + fixed_fee
    return fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_platform_fee(price):
    price = Decimal(price)
    platform_rate = Decimal(str(PLATFORM_FEE))
    fee = platform_rate * price
    return fee.quantize(Decimal("0.01"), rounding=ROUND_UP)


def create_stripe_checkout_session_with_deposit(reservation, request):
    from common.services.network import get_client_ip

    ip = get_client_ip(request)
    try:
        logger.info(
            f"⚙️ Creating Stripe checkout session with deposit for reservation {reservation.code} | "
            f"user={reservation.user.id} email={reservation.user.email} logement={reservation.logement.name} | IP: {ip}"
        )

        # Ensure the user has a Stripe customer ID
        customer_id = create_stripe_customer_if_not_exists(reservation.user, request)

        if not customer_id:
            logger.error(f"❌ No customer ID returned from Stripe for user {reservation.user.id}, IP: {ip}")
            raise Exception("Customer ID creation failed.")

        # Validate and convert amount
        if reservation.price <= 0:
            logger.error(
                f"❌ Invalid reservation price ({reservation.price}) for reservation {reservation.code}, IP: {ip}"
            )
            raise ValueError("Reservation price must be positive.")

        amount = int(reservation.price * 100)

        # Build full URLs
        success_url = request.build_absolute_uri(reverse("logement:payment_success", args=[reservation.code]))
        cancel_url = request.build_absolute_uri(reverse("logement:payment_cancel", args=[reservation.code]))

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
                        "unit_amount": amount,
                    },
                    "quantity": 1,
                }
            ],
            "payment_intent_data": {
                "setup_future_usage": "off_session",
                "transfer_group": f"group_{reservation.code}",
            },
            "payment_method_options": {"card": {"setup_future_usage": "off_session"}},
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"code": reservation.code},
        }

        checkout_session = stripe.checkout.Session.create(**session_args)

        logger.info(
            f"✅ Stripe checkout session created for reservation {reservation.code} | session={checkout_session.id} | IP: {ip}"
        )
        logger.debug(f"🔗 Checkout URL: {checkout_session.url}")

        return {
            "checkout_session_url": checkout_session.url,
            "session_id": checkout_session.id,
        }

    except stripe.error.StripeError as e:
        logger.exception(
            f"❌ Stripe error creating checkout session for reservation {reservation.code}, IP: {ip}: {e.user_message or str(e)}"
        )
        raise
    except Exception as e:
        logger.exception(
            f"❌ Unexpected error creating checkout session for reservation {reservation.code}, IP: {ip}: {str(e)}"
        )
        raise


def create_stripe_customer_if_not_exists(user, request):
    try:
        from common.services.network import get_client_ip

        ip = get_client_ip(request)

        if user.stripe_customer_id:
            logger.info(f"ℹ️ Stripe customer already exists for user {user.id} ({user.email}) IP: {ip}")
            return user.stripe_customer_id

        if not user.email:
            logger.error(f"❌ Cannot create Stripe customer: user {user.id} has no email.")
            raise ValueError("User must have an email to create a Stripe customer.")

        logger.info(f"🔧 Creating Stripe customer for user {user.id} ({user.email})")
        customer = stripe.Customer.create(
            email=user.email,
            name=getattr(user, "name", None) or user.email,  # fallback if name missing
            metadata={"user_id": str(user.id)},
        )

        if not customer or not getattr(customer, "id", None):
            logger.error(f"❌ Stripe returned invalid customer object for user {user.id}")
            raise Exception("Stripe customer creation failed.")

        user.stripe_customer_id = customer.id
        user.save(update_fields=["stripe_customer_id"])
        logger.info(f"✅ Stripe customer created: {customer.id} for user {user.id}, IP: {ip}")

        return customer.id

    except stripe.error.StripeError as e:
        logger.exception(f"❌ Stripe error while creating customer for user {user.id}: {e.user_message or str(e)}")
        raise
    except Exception as e:
        logger.exception(f"❌ Failed to create Stripe customer for user {user.id}: {str(e)}")
        raise


def refund_payment(reservation, refund="full", amount_cents=None):
    try:
        logger.info(f"💸 Initiating refund for reservation {reservation.code}")

        params = {
            "payment_intent": reservation.stripe_payment_intent_id,
            "metadata": {"code": reservation.code, "refund": refund},
        }
        if amount_cents:
            params["amount"] = int(amount_cents)

        refund = stripe.Refund.create(**params)
        logger.info(f"✅ Refund processed: {refund.id}, Amount: {params.get('amount', 'full')} cents")
        return refund

    except stripe.error.StripeError as e:
        logger.exception(f"❌ Stripe refund error: {e}")
        raise

    except Exception as e:
        logger.exception(f"❌ Unexpected refund error: {e}")
        raise


def handle_charge_refunded(data: StripeChargeEventData):
    from logement.models import Reservation

    reservation_code = None
    try:
        metadata = data.object.metadata or {}
        reservation_code = metadata.get("code")
        if not reservation_code:
            logger.warning("⚠️ No reservation code found in the refund event metadata.")
            return

        refund = metadata.get("refund")
        if not refund:
            logger.warning("⚠️ No refound type found in the refund event metadata.")
            return

        logger.info(f"🔔 Handling charge.refunded for reservation {reservation_code}")

        try:
            reservation = Reservation.objects.get(code=reservation_code)
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found.")
            return

        amount = data.object.amount
        refund_id = data.object.id
        currency = data.object.currency or "eur"

        if not amount or amount <= 0:
            logger.warning(f"⚠️ Invalid or missing refund amount for event {refund_id}")
            return

        refunded_amount = Decimal(amount) / 100  # Convert cents to euros

        # Prevent duplicate processing based on refund ID
        if reservation.stripe_refund_id == refund_id:
            logger.info(f"ℹ️ Refund {refund_id} already recorded for reservation {reservation.code}.")
            return

        # Ensure existing refund_amount is a Decimal
        try:
            current_refund = Decimal(reservation.refund_amount or 0)
        except Exception:
            logger.warning(f"⚠️ Could not parse refund_amount on reservation {reservation.code}, defaulting to 0.")
            current_refund = Decimal(0)

        reservation.refunded = True
        reservation.refund_amount = current_refund + refunded_amount
        reservation.stripe_refund_id = refund_id
        if refund == "full":
            reservation.plaform_fee = 0
        reservation.save(update_fields=["refunded", "refund_amount", "stripe_refund_id", "platform_fee"])

        logger.info(
            f"💶 Refund ID: {refund_id}, Amount: {refunded_amount:.2f} {currency.upper()} recorded for reservation {reservation.code}"
        )

        try:
            send_mail_on_refund(reservation.logement, reservation, reservation.user)
            logger.info(f"📧 Refund notification sent for reservation {reservation.code}")
        except Exception as e:
            logger.exception(f"❌ Error sending refund email for reservation {reservation.code}: {e}")

    except Exception as e:
        logger.exception(
            f"❌ Unexpected error handling charge.refunded for reservation {reservation_code or '[unknown]'}: {e}"
        )


def handle_payment_intent_succeeded(data: StripePaymentIntentEventData):
    try:
        metadata = data.object.metadata or {}
        payment_type = metadata.get("type")

        if not payment_type:
            logger.warning("⚠️ No 'type' metadata found in payment intent.")
            return

        if payment_type != "deposit":
            logger.info("ℹ️ Payment type is not 'deposit', skipping.")
            return

        payment_intent_id = data.object.id
        reservation_code = metadata.get("code")
        amount_cents = data.object.amount_received

        if amount_cents is None or amount_cents <= 0:
            logger.warning(f"⚠️ Invalid deposit amount on PaymentIntent {payment_intent_id}.")
            return

        amount = Decimal(amount_cents) / 100  # Convert to euros
        logger.info(f"✅ Deposit received: {amount:.2f} € via PaymentIntent {payment_intent_id}")

        if not reservation_code:
            logger.warning("⚠️ No reservation code provided in metadata.")
            return

        try:
            reservation = Reservation.objects.get(code=reservation_code)
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found.")
            return

        # Prevent double processing
        if reservation.caution_charged:
            logger.info(f"ℹ️ Reservation {reservation.code} already marked as deposit charged.")

        # Safely convert and update amount_charged
        try:
            existing_amount = Decimal(reservation.amount_charged or 0)
        except Exception:
            logger.warning(f"⚠️ Failed to parse reservation.amount_charged for {reservation.code}, defaulting to 0.")
            existing_amount = Decimal(0)

        reservation.amount_charged = existing_amount + amount
        reservation.caution_charged = True
        reservation.stripe_deposit_payment_intent_id = payment_intent_id
        reservation.save(
            update_fields=[
                "amount_charged",
                "caution_charged",
                "stripe_deposit_payment_intent_id",
            ]
        )

        logger.info(f"🏠 Deposit charge confirmed for reservation {reservation.code}, amount: {amount:.2f} €")

    except Exception as e:
        logger.exception(f"❌ Unexpected error in handle_payment_intent_succeeded: {str(e)}")


def handle_payment_failed(data: StripePaymentIntentEventData):
    from logement.models import Reservation

    try:
        metadata = data.object.metadata or {}
        customer_id = data.customer
        payment_intent_id = data.object.id
        failure_message = data.object.last_payment_error.message if data.object.last_payment_error else None
        failure_code = data.object.last_payment_error.code if data.object.last_payment_error else None

        if failure_message:
            logger.warning(f"💥 Payment failure message: {failure_message}")
        if failure_code:
            logger.warning(f"� Stripe failure code: {failure_code}")

        reservation_code = metadata.get("code", "[unknown]")

        if not reservation_code:
            logger.warning(f"⚠️ No reservation code found in failed payment event {payment_intent_id}.")
        if not customer_id:
            logger.warning(f"⚠️ No customer ID found in failed payment event {payment_intent_id}.")

        logger.warning(
            f"⚠️ Payment failed for reservation {reservation_code}, customer {customer_id or '[unknown]'}, PaymentIntent {payment_intent_id}."
        )

        if failure_message:
            logger.warning(f"💥 Payment failure message: {failure_message}")
        if failure_code:
            logger.warning(f"📛 Stripe failure code: {failure_code}")

        # Optional: update reservation status or alert staff
        try:
            reservation = Reservation.objects.get(code=reservation_code)
            if reservation.statut != "confirmee":
                reservation.statut = "echec_paiement"
                reservation.save(update_fields=["statut"])
                logger.info(f"🚫 Reservation {reservation.code} marked as payment failed.")
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found in DB.")
        except Exception as e:
            logger.exception(f"❌ Unexpected error updating reservation {reservation_code} on payment failure: {e}")

    except Exception as e:
        logger.exception(f"❌ Unexpected error handling payment_intent.payment_failed event: {str(e)}")


def handle_checkout_session_completed(data: StripeCheckoutSessionEventData):
    from logement.models import Reservation

    reservation_code = None  # define early to use in exception messages
    try:
        # Extract metadata and payment intent ID from event
        reservation_code = data.object.metadata.get("code")
        payment_intent_id = data.object.payment_intent

        if not reservation_code or not payment_intent_id:
            logger.error("❌ Invalid Stripe session: missing reservation code or payment intent.")
            return

        logger.info(f"🔔 Handling checkout.session.completed for reservation {reservation_code}")

        try:
            reservation = Reservation.objects.get(code=reservation_code)
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found.")
            return

        if reservation.statut == "confirmee":
            logger.info(f"ℹ️ Reservation {reservation.code} already confirmed.")
            return

        # Retrieve the PaymentIntent with expanded payment method
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["payment_method"])
        except stripe.error.StripeError as e:
            logger.exception(
                f"❌ Stripe API error while retrieving intent {payment_intent_id}: {e.user_message or str(e)}"
            )
            return

        if intent.status != "succeeded":
            logger.warning(
                f"⚠️ PaymentIntent {payment_intent_id} has unexpected status '{intent.status}' "
                f"for reservation {reservation.code}. Aborting confirmation."
            )
            return

        payment_method = intent.payment_method
        if not payment_method or not getattr(payment_method, "id", None):
            logger.error(f"❌ No valid payment method found for intent {payment_intent_id}")
            return

        # Save payment method if not already saved
        if not reservation.stripe_saved_payment_method_id:
            reservation.stripe_saved_payment_method_id = payment_method.id
            logger.info(f"💾 Saved payment method {payment_method.id} for reservation {reservation.code}")

        # Confirm reservation and save PaymentIntent ID
        reservation.stripe_payment_intent_id = payment_intent_id
        reservation.statut = "confirmee"
        reservation.save(
            update_fields=[
                "stripe_payment_intent_id",
                "stripe_saved_payment_method_id",
                "statut",
            ]
        )
        logger.info(f"✅ Reservation {reservation.code} confirmed")

        # Try sending the confirmation email (non-blocking)
        try:
            send_mail_on_new_reservation(reservation.logement, reservation, reservation.user)
            logger.info(f"📧 Confirmation email sent for reservation {reservation.code}")
        except Exception as e:
            logger.exception(f"❌ Error sending confirmation email for reservation {reservation.code}: {e}")

    except Exception as e:
        logger.exception(
            f"❌ Unexpected error handling checkout.session.completed for reservation {reservation_code or '[unknown]'}: {e}"
        )


def charge_payment(saved_payment_method_id, amount_cents, customer_id, reservation, currency="eur"):
    try:
        if not saved_payment_method_id:
            raise ValueError("Missing saved payment method ID.")

        if not customer_id:
            raise ValueError("Customer ID is required to charge a saved payment method.")

        logger.info(f"🔄 Retrieving PaymentMethod {saved_payment_method_id} for customer {customer_id}")
        payment_method = stripe.PaymentMethod.retrieve(saved_payment_method_id)

        # Attach if not already attached
        if payment_method.customer != customer_id:
            logger.info(f"🔗 Attaching PaymentMethod {saved_payment_method_id} to Customer {customer_id}.")
            stripe.PaymentMethod.attach(saved_payment_method_id, customer=customer_id)

        logger.info(f"💳 Creating PaymentIntent of {amount_cents} cents for reservation {reservation.code}")
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            customer=customer_id,
            payment_method=saved_payment_method_id,
            confirm=True,
            off_session=True,
            description=f"Charge sur caution location {reservation.logement.name}",
            metadata={
                "type": "deposit",
                "code": str(reservation.code),
                "logement_id": reservation.logement.id,
            },
        )

        logger.info(f"✅ Payment successful for reservation {reservation.code}, intent ID: {intent.id}")
        return intent

    except stripe.error.CardError as e:
        # Declines, etc.
        logger.error(f"❌ Carte refusée pour la réservation {reservation.code} : {e.user_message}")
        raise ValueError(f"Carte refusée : {e.user_message}")

    except stripe.error.InvalidRequestError as e:
        logger.error(f"❌ Mauvaise requête Stripe (paramètre invalide) : {e.user_message or str(e)}")
        raise

    except stripe.error.AuthenticationError as e:
        logger.critical(f"❌ Authentification Stripe invalide. Vérifiez la clé API: {e}.")
        raise

    except stripe.error.APIConnectionError as e:
        logger.error(f"❌ Erreur de connexion réseau avec Stripe: {e}")
        raise

    except stripe.error.StripeError as e:
        logger.exception("❌ Erreur Stripe générale inattendue : %s", str(e))
        raise

    except Exception as e:
        logger.exception(
            "❌ Erreur interne lors du chargement du paiement pour la réservation %s : %s",
            reservation.code,
            str(e),
        )
        raise


def charge_reservation(reservation):
    try:
        logger.info(f"💼 Preparing transfer for reservation {reservation.code}")

        if reservation.transferable_amount <= 0:
            logger.warning(
                f"⚠️ Owner amount is non-positive ({reservation.transferable_amount}) for reservation {reservation.code}. Skipping transfer."
            )
            return

        transferable_amount = reservation.transferable_amount
        owner_amount = transferable_amount
        admin_amount = 0

        if reservation.logement.admin:
            admin_amount = transferable_amount * reservation.admin_fee_rate
            owner_amount = transferable_amount - admin_amount

            admin_account = reservation.logement.owner.stripe_account_id
            if not admin_account:
                logger.error(f"❌ Missing Stripe account ID for admin of reservation {reservation.code}")
                return

            # Perform the transfer
            transfer = stripe.Transfer.create(
                amount=int(admin_amount * 100),
                currency="eur",
                destination=admin_account,
                transfer_group=f"group_{reservation.code}",
                metadata={"code": reservation.code, "logement": reservation.logement.code, "transfer": "admin"},
            )

            logger.info(f"✅ Admin payout transferred for reservation {reservation.code} (transfer ID: {transfer.id})")

        owner_account = reservation.logement.owner.stripe_account_id
        if not owner_account:
            logger.error(f"❌ Missing Stripe account ID for owner of reservation {reservation.code}")
            return

        # Perform the transfer
        transfer = stripe.Transfer.create(
            amount=int(owner_amount * 100),
            currency="eur",
            destination=owner_account,
            transfer_group=f"group_{reservation.code}",
            metadata={"code": reservation.code, "logement": reservation.logement.code, "transfer": "owner"},
        )

        logger.info(f"✅ Owner payout transferred for reservation {reservation.code} (transfer ID: {transfer.id})")

    except stripe.error.InvalidRequestError as e:
        logger.exception(
            f"❌ Invalid request to Stripe during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
        )
    except stripe.error.AuthenticationError as e:
        logger.exception(
            f"❌ Authentication with Stripe failed during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
        )
    except stripe.error.APIConnectionError as e:
        logger.exception(
            f"❌ Network error with Stripe during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
        )
    except stripe.error.StripeError as e:
        logger.exception(
            f"❌ General Stripe error during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
        )
    except Exception as e:
        logger.exception(f"❌ Unexpected error during transfer for reservation {reservation.code}: {str(e)}")
        raise


def handle_transfer_paid(data: StripeTransferEventData):
    from logement.models import Reservation

    try:
        transfer_id = data.object.id
        amount = Decimal(data.object.amount) / 100
        currency = data.object.currency.upper()
        destination = data.object.destination
        metadata = data.object.metadata or {}
        reservation_code = metadata.get("code")
        if not reservation_code:
            logger.warning("⚠️ No reservation code found in the refund event metadata.")
            return
        transfer_user = metadata.get("transfer")
        if not transfer_user:
            logger.warning("⚠️ No reservation user found in the refund event metadata.")
            return

        logger.info(f"✅ Transfer succeeded: {transfer_id} | {amount:.2f} {currency} to {destination}")

        try:
            if transfer_user == "owner":
                reservation = Reservation.objects.get(code=reservation_code)
                reservation.transferred = True
                reservation.stripe_transfer_id = transfer_id
                reservation.transferred_amount = amount / 100
                reservation.save(update_fields=["transferred", "stripe_transfer_id", "transferred_amount"])
                logger.info(f"📦 Transfer recorded to owner for reservation {reservation_code}")
            elif transfer_user == "admin":
                reservation = Reservation.objects.get(code=reservation_code)
                reservation.admin_transferred = True
                reservation.admin_transferred_amount = amount / 100
                reservation.admin_stripe_transfer_id = transfer_id
                reservation.save(
                    update_fields=["admin_transferred", "admin_stripe_transfer_id", "admin_transferred_amount"]
                )
                logger.info(f"📦 Transfer recorded to admin for reservation {reservation_code}")
            else:
                logger.error(
                    f"📦 Incorrect user {transfer_user} defined for Transfer for reservation {reservation_code}"
                )
                return
            # Try sending the confirmation email (non-blocking)
            try:
                send_mail_on_new_transfer(reservation.logement, reservation, transfer_user)
                logger.info(f"📧 transfer email sent for reservation {reservation.code}")
            except Exception as e:
                logger.exception(f"❌ Error sending confirmation email for reservation {reservation.code}: {e}")
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found for transfer {transfer_id}")

    except Exception as e:
        logger.exception(f"❌ Error handling transfer.paid: {e}")


def handle_transfer_failed(data: StripeTransferEventData):
    from logement.models import Reservation

    try:
        transfer_id = data.object.id
        amount = Decimal(data.object.amount) / 100
        currency = data.object.currency.upper()
        destination = data.object.destination
        failure_message = getattr(data.object, "failure_message", "Unknown error")
        transfer_group = data.object.transfer_group

        logger.warning(
            f"❌ Transfer FAILED: {transfer_id} | {amount:.2f} {currency} to {destination} | Reason: {failure_message}"
        )

        if transfer_group and transfer_group.startswith("group_"):
            reservation_code = transfer_group.replace("group_", "")
            try:
                reservation = Reservation.objects.get(code=reservation_code)
                reservation.transfer_status = "failed"
                reservation.save(update_fields=["transfer_status"])
                logger.warning(f"🔁 Transfer marked as failed on reservation {reservation_code}")
                # Optional: notify admin via email or dashboard
            except Reservation.DoesNotExist:
                logger.warning(f"⚠️ Reservation {reservation_code} not found for failed transfer {transfer_id}")
        else:
            logger.warning(f"⚠️ No valid transfer group in failed transfer {transfer_id}")

    except Exception as e:
        logger.exception(f"❌ Error handling transfer.failed: {e}")
