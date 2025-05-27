from enum import Enum
from typing import Union, Literal, Any, Optional

from pydantic import BaseModel, Field
from common.services.stripe.checkout import StripeCheckoutSessionEventData
from .payment_intent import StripePaymentIntentEventData
from .charge import StripeChargeEventData
from .transfer import StripeTransferEventData


class EventType(str, Enum):
    """See: https://stripe.com/docs/api/events/types"""

    CHECKOUT_SESSION_COMPLETED = "checkout.session.completed"
    CHARGE_REFUNDED = "charge.refunded"
    REFUND_UPDATED = "refund.updated"
    PAYMENT_INTENT_FAILED = "payment_intent.payment_failed"
    PAYMENT_INTENT_SUCCEEDED = "payment_intent.succeeded"
    TRANSFER_REVERSED = "transfer.reversed"


class StripeEventRequest(BaseModel):
    """Based on: https://stripe.com/docs/api/events/object#event_object-request"""

    id: str = None
    idempotency_key: Optional[str] = None


class StripeBaseEvent(BaseModel):
    """
    Based on https://stripe.com/docs/api/events/object
    This is the base event template for more specific Stripe event classes
    """

    id: str
    api_version: str
    data: Any  # overwrite this attribute when inheriting
    type: Literal[Any]  # overwrite this attribute when inheriting


class StripeCheckoutEvent(StripeBaseEvent):
    data: StripeCheckoutSessionEventData
    type: Literal[EventType.CHECKOUT_SESSION_COMPLETED,]


class StripeChargeEvent(StripeBaseEvent):
    data: StripeChargeEventData
    type: Literal[EventType.CHARGE_REFUNDED, EventType.REFUND_UPDATED]


class StripePaymentIntentEvent(StripeBaseEvent):
    data: StripePaymentIntentEventData
    type: Literal[
        EventType.PAYMENT_INTENT_FAILED,
        EventType.PAYMENT_INTENT_SUCCEEDED,
    ]


class StripeTransferEvent(StripeBaseEvent):
    data: StripeTransferEventData
    type: Literal[EventType.TRANSFER_REVERSED,]


class StripeEvent(BaseModel):
    # Add event classes to this attribute as they are implemented, more specific types first.
    # see https://pydantic-docs.helpmanual.io/usage/types/#discriminated-unions-aka-tagged-unions
    event: Union[
        StripePaymentIntentEvent,
        StripeCheckoutEvent,
        StripeChargeEvent,
        StripeTransferEvent,
        StripeBaseEvent,
    ] = Field(discriminator="type")
