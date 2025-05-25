from typing import Optional, Dict, List
from pydantic import BaseModel
from .currency import StripeCurrency  # Assuming StripeCurrency is already defined


class StripePaymentIntent(BaseModel):
    """Represents a Stripe PaymentIntent object."""

    id: str  # Unique identifier for the PaymentIntent
    amount: int  # Amount in cents (e.g., 1000 means 10.00)
    amount_received: int  # Amount actually received for this PaymentIntent, in cents
    currency: str
    status: str  # Status of the PaymentIntent, e.g., 'succeeded', 'requires_payment_method', 'requires_action'
    payment_method: Optional[
        str
    ]  # PaymentMethod used for the PaymentIntent (if available)
    payment_method_types: List[str]  # List of payment method types (e.g., ['card'])
    confirmation_method: (
        str  # How the PaymentIntent was confirmed, 'automatic' or 'manual'
    )
    created: int  # Timestamp of when the PaymentIntent was created (in Unix format)
    customer: Optional[
        str
    ]  # Customer ID associated with the PaymentIntent (if available)
    description: Optional[str]  # Optional description of the payment
    metadata: Optional[Dict[str, str]]  # Custom metadata attached to the PaymentIntent
    receipt_email: Optional[str]  # Email to send the receipt (if provided)
    shipping: Optional[Dict[str, str]]  # Shipping information if applicable
    transfer_group: Optional[str]  # Group of transfers to be made (if applicable)
    transfer_data: Optional[Dict[str, str]]  # Data for transfer if applicable


class StripePaymentIntentEventData(BaseModel):
    """Event data for Stripe PaymentIntent object"""

    object: StripePaymentIntent
