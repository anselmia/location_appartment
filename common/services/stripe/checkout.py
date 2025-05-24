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


class StripeCheckoutSessionEventData(BaseModel):
    """Event data for the checkout session completed event."""

    session_id: str
    customer_email: Optional[str] = None  # Optional customer email, can be None if missing
    amount_total: int  # In cents
    payment_status: Optional[str] = None  # Optional payment status
    line_items: Optional[List[StripeCheckoutSessionLineItem]] = None  # Optional if line items are present
    metadata: Optional[Dict[str, str]] = None  # Optional metadata tied to the session
    success_url: Optional[str] = None  # Optional success URL
    cancel_url: Optional[str] = None  # Optional cancel URL
    client_reference_id: Optional[str] = None  # Optional client reference ID
    created: int  # The timestamp of when the session was created
    currency: StripeCurrency  # The currency for the session (e.g., 'usd', 'eur')
    mode: str  # The mode of the session ('payment', 'subscription', 'setup')
    status: str  # Status of the session ('open', 'complete', etc.)
    payment_intent: Optional[str] = None  # Optional payment intent ID (if applicable)
    payment_method_types: Optional[List[str]] = None  # List of payment method types allowed for the session (e.g., ['card'])
    shipping_address_collection: Optional[Dict[str, bool]] = None  # Whether to collect the shipping address
    phone_number_collection: Optional[Dict[str, bool]] = None  # Whether to collect the phone number
    discounts: Optional[List[Dict[str, str]]] = None  # List of discounts applied to the session
    automatic_tax: Optional[Dict[str, bool]] = None  # Whether automatic tax calculation is enabled
    expires_at: Optional[int] = None  # Timestamp of when the session will expire
    subscription: Optional[str] = None  # The subscription ID if the session is tied to a subscription
    customer: Optional[str] = None  # Stripe customer ID, optional
    locale: Optional[str] = None  # The locale for the checkout session (e.g., 'en', 'fr')
    shipping: Optional[Dict[str, str]] = None  # Shipping details, if collected


class StripeCheckoutSession(BaseModel):
    """Represents a Stripe Checkout Session object."""

    id: str
    object: str  # This should be 'checkout.session' according to Stripe's API
    amount_subtotal: int  # The subtotal amount for the session
    amount_total: int  # The total amount for the session (including taxes, discounts, etc.)
    cancel_url: str  # URL to redirect the user if they cancel the checkout
    client_reference_id: Optional[str] = None  # Optional reference ID set by the client
    created: int  # Timestamp when the session was created
    currency: StripeCurrency  # Currency for the session (e.g., 'usd', 'eur')
    customer: str  # Stripe customer ID
    customer_email: str  # Customer's email address
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
    subscription: Optional[str] = None  # Subscription ID (if this is for a subscription)