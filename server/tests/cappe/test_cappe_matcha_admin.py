"""Matcha admin's Cappe tools (/admin/cappe): plan changes and signup grants.

The gate is driven with real requests (see test_cappe_billing_routes.py for
why route introspection can't be trusted); the handlers run against fake
connections with the comp functions stubbed.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_matcha_admin.py -q
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models.cappe import CappeAdminPlanChange, CappeSignupGrantCreate  # noqa: E402
from app.cappe.routes import cappe_router, matcha_admin  # noqa: E402
from app.cappe.services import billing as billing_svc  # noqa: E402
from app.core.dependencies import get_current_user, require_admin  # noqa: E402

ADMIN = SimpleNamespace(email="admin@example.com", role="admin")
GRANT_ID = uuid.uuid4()
ACCOUNT_ID = uuid.uuid4()

ENDPOINTS = [
    ("GET", "/api/cappe/matcha-admin/plans"),
    ("POST", f"/api/cappe/matcha-admin/accounts/{ACCOUNT_ID}/plan"),
    ("GET", "/api/cappe/matcha-admin/signup-grants"),
    ("POST", "/api/cappe/matcha-admin/signup-grants"),
    ("POST", f"/api/cappe/matcha-admin/signup-grants/{GRANT_ID}/revoke"),
]


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(cappe_router, prefix="/api/cappe")
    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_anonymous_callers_are_refused(client, method, path):
    assert client.request(method, path, json={}).status_code in (401, 403)


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_a_signed_in_non_admin_is_forbidden(app, client, method, path):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        email="owner@example.com", role="client"
    )
    try:
        assert client.request(method, path, json={}).status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_the_admin_gets_past_the_gate(app, client, method, path):
    """No database here, so the handler fails afterwards: anything but 401/403
    means the gate let the admin through."""
    app.dependency_overrides[require_admin] = lambda: ADMIN
    try:
        assert client.request(method, path, json={}).status_code not in (401, 403)
    finally:
        app.dependency_overrides.clear()


# ── fakes ─────────────────────────────────────────────────────────────────────

class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, *, plan="business", account_plan="free", grant_row=None, revoked=GRANT_ID):
        self.plan = plan
        self.account_plan = account_plan
        self.grant_row = grant_row
        self.revoked = revoked
        self.executed = []
        self.inserted = None

    def transaction(self):
        return _Tx()

    async def fetchval(self, sql, *args):
        if "FROM cappe_billing_products" in sql:
            return self.plan
        if "FROM cappe_accounts" in sql:
            return self.account_plan
        if "INSERT INTO cappe_signup_grants" in sql:
            self.inserted = args
            return GRANT_ID
        if "UPDATE cappe_signup_grants" in sql:
            return self.revoked
        raise AssertionError(sql)

    async def fetchrow(self, sql, *args):
        return self.grant_row

    async def fetch(self, sql, *args):
        return [self.grant_row] if self.grant_row else []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


@pytest.fixture
def use(monkeypatch):
    calls = {"grant": [], "end": []}

    async def _grant_comp(conn, **kwargs):
        calls["grant"].append(kwargs)

    async def _end_comp(conn, **kwargs):
        calls["end"].append(kwargs)

    monkeypatch.setattr(billing_svc, "grant_comp", _grant_comp)
    monkeypatch.setattr(billing_svc, "end_comp", _end_comp)

    def _use(conn):
        monkeypatch.setattr(matcha_admin, "get_connection", lambda: _Ctx(conn))
        calls["conn"] = conn
        return calls

    return _use


def _audits(conn):
    return [(args[0], json.loads(args[2])) for sql, args in conn.executed if "cappe_admin_audit" in sql]


# ── plan changes ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_upgrade_is_a_comp_until_the_date_given(use):
    calls = use(_Conn())
    until = datetime.now(timezone.utc) + timedelta(days=30)
    res = await matcha_admin.set_account_plan(
        ACCOUNT_ID, CappeAdminPlanChange(plan_code="business", until=until, reason="Pilot"), admin=ADMIN,
    )
    assert res == {"plan": "business", "comped_until": until}
    assert calls["grant"] == [{"account_id": ACCOUNT_ID, "plan_code": "business", "until": until, "reason": "Pilot"}]
    [(action, payload)] = _audits(calls["conn"])
    assert action == "matcha:account.plan"
    assert payload["from"] == "free" and payload["to"] == "business"
    assert payload["admin_email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_an_upgrade_without_a_reason_records_who_did_it(use):
    calls = use(_Conn())
    await matcha_admin.set_account_plan(ACCOUNT_ID, CappeAdminPlanChange(plan_code="business"), admin=ADMIN)
    assert calls["grant"][0]["until"] is None
    assert calls["grant"][0]["reason"] == "Set by admin@example.com"


@pytest.mark.asyncio
async def test_a_downgrade_to_free_ends_the_comp(use):
    calls = use(_Conn(plan="free", account_plan="business"))
    res = await matcha_admin.set_account_plan(ACCOUNT_ID, CappeAdminPlanChange(plan_code="free"), admin=ADMIN)
    assert res == {"plan": "free", "comped_until": None}
    assert calls["end"] == [{"account_id": ACCOUNT_ID}] and calls["grant"] == []


@pytest.mark.asyncio
async def test_a_paying_account_is_refused_with_409(use, monkeypatch):
    calls = use(_Conn())

    async def _paying(conn, **_kwargs):
        raise billing_svc.LiveSubscriptionExists("This account has a live Stripe subscription.")

    monkeypatch.setattr(billing_svc, "grant_comp", _paying)
    with pytest.raises(HTTPException) as exc:
        await matcha_admin.set_account_plan(ACCOUNT_ID, CappeAdminPlanChange(plan_code="business"), admin=ADMIN)
    assert exc.value.status_code == 409 and "Stripe" in exc.value.detail
    assert _audits(calls["conn"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("conn,code", [
    (_Conn(plan=None), 404),
    (_Conn(account_plan=None), 404),
])
async def test_unknown_plans_and_accounts_are_404(use, conn, code):
    use(conn)
    with pytest.raises(HTTPException) as exc:
        await matcha_admin.set_account_plan(ACCOUNT_ID, CappeAdminPlanChange(plan_code="business"), admin=ADMIN)
    assert exc.value.status_code == code


@pytest.mark.asyncio
async def test_an_end_date_in_the_past_is_refused(use):
    use(_Conn())
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    with pytest.raises(HTTPException) as exc:
        await matcha_admin.set_account_plan(
            ACCOUNT_ID, CappeAdminPlanChange(plan_code="business", until=past), admin=ADMIN,
        )
    assert exc.value.status_code == 422


def test_an_end_date_without_a_timezone_is_refused_not_guessed():
    with pytest.raises(ValidationError):
        CappeAdminPlanChange(plan_code="business", until="2026-12-01T00:00:00")
    assert CappeAdminPlanChange(plan_code="business", until="2026-12-01T00:00:00Z").until.tzinfo


@pytest.mark.asyncio
async def test_a_plan_written_by_someone_else_at_the_same_moment_is_409_not_500(use, monkeypatch):
    use(_Conn())

    async def _clash(conn, **_kwargs):
        raise asyncpg.UniqueViolationError("uq_cappe_sub_live")

    monkeypatch.setattr(billing_svc, "grant_comp", _clash)
    with pytest.raises(HTTPException) as exc:
        await matcha_admin.set_account_plan(ACCOUNT_ID, CappeAdminPlanChange(plan_code="business"), admin=ADMIN)
    assert exc.value.status_code == 409 and "same moment" in exc.value.detail


@pytest.mark.asyncio
async def test_list_plans_returns_the_catalog_rows(monkeypatch):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"code": "free", "name": "Free", "status": "active"}])
    monkeypatch.setattr(matcha_admin, "get_connection", lambda: _Ctx(conn))
    assert await matcha_admin.list_plans() == [{"code": "free", "name": "Free", "status": "active"}]
    assert "status <> 'archived'" in conn.fetch.call_args.args[0]


# ── signup grants ─────────────────────────────────────────────────────────────

def _grant_row(**over):
    row = {
        "id": GRANT_ID, "token": "t" * 32, "plan_code": "business", "plan_name": "Business",
        "days": 30, "max_redemptions": 1, "redeemed_count": 0, "email": None, "note": None,
        "expires_at": None, "revoked_at": None, "created_by_email": "admin@example.com",
        "created_at": datetime.now(timezone.utc), "signup_count": 14,
        "accounts": json.dumps([{
            "id": str(ACCOUNT_ID), "email": "new@example.com", "plan": "free",
            "signed_up_at": "2026-10-19T12:00:00+00:00",
            "email_verified_at": "2026-10-19T12:05:00+00:00", "redeemed_at": None,
            "refused": "This invite link has already been used.",
        }]),
    }
    row.update(over)
    return row


@pytest.mark.asyncio
async def test_creating_a_grant_returns_its_link(use):
    calls = use(_Conn(grant_row=_grant_row()))
    body = CappeSignupGrantCreate(plan_code="business", days=30, email="Owner@Example.com", note="Partner")
    grant = await matcha_admin.create_signup_grant(body, admin=ADMIN)

    token, plan, days, uses, email, note, expires_at, created_by = calls["conn"].inserted
    assert len(token) == 32 and (plan, days, uses) == ("business", 30, 1)
    assert email == "owner@example.com" and note == "Partner" and created_by == "admin@example.com"
    # The link takes signups for 30 days by default.
    assert timedelta(days=29, hours=23) < expires_at - datetime.now(timezone.utc) <= timedelta(days=30)
    assert grant.signup_url.endswith("/cappe/signup?grant=" + "t" * 32)
    assert grant.accounts[0].email == "new@example.com"
    [(action, payload)] = _audits(calls["conn"])
    assert action == "matcha:signup_grant.create"
    # The invitee's address stays on the grant row, out of the audit payload.
    assert "email" not in payload and payload["email_locked"] is True
    assert payload["admin_email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_a_link_with_no_expiry_never_expires(use):
    calls = use(_Conn(grant_row=_grant_row()))
    await matcha_admin.create_signup_grant(
        CappeSignupGrantCreate(plan_code="business", link_valid_days=None), admin=ADMIN,
    )
    assert calls["conn"].inserted[6] is None


@pytest.mark.asyncio
async def test_a_grant_must_name_a_paid_plan_on_sale(use):
    calls = use(_Conn(plan=None))
    with pytest.raises(HTTPException) as exc:
        await matcha_admin.create_signup_grant(CappeSignupGrantCreate(plan_code="free"), admin=ADMIN)
    assert exc.value.status_code == 400 and calls["conn"].inserted is None


@pytest.mark.asyncio
async def test_listing_grants_decodes_their_accounts_and_outcomes(use):
    use(_Conn(grant_row=_grant_row()))
    [grant] = await matcha_admin.list_signup_grants()
    assert grant.plan_name == "Business" and grant.signup_count == 14
    [account] = grant.accounts
    assert account.email_verified_at is not None and account.redeemed_at is None
    assert account.refused == "This invite link has already been used."


def test_the_grant_list_shows_a_bounded_few_accounts_per_link():
    sql = matcha_admin._GRANT_LIST
    assert f"LIMIT {matcha_admin._GRANT_ACCOUNTS_SHOWN}" in sql and "AS signup_count" in sql


@pytest.mark.asyncio
async def test_revoking_stamps_it_once(use):
    calls = use(_Conn(grant_row=_grant_row(revoked_at=datetime.now(timezone.utc))))
    grant = await matcha_admin.revoke_signup_grant(GRANT_ID, admin=ADMIN)
    assert grant.revoked_at is not None
    assert _audits(calls["conn"])[0][0] == "matcha:signup_grant.revoke"

    use(_Conn(revoked=None))
    with pytest.raises(HTTPException) as exc:
        await matcha_admin.revoke_signup_grant(GRANT_ID, admin=ADMIN)
    assert exc.value.status_code == 404


# ── billing.end_comp ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_end_comp_cancels_comps_and_drops_to_free(monkeypatch):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    materialized = AsyncMock()
    monkeypatch.setattr(billing_svc, "_materialize_plan", materialized)
    await billing_svc.end_comp(conn, account_id=ACCOUNT_ID)

    lock_sql = conn.execute.call_args_list[0].args[0]
    assert "FROM cappe_accounts" in lock_sql and "FOR UPDATE" in lock_sql
    cancel_sql = conn.execute.call_args.args[0]
    assert "source = 'comp'" in cancel_sql and "status = 'canceled'" in cancel_sql
    materialized.assert_awaited_once_with(conn, ACCOUNT_ID, billing_svc.FREE_PLAN_CODE)


@pytest.mark.asyncio
async def test_grant_comp_locks_the_account_before_touching_its_comps(monkeypatch):
    """Two comp writers on one account run in turn instead of both inserting
    a live row (uq_cappe_sub_live)."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    monkeypatch.setattr(billing_svc, "_materialize_plan", AsyncMock())
    await billing_svc.grant_comp(conn, account_id=ACCOUNT_ID, plan_code="business", until=None, reason="x")
    statements = [c.args[0] for c in conn.execute.call_args_list]
    assert "FOR UPDATE" in statements[0]
    assert "INSERT INTO cappe_subscriptions" in statements[-1]


