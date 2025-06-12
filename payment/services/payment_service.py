import stripe
import logging
from django.urls import reverse
from django.conf import settings
from django.db import transaction

from common.services.email_service import (
    send_mail_on_new_reservation,
    send_mail_on_refund,
    send_mail_on_new_transfer,
    send_mail_payment_link,
    send_mail_on_payment_failure,
)
from common.services.stripe.stripe_event import (
    StripeCheckoutSessionEventData,
    StripeChargeEventData,
    StripePaymentIntentEventData,
    StripeTransferEventData,
)
from payment.models import PaymentTask
from decimal import Decimal, ROUND_UP, ROUND_HALF_UP


logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_PRIVATE_KEY
PLATFORM_FEE = 0.05
PAYMENT_FEE_VARIABLE = 0.025
PAYMENT_FEE_FIX = 0.25


def is_stripe_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False) or user.is_superuser or user.is_owner or user.is_owner_admin
    )


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


def get_refund(refund_id):
    try:
        refund = stripe.Refund.retrieve(refund_id)
        if not refund or not getattr(refund, "id", None):
            logger.error(f"❌ No valid refund object returned for ID {refund_id}")
            return None
        if refund.status != "succeeded":
            logger.warning(f"⚠️ Refund {refund_id} status is not 'succeeded': {refund.status}")
            return None

        return refund

    except Exception as e:
        logger.error(f"❌ Error retrieving refund {refund_id}: {e}")
        return None


def get_transfer(transfer_id):
    try:
        transfer = stripe.Transfer.retrieve(transfer_id)
        if not transfer or not getattr(transfer, "id", None):
            logger.error(f"❌ No valid transfer object returned for ID {transfer_id}")
            return None
        if transfer.status != "succeeded":
            logger.warning(f"⚠️ Transfer {transfer_id} status is not 'succeeded': {transfer.status}")
            return None

        return transfer

    except Exception as e:
        logger.error(f"❌ Error retrieving transfer {transfer_id}: {e}")
        return None


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
        success_url = request.build_absolute_uri(reverse("payment:payment_success", args=[reservation.code]))
        cancel_url = request.build_absolute_uri(reverse("payment:payment_cancel", args=[reservation.code]))

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


def send_stripe_payment_link(reservation, request):
    if not reservation.user.email:
        raise ValueError(f"L'utilisateur n'a pas d'e-mail lié à la réservation {reservation.code}")

    if reservation.price <= 0:
        raise ValueError(f"Montant invalide pour la réservation {reservation.code}")

    try:
        session = create_stripe_checkout_session_with_deposit(reservation, request)

        logger.info(f"✅ Stripe Checkout session created for reservation {reservation.code}: {session.url}")

        # Optionally send an email with the payment link
        send_mail_payment_link(reservation, session)

        logger.info(f"📧 Email envoyé à {reservation.user.email} avec le lien de paiement Stripe")

        return session.url

    except Exception as e:
        logger.exception(
            f"❌ Erreur lors de la création du lien de paiement Stripe pour la réservation {reservation.code}: {e}"
        )
        raise


def is_valid_stripe_customer(customer_id):
    try:
        customer = stripe.Customer.retrieve(customer_id)
        # Optional: check if customer is not deleted
        if getattr(customer, "deleted", False):
            return False
        return True
    except stripe.error.InvalidRequestError:
        # Happens if the customer ID doesn't exist
        return False
    except Exception as e:
        # Log unexpected errors
        logger.exception(f"❌ Unexpected error when checking Stripe customer ID: {e}")
        return False


def create_stripe_customer_if_not_exists(user, request):
    try:
        from common.services.network import get_client_ip

        ip = get_client_ip(request)

        if user.stripe_customer_id and is_valid_stripe_customer(user.stripe_customer_id):
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


