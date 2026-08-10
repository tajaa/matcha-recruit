"""Pure-function + authorization helper tests for Tell-Us Comms (no DB).

DB-touching paths (thread creation, message send, idempotency, rate limits,
blocking, closing, assignment, notifications) are integration-level — run
manually against dev per the repo's DB-test policy.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.tellus.models.tellus import TellusAccount
from app.tellus.services.comms_service import (
    get_thread_access,
    next_status,
    resolve_inbox_brand,
    thread_to_model,
)

OWNER_ID = uuid4()
MEMBER_ID = uuid4()
CONSUMER_ID = uuid4()
BRAND_ID = uuid4()
OTHER_BRAND_ID = uuid4()
THREAD_ID = uuid4()
STORE_ID = uuid4()


def make_account(account_type, account_id, brand_id=None):
    return TellusAccount(
        id=account_id,
        email=f"{account_id}@example.test",
        display_name="Test",
        account_type=account_type,
        brand_id=brand_id,
        email_verified=True,
        points=0,
    )


class TestNextStatus:
    def test_consumer_message_waits_for_business(self):
        assert next_status("consumer") == "waiting_brand"

    def test_business_message_waits_for_consumer(self):
        assert next_status("brand") == "waiting_consumer"

    def test_unknown_role_defaults_to_waiting_consumer(self):
        assert next_status("admin") == "waiting_consumer"


class TestThreadToModel:
    def _base_row(self):
        return {
            "id": uuid4(),
            "report_id": None,
            "brand_name": "Shop",
            "consumer_display_name": "Alex",
            "last_message_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "assigned_member_id": uuid4(),
            "assigned_member_name": "Staff",
            "kind": "general",
            "status": "waiting_brand",
            "blocked_at": None,
        }

    def test_consumer_view_redacts_inbox_assignment(self):
        row = self._base_row()
        view = thread_to_model(row, "consumer")
        assert view.assigned_member_id is None
        assert view.assigned_member_name is None
        assert view.viewer_role == "consumer"

    def test_brand_view_materializes_assignment(self):
        row = self._base_row()
        member_id = row["assigned_member_id"]
        view = thread_to_model(row, "brand")
        assert view.assigned_member_id == member_id
        assert view.assigned_member_name == "Staff"
        assert view.viewer_role == "brand"

    def test_consumer_view_sees_brand_name_as_counterparty(self):
        row = self._base_row()
        view = thread_to_model(row, "consumer")
        assert view.counterparty_name == "Shop"

    def test_brand_view_sees_consumer_name_as_counterparty(self):
        row = self._base_row()
        view = thread_to_model(row, "brand")
        assert view.counterparty_name == "Alex"

    def test_brand_view_fallback_counterparty_when_no_display_name(self):
        row = self._base_row()
        row["consumer_display_name"] = None
        view = thread_to_model(row, "brand")
        assert view.counterparty_name == "Reviewer"

    def test_blocked_state_detected(self):
        row = self._base_row()
        row["blocked_at"] = datetime.now(timezone.utc)
        view = thread_to_model(row, "consumer")
        assert view.blocked is True

    def test_closed_state_present(self):
        row = self._base_row()
        row["closed_at"] = datetime.now(timezone.utc)
        view = thread_to_model(row, "brand")
        assert view.closed_at is not None

    def test_first_brand_response_at_present(self):
        row = self._base_row()
        row["first_brand_response_at"] = datetime.now(timezone.utc)
        view = thread_to_model(row, "brand")
        assert view.first_brand_response_at is not None

    def test_unread_count_defaults_to_zero(self):
        row = self._base_row()
        view = thread_to_model(row, "consumer")
        assert view.unread_count == 0

    def test_kind_defaults_to_feedback(self):
        row = self._base_row()
        del row["kind"]
        view = thread_to_model(row, "consumer")
        assert view.kind == "feedback"

    def test_status_defaults_to_waiting_consumer(self):
        row = self._base_row()
        del row["status"]
        view = thread_to_model(row, "consumer")
        assert view.status == "waiting_consumer"


class TestResolveInboxBrand:
    @pytest.mark.asyncio
    async def test_owner_short_circuits_without_member_row(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {
                "id": BRAND_ID,
                "owner_account_id": OWNER_ID,
                "plan_status": "active",
                "messaging_enabled": True,
            },
            None,  # no member row for owner
        ]
        account = make_account("brand", OWNER_ID, BRAND_ID)
        brand, member = await resolve_inbox_brand(conn, account)
        assert brand["id"] == BRAND_ID
        assert member["role"] == "owner"
        assert member["can_manage_inbox"] is True

    @pytest.mark.asyncio
    async def test_member_with_active_plan(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "id": BRAND_ID,
                "owner_account_id": OWNER_ID,
                "plan_status": "active",
                "messaging_enabled": True,
                "member_id": MEMBER_ID,
                "member_role": "agent",
                "can_manage_inbox": True,
            }
        ]
        account = make_account("consumer", MEMBER_ID)
        brand, member = await resolve_inbox_brand(conn, account, brand_id=BRAND_ID)
        assert brand["id"] == BRAND_ID
        assert member["can_manage_inbox"] is True

    @pytest.mark.asyncio
    async def test_member_with_inactive_plan_raises_402(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "id": BRAND_ID,
                "owner_account_id": OWNER_ID,
                "plan_status": "inactive",
                "messaging_enabled": True,
                "member_id": MEMBER_ID,
                "member_role": "agent",
                "can_manage_inbox": True,
            }
        ]
        account = make_account("consumer", MEMBER_ID)
        with pytest.raises(HTTPException) as exc:
            await resolve_inbox_brand(conn, account, brand_id=BRAND_ID)
        assert exc.value.status_code == 402

    @pytest.mark.asyncio
    async def test_no_membership_raises_404(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        account = make_account("consumer", MEMBER_ID)
        with pytest.raises(HTTPException) as exc:
            await resolve_inbox_brand(conn, account, brand_id=BRAND_ID)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_inboxes_without_brand_id_raises_400(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {"id": BRAND_ID, "plan_status": "active"},
            {"id": OTHER_BRAND_ID, "plan_status": "active"},
        ]
        account = make_account("consumer", MEMBER_ID)
        with pytest.raises(HTTPException) as exc:
            await resolve_inbox_brand(conn, account)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_single_inbox_resolves_without_brand_id(self):
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "id": BRAND_ID,
                "owner_account_id": OWNER_ID,
                "plan_status": "active",
                "messaging_enabled": True,
                "member_id": MEMBER_ID,
                "member_role": "agent",
                "can_manage_inbox": True,
            }
        ]
        account = make_account("consumer", MEMBER_ID)
        brand, member = await resolve_inbox_brand(conn, account)
        assert brand["id"] == BRAND_ID


class TestGetThreadAccess:
    def _base_thread_row(self, consumer_id=CONSUMER_ID, brand_id=BRAND_ID):
        return {
            "id": THREAD_ID,
            "consumer_account_id": consumer_id,
            "brand_id": brand_id,
            "brand_name": "Shop",
            "brand_slug": "shop",
            "report_id": None,
            "report_title": None,
            "report_number": None,
            "review_state": None,
            "publish_at": None,
            "store_id": STORE_ID,
            "store_name": "Downtown",
            "store_city": "LA",
            "assigned_member_id": None,
            "assigned_member_name": None,
            "consumer_display_name": "Alex",
            "last_message_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "kind": "general",
            "topic": "hours",
            "status": "waiting_brand",
            "blocked_at": None,
            "first_brand_response_at": None,
            "closed_at": None,
            "closed_by_account_id": None,
        }

    @pytest.mark.asyncio
    async def test_consumer_can_access_own_thread(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._base_thread_row()
        account = make_account("consumer", CONSUMER_ID)
        thread, role = await get_thread_access(conn, THREAD_ID, account)
        assert role == "consumer"
        assert thread["id"] == THREAD_ID

    @pytest.mark.asyncio
    async def test_brand_owner_can_access_own_brand_thread(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._base_thread_row()
        account = make_account("brand", OWNER_ID, BRAND_ID)
        thread, role = await get_thread_access(conn, THREAD_ID, account)
        assert role == "brand"

    @pytest.mark.asyncio
    async def test_member_with_active_plan_can_access(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = self._base_thread_row()
        conn.fetchrow.side_effect = [
            self._base_thread_row(),
            {"can_manage_inbox": True},
        ]
        conn.fetchval.return_value = "active"
        account = make_account("consumer", MEMBER_ID)
        thread, role = await get_thread_access(conn, THREAD_ID, account)
        assert role == "brand"

    @pytest.mark.asyncio
    async def test_member_with_inactive_plan_raises_402(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._base_thread_row(),
            {"can_manage_inbox": True},
        ]
        conn.fetchval.return_value = "inactive"
        account = make_account("consumer", MEMBER_ID)
        with pytest.raises(HTTPException) as exc:
            await get_thread_access(conn, THREAD_ID, account)
        assert exc.value.status_code == 402
        assert "plan is inactive" in exc.value.detail

    @pytest.mark.asyncio
    async def test_same_brand_member_with_inactive_plan_raises_402(self):
        """Regression guard: same-brand non-owner members must also hit plan check.

        The account must be consumer-type (team member) to reach the membership
        path rather than the brand-owner short-circuit.
        """
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._base_thread_row(brand_id=BRAND_ID),
            {"can_manage_inbox": True},
        ]
        conn.fetchval.return_value = "inactive"
        account = make_account("consumer", MEMBER_ID)
        with pytest.raises(HTTPException) as exc:
            await get_thread_access(conn, THREAD_ID, account)
        assert exc.value.status_code == 402

    @pytest.mark.asyncio
    async def test_no_membership_raises_404(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._base_thread_row(),
            None,
        ]
        account = make_account("consumer", uuid4())
        with pytest.raises(HTTPException) as exc:
            await get_thread_access(conn, THREAD_ID, account)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_foreign_thread_id_raises_404(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        account = make_account("consumer", CONSUMER_ID)
        with pytest.raises(HTTPException) as exc:
            await get_thread_access(conn, THREAD_ID, account)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_member_without_inbox_permission_raises_404(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            self._base_thread_row(),
            {"can_manage_inbox": False},
        ]
        account = make_account("consumer", MEMBER_ID)
        with pytest.raises(HTTPException) as exc:
            await get_thread_access(conn, THREAD_ID, account)
        assert exc.value.status_code == 404
