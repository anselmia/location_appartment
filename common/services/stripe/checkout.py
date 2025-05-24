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


class StripeCheckoutSessionEventobject(BaseModel):
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


class StripeCheckoutSessionEventdata(BaseModel):
    """Contains the session object data in the webhook event."""

    object: StripeCheckoutSessionEventobject
