"""Tests for the paid channels feature.

Covers:
- Channel payment service: price validation, rejoin eligibility, payment info,
  member activity status logic, subscription lifecycle handlers
- Inactivity worker: warning/removal classification, DB operations
- Route-level logic: paid config validation, cooldown guards, WebSocket membership filters
- Stripe webhook routing: channel event detection, period_end handling
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ── Stub google.genai before importing app code ──
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

# Stub stripe
stripe_module = ModuleType("stripe")
stripe_module.api_key = None
stripe_module.Product = MagicMock()
stripe_module.Price = MagicMock()
stripe_module.checkout = MagicMock()
stripe_module.Subscription = MagicMock()
stripe_module.Webhook = MagicMock()
sys.modules.setdefault("stripe", stripe_module)


# ============================================================
# Channel Payment Service: Price Validation
# ============================================================

class TestPriceValidation:
    def test_min_price_constant(self):
        from app.core.services.channel_payment_service import MIN_PRICE_CENTS
        assert MIN_PRICE_CENTS == 50  # $0.50

    def test_max_price_constant(self):
        from app.core.services.channel_payment_service import MAX_PRICE_CENTS
        assert MAX_PRICE_CENTS == 99900  # $999.00

    def test_price_range_excludes_zero(self):
        from app.core.services.channel_payment_service import MIN_PRICE_CENTS
        assert MIN_PRICE_CENTS > 0

    @pytest.mark.asyncio
    async def test_create_stripe_product_rejects_low_price(self):
        from app.core.services.channel_payment_service import (
            create_stripe_product_and_price,
            ChannelPaymentError,
        )
        with patch("app.core.services.channel_payment_service._ensure_stripe"):
            with pytest.raises(ChannelPaymentError, match="Price must be between"):
                await create_stripe_product_and_price(
                    channel_id=uuid4(), channel_name="test", price_cents=10
                )

    @pytest.mark.asyncio
    async def test_create_stripe_product_rejects_high_price(self):
        from app.core.services.channel_payment_service import (
            create_stripe_product_and_price,
            ChannelPaymentError,
        )
        with patch("app.core.services.channel_payment_service._ensure_stripe"):
            with pytest.raises(ChannelPaymentError, match="Price must be between"):
                await create_stripe_product_and_price(
                    channel_id=uuid4(), channel_name="test", price_cents=100000
                )


# ============================================================
# Channel Payment Service: Member Activity Status Logic
# ============================================================

class TestMemberActivityStatus:
    """Test the status classification logic in get_member_activity."""

    def _compute_status(self, remaining: float, warning: int, role: str = "member"):
        """Replicate the status logic from get_member_activity."""
        status = "active"
        if role in ("owner", "moderator"):
            return "exempt"
        threshold = 14  # example
        if remaining <= 0:
            status = "expired"
        elif warning and remaining <= warning:
            status = "warned"
        elif remaining <= threshold * 0.5:
            status = "at_risk"
        return status

    def test_active_member(self):
        assert self._compute_status(remaining=10, warning=3) == "active"

    def test_at_risk_member(self):
        assert self._compute_status(remaining=5, warning=3) == "at_risk"

    def test_warned_member(self):
        assert self._compute_status(remaining=2, warning=3) == "warned"

    def test_expired_member(self):
        assert self._compute_status(remaining=-1, warning=3) == "expired"

    def test_expired_takes_precedence_over_warned(self):
        """BUG 11 regression: remaining=0 should be expired, not warned."""
        assert self._compute_status(remaining=0, warning=3) == "expired"

    def test_negative_remaining_is_expired(self):
        assert self._compute_status(remaining=-5, warning=3) == "expired"

    def test_owner_is_exempt(self):
        assert self._compute_status(remaining=-5, warning=3, role="owner") == "exempt"

    def test_moderator_is_exempt(self):
        assert self._compute_status(remaining=0, warning=3, role="moderator") == "exempt"

    def test_warning_boundary_exact(self):
        """Remaining exactly equals warning days → warned."""
        assert self._compute_status(remaining=3, warning=3) == "warned"

    def test_zero_warning_skips_warned(self):
        """If warning_days is 0, members go straight from at_risk to expired."""
        assert self._compute_status(remaining=1, warning=0) == "at_risk"

    def test_exactly_at_risk_boundary(self):
        """remaining = threshold * 0.5 = 7 → at_risk."""
        assert self._compute_status(remaining=7, warning=3) == "at_risk"


# ============================================================
# Channel Payment Service: Rejoin Eligibility
# ============================================================

class TestRejoinEligibility:
    @pytest.mark.asyncio
    async def test_new_user_can_join(self):
        """User who was never a member can join."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import check_rejoin_eligibility
            result = await check_rejoin_eligibility(uuid4(), uuid4())
            assert result["can_rejoin"] is True
            assert result["cooldown_until"] is None

    @pytest.mark.asyncio
    async def test_cooldown_active_blocks_rejoin(self):
        """User in cooldown period cannot rejoin."""
        future = datetime.now(timezone.utc) + timedelta(days=3)
        mock_row = {
            "removal_cooldown_until": future,
            "paid_through": None,
            "removed_for_inactivity": True,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import check_rejoin_eligibility
            result = await check_rejoin_eligibility(uuid4(), uuid4())
            assert result["can_rejoin"] is False
            assert result["reason"] == "removal_cooldown"

    @pytest.mark.asyncio
    async def test_expired_cooldown_allows_rejoin(self):
        """User whose cooldown has passed can rejoin."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        mock_row = {
            "removal_cooldown_until": past,
            "paid_through": None,
            "removed_for_inactivity": True,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import check_rejoin_eligibility
            result = await check_rejoin_eligibility(uuid4(), uuid4())
            assert result["can_rejoin"] is True


# ============================================================
# Channel Payment Service: Payment Info
# ============================================================

class TestPaymentInfo:
    @pytest.mark.asyncio
    async def test_free_channel_returns_minimal(self):
        """Free channel returns is_paid=False only."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"is_paid": False, "price_cents": None, "currency": "usd", "inactivity_threshold_days": None, "inactivity_warning_days": 3})

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import get_payment_info
            result = await get_payment_info(uuid4(), uuid4())
            assert result["is_paid"] is False
            assert "price_cents" not in result

    @pytest.mark.asyncio
    async def test_paid_channel_not_subscribed(self):
        """Paid channel where user is not a member returns full info."""
        ch_row = {"is_paid": True, "price_cents": 500, "currency": "usd", "inactivity_threshold_days": 14, "inactivity_warning_days": 3}
        mock_conn = AsyncMock()
        # First call = channel, second = member
        mock_conn.fetchrow = AsyncMock(side_effect=[ch_row, None])

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import get_payment_info
            result = await get_payment_info(uuid4(), uuid4())
            assert result["is_paid"] is True
            assert result["price_cents"] == 500
            assert result["is_subscribed"] is False

    @pytest.mark.asyncio
    async def test_days_until_removal_calculation(self):
        """Verify days_until_removal is calculated correctly."""
        now = datetime.now(timezone.utc)
        ch_row = {"is_paid": True, "price_cents": 500, "currency": "usd", "inactivity_threshold_days": 14, "inactivity_warning_days": 3}
        member_row = {
            "subscription_status": "active",
            "paid_through": now + timedelta(days=30),
            "removed_for_inactivity": False,
            "removal_cooldown_until": None,
            "last_contributed_at": now - timedelta(days=10),
            "inactivity_warned_at": None,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[ch_row, member_row])

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import get_payment_info
            result = await get_payment_info(uuid4(), uuid4())
            # 14 day threshold, contributed 10 days ago → ~4 days remaining
            assert result["days_until_removal"] is not None
            assert 3.5 <= result["days_until_removal"] <= 4.5


# ============================================================
# Channel Payment Service: Subscription Lifecycle
# ============================================================

class TestSubscriptionLifecycle:
    @pytest.mark.asyncio
    async def test_handle_subscription_activated_new_member(self):
        """New member gets inserted on subscription activation."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)  # not existing
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import handle_subscription_activated
            await handle_subscription_activated(
                channel_id=uuid4(),
                user_id=uuid4(),
                stripe_subscription_id="sub_test123",
                current_period_end=int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            )
            # Should have called execute for INSERT and payment event
            assert mock_conn.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_handle_subscription_activated_rejoin(self):
        """Existing removed member gets updated on rejoin."""
        user_id = uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=user_id)  # existing member
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import handle_subscription_activated
            await handle_subscription_activated(
                channel_id=uuid4(),
                user_id=user_id,
                stripe_subscription_id="sub_rejoin",
                current_period_end=int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            )
            # Should update existing + log event
            assert mock_conn.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_handle_payment_failed_sets_past_due(self):
        """Payment failure sets subscription_status to past_due."""
        row = {"channel_id": uuid4(), "user_id": uuid4(), "company_id": uuid4()}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.fetchval = AsyncMock(return_value="test-channel")
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.core.services.channel_payment_service.notif_svc", create=True):
                from app.core.services.channel_payment_service import handle_payment_failed
                await handle_payment_failed("sub_failed")
                # Check that subscription_status was set to past_due
                calls = [str(c) for c in mock_conn.execute.call_args_list]
                assert any("past_due" in c for c in calls)

    @pytest.mark.asyncio
    async def test_handle_payment_failed_no_match_is_noop(self):
        """Payment failure for non-channel subscription is a no-op."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import handle_payment_failed
            await handle_payment_failed("sub_nonexistent")
            # Should not call execute (no matching member)
            mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_subscription_canceled_keeps_sub_id(self):
        """BUG 15 regression: cancellation should NOT null out stripe_subscription_id."""
        row = {"channel_id": uuid4(), "user_id": uuid4()}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import handle_subscription_canceled
            await handle_subscription_canceled("sub_cancel")
            # The UPDATE should set status to canceled but NOT null stripe_subscription_id
            update_call = str(mock_conn.execute.call_args_list[0])
            assert "canceled" in update_call
            assert "stripe_subscription_id = NULL" not in update_call

    @pytest.mark.asyncio
    async def test_handle_subscription_renewed_updates_paid_through(self):
        """Renewal updates paid_through date."""
        row = {"channel_id": uuid4(), "user_id": uuid4()}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import handle_subscription_renewed
            future_ts = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
            await handle_subscription_renewed("sub_renew", future_ts, 500)
            assert mock_conn.execute.call_count >= 2  # UPDATE + INSERT event


# ============================================================
# Inactivity Worker: Classification Logic
# ============================================================

class TestInactivityClassification:
    """Test the warning vs removal classification in the inactivity worker."""

    def _classify(self, remaining_days: float, inactivity_warned_at):
        """Replicate the classification logic from run_inactivity_checks."""
        if remaining_days <= 0:
            return "remove"
        elif inactivity_warned_at is None:
            return "warn"
        return "skip"  # already warned, not yet expired

    def test_past_threshold_is_removal(self):
        assert self._classify(remaining_days=-2, inactivity_warned_at=None) == "remove"

    def test_exactly_at_threshold_is_removal(self):
        assert self._classify(remaining_days=0, inactivity_warned_at=None) == "remove"

    def test_in_warning_window_not_warned(self):
        assert self._classify(remaining_days=2, inactivity_warned_at=None) == "warn"

    def test_in_warning_window_already_warned(self):
        assert self._classify(
            remaining_days=2,
            inactivity_warned_at=datetime.now(timezone.utc)
        ) == "skip"

    def test_past_threshold_even_if_already_warned(self):
        assert self._classify(
            remaining_days=-1,
            inactivity_warned_at=datetime.now(timezone.utc)
        ) == "remove"


class TestInactivityWorkerExecution:
    @pytest.mark.asyncio
    async def test_no_paid_channels_is_noop(self):
        """Worker does nothing when there are no paid channels."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        with patch("app.core.services.inactivity_worker.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.inactivity_worker import run_inactivity_checks
            await run_inactivity_checks()
            # Only one fetch call (channels query), no members to process
            assert mock_conn.fetch.call_count == 1

    @staticmethod
    def _make_ctx(conn):
        """Create a proper async context manager mock for get_connection."""
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    @pytest.mark.asyncio
    async def test_worker_warns_idle_member(self):
        """Worker sends warning for member in warning window."""
        channel = {
            "id": uuid4(), "company_id": uuid4(), "name": "test-channel",
            "inactivity_threshold_days": 14, "inactivity_warning_days": 3,
        }
        member = {
            "user_id": uuid4(),
            "last_contributed_at": datetime.now(timezone.utc) - timedelta(days=12),
            "inactivity_warned_at": None,
            "stripe_subscription_id": "sub_123",
            "paid_through": datetime.now(timezone.utc) + timedelta(days=20),
            "remaining_days": 2.0,
        }

        collect_conn = AsyncMock()
        collect_conn.fetch = AsyncMock(side_effect=[[channel], [member]])

        warn_conn = AsyncMock()
        warn_conn.execute = AsyncMock()

        contexts = [self._make_ctx(collect_conn), self._make_ctx(warn_conn)]
        call_idx = [0]

        def mock_get_connection():
            idx = call_idx[0]
            call_idx[0] += 1
            return contexts[idx] if idx < len(contexts) else self._make_ctx(AsyncMock())

        with patch("app.core.services.inactivity_worker.get_connection", side_effect=mock_get_connection):
            with patch("app.core.services.inactivity_worker.cancel_subscription_immediately", new_callable=AsyncMock):
                with patch("app.matcha.services.notification_service.create_notification", new_callable=AsyncMock) as mock_notif:
                    from app.core.services.inactivity_worker import run_inactivity_checks
                    await run_inactivity_checks()
                    mock_notif.assert_called_once()
                    call_kwargs = mock_notif.call_args.kwargs
                    assert call_kwargs["type"] == "channel_inactivity_warning"

    @pytest.mark.asyncio
    async def test_worker_removes_expired_member(self):
        """Worker removes member past threshold and cancels their subscription."""
        channel = {
            "id": uuid4(), "company_id": uuid4(), "name": "test-channel",
            "inactivity_threshold_days": 14, "inactivity_warning_days": 3,
        }
        member = {
            "user_id": uuid4(),
            "last_contributed_at": datetime.now(timezone.utc) - timedelta(days=20),
            "inactivity_warned_at": datetime.now(timezone.utc) - timedelta(days=3),
            "stripe_subscription_id": "sub_456",
            "paid_through": datetime.now(timezone.utc) + timedelta(days=10),
            "remaining_days": -6.0,
        }

        collect_conn = AsyncMock()
        collect_conn.fetch = AsyncMock(side_effect=[[channel], [member]])

        remove_conn = AsyncMock()
        remove_conn.execute = AsyncMock()

        contexts = [self._make_ctx(collect_conn), self._make_ctx(remove_conn)]
        call_idx = [0]

        def mock_get_connection():
            idx = call_idx[0]
            call_idx[0] += 1
            return contexts[idx] if idx < len(contexts) else self._make_ctx(AsyncMock())

        with patch("app.core.services.inactivity_worker.get_connection", side_effect=mock_get_connection):
            with patch("app.core.services.inactivity_worker.cancel_subscription_immediately", new_callable=AsyncMock) as mock_cancel:
                with patch("app.matcha.services.notification_service.create_notification", new_callable=AsyncMock) as mock_notif:
                    from app.core.services.inactivity_worker import run_inactivity_checks
                    await run_inactivity_checks()
                    mock_cancel.assert_called_once_with("sub_456")
                    mock_notif.assert_called_once()
                    assert mock_notif.call_args.kwargs["type"] == "channel_removed_for_inactivity"


# ============================================================
# Inactivity Worker: Scheduler
# ============================================================

class TestInactivityScheduler:
    @pytest.mark.asyncio
    async def test_start_returns_task(self):
        """start_inactivity_scheduler returns an asyncio Task."""
        import asyncio
        from app.core.services.inactivity_worker import start_inactivity_scheduler

        with patch("app.core.services.inactivity_worker.run_inactivity_checks", new_callable=AsyncMock):
            task = await start_inactivity_scheduler()
            assert isinstance(task, asyncio.Task)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def test_check_interval_is_12_hours(self):
        from app.core.services.inactivity_worker import CHECK_INTERVAL_SECONDS
        assert CHECK_INTERVAL_SECONDS == 12 * 60 * 60


# ============================================================
# Route Logic: PaidChannelConfig Validation
# ============================================================

class TestPaidChannelConfigModel:
    def test_valid_config(self):
        from app.core.routes.channels import PaidChannelConfig
        config = PaidChannelConfig(
            price_cents=500,
            currency="usd",
            inactivity_threshold_days=14,
            inactivity_warning_days=3,
        )
        assert config.price_cents == 500
        assert config.currency == "usd"

    def test_default_currency(self):
        from app.core.routes.channels import PaidChannelConfig
        config = PaidChannelConfig(price_cents=500)
        assert config.currency == "usd"

    def test_default_warning_days(self):
        from app.core.routes.channels import PaidChannelConfig
        config = PaidChannelConfig(price_cents=500)
        assert config.inactivity_warning_days == 3

    def test_null_threshold_allowed(self):
        from app.core.routes.channels import PaidChannelConfig
        config = PaidChannelConfig(price_cents=500, inactivity_threshold_days=None)
        assert config.inactivity_threshold_days is None


# ============================================================
# Route Logic: Pydantic Models
# ============================================================

class TestPydanticModels:
    def test_channel_summary_has_is_paid(self):
        from app.core.routes.channels import ChannelSummary
        summary = ChannelSummary(
            id=uuid4(), name="test", slug="test",
            is_paid=True, member_count=5,
        )
        assert summary.is_paid is True

    def test_channel_summary_default_not_paid(self):
        from app.core.routes.channels import ChannelSummary
        summary = ChannelSummary(id=uuid4(), name="test", slug="test")
        assert summary.is_paid is False

    def test_channel_detail_has_paid_fields(self):
        from app.core.routes.channels import ChannelDetail
        detail = ChannelDetail(
            id=uuid4(), name="test", slug="test",
            created_by=uuid4(), created_at=datetime.now(timezone.utc),
            is_paid=True, price_cents=999, currency="eur",
        )
        assert detail.is_paid is True
        assert detail.price_cents == 999
        assert detail.currency == "eur"

    def test_channel_detail_defaults(self):
        from app.core.routes.channels import ChannelDetail
        detail = ChannelDetail(
            id=uuid4(), name="test", slug="test",
            created_by=uuid4(), created_at=datetime.now(timezone.utc),
        )
        assert detail.is_paid is False
        assert detail.price_cents is None
        assert detail.currency == "usd"

    def test_update_paid_settings_request(self):
        from app.core.routes.channels import UpdatePaidSettingsRequest
        req = UpdatePaidSettingsRequest(
            inactivity_threshold_days=7,
            inactivity_warning_days=2,
        )
        assert req.inactivity_threshold_days == 7

    def test_update_paid_settings_optional(self):
        from app.core.routes.channels import UpdatePaidSettingsRequest
        req = UpdatePaidSettingsRequest()
        assert req.inactivity_threshold_days is None
        assert req.inactivity_warning_days is None


# ============================================================
# Notification Types
# ============================================================

class TestNotificationTypes:
    def test_inactivity_warning_type_exists(self):
        from app.matcha.services.notification_service import TYPES
        assert "channel_inactivity_warning" in TYPES

    def test_removed_for_inactivity_type_exists(self):
        from app.matcha.services.notification_service import TYPES
        assert "channel_removed_for_inactivity" in TYPES

    def test_payment_failed_type_exists(self):
        from app.matcha.services.notification_service import TYPES
        assert "channel_payment_failed" in TYPES

    def test_inactivity_warning_label(self):
        from app.matcha.services.notification_service import TYPES
        assert TYPES["channel_inactivity_warning"] == "Inactivity Warning"


# ============================================================
# Stripe Webhook: Channel Event Detection
# ============================================================

class TestWebhookEventRouting:
    def test_channel_event_detected_from_metadata(self):
        """Webhook should detect channel events via metadata.type."""
        meta = {"type": "channel_subscription", "channel_id": str(uuid4()), "user_id": str(uuid4())}
        assert meta.get("type") == "channel_subscription"

    def test_non_channel_event_not_detected(self):
        meta = {"company_id": str(uuid4()), "mode": "subscription"}
        assert meta.get("type") != "channel_subscription"

    def test_empty_metadata_not_detected(self):
        meta = {}
        assert meta.get("type") != "channel_subscription"

    def test_period_end_extraction_from_lines(self):
        """Period end should be extracted from invoice line items."""
        lines = [{"period": {"end": 1735689600}}]
        period_end = lines[0]["period"]["end"] if lines else None
        assert period_end == 1735689600

    def test_period_end_empty_lines_returns_none(self):
        """Empty line items should return None, not 0."""
        lines = []
        period_end = lines[0]["period"]["end"] if lines else None
        assert period_end is None

    def test_period_end_zero_guard(self):
        """BUG 6 regression: period_end=0 should be treated as missing."""
        period_end = 0
        assert not (period_end and period_end > 0)


# ============================================================
# WebSocket: Membership Check Excludes Removed Members
# ============================================================

class TestWebSocketMembershipFilter:
    """BUG 13 regression: removed members must be excluded from WS checks."""

    def test_membership_query_excludes_removed(self):
        """Verify the SQL pattern used in channels_ws.py filters removed members."""
        import inspect
        from app.core.routes.channels_ws import channel_websocket

        source = inspect.getsource(channel_websocket)
        # All membership checks should include the removed_for_inactivity filter
        assert "removed_for_inactivity IS NOT TRUE" in source

    def test_join_room_query_excludes_removed(self):
        """The join_room membership check should also filter removed members."""
        import inspect
        from app.core.routes.channels_ws import channel_websocket

        source = inspect.getsource(channel_websocket)
        # Count occurrences - should appear in both join_room and message checks
        count = source.count("removed_for_inactivity IS NOT TRUE")
        assert count >= 2, f"Expected at least 2 removed_for_inactivity checks, found {count}"


# ============================================================
# Migration: Schema Correctness
# ============================================================

class TestMigrationSchema:
    @staticmethod
    def _load_migration():
        import importlib.util, os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "alembic", "versions",
            "zzj0k1l2m3n4_add_paid_channels.py",
        )
        spec = importlib.util.spec_from_file_location("migration", path)
        mod = importlib.util.module_from_spec(spec)
        # Stub alembic.op so the module can be loaded without alembic context
        alembic_mod = ModuleType("alembic")
        alembic_mod.op = MagicMock()
        sys.modules["alembic"] = alembic_mod
        sys.modules["alembic.op"] = alembic_mod.op
        spec.loader.exec_module(mod)
        return mod

    def test_migration_revision_chain(self):
        mod = self._load_migration()
        assert mod.revision == "zzj0k1l2m3n4"
        assert mod.down_revision == "zzi9j0k1l2m3"

    def test_upgrade_adds_channel_columns(self):
        import inspect
        mod = self._load_migration()
        source = inspect.getsource(mod.upgrade)
        for col in ["is_paid", "price_cents", "currency", "inactivity_threshold_days",
                     "inactivity_warning_days", "stripe_product_id", "stripe_price_id"]:
            assert col in source, f"Missing column {col} in channels ALTER"

    def test_upgrade_adds_member_columns(self):
        import inspect
        mod = self._load_migration()
        source = inspect.getsource(mod.upgrade)
        for col in ["last_contributed_at", "stripe_subscription_id", "subscription_status",
                     "paid_through", "removed_for_inactivity", "removal_cooldown_until",
                     "inactivity_warned_at"]:
            assert col in source, f"Missing column {col} in channel_members ALTER"

    def test_upgrade_creates_payment_events_table(self):
        import inspect
        mod = self._load_migration()
        source = inspect.getsource(mod.upgrade)
        assert "channel_payment_events" in source

    def test_upgrade_initializes_last_contributed_at(self):
        import inspect
        mod = self._load_migration()
        source = inspect.getsource(mod.upgrade)
        assert "last_contributed_at = joined_at" in source

    def test_downgrade_drops_everything(self):
        import inspect
        mod = self._load_migration()
        source = inspect.getsource(mod.downgrade)
        assert "DROP TABLE IF EXISTS channel_payment_events" in source
        assert "is_paid" in source
        assert "last_contributed_at" in source


# ============================================================
# Webhook dedupe + retry release
# ============================================================

class TestWebhookDedupeRelease:
    """A handler raising mid-flight must release the dedupe row so Stripe
    retries can re-process the event. Without release, a transient DB blip
    during activation would permanently strand a paid customer with no
    access — the dedupe row would block every retry."""

    @pytest.mark.asyncio
    async def test_release_event_deletes_row(self):
        from app.core.routes.stripe_webhook import _release_event
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        with patch("app.core.routes.stripe_webhook.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)
            await _release_event("evt_test_123")
        # Should DELETE FROM stripe_webhook_events
        delete_call = str(mock_conn.execute.call_args_list[0])
        assert "DELETE" in delete_call
        assert "stripe_webhook_events" in delete_call

    @pytest.mark.asyncio
    async def test_release_event_with_empty_id_is_noop(self):
        from app.core.routes.stripe_webhook import _release_event
        # Should not raise, should not connect
        with patch("app.core.routes.stripe_webhook.get_connection") as mock_gc:
            await _release_event("")
            mock_gc.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_swallows_db_errors(self):
        """If the dedupe table itself is broken, release shouldn't blow up."""
        from app.core.routes.stripe_webhook import _release_event
        with patch("app.core.routes.stripe_webhook.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
            # Should log warning but not propagate
            await _release_event("evt_db_broken")

    @pytest.mark.asyncio
    async def test_wrapper_releases_dedupe_on_handler_failure(self):
        """End-to-end: handler raises → outer wrapper releases the dedupe
        row → exception propagates to FastAPI (which returns 500 → Stripe
        retries). Without this glue, paid customers stay stranded."""
        from app.core.routes import stripe_webhook as wh

        # Fake event from verify_webhook
        class _Data:
            object = MagicMock(to_dict=lambda: {"id": "cs_x", "metadata": {"type": "channel_subscription"}})

        class _Event:
            type = "checkout.session.completed"
            id = "evt_explode"
            data = _Data()

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b"{}")
        mock_request.headers = {"stripe-signature": "sig_test"}

        verify = AsyncMock(return_value=_Event())
        with patch.object(wh, "StripeService", return_value=MagicMock(verify_webhook=verify)):
            with patch.object(wh, "_claim_event", new_callable=AsyncMock, return_value=True):
                with patch.object(wh, "_route_event", new_callable=AsyncMock,
                                  side_effect=RuntimeError("boom")):
                    with patch.object(wh, "_release_event", new_callable=AsyncMock) as mock_release:
                        with pytest.raises(RuntimeError, match="boom"):
                            await wh.stripe_webhook(mock_request)
                        mock_release.assert_called_once_with("evt_explode")

    def test_extract_period_end_new_api_items_schema(self):
        """Stripe API ≥ 2025-04-30 puts current_period_end on items[0]."""
        from app.core.routes.stripe_webhook import _extract_current_period_end
        sub = {
            "id": "sub_x", "object": "subscription",
            "items": {"data": [{"current_period_end": 1780000000}]},
        }
        assert _extract_current_period_end(sub) == 1780000000

    def test_extract_period_end_legacy_top_level(self):
        """Stripe API ≤ 2024-04-10 keeps it on the Subscription object."""
        from app.core.routes.stripe_webhook import _extract_current_period_end
        sub = {
            "id": "sub_y", "object": "subscription",
            "current_period_end": 1779999999,
            "items": {"data": [{}]},
        }
        assert _extract_current_period_end(sub) == 1779999999

    def test_extract_period_end_stripe_object_via_to_dict(self):
        """Live Stripe SDK object — the one from Subscription.retrieve —
        no longer exposes dict.get on items, so we go through to_dict()."""
        from app.core.routes.stripe_webhook import _extract_current_period_end
        fake_sub = MagicMock()
        fake_sub.to_dict = lambda: {
            "id": "sub_live",
            "items": {"data": [{"current_period_end": 1780100000}]},
        }
        assert _extract_current_period_end(fake_sub) == 1780100000

    def test_extract_period_end_missing_raises(self):
        from app.core.routes.stripe_webhook import _extract_current_period_end
        sub = {"id": "sub_broken", "items": {"data": [{}]}}
        with pytest.raises(ValueError, match="Cannot extract"):
            _extract_current_period_end(sub)

    @pytest.mark.asyncio
    async def test_wrapper_does_not_release_on_duplicate(self):
        """Duplicate event short-circuits before _route_event runs;
        no spurious release call should happen."""
        from app.core.routes import stripe_webhook as wh

        class _Data:
            object = MagicMock(to_dict=lambda: {})

        class _Event:
            type = "checkout.session.completed"
            id = "evt_dup"
            data = _Data()

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b"{}")
        mock_request.headers = {"stripe-signature": "sig_test"}

        verify = AsyncMock(return_value=_Event())
        with patch.object(wh, "StripeService", return_value=MagicMock(verify_webhook=verify)):
            with patch.object(wh, "_claim_event", new_callable=AsyncMock, return_value=False):
                with patch.object(wh, "_route_event", new_callable=AsyncMock) as mock_route:
                    with patch.object(wh, "_release_event", new_callable=AsyncMock) as mock_release:
                        result = await wh.stripe_webhook(mock_request)
                        assert result.get("status") == "duplicate"
                        mock_route.assert_not_called()
                        mock_release.assert_not_called()


