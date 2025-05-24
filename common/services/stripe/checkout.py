from typing import Optional, List, Dict
from pydantic import BaseModel
from .currency import StripeCurrency  # Assuming StripeCurrency is already defined
from .price import StripePrice  # Assuming StripePrice is already defined


class StripeCheckoutSessionLineItem(BaseModel):
    """Represents an item in the Stripe Checkout Session."""

    price: StripePrice
    quantity: int
    description: Optional[str]  # Optional description of the item
    amount_total: int  # Amount in cents
    currency: StripeCurrency


class StripeCheckoutSessionEventData(BaseModel):
    """Event data for the checkout session completed event."""

    session_id: str
    customer_email: Optional[str]  # Optional since it might not be present in all cases
    amount_total: int  # In cents
    payment_status: Optional[str]  # Optional payment status
    line_items: Optional[
        List[StripeCheckoutSessionLineItem]
    ]  # Optional if line items are present
    metadata: Optional[Dict[str, str]]  # Optional metadata tied to the session
    success_url: Optional[str]  # Optional success URL
    cancel_url: Optional[str]  # Optional cancel URL
    client_reference_id: Optional[str]  # Optional client reference ID
    created: int  # The timestamp of when the session was created
    currency: StripeCurrency  # The currency for the session (e.g., 'usd', 'eur')
    mode: str  # The mode of the session ('payment', 'subscription', 'setup')
    status: str  # Status of the session ('open', 'complete', etc.)
    payment_intent: Optional[str]  # Payment intent ID (if applicable)
    payment_method_types: Optional[
        List[str]
    ]  # List of payment method types allowed for the session (e.g., ['card'])
    shipping_address_collection: Optional[
        Dict[str, bool]
    ]  # Whether to collect the shipping address
    phone_number_collection: Optional[
        Dict[str, bool]
    ]  # Whether to collect the phone number
    discounts: Optional[
        List[Dict[str, str]]
    ]  # List of discounts applied to the session
    automatic_tax: Optional[
        Dict[str, bool]
    ]  # Whether automatic tax calculation is enabled
    expires_at: Optional[int]  # Timestamp of when the session will expire
    subscription: Optional[
        str
    ]  # The subscription ID if the session is tied to a subscription
    customer: Optional[str]  # Stripe customer ID, optional
    locale: Optional[str]  # The locale for the checkout session (e.g., 'en', 'fr')
    shipping: Optional[Dict[str, str]]  # Shipping details, if collected


class StripeCheckoutSession(BaseModel):
    """Represents a Stripe Checkout Session object."""

    id: str
    object: str  # This should be 'checkout.session' according to Stripe's API
    amount_subtotal: int  # The subtotal amount for the session
    amount_total: (
        int  # The total amount for the session (including taxes, discounts, etc.)
    )
    cancel_url: str  # URL to redirect the user if they cancel the checkout
    client_reference_id: Optional[str]  # Optional reference ID set by the client
    created: int  # Timestamp when the session was created
    currency: StripeCurrency  # Currency for the session (e.g., 'usd', 'eur')
    customer: str  # Stripe customer ID
    customer_email: str  # Customer's email address
    metadata: Optional[Dict[str, str]]  # Custom metadata attached to the session
    payment_intent: Optional[str]  # Payment intent ID (if applicable)
    payment_method_types: List[str]  # Allowed payment method types (e.g., 'card')
    payment_status: str  # The payment status (e.g., 'paid', 'unpaid')
    shipping_address_collection: Optional[
        Dict[str, bool]
    ]  # Whether to collect shipping address
    status: str  # Status of the session (e.g., 'complete', 'open')
    success_url: str  # URL to redirect the user after successful checkout
    total_details: Dict[
        str, int
    ]  # Breakdown of the total (e.g., shipping, taxes, discounts)
    mode: str  # Mode of the session (e.g., 'payment', 'subscription')
    shipping: Optional[Dict[str, str]]  # Shipping details if applicable
    discounts: Optional[List[Dict[str, str]]]  # Discounts applied to the session
    automatic_tax: Optional[Dict[str, bool]]  # Whether tax is calculated automatically
    expires_at: Optional[int]  # The timestamp for when the session will expire
    subscription: Optional[str]  # Subscription ID (if this is for a subscription)