def charge_payment(saved_payment_method_id, amount_cents, customer_id, reservation, currency="eur"):
    task, _ = PaymentTask.objects.get_or_create(
        reservation=reservation,
        type="charge_deposit",
    )
    try:
        if not saved_payment_method_id:
            raise ValueError("Missing saved payment method ID.")

        if not customer_id:
            raise ValueError("Customer ID is required to charge a saved payment method.")

        if reservation.caution_charged:
            raise ValueError("La caution a déjà été prélevée.")

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
            idempotency_key=f"deposit_{reservation.code}",
        )

        task.mark_success(intent.id)

        logger.info(f"✅ Deposit Charged successful for reservation {reservation.code}, intent ID: {intent.id}")
        return intent

    except stripe.error.CardError as e:
        # Declines, etc.
        logger.error(f"❌ Carte refusée pour la réservation {reservation.code} : {e.user_message}")
        task.mark_failure(e, getattr(intent, "id", None) if intent else None)
        raise ValueError(f"Carte refusée : {e.user_message}")

    except stripe.error.InvalidRequestError as e:
        logger.error(f"❌ Mauvaise requête Stripe (paramètre invalide) : {e.user_message or str(e)}")
        task.mark_failure(e, getattr(intent, "id", None) if intent else None)
        raise

    except stripe.error.AuthenticationError as e:
        logger.critical(f"❌ Authentification Stripe invalide. Vérifiez la clé API: {e}.")
        task.mark_failure(e, getattr(intent, "id", None) if intent else None)
        raise

    except stripe.error.APIConnectionError as e:
        logger.error(f"❌ Erreur de connexion réseau avec Stripe: {e}")
        task.mark_failure(e, getattr(intent, "id", None) if intent else None)
        raise

    except stripe.error.StripeError as e:
        logger.exception("❌ Erreur Stripe générale inattendue : %s", str(e))
        task.mark_failure(e, getattr(intent, "id", None) if intent else None)
        raise

    except Exception as e:
        task.mark_failure(e, getattr(intent, "id", None) if intent else None)
        logger.exception(
            "❌ Erreur interne lors du chargement du paiement pour la réservation %s : %s",
            reservation.code,
            str(e),
        )
        raise


