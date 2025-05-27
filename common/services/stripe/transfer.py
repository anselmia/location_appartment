from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from .currency import StripeCurrency  # You must define this Enum


class StripeTransfer(BaseModel):
    """Represents a Stripe Transfer object."""

    id: str
    object: str
    amount: int
    amount_reversed: int
    balance_transaction: Optional[str]
    created: int
    currency: StripeCurrency
    description: Optional[str]
    destination: Optional[str]
    destination_payment: Optional[str]
    livemode: bool
    metadata: Dict[str, Any]
    reversals: Dict[str, Any]
    reversed: bool
    source_transaction: Optional[str]
    source_type: Optional[str]
    transfer_group: Optional[str]

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.created)


class StripeTransferEventData(BaseModel):
    """Event data wrapper for a Stripe Transfer event"""

    object: StripeTransfer
