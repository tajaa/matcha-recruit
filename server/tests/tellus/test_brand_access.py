"""Pure and fake-connection tests for the Tell-Us brand access foundation."""
import inspect
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.tellus.models.tellus import TellusAccount
from app.tellus.services.access_service import (
    ALL_CAPABILITIES,
    apply_capability_overrides,
    assert_capability,
    default_capabilities,
    list_business_memberships,
    resolve_brand_access,
    resolve_store_access,
)
from app.tellus.services import access_service


def account() -> TellusAccount:
    return TellusAccount(id=uuid4(), email="staff@example.test")


class TestRoleCapabilities:
    def test_owner_has_all_capabilities(self):
        assert default_capabilities("owner") == ALL_CAPABILITIES

    def test_admin_has_billing_by_default(self):
        assert "billing.manage" in default_capabilities("admin")
        assert "team.manage" in default_capabilities("admin")

    def test_staff_is_limited_to_operational_work(self):
        capabilities = default_capabilities("staff")
        assert "comms.reply" in capabilities
        assert "redemptions.redeem" in capabilities
        assert "billing.manage" not in capabilities
        assert "stores.manage" not in capabilities

    def test_grant_and_deny_overrides(self):
        capabilities = apply_capability_overrides(
            default_capabilities("staff"),
            [
                {"capability": "board.manage", "effect": "grant"},
                {"capability": "comms.reply", "effect": "deny"},
            ],
        )
        assert "board.manage" in capabilities
        assert "comms.reply" not in capabilities

    def test_unknown_override_is_ignored(self):
        capabilities = apply_capability_overrides(
            default_capabilities("staff"),
            [{"capability": "not-a-capability", "effect": "grant"}],
        )
        assert capabilities == default_capabilities("staff")

    def test_missing_capability_is_forbidden(self):
        context = type("Context", (), {"capabilities": default_capabilities("staff")})()
        with pytest.raises(HTTPException) as exc:
            assert_capability(context, "billing.manage")
        assert exc.value.status_code == 403


class FakeConn:
    def __init__(self, membership=None, stores=(), overrides=()):
        self.membership = membership
        self.stores = list(stores)
        self.overrides = list(overrides)

    async def fetchrow(self, query, *args):
        if "FROM tellus_brand_members m" in query:
            return self.membership
        if "FROM tellus_stores" in query:
            for store in self.stores:
                if store["id"] == args[0] and store["brand_id"] == args[1]:
                    return store
        return None

    async def fetch(self, query, *args):
        if "FROM tellus_stores s" in query:
            member_id = args[2]
            if args[1]:
                return self.stores
            return [s for s in self.stores if s.get("member_id") == member_id]
        if "FROM tellus_brand_member_capabilities" in query:
            return self.overrides
        return []


class MembershipListConn:
    def __init__(self, memberships, stores=(), overrides=()):
        self.memberships = list(memberships)
        self.stores = list(stores)
        self.overrides = list(overrides)

    async def fetch(self, query, *args):
        if "SELECT m.id, m.brand_id" in query:
            return self.memberships
        if "JOIN tellus_stores s" in query:
            member_ids = set(args[0])
            return [store for store in self.stores if store["member_id"] in member_ids]
        if "FROM tellus_brand_member_capabilities" in query:
            member_ids = set(args[0])
            return [row for row in self.overrides if row["member_id"] in member_ids]
        return []


@pytest.mark.asyncio
async def test_resolve_brand_access_builds_store_and_capability_context():
    brand_id = uuid4()
    member_id = uuid4()
    store_id = uuid4()
    conn = FakeConn(
        {
            "membership_id": member_id,
            "brand_id": brand_id,
            "role": "staff",
            "status": "active",
            "all_stores": False,
            "plan_status": "active",
        },
        stores=[{"id": store_id, "brand_id": brand_id, "member_id": member_id}],
        overrides=[{"capability": "board.manage", "effect": "grant"}],
    )
    context = await resolve_brand_access(conn, uuid4(), brand_id)
    assert context.brand_id == brand_id
    assert context.membership_id == member_id
    assert context.store_ids == frozenset({store_id})
    assert "board.manage" in context.capabilities


@pytest.mark.asyncio
async def test_suspended_membership_is_not_resolvable():
    conn = FakeConn({"status": "suspended"})
    with pytest.raises(HTTPException) as exc:
        await resolve_brand_access(conn, uuid4(), uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_store_access_rejects_unassigned_store():
    brand_id = uuid4()
    store_id = uuid4()
    context = type(
        "Context",
        (),
        {"all_stores": False, "store_ids": frozenset(), "brand_id": brand_id},
    )()
    conn = FakeConn()
    with pytest.raises(HTTPException) as exc:
        await resolve_store_access(conn, context, store_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_store_access_accepts_same_brand_store():
    brand_id = uuid4()
    store_id = uuid4()
    context = type(
        "Context",
        (),
        {"all_stores": True, "store_ids": frozenset(), "brand_id": brand_id},
    )()
    conn = FakeConn(stores=[{"id": store_id, "brand_id": brand_id, "name": "Downtown"}])
    result = await resolve_store_access(conn, context, store_id)
    assert result.store_id == store_id
    assert result.store_name == "Downtown"


def test_pre_location_access_queries_do_not_require_store_status():
    source = inspect.getsource(access_service)
    assert "status = 'active'" not in source
    assert "'active'::text AS status" in source


def test_app19_backfills_legacy_staff_as_all_store():
    from pathlib import Path

    migration = Path(__file__).parents[2] / "alembic/versions/tellus_app_19_brand_access.py"
    source = migration.read_text()
    assert "role IN ('owner', 'admin', 'staff')" in source


@pytest.mark.asyncio
async def test_list_business_memberships_materializes_store_grants_and_overrides():
    account_id = uuid4()
    member_id = uuid4()
    brand_id = uuid4()
    store_id = uuid4()
    conn = MembershipListConn(
        memberships=[
            {
                "id": member_id,
                "brand_id": brand_id,
                "brand_name": "Shop",
                "brand_slug": "shop",
                "plan_status": "active",
                "role": "staff",
                "status": "active",
                "all_stores": False,
            }
        ],
        stores=[
            {
                "member_id": member_id,
                "id": store_id,
                "name": "Downtown",
                "city": "Austin",
                "state": "TX",
                "status": "active",
            }
        ],
        overrides=[
            {"member_id": member_id, "capability": "board.manage", "effect": "grant"}
        ],
    )
    memberships = await list_business_memberships(conn, account_id)
    assert len(memberships) == 1
    assert memberships[0].brand_id == brand_id
    assert memberships[0].stores[0].id == store_id
    assert "board.manage" in memberships[0].capabilities
