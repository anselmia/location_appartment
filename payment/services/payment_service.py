import stripe
import logging
from datetime import datetime
from decimal import Decimal, ROUND_UP, ROUND_HALF_UP
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.core.mail import mail_admins
from typing import Any

from common.services.email_service import (
    send_mail_on_logement_refund,
    send_mail_on_activity_refund,
    send_mail_on_new_transfer,
    send_mail_payment_link,
    send_mail_on_payment_failure,
    send_mail_on_activity_payment_failure,
    send_mail_on_new_activity_transfer,
    send_mail_on_manual_payment_intent_failure,
    send_mail_activity_payment_link,
    send_mail_logement_payment_success,
    send_mail_activity_payment_success,
)
from common.services.stripe.stripe_event import (
    StripeCheckoutSessionEventData,
    StripeChargeEventData,
    StripePaymentIntentEventData,
    StripeTransferEventData,
)

from logement.models import PlatformFeeWaiver
from payment.models import PaymentTask
from reservation.models import ReservationHistory, ActivityReservationHistory

from accounts.models import CustomUser

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_PRIVATE_KEY
PLATFORM_FEE = 0.05
PAYMENT_FEE_VARIABLE = 0.025
PAYMENT_FEE_FIX = 0.25


def is_stripe_admin(user):
    return user.is_authenticated and (
        getattr(user, "is_admin", False)
        or user.is_superuser
        or user.is_owner
        or user.has_conciergerie
        or user.has_valid_partners
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


def get_fee_waiver(platform_fee: Decimal, owner: CustomUser) -> Decimal:
    """
    Calcule le montant de frais de plateforme restant à payer après application de l'exemption.

    Args:
        platform_fee (Decimal): Les frais de plateforme initiaux.
        owner (CustomUser): Le propriétaire du logement ou de l'activité.

    Returns:
        Decimal: Le montant de frais restant à payer (après réduction).
    """

    waivers = PlatformFeeWaiver.objects.filter(Q(owner=owner))
    for waiver in waivers:
        if waiver.is_active():
            # Si plafond, on applique la réduction dans la limite du montant restant
            if waiver.max_amount:
                remaining = waiver.max_amount - waiver.total_used
                fee_waived = min(platform_fee, remaining)
                # Met à jour le montant utilisé
                waiver.total_used += fee_waived
                waiver.save(update_fields=["total_used"])
                return platform_fee - fee_waived  # Montant restant à payer
            elif waiver.end_date and waiver.end_date > datetime.now().date():
                return Decimal("0.00")
    return platform_fee  # Aucun waiver actif, le client paie tout


def get_refund(refund_id: str) -> Any:
    """
    Retrieve a Stripe refund object by its ID.
    Args:
        refund_id (str): The Stripe refund ID.
    Returns:
        Refund object if found and succeeded, else None.
    """
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


def get_transfer(transfer_id: str) -> Any:
    """
    Retrieve a Stripe transfer object by its ID.
    Args:
        transfer_id (str): The Stripe transfer ID.
    Returns:
        Transfer object if found and succeeded, else None.
    """
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


def get_payment_intent(payment_intent_id: str) -> Any:
    """
    Retrieve a Stripe PaymentIntent object by its ID.
    Args:
        payment_intent_id (str): The Stripe PaymentIntent ID.
    Returns:
        PaymentIntent object if found and succeeded, else None.
    """
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["payment_method"])
        if not intent or not getattr(intent, "id", None):
            logger.error(f"❌ No valid PaymentIntent object returned for ID {payment_intent_id}")
            return None
        if intent.status != "succeeded":
            logger.warning(f"⚠️ PaymentIntent {payment_intent_id} status is not 'succeeded': {intent.status}")
            return None

        return intent

    except Exception as e:
        logger.error(f"❌ Error retrieving PaymentIntent {payment_intent_id}: {e}")
        return None