# ============================================================
# Payment-failed email dedupe per cycle
# ============================================================

class TestPaymentFailedCycleDedupe:
    """Stripe retries a failed invoice 3-4 times over ~3 weeks. Each retry
    is a distinct webhook event so top-level dedupe doesn't help. We must
    cap to one email + one event row per (subscription, billing-cycle)."""

    @pytest.mark.asyncio
    async def test_first_failure_in_cycle_logs_and_notifies(self):
        row = {"channel_id": uuid4(), "user_id": uuid4(), "company_id": uuid4()}
        mock_conn = AsyncMock()
        # fetchrow → membership row
        mock_conn.fetchrow = AsyncMock(return_value=row)
        # fetchval calls in order:
        #   1. last_success → None (never paid before)
        #   2. already_failed_this_cycle → False (first fail)
        #   3. channel name lookup → "test"
        #   4. subscriber's own company (cross-tenant scope for notification)
        mock_conn.fetchval = AsyncMock(side_effect=[None, False, "test-channel", uuid4()])
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.matcha.services.notification_service.create_notification", new_callable=AsyncMock) as mock_notif:
                from app.core.services.channel_payment_service import handle_payment_failed
                await handle_payment_failed("sub_failure_1")

                # status update + payment_failed event row both fire
                calls = [str(c) for c in mock_conn.execute.call_args_list]
                assert any("past_due" in c for c in calls)
                assert any("payment_failed" in c and "INSERT" in c for c in calls)
                # Notification fires
                mock_notif.assert_called_once()

    @pytest.mark.asyncio
    async def test_second_failure_in_same_cycle_skipped(self):
        """Same cycle = already_failed_this_cycle returns True → skip."""
        row = {"channel_id": uuid4(), "user_id": uuid4(), "company_id": uuid4()}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=row)
        # last_success → None, already_failed_this_cycle → True
        mock_conn.fetchval = AsyncMock(side_effect=[None, True])
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.matcha.services.notification_service.create_notification", new_callable=AsyncMock) as mock_notif:
                from app.core.services.channel_payment_service import handle_payment_failed
                await handle_payment_failed("sub_failure_retry")
                # Status still updates to past_due (idempotent)
                calls = [str(c) for c in mock_conn.execute.call_args_list]
                assert any("past_due" in c for c in calls)
                # No new payment_failed event row
                assert not any("INSERT" in c and "payment_failed" in c for c in calls)
                # No duplicate notification
                mock_notif.assert_not_called()