def charge_reservation(reservation):
    try:
        logger.info(f"💼 Preparing transfer for reservation {reservation.code}")

        admin = reservation.logement.admin
        if admin and reservation.admin_transferable_amount > 0:
            task, _ = PaymentTask.objects.get_or_create(
                reservation=reservation,
                type="transfer_admin",
            )
            try:
                admin_amount = reservation.admin_transferable_amount

                if reservation.admin_transferred:
                    raise ValueError(
                        f"Le transfert des fonds à l'admin du logement {reservation.logement.name} pour la réservation {reservation.code} a déjà été effectué."
                    )

                admin_account = admin.stripe_account_id
                if not admin_account:
                    logger.error(f"❌ Missing Stripe account ID for admin of reservation {reservation.code}")
                    return

                logger.info(f"⚠️ Transfering {admin_amount} for reservation {reservation.code} to {admin}.")

                # Perform the transfer
                transfer = stripe.Transfer.create(
                    amount=int(admin_amount * 100),
                    currency="eur",
                    destination=admin_account,
                    transfer_group=f"group_{reservation.code}",
                    metadata={"code": reservation.code, "logement": reservation.logement.code, "transfer": "admin"},
                    idempotency_key=f"transfer_{reservation.code}",
                )

                with transaction.atomic():
                    # Update transfer status
                    reservation.admin_transferred = True
                    reservation.admin_stripe_transfer_id = transfer.id
                    reservation.save(update_fields=["admin_transferred", "admin_stripe_transfer_id"])

                logger.info(
                    f"✅ Payout transferred to {admin} for reservation {reservation.code} (transfer ID: {transfer.id})"
                )
            except stripe.error.InvalidRequestError as e:
                logger.exception(
                    f"❌ Invalid request to Stripe during transfer for reservation {reservation.code}: {e or str(e)}"
                )
                task.mark_failure(e)
                raise

            except stripe.error.AuthenticationError as e:
                logger.exception(
                    f"❌ Authentication with Stripe failed during transfer for reservation {reservation.code}: {e or str(e)}"
                )
                task.mark_failure(e)
                raise
            except stripe.error.APIConnectionError as e:
                logger.exception(
                    f"❌ Network error with Stripe during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
                )
                task.mark_failure(e)
                raise
            except stripe.error.StripeError as e:
                logger.exception(
                    f"❌ General Stripe error during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
                )
                task.mark_failure(e)
                raise
            except Exception as e:
                logger.exception(f"❌ Unexpected error during transfer for reservation {reservation.code}: {str(e)}")
                task.mark_failure(e)
                raise

        if reservation.transferred:
            raise ValueError(
                f"Le transfert des fonds au propriétaire du logement {reservation.logement.name} pour la réservation {reservation.code} a déjà été effectué."
            )

        owner = reservation.logement.owner
        owner_amount = reservation.transferable_amount

        if owner_amount <= 0:
            logger.info(
                f"⚠️ The transfer to owner {owner} is not a positive value for reservation {reservation.code}: {owner_amount} ."
            )

        owner_account = owner.stripe_account_id
        if not owner_account:
            logger.error(f"❌ Missing Stripe account ID for owner of reservation {reservation.code}")
            return

        logger.info(f"⚠️ Transfering {owner_amount} for reservation {reservation.code} to {owner}.")
        try:
            task, _ = PaymentTask.objects.get_or_create(
                reservation=reservation,
                type="transfer_owner",
            )
            # Perform the transfer
            transfer = stripe.Transfer.create(
                amount=int(owner_amount * 100),
                currency="eur",
                destination=owner_account,
                transfer_group=f"group_{reservation.code}",
                metadata={"code": reservation.code, "logement": reservation.logement.code, "transfer": "owner"},
                idempotency_key=f"transfer_{reservation.code}",
            )

            with transaction.atomic():
                # Update transfer status
                reservation.transferred = True
                reservation.stripe_transfer_id = transfer.id
                reservation.save(update_fields=["transferred", "stripe_transfer_id"])
                
            task.mark_success(transfer.id)
            logger.info(f"✅ Owner payout transferred for reservation {reservation.code} (transfer ID: {transfer.id})")

        except stripe.error.InvalidRequestError as e:
            logger.exception(
                f"❌ Invalid request to Stripe during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
            )
            task.mark_failure(e, getattr(transfer, "id", None) if transfer else None)
            raise

        except stripe.error.AuthenticationError as e:
            logger.exception(
                f"❌ Authentication with Stripe failed during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
            )
            task.mark_failure(e, getattr(transfer, "id", None) if transfer else None)
            raise
        except stripe.error.APIConnectionError as e:
            logger.exception(
                f"❌ Network error with Stripe during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
            )
            task.mark_failure(e, getattr(transfer, "id", None) if transfer else None)
            raise
        except stripe.error.StripeError as e:
            logger.exception(
                f"❌ General Stripe error during transfer for reservation {reservation.code}: {e.user_message or str(e)}"
            )
            task.mark_failure(e, getattr(transfer, "id", None) if transfer else None)
            raise
        except Exception as e:
            logger.exception(f"❌ Unexpected error during transfer for reservation {reservation.code}: {str(e)}")
            task.mark_failure(e, getattr(transfer, "id", None) if transfer else None)
            raise
    except Exception as e:
        logger.exception(f"❌ Unexpected error during transfer for reservation {reservation.code}: {str(e)}")
        raise


def refund_payment(reservation, refund="full", amount_cents=None):
    task, _ = PaymentTask.objects.get_or_create(
        reservation=reservation,
        type="refund",
    )
    try:
        logger.info(f"💸 Initiating refund for reservation {reservation.code}")

        params = {
            "payment_intent": reservation.stripe_payment_intent_id,
            "metadata": {"code": reservation.code, "refund": refund},
            "idempotency_key": f"refund_{reservation.code}",
        }

        if reservation.refunded:
            raise ValueError(f"La réservation {reservation.code} a déjà été remboursée.")

        if amount_cents:
            params["amount"] = int(amount_cents)

        refund = stripe.Refund.create(**params)

        with transaction.atomic():
            # Update refund status
            reservation.refunded = True
            reservation.stripe_refund_id = refund.id
            reservation.save(update_fields=["refunded", "stripe_refund_id"])

        task.mark_success(refund.id)
        logger.info(
            f"✅ Refund processed for Reservation {reservation.code}: {refund.id}, Amount: {params.get('amount', 'full')} cents"
        )

        return refund

    except stripe.error.StripeError as e:
        logger.exception(f"❌ Stripe refund error: {e}")
        task.mark_failure(e, getattr(refund, "id", None) if refund else None)
        raise

    except Exception as e:
        logger.exception(f"❌ Unexpected refund error: {e}")
        task.mark_failure(e, getattr(refund, "id", None) if refund else None)
        raise


