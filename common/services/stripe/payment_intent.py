from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from .currency import StripeCurrency  # Assuming StripeCurrency is already defined


class StripePaymentError(BaseModel):
    code: Optional[str]
    message: Optional[str]
    type: Optional[str]
    payment_method: Optional[Dict[str, Any]]


class StripePaymentIntent(BaseModel):
    """Represents a Stripe PaymentIntent object."""

    id: str
    amount: int
    amount_received: int
    currency: str
    status: str
    payment_method: Optional[str]
    payment_method_types: List[str]
    confirmation_method: str
    created: int
    customer: Optional[str]
    description: Optional[str]
    metadata: Optional[Dict[str, str]]
    receipt_email: Optional[str]
    shipping: Optional[Dict[str, str]]
    transfer_group: Optional[str]
    transfer_data: Optional[Dict[str, str]]
    last_payment_error: Optional[StripePaymentError]


class StripePaymentIntentEventData(BaseModel):
    """Event data for Stripe PaymentIntent object"""

    object: StripePaymentIntent