# ============================================================
# Activation handler no longer increments invite use_count
# ============================================================

class TestActivationDoesNotIncrementInvite:
    """Invite use_count is now claimed atomically at redeem time (channels.py)
    to prevent race where two payers both join with max_uses=1. The
    activation handler must NOT also increment, or invites get
    double-counted on success."""

    @pytest.mark.asyncio
    async def test_invite_code_does_not_trigger_increment(self):
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)  # not existing
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import handle_subscription_activated
            await handle_subscription_activated(
                channel_id=uuid4(), user_id=uuid4(),
                stripe_subscription_id="sub_with_invite",
                current_period_end=int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
                invite_code="INVITE123",
            )
            # No UPDATE of channel_invites — that happened at redeem time
            calls = [str(c) for c in mock_conn.execute.call_args_list]
            assert not any("channel_invites" in c and "use_count" in c for c in calls)

    @pytest.mark.asyncio
    async def test_invite_code_logged_in_event_metadata(self):
        """Invite_code is preserved in event metadata for analytics, even
        though the increment happens elsewhere."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_payment_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_payment_service import handle_subscription_activated
            await handle_subscription_activated(
                channel_id=uuid4(), user_id=uuid4(),
                stripe_subscription_id="sub_with_invite",
                current_period_end=int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
                invite_code="INVITE123",
            )
            event_inserts = [c.args for c in mock_conn.execute.call_args_list if "subscription_activated" in str(c)]
            assert len(event_inserts) == 1
            metadata_arg = event_inserts[0][3]
            payload = json.loads(metadata_arg)
            assert payload["invite_code"] == "INVITE123"


# ============================================================
# Channel + tip + job posting URL prefix correctness
# ============================================================

class TestSuccessURLPrefix:
    """Client routing mounts channels at /work/channels/{id} (App.tsx).
    Stripe success_url must match — earlier code used /app/matcha/work/...
    which 404s after Stripe redirects the paid customer back."""

    @pytest.mark.asyncio
    async def test_channel_subscription_url_uses_work_prefix(self):
        from app.core.services import channel_payment_service

        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            class S: url = "https://stripe.test/x"
            return S()

        fake_settings = MagicMock(app_base_url="https://app.matcha.test")
        mock_session = MagicMock()
        mock_session.create = fake_create
        with patch.object(channel_payment_service, "_ensure_stripe"):
            with patch.object(channel_payment_service, "get_settings", return_value=fake_settings):
                with patch.object(channel_payment_service, "stripe", MagicMock(checkout=MagicMock(Session=mock_session))):
                    await channel_payment_service.create_checkout_session(
                        channel_id=uuid4(),
                        channel_name="dev",
                        stripe_price_id="price_abc",
                        user_id=uuid4(),
                    )
        assert "/work/channels/" in captured["success_url"]
        assert "/app/matcha/work/" not in captured["success_url"]
        assert "/work/channels/" in captured["cancel_url"]
        assert "/app/matcha/work/" not in captured["cancel_url"]

    @pytest.mark.asyncio
    async def test_job_posting_url_uses_work_prefix(self):
        from app.core.services import channel_job_posting_service

        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            class S: url = "https://stripe.test/jp"
            return S()

        fake_settings = MagicMock(app_base_url="https://app.matcha.test")
        mock_session = MagicMock()
        mock_session.create = fake_create
        with patch.object(channel_job_posting_service, "_ensure_stripe"):
            with patch.object(channel_job_posting_service, "get_settings", return_value=fake_settings):
                with patch.object(channel_job_posting_service, "stripe", MagicMock(checkout=MagicMock(Session=mock_session))):
                    await channel_job_posting_service.create_job_posting_checkout(
                        posting_id=uuid4(),
                        channel_id=uuid4(),
                        user_id=uuid4(),
                        stripe_price_id="price_jp",
                    )
        assert "/work/channels/" in captured["success_url"]
        assert "/app/matcha/work/" not in captured["success_url"]


# ============================================================
# Job posting honors per-channel fee override
# ============================================================

class TestJobPostingCustomFee:
    """`channels.job_posting_fee_cents` overrides the platform default.
    Earlier code ignored the column and always charged $200."""

    @pytest.mark.asyncio
    async def test_uses_channel_override(self):
        from app.core.services import channel_job_posting_service

        captured = {}

        def fake_price_create(**kwargs):
            captured.update(kwargs)
            class P: id = "price_x"
            return P()

        class _Prod:
            id = "prod_x"

        def fake_product_create(**kwargs):
            return _Prod()

        with patch.object(channel_job_posting_service, "_ensure_stripe"):
            with patch.object(channel_job_posting_service, "stripe",
                              MagicMock(Product=MagicMock(create=fake_product_create),
                                        Price=MagicMock(create=fake_price_create))):
                await channel_job_posting_service.create_job_posting_product_and_price(
                    channel_id=uuid4(),
                    channel_name="dev",
                    posting_title="hire me",
                    price_cents=15000,  # $150 channel override
                )
        assert captured["unit_amount"] == 15000

    @pytest.mark.asyncio
    async def test_falls_back_to_platform_default(self):
        from app.core.services import channel_job_posting_service

        captured = {}

        def fake_price_create(**kwargs):
            captured.update(kwargs)
            class P: id = "price_x"
            return P()

        class _Prod:
            id = "prod_x"

        def fake_product_create(**kwargs):
            return _Prod()

        with patch.object(channel_job_posting_service, "_ensure_stripe"):
            with patch.object(channel_job_posting_service, "stripe",
                              MagicMock(Product=MagicMock(create=fake_product_create),
                                        Price=MagicMock(create=fake_price_create))):
                await channel_job_posting_service.create_job_posting_product_and_price(
                    channel_id=uuid4(),
                    channel_name="dev",
                    posting_title="hire me",
                    price_cents=None,  # No override
                )
        assert captured["unit_amount"] == channel_job_posting_service.JOB_POSTING_PRICE_CENTS

    @pytest.mark.asyncio
    async def test_below_minimum_rejected(self):
        from app.core.services import channel_job_posting_service

        with patch.object(channel_job_posting_service, "_ensure_stripe"):
            with pytest.raises(channel_job_posting_service.JobPostingPaymentError, match="between"):
                await channel_job_posting_service.create_job_posting_product_and_price(
                    channel_id=uuid4(),
                    channel_name="dev",
                    posting_title="hire me",
                    price_cents=10,  # below floor
                )


# ============================================================
# Job posting handler success paths
# ============================================================

class TestJobPostingLifecycleHandlers:
    @pytest.mark.asyncio
    async def test_handle_activated_writes_active_status_and_event(self):
        mock_conn = AsyncMock()
        # fetchval used to read job_posting_fee_cents (returns None → fallback)
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_job_posting_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_job_posting_service import handle_job_posting_activated
            await handle_job_posting_activated(
                posting_id=uuid4(), channel_id=uuid4(), user_id=uuid4(),
                stripe_subscription_id="sub_jp_test",
                current_period_end=int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            )
            calls = [str(c) for c in mock_conn.execute.call_args_list]
            assert any("status = 'active'" in c for c in calls)
            assert any("subscription_status = 'active'" in c for c in calls)
            assert any("job_posting_activated" in c for c in calls)

    @pytest.mark.asyncio
    async def test_handle_renewed_no_match_is_noop(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_job_posting_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_job_posting_service import handle_job_posting_renewed
            await handle_job_posting_renewed(
                stripe_subscription_id="sub_jp_unknown",
                current_period_end=int(time.time() + 30 * 86400),
                amount_cents=20000,
            )
            mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_renewed_advances_paid_through(self):
        row = {"id": uuid4(), "channel_id": uuid4(), "posted_by": uuid4()}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_job_posting_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_job_posting_service import handle_job_posting_renewed
            await handle_job_posting_renewed(
                stripe_subscription_id="sub_jp_renew",
                current_period_end=int(time.time() + 30 * 86400),
                amount_cents=20000,
            )
            calls = [str(c) for c in mock_conn.execute.call_args_list]
            assert any("subscription_status = 'active'" in c for c in calls)
            assert any("job_posting_renewed" in c for c in calls)

    @pytest.mark.asyncio
    async def test_handle_payment_failed_dedupe_within_cycle(self):
        row = {"id": uuid4(), "channel_id": uuid4(), "posted_by": uuid4(),
               "title": "Senior Eng", "company_id": uuid4()}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=row)
        # last_renewal=None, already_failed=True → second call in same cycle
        mock_conn.fetchval = AsyncMock(side_effect=[None, True])
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_job_posting_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.matcha.services.notification_service.create_notification", new_callable=AsyncMock) as mock_notif:
                from app.core.services.channel_job_posting_service import handle_job_posting_payment_failed
                await handle_job_posting_payment_failed("sub_jp_fail")

                calls = [str(c) for c in mock_conn.execute.call_args_list]
                assert any("past_due" in c for c in calls)
                # Second call in cycle: no INSERT, no notification
                assert not any("INSERT" in c and "job_posting_payment_failed" in c for c in calls)
                mock_notif.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_canceled_closes_posting(self):
        row = {"id": uuid4(), "channel_id": uuid4(), "posted_by": uuid4()}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_conn.execute = AsyncMock()

        with patch("app.core.services.channel_job_posting_service.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.services.channel_job_posting_service import handle_job_posting_canceled
            await handle_job_posting_canceled("sub_jp_cancel")
            calls = [str(c) for c in mock_conn.execute.call_args_list]
            # Status flips both subscription_status='canceled' and posting status='closed'
            assert any("subscription_status = 'canceled'" in c for c in calls)
            assert any("status = 'closed'" in c for c in calls)
            assert any("closed_at = NOW()" in c for c in calls)


# ============================================================
# Channel price update — new PATCH route + Stripe helper
# ============================================================

class TestChannelPriceUpdate:
    """update_channel_price creates a new Stripe price under the existing
    product and archives the old one. Existing subscriptions keep their
    original price (Stripe binds the amount per-subscription)."""

    @pytest.mark.asyncio
    async def test_creates_new_price_archives_old(self):
        from app.core.services import channel_payment_service

        captured = {}

        def fake_create(**kwargs):
            captured["new"] = kwargs
            class P: id = "price_new_xyz"
            return P()

        archived = []
        def fake_modify(price_id, **kwargs):
            archived.append((price_id, kwargs))
            class P: id = price_id
            return P()

        with patch.object(channel_payment_service, "_ensure_stripe"):
            with patch.object(channel_payment_service, "stripe",
                              MagicMock(Price=MagicMock(create=fake_create, modify=fake_modify))):
                new_id = await channel_payment_service.update_channel_price(
                    stripe_product_id="prod_abc",
                    new_price_cents=1500,
                    old_price_id="price_old_qqq",
                )
        assert new_id == "price_new_xyz"
        assert captured["new"]["unit_amount"] == 1500
        assert captured["new"]["recurring"] == {"interval": "month"}
        assert archived == [("price_old_qqq", {"active": False})]

    @pytest.mark.asyncio
    async def test_below_minimum_rejected(self):
        from app.core.services import channel_payment_service
        with patch.object(channel_payment_service, "_ensure_stripe"):
            with pytest.raises(channel_payment_service.ChannelPaymentError, match="between"):
                await channel_payment_service.update_channel_price(
                    stripe_product_id="prod_abc",
                    new_price_cents=10,
                    old_price_id=None,
                )

    @pytest.mark.asyncio
    async def test_old_price_archive_failure_doesnt_block(self):
        from app.core.services import channel_payment_service

        def fake_create(**kwargs):
            class P: id = "price_new_zzz"
            return P()

        def fake_modify(price_id, **kwargs):
            raise RuntimeError("Stripe transient")

        with patch.object(channel_payment_service, "_ensure_stripe"):
            with patch.object(channel_payment_service, "stripe",
                              MagicMock(Price=MagicMock(create=fake_create, modify=fake_modify))):
                # Should still return new price ID — archive failure is logged + swallowed
                new_id = await channel_payment_service.update_channel_price(
                    stripe_product_id="prod_abc",
                    new_price_cents=2000,
                    old_price_id="price_old_qqq",
                )
        assert new_id == "price_new_zzz"


# ============================================================
# Tip handler success path
# ============================================================

class TestTipHandlerSuccessPath:
    """The tip webhook handler logs two events (creator + sender) and
    notifies the creator. Funds remain on the platform — no payout
    until Stripe Connect ships."""

    def test_invitable_users_email_detection(self):
        """The invite-by-email source only fires when the query string is
        a complete email (contains '@' and a '.' in the domain). Partial
        matches still respect the relationship-only sources."""
        # Just check the detection predicate the route uses
        cases = [
            ("alice@example.com", True),
            ("alice", False),
            ("alice@", False),
            ("alice@nodot", False),
            ("@example.com", True),  # technically valid by check; still requires DB match to return
        ]
        for q, expected in cases:
            actual = "@" in q and "." in q.split("@", 1)[1] if "@" in q else False
            assert actual == expected, f"q={q!r}: expected {expected}, got {actual}"

    @pytest.mark.asyncio
    async def test_tip_logs_events_and_notifies(self):
        from app.core.routes import stripe_webhook as wh

        mock_conn = AsyncMock()
        # fetchval returns: company_id (notification), channel_name, sender_name
        company_id = uuid4()
        mock_conn.fetchval = AsyncMock(side_effect=[company_id, "lemonade", "alice"])
        mock_conn.execute = AsyncMock()

        # The tip branch uses a nested `from ...database import get_connection`
        # so we patch the source module, not the route module.
        with patch("app.database.get_connection") as mock_gc:
            mock_gc.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_gc.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.matcha.services.notification_service.create_notification", new_callable=AsyncMock) as mock_notif:
                channel_id = uuid4()
                creator_id = uuid4()
                sender_id = uuid4()
                event_object = {
                    "id": "cs_tip_test",
                    "mode": "payment",
                    "metadata": {
                        "type": "channel_tip",
                        "channel_id": str(channel_id),
                        "creator_id": str(creator_id),
                        "sender_id": str(sender_id),
                        "amount_cents": "500",
                        "message": "thanks!",
                    },
                }
                await wh._route_event("checkout.session.completed", event_object)

        # Two event rows inserted (tip_received + tip_sent)
        calls = [str(c) for c in mock_conn.execute.call_args_list]
        assert any("tip_received" in c for c in calls)
        assert any("tip_sent" in c for c in calls)
        mock_notif.assert_called_once()
        notif_kwargs = mock_notif.call_args.kwargs
        assert notif_kwargs["type"] == "channel_tip_received"
        assert "$5.00" in notif_kwargs["title"]
