"""Stripe service wrapper for Matcha Work credit checkout."""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import UUID

try:
    import stripe
except Exception:  # pragma: no cover - handled at runtime
    stripe = None

from ...config import get_settings

CREDIT_PACKS: dict[str, dict[str, Any]] = {
    "starter": {"credits": 100, "amount_cents": 2900, "label": "100 Credits"},
    "pro": {"credits": 500, "amount_cents": 9900, "label": "500 Credits"},
    "business": {"credits": 2000, "amount_cents": 29900, "label": "2,000 Credits"},
}


class StripeServiceError(Exception):
    """Raised when Stripe operations fail or are misconfigured."""


class StripeService:
    def __init__(self):
        self.settings = get_settings()

    def _ensure_secret_key(self) -> None:
        if stripe is None:
            raise StripeServiceError("Stripe SDK is not installed. Run `pip install stripe`.")
        if not self.settings.stripe_secret_key:
            raise StripeServiceError("Stripe is not configured for this environment")
        stripe.api_key = self.settings.stripe_secret_key

    def _ensure_webhook_secret(self) -> None:
        if not self.settings.stripe_webhook_secret:
            raise StripeServiceError("Stripe webhook secret is not configured")

    def get_credit_pack(self, pack_id: str) -> Optional[dict[str, Any]]:
        return CREDIT_PACKS.get(pack_id)

    def list_credit_packs(self) -> list[dict[str, Any]]:
        return [
            {
                "pack_id": pack_id,
                "credits": int(pack["credits"]),
                "amount_cents": int(pack["amount_cents"]),
                "label": str(pack["label"]),
                "currency": "usd",
            }
            for pack_id, pack in CREDIT_PACKS.items()
        ]

    async def create_checkout_session(
        self,
        company_id: UUID,
        pack_id: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ):
        self._ensure_secret_key()

        pack = self.get_credit_pack(pack_id)
        if pack is None:
            raise StripeServiceError("Invalid credit pack selected")

        resolved_success_url = success_url or self.settings.stripe_success_url
        resolved_cancel_url = cancel_url or self.settings.stripe_cancel_url

        metadata = {
            "company_id": str(company_id),
            "pack_id": pack_id,
            "credits_to_add": str(pack["credits"]),
        }

        def _create():
            return stripe.checkout.Session.create(
                mode="payment",
                success_url=resolved_success_url,
                cancel_url=resolved_cancel_url,
                payment_method_types=["card"],
                metadata=metadata,
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": int(pack["amount_cents"]),
                            "product_data": {
                                "name": f"Matcha Work Credits - {pack['label']}",
                                "description": f"{pack['credits']} AI operations",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            raise StripeServiceError(f"Failed to create Stripe checkout session: {exc}") from exc

    async def verify_webhook(self, payload: bytes, signature: str):
        self._ensure_secret_key()
        self._ensure_webhook_secret()

        def _construct():
            return stripe.Webhook.construct_event(
                payload,
                signature,
                self.settings.stripe_webhook_secret,
            )

        try:
            return await asyncio.to_thread(_construct)
        except Exception as exc:
            raise StripeServiceError(f"Invalid Stripe webhook: {exc}") from exc

    async def get_session(self, session_id: str):
        self._ensure_secret_key()

        def _retrieve():
            return stripe.checkout.Session.retrieve(session_id)

        try:
            return await asyncio.to_thread(_retrieve)
        except Exception as exc:
            raise StripeServiceError(f"Failed to retrieve Stripe checkout session: {exc}") from exc
