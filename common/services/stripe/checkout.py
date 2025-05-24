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

    id: str  # The session ID
    object: str  # Always 'checkout.session' for checkout session events
    amount_subtotal: int  # The subtotal amount for the session
    amount_total: int  # Total amount for the session (including taxes, discounts, etc.)
    cancel_url: str  # URL to redirect the user if they cancel the checkout
    client_reference_id: Optional[str] = None  # Optional reference ID set by the client
    created: int  # Timestamp when the session was created
    currency: StripeCurrency  # The currency of the session (e.g., 'usd', 'eur')
    customer: str  # Stripe customer ID
    customer_email: Optional[str] = None  # Customer's email address (nullable)
    metadata: Optional[Dict[str, str]] = None  # Custom metadata attached to the session
    payment_intent: Optional[str] = None  # Payment intent ID (if applicable)
    payment_method_types: List[str]  # Allowed payment method types (e.g., 'card')
    payment_status: str  # The payment status (e.g., 'paid', 'unpaid')
    shipping_address_collection: Optional[Dict[str, bool]] = None  # Whether to collect shipping address
    status: str  # Status of the session (e.g., 'complete', 'open')
    success_url: str  # URL to redirect the user after successful checkout
    total_details: Dict[str, int]  # Breakdown of the total (e.g., shipping, taxes, discounts)
    mode: str  # Mode of the session (e.g., 'payment', 'subscription')
    shipping: Optional[Dict[str, str]] = None  # Shipping details if applicable
    discounts: Optional[List[Dict[str, str]]] = None  # Discounts applied to the session
    automatic_tax: Optional[Dict[str, bool]] = None  # Whether tax is calculated automatically
    expires_at: Optional[int] = None  # The timestamp for when the session will expire
    subscription: Optional[str] = None  # Subscription ID (if applicable)


class StripeEventRequest(BaseModel):
    """Request field in the Stripe event, such as 'idempotency_key'."""

    id: Optional[str] = None  # It might be null
    idempotency_key: Optional[str] = None


class StripeBaseEvent(BaseModel):
    """The base event object for Stripe webhook events."""

    id: str
    api_version: str
    request: StripeEventRequest  # Optional request data
    type: str  # The event type (e.g., 'checkout.session.completed')
    data: StripeCheckoutSessionData  # This holds the session data


class StripeCheckoutSessionEventData(BaseModel):
    """Event data for the checkout session completed event."""

    object: StripeBaseEvent  # Here we nest the base event with 'object' containing the data