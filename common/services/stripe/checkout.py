from typing import Optional, List, Dict
from pydantic import BaseModel
from .currency import StripeCurrency  # Assuming StripeCurrency is already defined
from .price import StripePrice  # Assuming StripePrice is already defined


class StripeCheckoutSessionLineItem(BaseModel):
    """Represents an item in the Stripe Checkout Session."""

    price: StripePrice
    quantity: int
    description: Optional[str] = None  # Optional description of the item
    amount_total: int  # Amount in cents
    currency: StripeCurrency


class StripeCheckoutSessionData(BaseModel):
    """Contains the session object data in the webhook event."""

    id: str
    object: str
    amount_subtotal: int
    amount_total: int
    cancel_url: str
    client_reference_id: Optional[str] = None
    created: int
    currency: StripeCurrency
    customer: str
    customer_email: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
    payment_intent: Optional[str] = None
    payment_method_types: List[str]
    payment_status: str
    shipping_address_collection: Optional[Dict[str, bool]] = None
    status: str
    success_url: str
    total_details: Dict[str, int]
    mode: str
    shipping: Optional[Dict[str, str]] = None
    discounts: Optional[List[Dict[str, str]]] = None
    automatic_tax: Optional[Dict[str, bool]] = None
    expires_at: Optional[int] = None
    subscription: Optional[str] = None

    # Making missing fields optional
    data: Optional[Dict[str, str]] = None
    type: Optional[str] = None
    request: Optional[Dict[str, str]] = None
    api_version: Optional[str] = None


class StripeEventRequest(BaseModel):
    """Request field in the Stripe event, such as 'idempotency_key'."""

    id: Optional[str] = None  # It might be null
    idempotency_key: Optional[str] = None


class StripeBaseEvent(BaseModel):
    """The base event object for Stripe webhook events."""

    id: str
    api_version: str
    request: Optional[StripeEventRequest]  # Make request optional
    type: str
    data: (
        StripeCheckoutSessionData  # Adjust this model to reflect actual data structure
    )


class StripeCheckoutSessionEventData(BaseModel):
    """Event data for the checkout session completed event."""

    object: (
        StripeBaseEvent  # Here we nest the base event with 'object' containing the data
    )
