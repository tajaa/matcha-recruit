"""Cappe billing service: pure-function edges found in PR review.

Each test pins a defect that was real and reachable: a migration syntax error,
a Stripe API-version field move, and two unguarded webhook crashes. These are
the cheapest possible regression guard for money-path code that otherwise has
no coverage against a live database or Stripe.

Pure — no DB, no app boot.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_billing_service.py -q
"""
import os

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from app.cappe.services import billing as billing_svc  # noqa: E402


class TestInvoiceSubscriptionId:
    """Stripe moved Invoice.subscription to
    invoice.parent.subscription_details.subscription in API version
    2025-04-30+; the pinned SDK's default version is later still. Reading only
    the legacy field makes handle_invoice_event silently never fire."""

    def test_reads_legacy_top_level_field(self):
        invoice = {"id": "in_1", "subscription": "sub_abc"}
        assert billing_svc._invoice_subscription_id(invoice) == "sub_abc"

    def test_reads_current_nested_field(self):
        invoice = {
            "id": "in_1",
            "parent": {"subscription_details": {"subscription": "sub_xyz"}},
        }
        assert billing_svc._invoice_subscription_id(invoice) == "sub_xyz"

    def test_legacy_field_wins_when_both_present(self):
        invoice = {
            "id": "in_1",
            "subscription": "sub_legacy",
            "parent": {"subscription_details": {"subscription": "sub_current"}},
        }
        assert billing_svc._invoice_subscription_id(invoice) == "sub_legacy"

    def test_missing_both_returns_none(self):
        assert billing_svc._invoice_subscription_id({"id": "in_1"}) is None

    def test_non_subscription_invoice_returns_none(self):
        """A one-off invoice (no parent, or parent without subscription_details)
        must not raise on the nested .get() chain."""
        assert billing_svc._invoice_subscription_id({"parent": {}}) is None
        assert billing_svc._invoice_subscription_id(
            {"parent": {"subscription_details": {}}}
        ) is None

    def test_non_string_subscription_is_ignored(self):
        """A `null` or expanded-object subscription must not be treated as an id."""
        assert billing_svc._invoice_subscription_id({"subscription": None}) is None
        assert billing_svc._invoice_subscription_id(
            {"subscription": {"id": "sub_expanded"}}
        ) is None


class TestEffectivePlanCode:
    def test_active_and_trialing_and_past_due_keep_the_plan(self):
        for s in ("active", "trialing", "past_due"):
            assert billing_svc.effective_plan_code(s, "creator") == "creator"

    def test_incomplete_maps_to_free(self):
        """A customer who started checkout but never paid must not get the
        tier — that is giving away a paid plan to an abandoned card."""
        assert billing_svc.effective_plan_code("incomplete", "creator") == "free"

    def test_canceled_and_unpaid_map_to_free(self):
        for s in ("canceled", "unpaid", "incomplete_expired"):
            assert billing_svc.effective_plan_code(s, "business") == "free"


class TestHandleCheckoutCompletedGuards:
    """This webhook receives every checkout.session.completed on the shared
    platform account, including sessions from other products. Both guards
    exist so a session that is not Cappe's own is ignored rather than crashing
    the handler — an unguarded exception here 500s, releases the dedupe claim,
    and Stripe retries the same non-Cappe event forever."""

    @pytest.mark.asyncio
    async def test_non_uuid_account_id_is_ignored_not_raised(self):
        session = {
            "metadata": {"account_id": "not-a-uuid"},
            "subscription": "sub_123",
        }
        result = await billing_svc.handle_checkout_completed(session, None)
        assert result == {"status": "ignored"}

    @pytest.mark.asyncio
    async def test_null_metadata_does_not_crash(self):
        """Stripe can send metadata as an explicit `null`, not just an absent
        key. `session.get("metadata", {})` returns None in that case, and
        `None.get(...)` is an AttributeError, not a missing key."""
        session = {"metadata": None, "subscription": "sub_123"}
        result = await billing_svc.handle_checkout_completed(session, None)
        assert result == {"status": "ignored"}

    @pytest.mark.asyncio
    async def test_null_metadata_falls_back_to_client_reference_id(self):
        """A valid UUID via client_reference_id must still work when metadata
        is null — the guard must not over-reject."""
        import uuid as uuid_mod

        account_id = str(uuid_mod.uuid4())
        session = {
            "metadata": None,
            "client_reference_id": account_id,
            "subscription": "sub_123",
            "customer": None,
        }
        mock_conn = AsyncMock()
        tx_cm = AsyncMock()
        tx_cm.__aenter__ = AsyncMock(return_value=None)
        tx_cm.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=tx_cm)

        mock_cs = AsyncMock()
        mock_cs.retrieve_subscription = AsyncMock(return_value={"id": "sub_123", "items": {"data": []}})

        with patch.object(billing_svc, "get_connection") as mock_gc, \
             patch.object(billing_svc, "get_cappe_stripe", return_value=mock_cs), \
             patch.object(billing_svc, "sync_subscription", new_callable=AsyncMock) as mock_sync:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await billing_svc.handle_checkout_completed(session, None)

        assert result == {"status": "ok"}
        mock_sync.assert_awaited_once()