def get_session(session_id: str) -> Any:
    """
    Retrieve a Stripe Checkout Session by its ID.
    Args:
        session_id (str): The Stripe session ID.
    Returns:
        Session object if found and complete, else None.
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if not session or not getattr(session, "id", None):
            logger.error(f"❌ No valid session object returned for ID {session_id}")
            return None
        if session.status != "complete":
            logger.warning(f"⚠️ Session {session_id} status is not 'complete': {session.status}")
            return None

        return session

    except Exception as e:
        logger.error(f"❌ Error retrieving session {session_id}: {e}")
        return None


def create_stripe_setup_intent(reservation, user, request):
    """
    Crée un SetupIntent Stripe pour enregistrer une carte (usage off_session).
    Args:
        user: L'utilisateur Django (doit avoir stripe_customer_id).
        request: L'objet request Django (pour logs/IP).
    Returns:
        dict: { 'client_secret': ..., 'setup_intent_id': ... }
    Raises:
        Exception si création impossible.
    """
    from common.services.network import get_client_ip

    ip = get_client_ip(request)
    if not getattr(user, "stripe_customer_id", None):
        raise ValueError("L'utilisateur n'a pas de stripe_customer_id.")

    # Ensure the user has a Stripe customer ID
    customer_id = create_stripe_customer_if_not_exists(user, request)
    if not customer_id:
        logger.error(f"❌ No customer ID returned from Stripe for user {user.id}, IP: {ip}")
        raise Exception("Customer ID creation failed.")

    content_type = ContentType.objects.get_for_model(reservation)
    task, _ = PaymentTask.objects.get_or_create(
        content_type=content_type,
        object_id=reservation.id,
        type="create_setup_intent",
    )

    try:
        logger.info(f"🔧 Création d'un SetupIntent Stripe pour user {user.id} ({user.email}), IP: {ip}")
        setup_intent = stripe.SetupIntent.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            usage="off_session",
            metadata={"user_id": str(user.id)},
        )
        logger.info(f"✅ SetupIntent créé: {setup_intent.id} pour user {user.id}")
        task.mark_success(setup_intent.id)
        return {
            "client_secret": setup_intent.client_secret,
            "setup_intent_id": setup_intent.id,
        }
    except stripe.error.StripeError as e:
        logger.exception(
            f"❌ Stripe error lors de la création du SetupIntent pour user {user.id}: {e.user_message or str(e)}"
        )
        task.mark_failure(e)
        raise
    except Exception as e:
        logger.exception(f"❌ Erreur inattendue lors de la création du SetupIntent pour user {user.id}: {str(e)}")
        task.mark_failure(e)
        raise


def create_stripe_checkout_session_with_deposit(reservation: Any, request: Any) -> dict:
    """
    Create a Stripe Checkout Session for a reservation deposit.
    Args:
        reservation: The reservation object.
        request: The Django request object.
    Returns:
        dict: Contains checkout_session_url and session_id.
    Raises:
        Exception: If session creation fails.
    """
    from common.services.network import get_client_ip
    from reservation.services.reservation_service import get_reservation_type

    ip = get_client_ip(request)
    try:
        logger.info(
            f"⚙️ Creating Stripe checkout session with deposit for reservation {reservation.code} | "
            f"user={reservation.user.id} email={reservation.user.email} | IP: {ip}"
        )

        reservation_type = get_reservation_type(reservation)

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
        success_url = (
            request.build_absolute_uri(reverse("payment:payment_success", args=[reservation_type, reservation.code]))
            + "?session_id={CHECKOUT_SESSION_ID}"
        )
        cancel_url = request.build_absolute_uri(
            reverse("payment:payment_cancel", args=[reservation_type, reservation.code])
        )

        session_args = {
            "payment_method_types": ["card"],
            "mode": "payment",
            "customer": customer_id,
            "line_items": [
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": f"Réservation - {reservation.code}",
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
            "metadata": {"code": reservation.code, "product": reservation_type},
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


def create_stripe_checkout_session_without_deposit(reservation: Any, request: Any) -> dict:
    """
    Create a Stripe Checkout Session for a reservation without a deposit.
    Args:
        reservation: The reservation object.
        request: The Django request object.
    Returns:
        dict: Contains checkout_session_url and session_id.
    Raises:
        Exception: If session creation fails.
    """
    from common.services.network import get_client_ip
    from reservation.services.reservation_service import get_reservation_type

    ip = get_client_ip(request)
    try:
        logger.info(
            f"⚙️ Creating Stripe checkout session with deposit for reservation {reservation.code} | "
            f"user={reservation.user.id} email={reservation.user.email} | IP: {ip}"
        )

        reservation_type = get_reservation_type(reservation)

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
        success_url = (
            request.build_absolute_uri(reverse("payment:payment_success", args=[reservation_type, reservation.code]))
            + "?session_id={CHECKOUT_SESSION_ID}"
        )
        cancel_url = request.build_absolute_uri(
            reverse("payment:payment_cancel", args=[reservation_type, reservation.code])
        )

        session_args = {
            "payment_method_types": ["card"],
            "mode": "payment",
            "customer": customer_id,
            "line_items": [
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": f"Réservation - {reservation.code}",
                        },
                        "unit_amount": amount,
                    },
                    "quantity": 1,
                }
            ],
            "payment_intent_data": {
                "transfer_group": f"group_{reservation.code}",
            },
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"code": reservation.code, "product": reservation_type},
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


def create_stripe_checkout_session_with_manual_capture(reservation: Any, request: Any) -> dict:
    """
    Create a Stripe Checkout Session without payment method save and manual capture later.
    Args:
        reservation: The reservation object.
        request: The Django request object.
    Returns:
        dict: Contains checkout_session_url and session_id.
    Raises:
        Exception: If session creation fails.
    """
    from common.services.network import get_client_ip
    from reservation.services.reservation_service import get_reservation_type

    ip = get_client_ip(request)
    try:
        logger.info(
            f"⚙️ Creating Stripe checkout session without deposit for reservation {reservation.code} | "
            f"user={reservation.user.id} email={reservation.user.email} | IP: {ip}"
        )

        reservation_type = get_reservation_type(reservation)

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
        success_url = (
            request.build_absolute_uri(reverse("payment:payment_success", args=[reservation_type, reservation.code]))
            + "?session_id={CHECKOUT_SESSION_ID}"
        )
        cancel_url = request.build_absolute_uri(
            reverse("payment:payment_cancel", args=[reservation_type, reservation.code])
        )

        session_args = {
            "payment_method_types": ["card"],
            "mode": "payment",
            "customer": customer_id,
            "line_items": [
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": f"Réservation - {reservation.code}",
                        },
                        "unit_amount": amount,
                    },
                    "quantity": 1,
                }
            ],
            "payment_intent_data": {
                "capture_method": "automatic",
                "transfer_group": f"group_{reservation.code}",
            },
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"code": reservation.code, "product": reservation_type},
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


def create_reservation_payment_intents(reservation: Any) -> None:
    """
    Create payment intents for a reservation.
    Args:
        reservation: The reservation object.
    Returns:
        None
    Raises:
        Exception: If payment intent creation fails.
    """
    from reservation.services.reservation_service import get_reservation_type

    reservation_type = get_reservation_type(reservation)
    if not reservation.user.email:
        raise ValueError(f"L'utilisateur n'a pas d'e-mail lié à la réservation {reservation.code}")

    if reservation.price <= 0:
        raise ValueError(f"Montant invalide pour la réservation {reservation.code}")

    payment_method_id = getattr(reservation, "stripe_saved_payment_method_id", None)
    customer_id = getattr(reservation.user, "stripe_customer_id", None)

    amount_cents = int(reservation.price * 100)

    logger.info(
        f"💳 Création d'un PaymentIntent Stripe off_session pour la réservation {reservation.code} "
        f"(user={reservation.user.email}, customer={customer_id}, payment_method={payment_method_id}, amount={amount_cents})"
    )
    content_type = ContentType.objects.get_for_model(reservation)
    task, _ = PaymentTask.objects.get_or_create(
        content_type=content_type,
        object_id=reservation.id,
        type="create_manual_payment_intent",
    )

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="eur",
            customer=customer_id,
            payment_method=payment_method_id,
            off_session=True,
            confirm=True,
            capture_method="manual",  # Use manual capture for later processing
            transfer_group=f"group_{reservation.code}",
            description=f"Paiement réservation {reservation.code}",
            metadata={
                "code": reservation.code,
                "product": reservation_type,
                "type": "prepare_payment",
            },
            idempotency_key=f"reservation_payment_{reservation.code}",
        )

        # Vérifie le statut du PaymentIntent
        if not intent or intent.status not in ["requires_capture", "succeeded"]:
            logger.error(
                f"❌ PaymentIntent {intent.id} pour la réservation {reservation.code} n'a pas abouti (statut: {intent.status})"
            )
            send_mail_on_manual_payment_intent_failure(reservation)
            reservation.status = "echec_paiement"
            reservation.save()
            raise Exception(f"Le paiement n'a pas pu être capturé automatiquement (statut: {intent.status})")

        # Sauvegarde l'ID du PaymentIntent sur la réservation
        reservation.stripe_payment_intent_id = intent.id
        task.mark_success(intent.id)
        reservation.save()

        logger.info(f"✅ PaymentIntent with manual capture created for {reservation.code} (PaymentIntent: {intent.id})")

    except Exception as e:
        logger.exception(f"❌ Error creating payment intents for reservation {reservation.code}: {e}")
        task.mark_failure(e)
        raise


def send_stripe_payment_link(reservation: Any, ) -> str:
    """
    Send a Stripe payment link to the user for a reservation.
    Args:
        reservation: The reservation object.
        request: The Django request object.
    Returns:
        str: The Stripe Checkout session URL.
    Raises:
        Exception: If link creation or email sending fails.
    """
    from reservation.services.reservation_service import get_reservation_type

    reservation_type = get_reservation_type(reservation)
    if not reservation.user.email:
        raise ValueError(f"L'utilisateur n'a pas d'e-mail lié à la réservation {reservation.code}")

    if reservation.price <= 0:
        raise ValueError(f"Montant invalide pour la réservation {reservation.code}")

    try:
        if reservation_type == "logement":            
            send_mail_payment_link(reservation)
        else:
            send_mail_activity_payment_link(reservation)

        logger.info(
            f"✅ Payment link for {reservation.code} sent to {reservation.user.email} "
        )
    except Exception as e:
        logger.exception(
            f"❌Error creating payment link for {reservation.code}: {e}"
        )
        raise


def is_valid_stripe_customer(customer_id: str) -> bool:
    """
    Check if a Stripe customer ID is valid and not deleted.
    Args:
        customer_id (str): The Stripe customer ID.
    Returns:
        bool: True if valid, False otherwise.
    """
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


def create_stripe_customer_if_not_exists(user: Any, request: Any) -> str:
    """
    Create a Stripe customer for the user if one does not exist.
    Args:
        user: The user object.
        request: The Django request object.
    Returns:
        str: The Stripe customer ID.
    Raises:
        Exception: If customer creation fails.
    """
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


def charge_deposit(
    saved_payment_method_id: str,
    amount_cents: int,
    customer_id: str,
    reservation: Any,
    currency: str = "eur",
) -> Any:
    """
    Charge a saved payment method for a reservation deposit.
    Args:
        saved_payment_method_id (str): The Stripe PaymentMethod ID.
        amount_cents (int): Amount to charge in cents.
        customer_id (str): The Stripe customer ID.
        reservation: The reservation object.
        currency (str): Currency code (default 'eur').
    Returns:
        PaymentIntent object if successful.
    Raises:
        Exception: If payment fails.
    """
    intent = None
    content_type = ContentType.objects.get_for_model(reservation)
    task, _ = PaymentTask.objects.get_or_create(
        content_type=content_type,
        object_id=reservation.id,
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
                "product": "logement",
            },
            idempotency_key=f"deposit_{reservation.code}",
        )

        with transaction.atomic():
            # Update reservation with payment intent details
            reservation.caution_charged = True
            reservation.stripe_deposit_payment_intent_id = intent.id
            reservation.save(
                update_fields=[
                    "caution_charged",
                    "stripe_deposit_payment_intent_id",
                ]
            )

        task.mark_success(intent.id)

        amount = Decimal(amount_cents) / 100
        ReservationHistory.objects.create(
            reservation=reservation,
            details=f"Réservation {reservation.code} - Un montant de {amount} € a été prélevé sur la caution.",
        )

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


def transfer_funds(reservation: Any) -> None:
    """
    Transfer funds to admin and owner for a reservation, if eligible.
    Args:
        reservation: The reservation object.
    Raises:
        Exception: If transfer fails.
    """
    try:
        from reservation.services.reservation_service import get_reservation_type

        logger.info(f"💼 Preparing transfer for reservation {reservation.code}")

        reservation_type = get_reservation_type(reservation)
        if reservation_type == "logement":
            admin = reservation.logement.admin
            if admin and reservation.admin_transferable_amount > 0:
                content_type = ContentType.objects.get_for_model(reservation)
                task, _ = PaymentTask.objects.get_or_create(
                    content_type=content_type,
                    object_id=reservation.id,
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
                        metadata={
                            "code": reservation.code,
                            "logement": reservation.logement.code,
                            "transfer": "admin",
                            "product": reservation_type,
                        },
                        idempotency_key=f"transfer_{reservation.code}",
                    )

                    with transaction.atomic():
                        # Update transfer status
                        reservation.admin_transferred = True
                        reservation.admin_stripe_transfer_id = transfer.id
                        reservation.save(update_fields=["admin_transferred", "admin_stripe_transfer_id"])

                    task.mark_success(transfer.id)
                    if reservation_type == "logement":
                        ReservationHistory.objects.create(
                            reservation=reservation,
                            details=f"Réservation {reservation.code} - Un paiement de {admin_amount} € a été transféré à {admin.full_name}.",
                        )

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
                    logger.exception(
                        f"❌ Unexpected error during transfer for reservation {reservation.code}: {str(e)}"
                    )
                    task.mark_failure(e)
                    raise

        if reservation.transferred:
            raise ValueError(
                f"Le transfert des fonds au propriétaire du logement {reservation.logement.name} pour la réservation {reservation.code} a déjà été effectué."
            )

        if reservation_type == "logement":
            owner = reservation.logement.owner
        elif reservation_type == "activity":
            owner = reservation.activity.owner
        owner_amount = reservation.transferable_amount

        if owner_amount <= 0:
            logger.info(
                f"⚠️ The transfer to owner {owner} is not a positive value for reservation {reservation.code}: {owner_amount} ."
            )
            raise ValueError(
                f"Le montant du transfert au propriétaire {owner} pour la réservation {reservation.code} n'est pas positif: {owner_amount}."
            )

        owner_account = owner.stripe_account_id
        if not owner_account:
            logger.error(f"❌ Missing Stripe account ID for owner of reservation {reservation.code}")
            return

        logger.info(f"⚠️ Transfering {owner_amount} for reservation {reservation.code} to {owner}.")
        try:
            content_type = ContentType.objects.get_for_model(reservation)
            task, _ = PaymentTask.objects.get_or_create(
                content_type=content_type,
                object_id=reservation.id,
                type="transfer_owner",
            )
            # Perform the transfer
            if reservation_type == "logement":
                transfer = stripe.Transfer.create(
                    amount=int(owner_amount * 100),
                    currency="eur",
                    destination=owner_account,
                    transfer_group=f"group_{reservation.code}",
                    metadata={
                        "code": reservation.code,
                        "logement": reservation.logement.code,
                        "transfer": "owner",
                        "product": reservation_type,
                    },
                    idempotency_key=f"transfer_{reservation.code}",
                )
            elif reservation_type == "activity":
                transfer = stripe.Transfer.create(
                    amount=int(owner_amount * 100),
                    currency="eur",
                    destination=owner_account,
                    transfer_group=f"group_{reservation.code}",
                    metadata={
                        "code": reservation.code,
                        "activity": reservation.activity.code,
                        "transfer": "owner",
                        "product": reservation_type,
                    },
                    idempotency_key=f"transfer_{reservation.code}",
                )
            else:
                raise ValueError(f"Unknown reservation type {reservation_type} for reservation {reservation.code}")

            with transaction.atomic():
                # Update transfer status
                reservation.transferred = True
                reservation.stripe_transfer_id = transfer.id
                reservation.save(update_fields=["transferred", "stripe_transfer_id"])

            task.mark_success(transfer.id)

            if reservation_type == "logement":
                ReservationHistory.objects.create(
                    reservation=reservation,
                    details=f"Réservation {reservation.code} - Un paiement de {owner_amount} € a été transféré à {owner.full_name}.",
                )
            elif reservation_type == "activity":
                ActivityReservationHistory.objects.create(
                    reservation=reservation,
                    details=f"Réservation {reservation.code} - Un paiement de {owner_amount} € a été transféré à {owner.full_name}.",
                )
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


def refund_payment(reservation: Any, refund: str = "full", amount_cents: Any = None) -> Any:
    """
    Refund a payment for a reservation.
    Args:
        reservation: The reservation object.
        refund (str): Refund type ('full' or custom).
        amount_cents (int, optional): Amount to refund in cents.
    Returns:
        Refund object if successful.
    Raises:
        Exception: If refund fails.
    """
    from reservation.services.reservation_service import get_reservation_type

    content_type = ContentType.objects.get_for_model(reservation)
    task, _ = PaymentTask.objects.get_or_create(
        content_type=content_type,
        object_id=reservation.id,
        type="refund",
    )
    try:
        amount = 0.0
        logger.info(f"💸 Initiating refund for reservation {reservation.code}")

        reservation_type = get_reservation_type(reservation)

        params = {
            "payment_intent": reservation.stripe_payment_intent_id,
            "metadata": {"code": reservation.code, "refund": refund, "product": reservation_type},
            "idempotency_key": f"refund_{reservation.code}",
        }

        if reservation.refunded:
            raise ValueError(f"La réservation {reservation.code} a déjà été remboursée.")

        if amount_cents:
            params["amount"] = int(amount_cents)
            amount = Decimal(amount_cents) / 100

        refund = stripe.Refund.create(**params)

        with transaction.atomic():
            # Update refund status
            reservation.refunded = True
            reservation.stripe_refund_id = refund.id
            reservation.save(update_fields=["refunded", "stripe_refund_id"])

        task.mark_success(refund.id)

        if reservation_type == "logement":
            ReservationHistory.objects.create(
                reservation=reservation,
                details=f"Réservation {reservation.code} - Un remboursement de {amount} € a été effectué pour {reservation.user.full_name}.",
            )
        elif reservation_type == "activity":
            ActivityReservationHistory.objects.create(
                reservation=reservation,
                details=f"Réservation {reservation.code} - Un remboursement de {amount} € a été effectué pour {reservation.user.full_name}.",
            )
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


def capture_reservation_payment(reservation):
    """
    Charge the payment for a confirmed activity reservation.
    Returns a dict: { 'success': True/False, 'error': '...' }
    Idempotent: will not double-capture or double-log. Uses Stripe idempotency key.
    """
    from reservation.services.reservation_service import get_reservation_type
    content_type = ContentType.objects.get_for_model(reservation)
    task, _ = PaymentTask.objects.get_or_create(
        content_type=content_type,
        object_id=reservation.id,
        type="capture",
    )

    reservation_type = get_reservation_type(reservation)

    # If already marked as success, return immediately (idempotency)
    if task.status == "success":
        return {"success": True, "error": None}

    try:
        if not reservation.stripe_payment_intent_id:
            error = "Aucun PaymentIntent Stripe associé à cette réservation."
            task.mark_failure(error, None)
            return {"success": False, "error": error}

        # Retrieve the PaymentIntent
        intent = stripe.PaymentIntent.retrieve(reservation.stripe_payment_intent_id)
        # Try to update the saved payment method from the PaymentIntent
        payment_method_id = None
        if hasattr(intent, "payment_method") and intent.payment_method:
            if isinstance(intent.payment_method, dict):
                payment_method_id = intent.payment_method.get("id")
            else:
                payment_method_id = intent.payment_method
        if payment_method_id and getattr(reservation, "stripe_saved_payment_method_id", None) != payment_method_id:
            reservation.stripe_saved_payment_method_id = payment_method_id
            reservation.save(update_fields=["stripe_saved_payment_method_id"])
        if intent.status == "succeeded":
            task.mark_success(intent.id)
            return {"success": True, "error": None}  # Already paid

        idempotency_key = f"capture-{reservation.stripe_payment_intent_id}-{reservation.id}"
        capture_metadata = {
            "code": reservation.code,
            "product": "activity",
            "type": "payment_capture",
        }
        captured_intent = stripe.PaymentIntent.capture(
            reservation.stripe_payment_intent_id, idempotency_key=idempotency_key, metadata=capture_metadata
        )

        if captured_intent.status != "succeeded":
            error_message = f"Échec de la capture du paiement pour la réservation {reservation.code}."
            reservation.statut = "echec_paiement"
            reservation.save(update_fields=["statut"])
            logger.error(error_message)
            task.mark_failure(error_message, captured_intent.id)
            if reservation_type == "logement":
                ReservationHistory.objects.create(
                    reservation=reservation,
                    details=f"Échec du paiement de la Réservation {reservation.code} ! Le montant de {amount_captured} € n'a pas pu être payé.",
                )
                send_mail_on_payment_failure(reservation.logement, reservation, reservation.user)
            elif reservation_type == "activity":
                ActivityReservationHistory.objects.create(
                    reservation=reservation,
                    details=f"Échec du paiement de la Réservation {reservation.code} ! Le montant de {amount_captured} € n'a pas pu être payé.",
                )            
                send_mail_on_activity_payment_failure(reservation.activity, reservation, reservation.user)
            return {"success": False, "error": error_message}

        # Try to update the saved payment method from the captured intent
        payment_method_id = None
        if hasattr(captured_intent, "payment_method") and captured_intent.payment_method:
            if isinstance(captured_intent.payment_method, dict):
                payment_method_id = captured_intent.payment_method.get("id")
            else:
                payment_method_id = captured_intent.payment_method

        if payment_method_id and getattr(reservation, "stripe_saved_payment_method_id", None) != payment_method_id:
            reservation.stripe_saved_payment_method_id = payment_method_id
        reservation.paid = True

        reservation.save(update_fields=["stripe_saved_payment_method_id", "paid"])

        task.mark_success(captured_intent.id)

        amount_captured = (
            Decimal(captured_intent.amount_received) / 100
            if hasattr(captured_intent, "amount_received")
            else Decimal("0.00")
        )
        if reservation_type == "logement":
            ReservationHistory.objects.create(
                reservation=reservation,
                details=f"Réservation {reservation.code} validée ! Le montant de {amount_captured} € a été payé.",
            )
            send_mail_logement_payment_success(reservation.logement, reservation, reservation.user)
        elif reservation_type == "activity":
            ActivityReservationHistory.objects.create(
                reservation=reservation,
                details=f"Réservation {reservation.code} validée ! Le montant de {amount_captured} € a été payé.",
            )
            send_mail_activity_payment_success(reservation.activity, reservation, reservation.user)
        return {"success": True, "error": None}
    except stripe.error.InvalidRequestError as e:
        logger.exception(
            f"❌ Invalid request to Stripe during capture for reservation {reservation.code}: {getattr(e, 'user_message', str(e))}"
        )
        task.mark_failure(e, getattr(reservation, "stripe_payment_intent_id", None))
        raise
    except stripe.error.AuthenticationError as e:
        logger.exception(
            f"❌ Authentication with Stripe failed during capture for reservation {reservation.code}: {getattr(e, 'user_message', str(e))}"
        )
        task.mark_failure(e, getattr(reservation, "stripe_payment_intent_id", None))
        raise
    except stripe.error.APIConnectionError as e:
        logger.exception(
            f"❌ Network error with Stripe during capture for reservation {reservation.code}: {getattr(e, 'user_message', str(e))}"
        )
        task.mark_failure(e, getattr(reservation, "stripe_payment_intent_id", None))
        raise
    except stripe.error.StripeError as e:
        logger.exception(
            f"❌ General Stripe error during capture for reservation {reservation.code}: {getattr(e, 'user_message', str(e))}"
        )
        task.mark_failure(e, getattr(reservation, "stripe_payment_intent_id", None))
        raise
    except Exception as e:
        logger.error(f"Error during Stripe capture: {e}")
        task.mark_failure(str(e), getattr(reservation, "stripe_payment_intent_id", None))
        return {"success": False, "error": str(e)}


def handle_charge_refunded(data: StripeChargeEventData):
    """
    Handle a Stripe charge.refunded webhook event.
    Args:
        data (StripeChargeEventData): The event data.
    """
    from reservation.models import Reservation, ActivityReservation

    reservation_code = None
    try:
        metadata = data.object.metadata or {}
        reservation_code = metadata.get("code")
        if not reservation_code:
            logger.error("⚠️ No reservation code found in refund metadata.")
            return

        refund_type = metadata.get("refund")
        if not refund_type:
            logger.error(f"⚠️ No refund type found for reservation {reservation_code}.")
            return
        product = metadata.get("product")
        if not product:
            logger.error(f"⚠️ No product found for reservation {reservation_code}.")
            return

        logger.info(f"🔔 Handling charge.refunded for reservation {reservation_code}")

        try:
            with transaction.atomic():
                if product == "logement":
                    reservation = Reservation.objects.select_for_update().get(code=reservation_code)
                elif product == "activity":
                    reservation = ActivityReservation.objects.select_for_update().get(code=reservation_code)
                else:
                    logger.error(f"⚠️ Unknown product type {product} for reservation {reservation_code}.")
                    return

                amount = data.object.amount
                refund_id = data.object.id
                currency = data.object.currency or "eur"

                if not amount or amount <= 0:
                    logger.warning(f"⚠️ Invalid or missing refund amount for event {refund_id}")
                    return

                refunded_amount = Decimal(amount) / 100

                # Update reservation
                reservation.refund_amount = refunded_amount
                reservation.stripe_refund_id = refund_id
                if refund_type == "full":
                    reservation.platform_fee = Decimal("0.00")
                    reservation.statut = "annulee"
                    if product == "logement":
                        reservation.tax = Decimal("0.00")
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
            if product == "logement":
                send_mail_on_logement_refund(reservation.logement, reservation, reservation.user)
            elif product == "activity":
                send_mail_on_activity_refund(reservation.activity, reservation, reservation.user)
            logger.info(f"📧 Refund notification sent for reservation {reservation.code}")
        except Exception as e:
            logger.exception(f"❌ Error sending refund email for reservation {reservation.code}: {e}")

    except Exception as e:
        logger.exception(
            f"❌ Unexpected error handling charge.refunded for reservation {reservation_code or '[unknown]'}: {e}"
        )


def handle_payment_intent_succeeded(data: StripePaymentIntentEventData) -> None:
    """
    Handle a Stripe payment_intent.succeeded webhook event for deposit.
    Args:
        data (StripePaymentIntentEventData): The event data.
    """
    from reservation.models import Reservation, ActivityReservation
    from reservation.services.reservation_service import get_reservation_by_code

    reservation_code = None
    try:
        metadata = data.object.metadata or {}
        payment_type = metadata.get("type")
        reservation_code = metadata.get("code")
        product = metadata.get("product")
        payment_intent_id = data.object.id
        amount_cents = data.object.amount_received

        if not product:
            logger.warning("⚠️ No product type in metadata.")
            return

        if not payment_type:
            logger.warning("⚠️ No 'type' metadata in payment intent.")
            return

        if not reservation_code:
            logger.warning("⚠️ No reservation code in metadata.")
            return

        if amount_cents is None or amount_cents <= 0:
            logger.warning(f"⚠️ Invalid deposit amount in PaymentIntent {payment_intent_id}.")
            return

        amount = Decimal(amount_cents) / 100  # cents to euros
        logger.info(f"✅ Amount received: {amount:.2f} € via PaymentIntent {payment_intent_id}")

        with transaction.atomic():
            try:
                reservation = get_reservation_by_code(reservation_code)
                if product == "logement":
                    if payment_type == "deposit":
                        reservation.amount_charged = amount
                    elif payment_type == "payment_capture":
                        reservation.checkout_amount = amount
                    reservation.save(update_fields=["amount_charged"])
                elif product == "activity":
                    reservation.checkout_amount = amount
                    reservation.save(update_fields=["checkout_amount"])                    
                else:
                    logger.error(f"❌ Unknown product type {product} for reservation {reservation_code}.")
                    return
            except (Reservation.DoesNotExist, ActivityReservation.DoesNotExist):
                logger.warning(f"⚠️ Reservation {reservation_code} not found.")
                return

        logger.info(f"🏠 Deposit successfully recorded for reservation {reservation.code}, amount: {amount:.2f} €")

    except Exception as e:
        logger.error(
            f"❌ Unexpected error in handle_payment_intent_succeeded "
            f"for reservation {reservation_code or '[unknown]'}: {str(e)}"
        )


def handle_payment_failed(data: StripePaymentIntentEventData) -> None:
    """
    Handle a Stripe payment_intent.payment_failed webhook event.
    Args:
        data (StripePaymentIntentEventData): The event data.
    """
    from reservation.models import Reservation, ActivityReservation

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

        reservation_code = metadata.get("code")
        product = metadata.get("product")

        if not reservation_code:
            logger.warning(f"⚠️ No reservation code found in failed payment event {payment_intent_id}.")
        if not customer_id:
            logger.warning(f"⚠️ No customer ID found in failed payment event {payment_intent_id}.")
        if not product:
            logger.warning(f"⚠️ No product type found in failed payment event {payment_intent_id}.")
            return

        logger.warning(
            f"⚠️ Payment failed for reservation {reservation_code}, customer {customer_id or '[unknown]'}, PaymentIntent {payment_intent_id}."
        )

        if failure_message:
            logger.warning(f"💥 Payment failure message: {failure_message}")
        if failure_code:
            logger.warning(f"📛 Stripe failure code: {failure_code}")

        try:
            if product == "logement":
                reservation = Reservation.objects.get(code=reservation_code)
            elif product == "activity":
                reservation = ActivityReservation.objects.get(code=reservation_code)
            with transaction.atomic():
                # Mark reservation as payment failed
                reservation.statut = "echec_paiement"
                reservation.save(update_fields=["statut"])
                logger.info(f"🚫 Reservation {reservation.code} marked as payment failed.")

                try:
                    if product == "logement":
                        send_mail_on_payment_failure(reservation.logement, reservation, reservation.user)
                    elif product == "activity":
                        send_mail_on_activity_payment_failure(reservation.activity, reservation, reservation.user)
                    logger.info(f"📧 Payment failure email sent for reservation {reservation.code}")
                except Exception as e:
                    logger.exception(f"❌ Error sending failure payment email for reservation {reservation.code}: {e}")
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found in DB.")
        except Exception as e:
            logger.exception(f"❌ Unexpected error updating reservation {reservation_code} on payment failure: {e}")

    except Exception as e:
        logger.exception(f"❌ Unexpected error handling payment_intent.payment_failed event: {str(e)}")


def handle_checkout_session_completed(data: StripeCheckoutSessionEventData) -> None:
    """
    Handle a Stripe checkout.session.completed webhook event.
    Args:
        data (StripeCheckoutSessionEventData): The event data.
    """
    from reservation.services.reservation_service import get_reservation_by_code

    reservation_code = None
    try:
        # Extract metadata and payment intent ID
        reservation_code = data.object.metadata.get("code")
        product = data.object.metadata.get("product")
        payment_intent_id = data.object.payment_intent

        if not reservation_code or not payment_intent_id or not product:
            logger.error("❌ Stripe checkout session is missing info.")
            return

        logger.info(f"🔔 Handling checkout.session.completed for reservation {reservation_code}")

        reservation = get_reservation_by_code(reservation_code)
        content_type = ContentType.objects.get_for_model(reservation)
        task, _ = PaymentTask.objects.get_or_create(
            content_type=content_type,
            object_id=reservation.id,
            type="checkout",
        )            

        task.mark_success(payment_intent_id)

        logger.info(f"✅ Reservation {reservation.code} confirmed")

    except Exception as e:
        logger.exception(
            f"❌ Unexpected error in handle_checkout_session_completed for reservation {reservation_code or '[unknown]'}: {e}"
        )
        task.mark_failure(e, payment_intent_id)


def handle_transfer_created(data: StripeTransferEventData) -> None:
    """
    Handle a Stripe transfer.paid webhook event.
    Args:
        data (StripeTransferEventData): The event data.
    """
    from reservation.models import Reservation, ActivityReservation

    try:
        transfer_id = data.object.id
        amount = Decimal(data.object.amount) / 100
        currency = data.object.currency.upper()
        destination = data.object.destination
        metadata = data.object.metadata or {}
        reservation_code = metadata.get("code")
        if not reservation_code:
            logger.error("⚠️ No reservation code found in the transfer event metadata.")
            return
        transfer_user = metadata.get("transfer")
        if not transfer_user:
            logger.error("⚠️ No reservation user found in the transfer event metadata.")
            return
        product = metadata.get("product")
        if not product:  # Ensure product is defined
            logger.error(f"⚠️ No product type found in transfer event metadata for reservation {reservation_code}.")
            return

        logger.info(f"✅ Transfer succeeded: {transfer_id} | {amount:.2f} {currency} to {destination}")

        try:
            with transaction.atomic():
                if transfer_user == "owner":
                    if product == "logement":
                        reservation = Reservation.objects.get(code=reservation_code)
                    elif product == "activity":
                        reservation = ActivityReservation.objects.get(code=reservation_code)
                    else:
                        logger.error(f"❌ Unknown product type {product} for reservation {reservation_code}.")
                        return

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
                if product == "logement":
                    send_mail_on_new_transfer(reservation.logement, reservation, transfer_user)
                elif product == "activity":
                    send_mail_on_new_activity_transfer(reservation.activity, reservation, transfer_user)
                logger.info(f"📧 transfer email sent for reservation {reservation.code}")
            except Exception as e:
                logger.exception(f"❌ Error sending confirmation email for reservation {reservation.code}: {e}")
        except Reservation.DoesNotExist:
            logger.warning(f"⚠️ Reservation {reservation_code} not found for transfer {transfer_id}")

    except Exception as e:
        logger.exception(f"❌ Error handling transfer.paid: {e}")


def handle_transfer_failed(data: StripeTransferEventData) -> None:
    """
    Handle a Stripe transfer.failed webhook event.
    Args:
        data (StripeTransferEventData): The event data.
    """

    try:
        transfer_id = data.object.id
        amount = Decimal(data.object.amount) / 100
        currency = data.object.currency.upper()
        destination = data.object.destination
        failure_message = getattr(data.object, "failure_message", "Unknown error")

        metadata = data.object.metadata or {}
        reservation_code = metadata.get("code")
        if not reservation_code:
            logger.error("⚠️ No reservation code found in the transfer event metadata.")
            return

        transfer_user = metadata.get("transfer")
        if not transfer_user:
            logger.error("⚠️ No reservation user found in the transfer event metadata.")
            return

        product = metadata.get("product")
        if not product:
            logger.error(f"⚠️ No product type found in transfer event metadata for reservation {reservation_code}.")
            return

        logger.warning(
            f"❌ Transfer FAILED: {transfer_id} | {amount:.2f} {currency} to {destination} | Reason: {failure_message}"
        )

        mail_admins(
            subject=f"[Transfer Integrity] Transfer to {transfer_user} failed for reservation {reservation_code}",
            message=f"Transfer failed on Stripe for reservation {reservation_code} (transfer_id={transfer_id}).",
        )

    except Exception as e:
        logger.exception(f"❌ Error handling transfer.failed: {e}")


def retrieve_balance() -> Any:
    """
    Retrieve the current Stripe account balance.
    Returns:
        The Stripe balance object.
    """
    return stripe.Balance.retrieve()


def verify_payment(reservation: Any) -> tuple[bool, str]:
    """
    Vérifie si une réservation a été payée et retourne un message d'état en français.
    Args:
        reservation: L'objet réservation.
    Returns:
        (True, message) si payée, (False, message) sinon.
    """
    if not reservation.stripe_payment_intent_id:
        return False, "Aucun paiement Stripe associé à cette réservation."

    try:
        intent = stripe.PaymentIntent.retrieve(reservation.stripe_payment_intent_id)
        status = intent.status

        if status == "succeeded":
            amount_cents = intent.amount_received
            amount = Decimal(amount_cents) / 100  # cents to euros
            reservation.checkout_amount = amount
            reservation.paid = True
            reservation.save(update_fields=["checkout_amount", "paid"])
            logger.info(f"✅ Réservation {reservation.code} confirmée payée : {amount:.2f} €")
            return True, f"Paiement confirmé ({amount:.2f} € reçus)."
        elif status == "processing":
            return False, "Le paiement est en cours de traitement. Veuillez réessayer plus tard."
        elif status == "requires_payment_method":
            return False, "Le paiement a échoué ou a été annulé. Un nouveau moyen de paiement est requis."
        elif status == "requires_action":
            return False, "Le paiement nécessite une action supplémentaire de l'utilisateur (3D Secure, etc.)."
        elif status == "canceled":
            return False, "Le paiement a été annulé."
        else:
            return False, f"Statut du paiement Stripe : {status}."

    except stripe.error.StripeError as e:
        logger.error(
            f"❌ Erreur Stripe lors de la vérification du paiement pour la réservation {reservation.code}: {e}"
        )
        return False, "Erreur Stripe lors de la vérification du paiement."
    except Exception as e:
        logger.error(
            f"❌ Erreur inattendue lors de la vérification du paiement pour la réservation {reservation.code}: {e}"
        )
        return False, "Erreur inattendue lors de la vérification du paiement."


def verify_transfer(reservation):
    """
    Checks the Stripe transfer status for a reservation.
    Returns (success: bool, message: str)
    """
    transfer_id = getattr(reservation, "stripe_transfer_id", None)
    if not transfer_id:
        logger.warning(
            f"[verify_transfer] Aucun transfert Stripe associé à la réservation {getattr(reservation, 'code', '[unknown]')}."
        )
        return False, "Aucun transfert Stripe associé à cette réservation."

    try:
        logger.info(
            f"[verify_transfer] Vérification du transfert Stripe {transfer_id} pour la réservation {getattr(reservation, 'code', '[unknown]')}."
        )
        transfer = stripe.Transfer.retrieve(transfer_id)
        if transfer.amount > 0:
            amount_cents = transfer.amount
            amount = Decimal(amount_cents) / 100  # cents to euros
            reservation.transferred_amount = amount
            reservation.transferred = True
            reservation.save(update_fields=["transferred_amount", "transferred"])
            logger.info(
                f"[verify_transfer] Transfert confirmé pour la réservation {getattr(reservation, 'code', '[unknown]')} : {amount:.2f} €."
            )
            return True, f"Transfert confirmé : {amount:.2f} €."
        else:
            logger.warning(
                f"[verify_transfer] Le transfert {transfer_id} existe mais le montant est nul ou non défini."
            )
            return False, "Le transfert existe mais le montant est nul ou non défini."
    except Exception as e:
        logger.error(f"[verify_transfer] Erreur lors de la vérification du transfert Stripe {transfer_id} : {e}")
        return False, f"Erreur lors de la vérification du transfert Stripe : {e}"


def verify_payment_method(reservation):
    """
    Vérifie et retourne le moyen de paiement utilisé pour la réservation Stripe.
    Retourne (success: bool, message: str, payment_method_id: str|None)
    """
    payment_intent_id = getattr(reservation, "stripe_payment_intent_id", None)
    if not payment_intent_id:
        logger.warning(
            f"[verify_payment_method] Aucun PaymentIntent Stripe associé à la réservation {getattr(reservation, 'code', '[unknown]')}."
        )
        return False, "Aucun PaymentIntent Stripe associé à cette réservation."

    try:
        logger.info(
            f"[verify_payment_method] Vérification du PaymentIntent Stripe {payment_intent_id} pour la réservation {getattr(reservation, 'code', '[unknown]')}."
        )
        intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["payment_method"])
        payment_method = getattr(intent, "payment_method", None)
        if payment_method:
            # payment_method peut être un objet ou un id
            payment_method_id = payment_method.id if hasattr(payment_method, "id") else str(payment_method)
            logger.info(
                f"[verify_payment_method] Moyen de paiement trouvé pour la réservation {getattr(reservation, 'code', '[unknown]')} : {payment_method_id}"
            )
            reservation.stripe_saved_payment_method_id = payment_method_id
            reservation.save(update_fields=["stripe_saved_payment_method_id"])
            return (
                True,
                f"Moyen de paiement trouvé : {payment_method_id}",
            )
        else:
            logger.warning(
                f"[verify_payment_method] Aucun moyen de paiement trouvé pour le PaymentIntent {payment_intent_id}."
            )
            return False, "Aucun moyen de paiement trouvé pour cette réservation."
    except Exception as e:
        logger.error(
            f"[verify_payment_method] Erreur lors de la récupération du moyen de paiement Stripe {payment_intent_id} : {e}"
        )
        return False, f"Erreur lors de la récupération du moyen de paiement Stripe : {e}"


def verify_deposit_payment(reservation: Any) -> tuple[bool, str]:
    """
    Vérifie si la caution d'une réservation a été payée et retourne un message d'état en français.
    Args:
        reservation: L'objet réservation.
    Returns:
        (True, message) si payée, (False, message) sinon.
    """
    if not getattr(reservation, "stripe_deposit_payment_intent_id", None):
        return False, "Aucun paiement de caution Stripe associé à cette réservation."

    try:
        intent = stripe.PaymentIntent.retrieve(reservation.stripe_deposit_payment_intent_id)
        status = intent.status

        if status == "succeeded":
            amount_cents = getattr(intent, "amount_received", 0)
            amount = Decimal(amount_cents) / 100  # cents to euros
            reservation.caution_charged = True
            reservation.amount_charged = amount
            reservation.save(update_fields=["caution_charged", "amount_charged"])
            logger.info(f"✅ Caution pour la réservation {reservation.code} confirmée : {amount:.2f} €")
            return True, f"Caution payée et confirmée ({amount:.2f} € reçus)."
        elif status == "processing":
            return False, "Le paiement de la caution est en cours de traitement. Veuillez réessayer plus tard."
        elif status == "requires_payment_method":
            return False, "Le paiement de la caution a échoué ou a été annulé. Un nouveau moyen de paiement est requis."
        elif status == "requires_action":
            return (
                False,
                "Le paiement de la caution nécessite une action supplémentaire de l'utilisateur (3D Secure, etc.).",
            )
        elif status == "canceled":
            return False, "Le paiement de la caution a été annulé."
        else:
            return False, f"Statut du paiement Stripe pour la caution : {status}."

    except stripe.error.StripeError as e:
        logger.error(
            f"❌ Erreur Stripe lors de la vérification du paiement de caution pour la réservation {reservation.code}: {e}"
        )
        return False, "Erreur Stripe lors de la vérification du paiement de caution."
    except Exception as e:
        logger.error(
            f"❌ Erreur inattendue lors de la vérification du paiement de caution pour la réservation {reservation.code}: {e}"
        )
        return False, "Erreur inattendue lors de la vérification du paiement de caution."


def verify_refund(reservation: Any) -> tuple[bool, str, Decimal]:
    """
    Recherche le montant remboursé pour une réservation à partir du stripe_payment_intent_id.
    Args:
        reservation: L'objet réservation.
    Returns:
        (True, message, amount) si remboursé, (False, message, Decimal('0.00')) sinon.
    """
    payment_intent_id = getattr(reservation, "stripe_payment_intent_id", None)
    if not payment_intent_id:
        return False, "Aucun PaymentIntent Stripe associé à cette réservation.", Decimal("0.00")

    try:
        # Récupère tous les remboursements liés à ce PaymentIntent
        refunds = stripe.Refund.list(payment_intent=payment_intent_id, limit=10)
        total_refunded = Decimal("0.00")
        for refund in refunds.auto_paging_iter() if hasattr(refunds, "auto_paging_iter") else refunds.data:
            if getattr(refund, "status", None) == "succeeded":
                amount = Decimal(getattr(refund, "amount", 0)) / 100
                total_refunded += amount

        if total_refunded > 0:
            reservation.refunded = True
            reservation.refund_amount = amount
            reservation.save(update_fields=["refunded", "refund_amount"])
            return True, f"Montant total remboursé : {total_refunded:.2f} €."
        else:
            return False, "Aucun remboursement trouvé pour cette réservation."
    except stripe.error.StripeError as e:
        logger.error(
            f"❌ Erreur Stripe lors de la récupération du remboursement pour la réservation {reservation.code}: {e}"
        )
        return False, "Erreur Stripe lors de la récupération du remboursement."
    except Exception as e:
        logger.error(
            f"❌ Erreur inattendue lors de la récupération du remboursement pour la réservation {reservation.code}: {e}"
        )
        return False, "Erreur inattendue lors de la récupération du remboursement."
