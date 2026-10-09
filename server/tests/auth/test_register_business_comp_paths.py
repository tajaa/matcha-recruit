"""POST /register/business — which signups activate immediately vs wait for Stripe.

The only comp path is an admin-issued `lite_invite_token` (the broker seat-invite
and broker-pays paths were removed with the broker product). A fake connection
drives the real route function so the branches that pick the email, the
`next` route and the initial feature set are exercised without a database.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.models.auth import BusinessRegister
from app.core.routes.auth import register_business as rb

TOKEN = "invite-token"


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, *, invite_valid=True):
        self.invite_valid = invite_valid
        self.company_args = None
        self.company_id = uuid4()
        self.executed: list[str] = []

    def transaction(self):
        return _Tx()

    async def fetchval(self, sql, *args):
        assert "FROM users WHERE email" in sql
        return None

    async def fetchrow(self, sql, *args):
        if "UPDATE business_invitations" in sql:
            return {"id": uuid4()} if self.invite_valid else None
        if "UPDATE matcha_lite_invite_tokens" in sql:
            return {"id": uuid4()} if self.invite_valid else None
        if "INSERT INTO companies" in sql:
            self.company_args = args
            return {"id": self.company_id, "name": args[0]}
        if "INSERT INTO users" in sql:
            return {"id": uuid4(), "email": args[0], "role": "client", "is_active": True,
                    "created_at": datetime(2026, 1, 1)}
        raise AssertionError(f"unexpected fetchrow: {sql[:80]}")

    async def execute(self, sql, *args):
        self.executed.append(sql)
        return "OK"


class _Email:
    def __init__(self):
        self.sent: list[str] = []

    def __getattr__(self, name):
        if not name.startswith("send_"):
            raise AttributeError(name)

        async def _send(**_kwargs):
            self.sent.append(name)
            return True

        return _send


@pytest.fixture
def env(monkeypatch):
    conn = _FakeConn()
    email = _Email()

    @asynccontextmanager
    async def _get_connection():
        yield conn

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(rb, "get_connection", _get_connection)
    monkeypatch.setattr(rb, "check_rate_limit", _noop)
    monkeypatch.setattr(rb, "client_ip", lambda _r: "203.0.113.9")
    monkeypatch.setattr(rb, "_upsert_business_headcount_profile", _noop)
    monkeypatch.setattr(rb, "get_settings", lambda: SimpleNamespace(jwt_access_token_expire_minutes=15))
    monkeypatch.setattr(rb, "hash_password", lambda _p: "hashed")
    monkeypatch.setattr(rb, "create_access_token", lambda *_a: "access")
    monkeypatch.setattr(rb, "create_refresh_token", lambda *_a: "refresh")
    monkeypatch.setattr("app.core.services.email.get_email_service", lambda: email)

    async def _pricing(_conn, product_code):
        return SimpleNamespace(max_headcount=300)

    monkeypatch.setattr("app.core.services.matcha_lite_pricing.get_matcha_lite_pricing", _pricing)
    return SimpleNamespace(conn=conn, email=email)


def _register(tier, *, invited, **extra):
    body = BusinessRegister(
        company_name="Acme Test", headcount=25, email="owner@example.com",
        password="supersecret", name="Owner", tier=tier,
        lite_invite_token=TOKEN if invited else None, **extra,
    )
    return asyncio.run(rb.register_business(body, SimpleNamespace()))


def _features(env):
    return json.loads(env.conn.company_args[6])


@pytest.mark.parametrize("tier,onboarding,source", [
    ("matcha_lite", "/ir/onboarding", "matcha_lite"),
    ("matcha_x", "/matcha-x/onboarding", "matcha_x"),
    ("matcha_compliance", "/compliance/onboarding", "matcha_compliance"),
])
def test_admin_invite_activates_the_account_immediately(env, tier, onboarding, source):
    out = _register(tier, invited=True)
    assert out["lite_invite_activated"] is True
    assert out["next"] == onboarding
    assert out["signup_source"] == source
    assert env.email.sent == ["send_business_approved_email"]
    assert "lite_broker_pays" not in out
    assert any("UPDATE matcha_lite_invite_tokens" in s for s in env.conn.executed)


@pytest.mark.parametrize("tier,checkout", [
    ("matcha_lite", "/checkout/lite"),
    ("matcha_x", "/checkout/x"),
    ("matcha_compliance", "/checkout/compliance"),
])
def test_without_an_invite_the_account_waits_for_stripe(env, tier, checkout):
    out = _register(tier, invited=False)
    assert out["lite_invite_activated"] is False
    assert out["next"] == checkout
    assert env.email.sent == ["send_lite_payment_pending_email"]
    assert _features(env).get("incidents", False) is False


def test_invite_turns_on_the_paid_gate_features_for_each_tier(env):
    _register("matcha_lite", invited=True)
    assert _features(env)["incidents"] is True and _features(env)["employees"] is True


def test_essentials_invite_skips_the_employee_roster(env):
    _register("matcha_lite", invited=True, lite_essentials=True)
    feats = _features(env)
    assert feats["incidents"] is True
    assert feats.get("employees", False) is False


def test_x_and_compliance_invite_features(env):
    _register("matcha_x", invited=True)
    assert {k for k in ("incidents", "employees", "discipline") if _features(env).get(k)} == {
        "incidents", "employees", "discipline"}
    env.conn.company_args = None
    _register("matcha_compliance", invited=True)
    assert _features(env)["compliance"] is True


def test_a_used_invite_token_is_rejected(env):
    env.conn.invite_valid = False
    with pytest.raises(rb.HTTPException) as err:
        _register("matcha_lite", invited=True)
    assert err.value.status_code == 400


def test_business_invitation_approves_a_bespoke_company(env):
    body = BusinessRegister(
        company_name="Acme Test", headcount=25, email="owner@example.com",
        password="supersecret", name="Owner", invite_token="biz-invite",
    )
    out = asyncio.run(rb.register_business(body, SimpleNamespace()))
    assert out["signup_source"] == "invite"
    assert out["company_status"] == "approved"
    assert env.email.sent == ["send_business_approved_email"]


def test_public_bespoke_signup_stays_pending_with_no_paid_features(env):
    body = BusinessRegister(
        company_name="Acme Test", headcount=25, email="owner@example.com",
        password="supersecret", name="Owner",
    )
    out = asyncio.run(rb.register_business(body, SimpleNamespace()))
    assert out["signup_source"] == "bespoke"
    assert out["company_status"] == "pending"
    assert not any(_features(env).values())


class _Product(SimpleNamespace):
    pass


@pytest.mark.parametrize("activates,invited,email,nxt", [
    (True, False, "send_business_approved_email", "/app"),
    (False, True, "send_business_approved_email", "/app"),
    (False, False, "send_lite_payment_pending_email", "/checkout/product"),
])
def test_custom_product_comp_and_paid_paths(env, monkeypatch, activates, invited, email, nxt):
    product = _Product(name="Pro Pack", pricing_model="flat", is_paid=True, max_headcount=300,
                       activates_on_signup=activates, signup_source="product:pro-pack")

    async def _get(_conn, slug, published_only=True):
        return product

    monkeypatch.setattr("app.core.services.product_definitions.get_product_by_slug", _get)
    monkeypatch.setattr("app.core.services.product_definitions.materialize_features", lambda _p: {"on": True})
    monkeypatch.setattr("app.core.services.product_definitions.pending_features", lambda _p: {"on": False})
    out = _register("custom_product", invited=invited, product_slug="pro-pack")
    assert env.email.sent == [email]
    assert out["next"] == nxt
    assert out["signup_source"] == "product:pro-pack"
    assert _features(env) == ({"on": True} if (activates or invited) else {"on": False})