@pytest.mark.asyncio
async def test_end_comp_refuses_a_paying_account(monkeypatch):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value="sub_123")
    with pytest.raises(billing_svc.LiveSubscriptionExists):
        await billing_svc.end_comp(conn, account_id=ACCOUNT_ID)
    # Only the row lock ran; no comp was touched.
    [lock] = conn.execute.call_args_list
    assert "FOR UPDATE" in lock.args[0]


# ── the /admin/cappe roster shows comps ───────────────────────────────────────

@pytest.mark.asyncio
async def test_the_roster_carries_each_accounts_live_subscription(monkeypatch):
    from app.core.routes.admin import research

    until = datetime(2026, 11, 18, tzinfo=timezone.utc)
    account = {
        "id": ACCOUNT_ID, "email": "new@example.com", "name": None, "plan": "business",
        "status": "active", "account_type": "business", "email_verified_at": None,
        "created_at": None, "subscription_source": "comp", "subscription_status": "active",
        "comped_until": until, "campaign_count": 0, "offers_sent": 0, "active_collabs": 0,
        "collab_spend_cents": 0,
    }
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[[account], []])
    monkeypatch.setattr(research, "get_connection", lambda: _Ctx(conn))
    res = await research.admin_list_cappe_accounts()

    [row] = res["accounts"]
    assert (row["subscription_source"], row["subscription_status"]) == ("comp", "active")
    assert row["comped_until"] == until.isoformat()
    assert "LEFT JOIN LATERAL" in conn.fetch.call_args_list[0].args[0]
