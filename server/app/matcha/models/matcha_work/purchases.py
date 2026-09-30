"""Request shapes for saved payment cards and shipping addresses
(routes/matcha_work/payment_cards.py). Addresses are validated and cleaned
by services/matcha_work/shipping_addresses.normalize, not here: these only
carry the fields."""
from __future__ import annotations

from pydantic import BaseModel


class AddressIn(BaseModel):
    name: str
    line1: str
    line2: str = ""
    city: str
    region: str = ""
    postal_code: str
    country: str = "US"
    phone: str = ""


class PaymentCardCreate(BaseModel):
    number: str
    exp_month: int
    exp_year: int
    label: str = ""
    # None: bill to the shipping address.
    billing_address: AddressIn | None = None


class BillingAddressUpdate(BaseModel):
    # None: bill to the shipping address.
    billing_address: AddressIn | None = None


class ShippingAddressIn(AddressIn):
    is_default: bool = False
