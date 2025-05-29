import stripe
import logging
from rest_framework.request import Request
from pydantic import ValidationError
from django.conf import settings

from common.services.stripe.stripe_event import EventType, StripeEvent
from logement.services.payment_service import (
    handle_payment_intent_succeeded,
    handle_checkout_session_completed,
    handle_payment_failed,
    handle_charge_refunded,
    handle_transfer_created,
)

logger = logging.getLogger(__name__)
# Set up Stripe with the secret key
stripe.api_key = settings.STRIPE_PRIVATE_KEY


def handle_stripe_webhook_request(request):
    event = _make_webhook_event_from_request(request)
    handle_webhook_event(event)


def _make_webhook_event_from_request(request: Request):
    """
    Given a Rest Framework request, construct a webhook event.

    :param event: event from Stripe Webhook, defaults to None. Used for test.
    """

    logger.info(request.body)
    return stripe.Webhook.construct_event(
        payload=request.body,
        sig_header=request.META["HTTP_STRIPE_SIGNATURE"],
        secret=settings.STRIPE_WEBHOOK_SECRET,
    )


def _handle_event_type_validation_error(err: ValidationError):
    """
    Handle Pydantic ValidationError raised when parsing StripeEvent,
    ignores the error if it is caused by unimplemented event.type;
    Otherwise, raise the error.
    """
    event_type_error = False

    # Log the error message to help debug
    logger.error(f"❌ Validation error occurred: {err}")

    for error in err.errors():
        # Log the details of each error
        error_loc = error.get("loc")
        error_msg = error.get("msg")
        error_type = error.get("type")

        logger.error(
            f"Error Location: {error_loc}, Message: {error_msg}, Type: {error_type}"
        )

        # Check if the error is related to unimplemented event type
        if (
            error_loc[0] == "event"
            and error.get("ctx", {}).get("discriminator_key", {}) == "type"
        ):
            event_type_error = True
            logger.info(
                f"⚠️ Ignored validation error for unimplemented event type: {error_loc}"
            )
            break

    # If the error is not related to unimplemented event types, raise the error
    if event_type_error is False:
        logger.error(
            "❌ Validation error is not related to event type, raising exception."
        )
        raise err


def handle_webhook_event(event):
    """Perform actions given Stripe Webhook event data."""

    try:
        logger.info(f"📩 Handling Stripe event type: {event['type']}")

        e = StripeEvent(event=event)
    except ValidationError as err:
        logger.error(f"❌ Error parsing event: {err}")
        _handle_event_type_validation_error(err)
        return

    try:
        event_type = e.event.type

        # Debug logging to ensure we're passing the right data
        logger.debug(f"Event data: {e.event.data}")

        if event_type == EventType.CHECKOUT_SESSION_COMPLETED:
            handle_checkout_session_completed(e.event.data)

        elif event_type == EventType.PAYMENT_INTENT_SUCCEEDED:
            handle_payment_intent_succeeded(e.event.data)

        elif event_type == EventType.PAYMENT_INTENT_FAILED:
            handle_payment_failed(e.event.data)

        elif event_type == EventType.REFUND_UPDATED:
            handle_charge_refunded(e.event.data)

        elif event_type == EventType.TRANSFER_CREATED:
            handle_transfer_created(e.event.data)

        else:
            logger.warning(f"⚠️ Unsupported event type: {event_type}")
    except Exception as err:
        logger.error(f"❌ Error parsing event: {err}")
        return
