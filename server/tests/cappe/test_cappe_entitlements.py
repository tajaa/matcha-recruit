"""Cappe entitlement resolution: take rate, selling gate, fulfillment gate.

These encode money rules, so they are the highest-value tests in the billing
work: a wrong `platform_fee_bps` silently over- or under-charges every merchant
on that plan, and a wrong fallback either blocks live storefronts or gives away
paid tiers.

Pure — no DB, no app boot. The catalog is injected by seeding the module cache.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_entitlements.py -q
"""
import os
import time

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from fastapi import HTTPException  # noqa: E402

from app.config import load_settings  # noqa: E402

# `stripe_connect.platform_fee_cents` (the global helper this replaces) reads
# settings directly, so the parity test below needs them loaded.
load_settings()

from app.cappe.services import entitlements as ent  # noqa: E402


def _seed_catalog(rows):
    """Prime the module-level catalog cache so resolution does no I/O."""
    ent._catalog_cache = {r["code"]: r for r in rows}
    ent._catalog_cached_at = time.monotonic()


def _plan(code, **over):
    row = {
        "code": code,
        "kind": "plan",
        "name": code.title(),
        "status": "active",
        "can_sell": True,
        "platform_fee_bps": 200,
        "allowed_fulfillment": ["physical", "digital", "service", "booking"],
        "site_limit": None,
        "mailbox_quota_included": 0,
        "premium_design": False,
        "features": {},
    }
    row.update(over)
    return row


@pytest.fixture(autouse=True)
def _clear_cache():
    ent.invalidate_catalog_cache()
    yield
    ent.invalidate_catalog_cache()


# ── Take rate ─────────────────────────────────────────────────────────────

class TestFeeCents:
    def test_basic_percentages(self):
        assert ent.fee_cents(10_000, 200) == 200      # 2% of $100
        assert ent.fee_cents(10_000, 150) == 150      # 1.5%
        assert ent.fee_cents(10_000, 300) == 300      # 3%

    def test_floors_rather_than_rounds(self):
        # 2% of $9.99 is 19.98c — the platform takes 19, never 20. Rounding up
        # would over-charge the merchant by a cent on most orders.
        assert ent.fee_cents(999, 200) == 19

    def test_zero_rate_and_zero_amount(self):
        assert ent.fee_cents(10_000, 0) == 0
        assert ent.fee_cents(0, 200) == 0

    def test_never_negative(self):
        assert ent.fee_cents(-500, 200) == 0

    def test_matches_the_global_helper_it_replaces(self):
        """The per-plan rate must produce byte-identical numbers to the old
        global helper when the rate is the same — otherwise migrating to the
        catalog silently re-prices every existing merchant."""
        from app.cappe.services.stripe_connect import platform_fee_cents

        for amount in (1, 99, 100, 999, 12_345, 1_000_000):
            assert ent.fee_cents(amount, 200) == platform_fee_cents(amount)


# ── Resolution ────────────────────────────────────────────────────────────

class TestResolveEntitlements:
    @pytest.mark.asyncio
    async def test_reads_the_catalog_row(self):
        _seed_catalog([_plan("creator", platform_fee_bps=300, can_sell=True,
                             allowed_fulfillment=["service", "booking"],
                             premium_design=True, features={"rider": True})])
        e = await ent.resolve_entitlements("creator")
        assert e.platform_fee_bps == 300
        assert e.can_sell is True
        assert e.allowed_fulfillment == frozenset({"service", "booking"})
        assert e.premium_design is True
        assert e.has("rider") is True

    @pytest.mark.asyncio
    async def test_unknown_plan_falls_back_permissively(self):
        """An unknown code must not lock a merchant out. Fail open to today's
        behaviour — a billing-config problem is not a reason to stop a sale."""
        _seed_catalog([_plan("creator")])
        e = await ent.resolve_entitlements("some_tier_that_does_not_exist")
        assert e.can_sell is True
        assert e.allowed_fulfillment == ent.ALL_FULFILLMENT

    @pytest.mark.asyncio
    async def test_addon_row_is_not_a_plan(self):
        """A code that names an add-on must not resolve as a plan, or buying
        mailboxes would hand out an entitlement set."""
        _seed_catalog([{**_plan("mailbox"), "kind": "addon"}])
        e = await ent.resolve_entitlements("mailbox")
        assert e.plan_code == "mailbox"
        assert e.allowed_fulfillment == ent.ALL_FULFILLMENT  # fallback, not the row

    @pytest.mark.asyncio
    async def test_none_plan_is_free(self):
        _seed_catalog([_plan("free", can_sell=False, site_limit=1)])
        assert (await ent.resolve_entitlements(None)).plan_code == "free"

    @pytest.mark.asyncio
    async def test_json_string_features_are_parsed(self):
        """asyncpg hands back JSONB as a str when no codec is registered."""
        _seed_catalog([_plan("creator", features='{"rider": true}')])
        assert (await ent.resolve_entitlements("creator")).has("rider") is True