def handle_charge_refunded(data: StripeChargeEventData):
    from reservation.models import Reservation

    reservation_code = None
    try:
        metadata = data.object.metadata or {}
        reservation_code = metadata.get("code")
        if not reservation_code:
            logger.warning("⚠️ No reservation code found in refund metadata.")
            return

        refund_type = metadata.get("refund")
        if not refund_type:
            logger.warning(f"⚠️ No refund type found for reservation {reservation_code}.")
            return

        logger.info(f"🔔 Handling charge.refunded for reservation {reservation_code}")

        try:
            with transaction.atomic():
                reservation = Reservation.objects.select_for_update().get(code=reservation_code)

                amount = data.object.amount
                refund_id = data.object.id
                currency = data.object.currency or "eur"

                if not amount or amount <= 0:
                    logger.warning(f"⚠️ Invalid or missing refund amount for event {refund_id}")
                    return

                refunded_amount = Decimal(amount) / 100
                current_refund = Decimal(reservation.refund_amount or 0)

                # Update reservation
                reservation.refund_amount = current_refund + refunded_amount
                reservation.stripe_refund_id = refund_id
                if refund_type == "full":
                    reservation.platform_fee = Decimal("0.00")
                    reservation.tax = Decimal("0.00")
                    reservation.statut = "annulee"

                reservation.save()
                logger.info(f"✅ Reservation {reservation.code} updated successfully.")

        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found.")
            return

        logger.info(
            f"💶 Refund ID: {refund_id}, Amount: {refunded_amount:.2f} {currency.upper()} "
            f"recorded for reservation {reservation.code}"
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
    from reservation.models import Reservation

    reservation_code = None
    try:
        metadata = data.object.metadata or {}
        payment_type = metadata.get("type")
        reservation_code = metadata.get("code")
        payment_intent_id = data.object.id
        amount_cents = data.object.amount_received

        if not payment_type:
            logger.warning("⚠️ No 'type' metadata in payment intent.")
            return

        if payment_type != "deposit":
            logger.info("ℹ️ Payment type is not 'deposit', skipping.")
            return

        if not reservation_code:
            logger.warning("⚠️ No reservation code in metadata.")
            return

        if amount_cents is None or amount_cents <= 0:
            logger.warning(f"⚠️ Invalid deposit amount in PaymentIntent {payment_intent_id}.")
            return

        amount = Decimal(amount_cents) / 100  # cents to euros
        logger.info(f"✅ Deposit received: {amount:.2f} € via PaymentIntent {payment_intent_id}")

        with transaction.atomic():
            try:
                reservation = Reservation.objects.select_for_update().get(code=reservation_code)
            except Reservation.DoesNotExist:
                logger.warning(f"⚠️ Reservation {reservation_code} not found.")
                return

            if reservation.caution_charged:
                logger.info(f"ℹ️ Reservation {reservation.code} already marked as deposit charged.")
                return

            try:
                existing_amount = Decimal(reservation.amount_charged or 0)
            except Exception:
                logger.warning(f"⚠️ Failed to parse existing amount_charged for {reservation.code}, defaulting to 0.")
                existing_amount = Decimal("0.00")

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

        logger.info(f"🏠 Deposit successfully recorded for reservation {reservation.code}, amount: {amount:.2f} €")

    except Exception as e:
        logger.exception(
            f"❌ Unexpected error in handle_payment_intent_succeeded "
            f"for reservation {reservation_code or '[unknown]'}: {str(e)}"
        )


def handle_payment_failed(data: StripePaymentIntentEventData):
    from reservation.models import Reservation

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

                try:
                    send_mail_on_payment_failure(reservation.logement, reservation, reservation.user)
                    logger.info(f"📧 Payment failure email sent for reservation {reservation.code}")
                except Exception as e:
                    logger.exception(f"❌ Error sending failure payment email for reservation {reservation.code}: {e}")
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found in DB.")
        except Exception as e:
            logger.exception(f"❌ Unexpected error updating reservation {reservation_code} on payment failure: {e}")

    except Exception as e:
        logger.exception(f"❌ Unexpected error handling payment_intent.payment_failed event: {str(e)}")


def handle_checkout_session_completed(data: StripeCheckoutSessionEventData):
    from reservation.models import Reservation

    reservation_code = None
    try:
        # Extract metadata and payment intent ID
        reservation_code = data.object.metadata.get("code")
        payment_intent_id = data.object.payment_intent

        if not reservation_code or not payment_intent_id:
            logger.error("❌ Stripe session missing reservation code or payment intent.")
            return

        logger.info(f"🔔 Handling checkout.session.completed for reservation {reservation_code}")

        with transaction.atomic():
            try:
                reservation = Reservation.objects.select_for_update().get(code=reservation_code)
            except Reservation.DoesNotExist:
                logger.warning(f"⚠️ Reservation {reservation_code} not found.")
                return

            if reservation.statut == "confirmee":
                logger.info(f"ℹ️ Reservation {reservation.code} already confirmed.")
                return

            task, _ = PaymentTask.objects.get_or_create(
                reservation=reservation,
                type="checkout",
            )

            try:
                intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["payment_method"])
            except stripe.error.StripeError as e:
                logger.exception(
                    f"❌ Stripe API error retrieving intent {payment_intent_id}: {e.user_message or str(e)}"
                )
                return

            if intent.status != "succeeded":
                logger.warning(
                    f"⚠️ PaymentIntent {payment_intent_id} status '{intent.status}' is not 'succeeded'. Skipping confirmation."
                )
                return

            payment_method = intent.payment_method
            if not payment_method or not getattr(payment_method, "id", None):
                logger.error(f"❌ No valid payment method in intent {payment_intent_id}")
                return

            if not reservation.stripe_saved_payment_method_id:
                reservation.stripe_saved_payment_method_id = payment_method.id
                logger.info(f"💾 Saved payment method {payment_method.id} for reservation {reservation.code}")

            reservation.stripe_payment_intent_id = payment_intent_id
            reservation.statut = "confirmee"
            reservation.save(
                update_fields=[
                    "stripe_payment_intent_id",
                    "stripe_saved_payment_method_id",
                    "statut",
                ]
            )

            task.mark_success(payment_intent_id)

        logger.info(f"✅ Reservation {reservation.code} confirmed")

        try:
            send_mail_on_new_reservation(reservation.logement, reservation, reservation.user)
            logger.info(f"📧 Confirmation email sent for reservation {reservation.code}")
        except Exception as e:
            logger.exception(f"❌ Error sending confirmation email for reservation {reservation.code}: {e}")

    except Exception as e:
        logger.exception(
            f"❌ Unexpected error in handle_checkout_session_completed for reservation {reservation_code or '[unknown]'}: {e}"
        )
        task.mark_failure(e, payment_intent_id)


def handle_transfer_created(data: StripeTransferEventData):
    from reservation.models import Reservation

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
            with transaction.atomic():
                if transfer_user == "owner":
                    reservation = Reservation.objects.get(code=reservation_code)
                    reservation.transferred = True
                    reservation.stripe_transfer_id = transfer_id
                    reservation.transferred_amount = amount
                    reservation.save(update_fields=["transferred", "stripe_transfer_id", "transferred_amount"])
                    logger.info(f"📦 Transfer recorded to owner for reservation {reservation_code}")
                elif transfer_user == "admin":
                    reservation = Reservation.objects.get(code=reservation_code)
                    reservation.admin_transferred = True
                    reservation.admin_transferred_amount = amount
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
    from reservation.models import Reservation

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


def retrieve_balance():
    return stripe.Balance.retrieve()
