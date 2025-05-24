from typing import Optional, Dict
from pydantic import BaseModel
from .currency import StripeCurrency  # Assuming StripeCurrency is already defined
from .payment_method import PaymentMethodDetails


class StripeCharge(BaseModel):
    """Represents a Stripe Charge object"""

    id: str  # Charge ID
    amount: int  # Amount in cents (e.g., 31543 for 315.43)
    amount_captured: int  # Amount captured for this charge
    amount_refunded: int  # Amount refunded for this charge
    currency: StripeCurrency  # Currency of the charge (e.g., 'eur')
    status: str  # Status of the charge (e.g., "succeeded", "pending", "failed")
    created: int  # Timestamp when the charge was created
    payment_intent: Optional[
        str
    ]  # PaymentIntent ID (if associated with a PaymentIntent)
    captured: bool  # Whether the charge was captured
    receipt_url: Optional[str]  # URL to view the receipt for this charge
    customer: Optional[str]  # Customer ID associated with the charge
    metadata: Optional[Dict[str, str]]  # Metadata associated with the charge
    description: Optional[str]  # Description of the charge
    payment_method: Optional[str]  # Payment method details used for the charge
    payment_method_details: Optional[
        PaymentMethodDetails
    ]  # Payment method details for the charge

    class Config:
        anystr_strip_whitespace = True


class StripeChargeEventData(BaseModel):
    """Event data for a Stripe Charge object"""

    object: StripeCharge  # The charge object
    previous_attributes: Optional[StripeCharge]  # Optionally track previous attributes
