from typing import Optional, Dict
from pydantic import BaseModel, Field


class PaymentMethodDetailsCard(BaseModel):
    """Card payment method details for a Stripe charge"""

    brand: str  # Brand of the card (e.g., 'visa', 'mastercard')
    country: str  # Country of the card (e.g., 'US', 'FR')
    funding: str  # Funding type (e.g., 'credit', 'debit')
    last4: str  # Last 4 digits of the card number
    cvc_check: Optional[str] = None  # CVC check status (e.g., 'pass', 'fail')
    exp_month: int  # Expiration month of the card
    exp_year: int  # Expiration year of the card
    fingerprint: str  # Card fingerprint (for uniquely identifying cards)
    network: str  # Network of the card (e.g., 'visa')
    receipt_url: Optional[str] = None  # URL to view the receipt for the charge
    mandate: Optional[str] = None  # Mandate reference (if available)

    class Config:
        anystr_strip_whitespace = True


class PaymentMethodDetails(BaseModel):
    """Payment method details for a Stripe charge"""

    card: PaymentMethodDetailsCard  # Card payment method details


class StripeBillingDetails(BaseModel):
    """Billing details for the payment method."""

    name: Optional[str]  # Customer's name
    address: Optional[
        Dict[str, str]
    ]  # e.g., {"line1": "123 Main St", "city": "Anytown", "country": "US"}


class StripePaymentMethod(BaseModel):
    """Represents a Stripe PaymentMethod object."""

    amount: str
    amount_captured: str
    amount_refunded: str
    id: str  # Unique identifier for the payment method
    object: str  # Always 'payment_method'
    type: str  # Type of the payment method (e.g., 'card', 'ideal', 'bancontact')
    customer: Optional[str]  # Stripe customer ID associated with this payment method
    billing_details: StripeBillingDetails  # Billing details of the payment method
    payment_method_details: PaymentMethodDetails
    card: Optional[PaymentMethodDetailsCard]  # If it's a card, the card details
    created: int  # Timestamp of when the payment method was created
    metadata: Optional[Dict[str, str]]  # Custom metadata attached to the payment method
    card_present: Optional[
        bool
    ]  # Indicates if the payment method was present for the transaction


class StripePaymentMethodEventData(BaseModel):
    """Event data for Stripe PaymentMethod object"""

    object: StripePaymentMethod
