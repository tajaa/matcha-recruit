"""Bounded public storefront account payloads."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from .shop import CappeCartItem


class ShopperStart(BaseModel):
    email: EmailStr = Field(max_length=320)


class ShopperVerify(ShopperStart):
    code: str = Field(pattern=r"^[0-9]{6}$")


class ShopperRefresh(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class ShopperProfile(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    push_order_updates: bool = True


class Shopper(ShopperProfile):
    id: UUID
    site_id: UUID
    email: str


class ShopperAddress(BaseModel):
    label: str | None = Field(default=None, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str = Field(min_length=1, max_length=20)
    country: str = Field(default="US", pattern=r"^[A-Z]{2}$")
    phone: str | None = Field(default=None, max_length=40)
    is_default: bool = False

    @field_validator("name", "line1", "city", "postal_code")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


class ShopperDevice(BaseModel):
    token: str = Field(min_length=32, max_length=200, pattern=r"^[0-9a-fA-F]+$")
    bundle_id: str = Field(min_length=3, max_length=155)
    environment: Literal["sandbox", "production"]
    app_version: str | None = Field(default=None, max_length=40)


class CartQuoteRequest(BaseModel):
    items: list[CappeCartItem] = Field(min_length=1, max_length=100)
    interval: Literal["week", "month"] | None = None


class SubscriptionCheckout(CartQuoteRequest):
    interval: Literal["week", "month"]
    success_url: str = Field(min_length=1, max_length=2000)
    cancel_url: str = Field(min_length=1, max_length=2000)
