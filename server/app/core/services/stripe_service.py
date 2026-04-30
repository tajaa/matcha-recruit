"""Stripe service wrapper for Matcha Work credit checkout."""

from __future__ import annotations

import asyncio
import math
from typing import Any, Optional
from uuid import UUID

try:
    import stripe
except ImportError:  # pragma: no cover - handled at runtime
    stripe = None

from ...config import get_settings

# $2.50 processing fee added on top of each pack
FEE_CENTS = 250

# Dollar-based credit packs — credits represent real dollar amounts
CREDIT_PACKS: dict[str, dict[str, Any]] = {
    "twenty": {
        "credits": 20.0,
        "base_cents": 2000,
        "amount_cents": 2000 + FEE_CENTS,   # $22.50
        "label": "$20 AI Credits",
        "description": "$20 of AI usage + $2.50 processing fee",
    },
    "fifty": {
        "credits": 50.0,
        "base_cents": 5000,
        "amount_cents": 5000 + FEE_CENTS,   # $52.50
        "label": "$50 AI Credits",
        "description": "$50 of AI usage + $2.50 processing fee",
    },
}

# Free credits granted to every new business on signup
FREE_SIGNUP_CREDITS = 5.0


def matcha_lite_price_cents(headcount: int) -> Optional[int]:
    """Monthly price for Matcha Lite in cents. Returns None if headcount < 1 or > 300."""
    if headcount < 1 or headcount > 300:
        return None
    return math.ceil(headcount / 10) * 10_000


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
                "credits": float(pack["credits"]),
                "base_cents": int(pack["base_cents"]),
                "amount_cents": int(pack["amount_cents"]),
                "fee_cents": FEE_CENTS,
                "label": str(pack["label"]),
                "description": str(pack["description"]),
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
        """Create a one-time payment checkout session."""
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
            "mode": "payment",
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
                                "name": f"Matcha Work — {pack['label']}",
                                "description": pack["description"],
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

    async def create_subscription_checkout_session(
        self,
        company_id: UUID,
        pack_id: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ):
        """Create a recurring subscription checkout session (monthly auto-renewal)."""
        self._ensure_secret_key()

        pack = self.get_credit_pack(pack_id)
        if pack is None:
            raise StripeServiceError("Invalid credit pack selected")

        resolved_success_url = success_url or self.settings.stripe_success_url
        resolved_cancel_url = cancel_url or self.settings.stripe_cancel_url

        metadata = {
            "company_id": str(company_id),
            "pack_id": pack_id,
            "credits_per_cycle": str(pack["credits"]),
            "mode": "subscription",
        }

        def _create():
            return stripe.checkout.Session.create(
                mode="subscription",
                success_url=resolved_success_url,
                cancel_url=resolved_cancel_url,
                payment_method_types=["card"],
                metadata=metadata,
                subscription_data={"metadata": metadata},
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": int(pack["amount_cents"]),
                            "recurring": {"interval": "month"},
                            "product_data": {
                                "name": f"Matcha Work — {pack['label']} (Monthly)",
                                "description": f"Auto-renews monthly. {pack['description']}",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            raise StripeServiceError(f"Failed to create Stripe subscription session: {exc}") from exc

    async def create_personal_subscription_checkout(
        self,
        company_id: UUID,
        user_id: UUID,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ):
        """Create the $20/month Matcha Work Personal Plus checkout for an individual user.

        Plus unlocks the pro Gemini model in matcha-work chat. Token quota stays
        at the free-tier level (1M/mo) — this is a model-access upgrade, not a
        token top-up. Reuses the existing subscription webhook path with a
        distinct pack_id.
        """
        self._ensure_secret_key()

        resolved_success_url = success_url or self.settings.stripe_success_url
        resolved_cancel_url = cancel_url or self.settings.stripe_cancel_url

        metadata = {
            "company_id": str(company_id),
            "user_id": str(user_id),
            "pack_id": "matcha_work_personal",
            "billing_type": "token_budget",
            "tokens_per_cycle": "1000000",
            "mode": "subscription",
        }

        def _create():
            return stripe.checkout.Session.create(
                mode="subscription",
                success_url=resolved_success_url,
                cancel_url=resolved_cancel_url,
                payment_method_types=["card"],
                metadata=metadata,
                subscription_data={"metadata": metadata},
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": 2000,
                            "recurring": {"interval": "month"},
                            "product_data": {
                                "name": "Matcha Work Plus",
                                "description": "Access to the pro AI model — better reasoning, longer context",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            raise StripeServiceError(f"Failed to create Personal subscription session: {exc}") from exc

    async def create_ir_upgrade_checkout(
        self,
        company_id: UUID,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ):
        """Subscription checkout for upgrading a resources_free tenant to Matcha IR.

        Webhook (`stripe_webhook.py`) catches the `checkout.session.completed`
        event with `metadata.type == 'matcha_ir_upgrade'` and flips the
        company to incidents=true + employees=true + signup_source=
        ir_only_self_serve so the slim IR sidebar takes over on next refresh.
        """
        self._ensure_secret_key()

        amount_cents = getattr(self.settings, "matcha_ir_price_cents", None) or 4900

        resolved_success_url = success_url or self.settings.stripe_success_url
        resolved_cancel_url = cancel_url or self.settings.stripe_cancel_url

        metadata = {
            "company_id": str(company_id),
            "type": "matcha_ir_upgrade",
            "mode": "subscription",
        }

        def _create():
            return stripe.checkout.Session.create(
                mode="subscription",
                success_url=resolved_success_url,
                cancel_url=resolved_cancel_url,
                payment_method_types=["card"],
                metadata=metadata,
                subscription_data={"metadata": metadata},
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": int(amount_cents),
                            "recurring": {"interval": "month"},
                            "product_data": {
                                "name": "Matcha IR",
                                "description": "Incident reporting + employee management. Auto-renews monthly.",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            raise StripeServiceError(f"Failed to create Matcha IR checkout: {exc}") from exc

    async def create_matcha_lite_checkout(
        self,
        company_id: UUID,
        headcount: int,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ):
        """Subscription checkout for Matcha Lite (IR + Resources) priced by headcount.

        Pricing: $100/mo per 10 employees (ceil). 1–10 → $100, 11–20 → $200, …, 291–300 → $3,000.
        Headcount > 300 is rejected — must contact sales.
        Webhook catches metadata.type == 'matcha_lite' and activates incidents+employees+discipline.
        """
        self._ensure_secret_key()

        amount_cents = matcha_lite_price_cents(headcount)
        if amount_cents is None:
            raise StripeServiceError("Headcount over 300 — please contact us for pricing")

        resolved_success_url = success_url or self.settings.stripe_success_url
        resolved_cancel_url = cancel_url or self.settings.stripe_cancel_url

        metadata = {
            "company_id": str(company_id),
            "type": "matcha_lite",
            "headcount": str(headcount),
            "mode": "subscription",
        }

        def _create():
            return stripe.checkout.Session.create(
                mode="subscription",
                success_url=resolved_success_url,
                cancel_url=resolved_cancel_url,
                payment_method_types=["card"],
                metadata=metadata,
                subscription_data={"metadata": metadata},
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": amount_cents,
                            "recurring": {"interval": "month"},
                            "product_data": {
                                "name": "Matcha Lite",
                                "description": (
                                    f"Incident reporting, employee management, discipline + HR resources "
                                    f"({headcount} employee{'s' if headcount != 1 else ''}). Auto-renews monthly."
                                ),
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            raise StripeServiceError(f"Failed to create Matcha Lite checkout: {exc}") from exc

    async def create_recruiter_tier_checkout(
        self,
        user_id: UUID,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ):
        """Create a $30/month Matcha Recruiter subscription checkout.

        Recruiter tier grants the user access to parsed applicant resumes
        on channel job postings. Webhook handler reads pack_id = matcha_recruiter
        and bumps users.recruiter_until by one month.
        """
        self._ensure_secret_key()

        resolved_success_url = success_url or self.settings.stripe_success_url
        resolved_cancel_url = cancel_url or self.settings.stripe_cancel_url

        metadata = {
            "user_id": str(user_id),
            "pack_id": "matcha_recruiter",
            "billing_type": "recruiter_tier",
            "mode": "subscription",
        }

        def _create():
            return stripe.checkout.Session.create(
                mode="subscription",
                success_url=resolved_success_url,
                cancel_url=resolved_cancel_url,
                payment_method_types=["card"],
                metadata=metadata,
                subscription_data={"metadata": metadata},
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": 3000,
                            "recurring": {"interval": "month"},
                            "product_data": {
                                "name": "Matcha Recruiter",
                                "description": "Unlock parsed applicant resumes on channel job postings",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            raise StripeServiceError(f"Failed to create Recruiter tier session: {exc}") from exc

    async def create_token_subscription_checkout(
        self,
        company_id: UUID,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ):
        """Create a $40/month token subscription checkout."""
        self._ensure_secret_key()

        resolved_success_url = success_url or self.settings.stripe_success_url
        resolved_cancel_url = cancel_url or self.settings.stripe_cancel_url

        metadata = {
            "company_id": str(company_id),
            "pack_id": "matcha_work_pro",
            "billing_type": "token_budget",
            "tokens_per_cycle": "5000000",
            "mode": "subscription",
        }

        def _create():
            return stripe.checkout.Session.create(
                mode="subscription",
                success_url=resolved_success_url,
                cancel_url=resolved_cancel_url,
                payment_method_types=["card"],
                metadata=metadata,
                subscription_data={"metadata": metadata},
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": 4000,
                            "recurring": {"interval": "month"},
                            "product_data": {
                                "name": "Matcha Work Pro",
                                "description": "5M AI tokens per month",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            raise StripeServiceError(f"Failed to create token subscription session: {exc}") from exc

    async def cancel_subscription(self, stripe_subscription_id: str):
        """Cancel a Stripe subscription at period end."""
        self._ensure_secret_key()

        def _cancel():
            return stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True,
            )

        try:
            return await asyncio.to_thread(_cancel)
        except Exception as exc:
            raise StripeServiceError(f"Failed to cancel Stripe subscription: {exc}") from exc

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