class TestLegacyFallback:
    def test_preserves_premium_design_for_legacy_codes(self):
        """`pro` is retired but existing accounts still carry it; the fallback
        must not silently revoke design features they have today."""
        for code in ("pro", "business", "creator"):
            assert ent._legacy_fallback(code).premium_design is True
        assert ent._legacy_fallback("free").premium_design is False

    def test_agrees_with_the_static_design_gate(self):
        from app.cappe.services.design_gate import PREMIUM_PLANS

        for code in PREMIUM_PLANS:
            assert ent._legacy_fallback(code).premium_design is True

    def test_free_keeps_its_one_site_cap(self):
        assert ent._legacy_fallback("free").site_limit == 1
        assert ent._legacy_fallback("business").site_limit is None


# ── Gates ─────────────────────────────────────────────────────────────────

class TestSellingGate:
    @pytest.mark.asyncio
    async def test_free_plan_cannot_sell(self):
        _seed_catalog([_plan("free", can_sell=False)])
        with pytest.raises(HTTPException) as exc:
            ent.require_can_sell(await ent.resolve_entitlements("free"))
        assert exc.value.status_code == 402

    @pytest.mark.asyncio
    async def test_paid_plan_can_sell(self):
        _seed_catalog([_plan("business", can_sell=True)])
        ent.require_can_sell(await ent.resolve_entitlements("business"))  # no raise


class TestFulfillmentGate:
    @pytest.mark.asyncio
    async def test_creator_is_services_only(self):
        _seed_catalog([_plan("creator", allowed_fulfillment=["service", "booking"])])
        e = await ent.resolve_entitlements("creator")
        ent.require_fulfillment(e, "service")
        ent.require_fulfillment(e, "booking")
        for blocked in ("physical", "digital"):
            with pytest.raises(HTTPException) as exc:
                ent.require_fulfillment(e, blocked)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_business_may_sell_everything(self):
        _seed_catalog([_plan("business")])
        e = await ent.resolve_entitlements("business")
        for kind in ("physical", "digital", "service", "booking"):
            ent.require_fulfillment(e, kind)

    @pytest.mark.asyncio
    async def test_missing_fulfillment_defaults_to_physical(self):
        """`cappe_products.fulfillment` defaults to 'physical' at the DB level,
        so an omitted value must be gated as physical rather than waved through."""
        _seed_catalog([_plan("creator", allowed_fulfillment=["service", "booking"])])
        e = await ent.resolve_entitlements("creator")
        with pytest.raises(HTTPException):
            ent.require_fulfillment(e, None)

    @pytest.mark.asyncio
    async def test_gate_is_case_insensitive(self):
        _seed_catalog([_plan("creator", allowed_fulfillment=["service", "booking"])])
        ent.require_fulfillment(await ent.resolve_entitlements("creator"), "SERVICE")


# ── Cache ─────────────────────────────────────────────────────────────────

class TestCatalogCache:
    @pytest.mark.asyncio
    async def test_invalidate_forces_a_reread(self):
        """Admin writes call invalidate_catalog_cache(); without it a fee change
        would take up to a TTL to apply."""
        _seed_catalog([_plan("creator", platform_fee_bps=300)])
        assert (await ent.resolve_entitlements("creator")).platform_fee_bps == 300

        ent.invalidate_catalog_cache()
        assert ent._catalog_cache is None

    @pytest.mark.asyncio
    async def test_trialing_counts_as_entitled(self):
        """The $1/30-day intro IS a Stripe trial. If `trialing` were not
        entitled, every intro customer would pay and get nothing."""
        assert "trialing" in ent.ENTITLED_SUBSCRIPTION_STATUSES
        assert "active" in ent.ENTITLED_SUBSCRIPTION_STATUSES
        # Stripe retries a failed card for days; dropping access on the first
        # failure would break a live storefront over a card that renews later.
        assert "past_due" in ent.ENTITLED_SUBSCRIPTION_STATUSES
        assert "canceled" not in ent.ENTITLED_SUBSCRIPTION_STATUSES
        assert "unpaid" not in ent.ENTITLED_SUBSCRIPTION_STATUSES
