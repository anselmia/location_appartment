from typing import Optional, Dict
from pydantic import BaseModel
from .currency import StripeCurrency  # Assuming StripeCurrency is already defined
from .payment_method import PaymentMethodDetails


class StripeCharge(BaseModel):
    """Represents a Stripe Charge object"""

    id: str  # Charge ID
    object: str
    amount: int  # Amount in cents (e.g., 31543 for 315.43)
    currency: StripeCurrency  # Currency of the charge (e.g., 'eur')
    status: str  # Status of the charge (e.g., "succeeded", "pending", "failed")
    created: int  # Timestamp when the charge was created
    payment_intent: Optional[
        str
    ]  # PaymentIntent ID (if associated with a PaymentIntent)
    metadata: Optional[Dict[str, str]]  # Metadata associated with the charge

    class Config:
        anystr_strip_whitespace = True


class StripeChargeEventData(BaseModel):
    """Event data for a Stripe Charge object"""

    object: StripeCharge  # The charge object
