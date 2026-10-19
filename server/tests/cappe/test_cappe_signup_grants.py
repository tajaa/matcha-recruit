"""Signup grants: a link that starts a new account on a paid plan, free for a
number of days, with no card.

No database: the service and routes run against fake connections, with the
comp itself (`billing.grant_comp`, covered elsewhere) stubbed.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_signup_grants.py -q
"""
import os
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models.auth import CappeSignup, CappeVerifyRequest  # noqa: E402
from app.cappe.routes import auth  # noqa: E402
from app.cappe.services import signup_grants  # noqa: E402

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
TOKEN = "a" * 32


def _grant(**over):
    row = {
        "id": uuid.uuid4(), "token": TOKEN, "plan_code": "business", "plan_name": "Business",
        "days": 30, "max_redemptions": 1, "redeemed_count": 0, "email": None,
        "note": None, "expires_at": None, "revoked_at": None,
    }
    row.update(over)
    return row


# ── unusable_reason ──────────────────────────────────────────────────────────

def test_a_fresh_grant_is_usable():
    assert signup_grants.unusable_reason(_grant(), now=NOW, email="new@example.com") is None


@pytest.mark.parametrize("grant,needle", [
    (None, "no longer valid"),
    (_grant(revoked_at=NOW), "no longer valid"),
    (_grant(expires_at=NOW), "expired"),
    (_grant(redeemed_count=1), "already been used"),
])
def test_unusable_grants_say_why(grant, needle):
    assert needle in signup_grants.unusable_reason(grant, now=NOW)


def test_a_grant_for_one_address_refuses_another_but_matches_case_insensitively():
    locked = _grant(email="owner@example.com")
    assert "different email" in signup_grants.unusable_reason(locked, now=NOW, email="x@example.com")
    assert signup_grants.unusable_reason(locked, now=NOW, email="Owner@Example.com") is None
    # The signup page asks before an address is typed: no email, no verdict on it.
    assert signup_grants.unusable_reason(locked, now=NOW) is None


def test_links_are_long_random_and_point_at_signup():
    token = signup_grants.new_token()
    assert len(token) == 32 and token != signup_grants.new_token()
    assert signup_grants.signup_url(token).endswith(f"/cappe/signup?grant={token}")


# ── redeem ───────────────────────────────────────────────────────────────────

class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _RedeemConn:
    def __init__(self, account, grant):
        self.account = account
        self.grant = grant
        self.executed = []
        self.selects = []

    def transaction(self):
        return _Tx()

    async def fetchrow(self, sql, *args):
        self.selects.append(sql)
        return self.account if "FROM cappe_accounts" in sql else self.grant

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


@pytest.fixture
def comps(monkeypatch):
    given = []

    async def _grant_comp(conn, **kwargs):
        given.append(kwargs)

    monkeypatch.setattr(signup_grants.billing, "grant_comp", _grant_comp)
    return given


def _account(**over):
    row = {
        "email": "new@example.com", "created_at": NOW - timedelta(hours=1),
        "signup_grant_id": uuid.uuid4(), "signup_grant_redeemed_at": None,
    }
    row.update(over)
    return row


@pytest.mark.asyncio
async def test_redeem_gives_the_plan_as_a_comp_that_ends_after_its_days(comps):
    grant = _grant(note="Launch partner")
    conn = _RedeemConn(_account(), grant)
    account_id = uuid.uuid4()
    result = await signup_grants.redeem(conn, account_id=account_id)

    [comp] = comps
    assert comp["account_id"] == account_id and comp["plan_code"] == "business"
    assert comp["reason"] == "Signup grant: Launch partner"
    days = (comp["until"] - datetime.now(timezone.utc)).total_seconds() / 86400
    assert 29.99 < days <= 30
    assert result == {"plan_code": "business", "plan_name": "Business", "until": comp["until"]}
    # Both rows are locked, account first, so racing confirmations give it once.
    assert "FOR UPDATE" in conn.selects[0] and "FOR UPDATE OF g" in conn.selects[1]
    [(count_sql, count_args), (stamp_sql, stamp_args)] = conn.executed
    assert "redeemed_count = redeemed_count + 1" in count_sql and count_args == (grant["id"],)
    assert "signup_grant_redeemed_at = $2" in stamp_sql and stamp_args[0] == account_id


@pytest.mark.asyncio
@pytest.mark.parametrize("account", [
    None,
    _account(signup_grant_id=None),
    _account(signup_grant_redeemed_at=NOW),
])
async def test_redeem_gives_nothing_without_an_unredeemed_grant(comps, account):
    conn = _RedeemConn(account, _grant())
    assert await signup_grants.redeem(conn, account_id=uuid.uuid4()) is None
    assert comps == [] and conn.executed == []


@pytest.mark.asyncio
async def test_a_used_up_or_revoked_grant_is_not_given_and_not_stamped(comps):
    for grant in (_grant(redeemed_count=1), _grant(revoked_at=NOW)):
        conn = _RedeemConn(_account(), grant)
        assert await signup_grants.redeem(conn, account_id=uuid.uuid4()) is None
        assert conn.executed == []
    assert comps == []


@pytest.mark.asyncio
async def test_expiry_is_judged_at_signup_not_at_confirmation(comps):
    """The link was used while it worked; reading the email a day late keeps it."""
    expired_since = _grant(expires_at=NOW - timedelta(minutes=30))
    signed_up_before = _account(created_at=NOW - timedelta(hours=2))
    assert await signup_grants.redeem(_RedeemConn(signed_up_before, expired_since), account_id=uuid.uuid4())
    signed_up_after = _account(created_at=NOW)
    assert await signup_grants.redeem(_RedeemConn(signed_up_after, expired_since), account_id=uuid.uuid4()) is None


# ── signup / verify / lookup ─────────────────────────────────────────────────

class _ConnCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _SignupConn:
    def __init__(self, verify_row=None):
        self.inserted = None
        self.executed = []
        self.verify_row = verify_row

    async def fetchrow(self, sql, *args):
        if "INSERT INTO cappe_accounts" in sql:
            self.inserted = args
            return {"id": uuid.uuid4(), "email": args[0], "name": args[2], "plan": "free",
                    "status": "active", "account_type": args[3]}
        return self.verify_row

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


@pytest.fixture
def wired(monkeypatch):
    state = {"grant": _grant(), "redeemed": [], "redeem_result": None}

    async def _no_limit(*_args, **_kwargs):
        return None

    async def _find(_conn, token):
        state["looked_up"] = token
        return state["grant"]

    async def _redeem(_conn, *, account_id):
        state["redeemed"].append(account_id)
        if isinstance(state["redeem_result"], Exception):
            raise state["redeem_result"]
        return state["redeem_result"]

    monkeypatch.setattr(auth, "check_rate_limit", _no_limit)
    monkeypatch.setattr(auth, "client_ip", lambda _request: "203.0.113.7")
    monkeypatch.setattr(auth, "hash_password", lambda _pw: "hashed")
    monkeypatch.setattr(auth, "_is_reserved_test_domain", lambda _email: False)
    monkeypatch.setattr(signup_grants, "find", _find)
    monkeypatch.setattr(signup_grants, "redeem", _redeem)

    def use(conn):
        monkeypatch.setattr(auth, "get_connection", lambda: _ConnCtx(conn))

    state["use"] = use
    return state


def _signup_body(**over):
    fields = dict(email="new@example.com", password="correct horse", name=None,
                  account_type="business", intended_plan=None, intended_interval=None,
                  grant_token=TOKEN)
    fields.update(over)
    return CappeSignup.model_construct(**fields)


@pytest.mark.asyncio
async def test_signup_through_a_grant_parks_it_and_skips_checkout(wired):
    conn = _SignupConn()
    wired["use"](conn)
    res = await auth.signup(_signup_body(intended_plan="creator", intended_interval="year"),
                            request=None, background=BackgroundTasks())

    assert res.verification_required is True
    assert conn.inserted[6:9] == (None, None, wired["grant"]["id"])
    assert wired["looked_up"] == TOKEN
    # Given at confirmation, not before.
    assert wired["redeemed"] == []


@pytest.mark.asyncio
async def test_signup_with_an_unusable_grant_is_refused_before_any_account_exists(wired):
    conn = _SignupConn()
    wired["use"](conn)
    wired["grant"] = _grant(email="someone-else@example.com")
    with pytest.raises(HTTPException) as exc:
        await auth.signup(_signup_body(), request=None, background=BackgroundTasks())
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "grant_invalid"
    assert "different email" in exc.value.detail["message"]
    assert conn.inserted is None


@pytest.mark.asyncio
async def test_an_auto_verified_signup_gets_the_grant_at_once(wired, monkeypatch):
    monkeypatch.setattr(auth, "_is_reserved_test_domain", lambda _email: True)
    wired["redeem_result"] = {"plan_code": "business", "plan_name": "Business", "until": NOW}
    conn = _SignupConn()
    wired["use"](conn)
    res = await auth.signup(_signup_body(email="seed@example.com"), request=None,
                            background=BackgroundTasks())

    assert res.verification_required is False and res.account.plan == "business"
    assert len(wired["redeemed"]) == 1


def _verify_row(**over):
    row = {
        "id": uuid.uuid4(), "email": "new@example.com", "name": None, "plan": "free",
        "status": "active", "account_type": "business",
        "verification_sent_at": datetime.now(timezone.utc),
        "intended_plan_code": "creator", "intended_interval": "month",
        "signup_grant_id": uuid.uuid4(),
    }
    row.update(over)
    return row


@pytest.mark.asyncio
async def test_confirming_gives_the_grant_and_no_checkout(wired):
    until = NOW + timedelta(days=30)
    wired["redeem_result"] = {"plan_code": "business", "plan_name": "Business", "until": until}
    wired["use"](_SignupConn(verify_row=_verify_row()))
    res = await auth.verify_email(CappeVerifyRequest(token=str(uuid.uuid4())), request=None)

    assert (res.granted_plan, res.granted_plan_name, res.granted_until) == ("business", "Business", until)
    assert res.account.plan == "business"
    assert res.intended_plan is None and res.intended_interval is None


@pytest.mark.asyncio
async def test_a_failed_redemption_still_signs_the_person_in(wired):
    """The link is spent by then; failing here would strand them signed out."""
    wired["redeem_result"] = RuntimeError("db hiccup")
    wired["use"](_SignupConn(verify_row=_verify_row()))
    res = await auth.verify_email(CappeVerifyRequest(token=str(uuid.uuid4())), request=None)

    assert res.access_token and res.granted_plan is None
    assert res.intended_plan == "creator"


@pytest.mark.asyncio
async def test_confirming_without_a_grant_never_tries_to_redeem(wired):
    wired["use"](_SignupConn(verify_row=_verify_row(signup_grant_id=None)))
    res = await auth.verify_email(CappeVerifyRequest(token=str(uuid.uuid4())), request=None)
    assert wired["redeemed"] == [] and res.intended_plan == "creator"


@pytest.mark.asyncio
async def test_the_signup_page_can_read_what_a_link_offers(wired):
    wired["grant"] = _grant(days=14, email="owner@example.com")
    wired["use"](_SignupConn())
    info = await auth.signup_grant_info(request=None, token=TOKEN)
    assert info.model_dump() == {
        "plan_code": "business", "plan_name": "Business", "days": 14, "email_locked": True,
    }


@pytest.mark.asyncio
async def test_a_dead_link_reads_as_404_with_the_reason(wired):
    wired["grant"] = _grant(redeemed_count=1)
    wired["use"](_SignupConn())
    with pytest.raises(HTTPException) as exc:
        await auth.signup_grant_info(request=None, token=TOKEN)
    assert exc.value.status_code == 404 and "already been used" in exc.value.detail["message"]


@pytest.mark.parametrize("token", ["short", "has spaces in it at all", "x" * 65, "semi;colon" * 2])
def test_signup_rejects_a_malformed_grant_token(token):
    with pytest.raises(ValidationError):
        CappeSignup(email="new@example.com", password="correct horse", grant_token=token)


def test_dev_refreshes_scrub_grant_tokens_and_emails():
    root = pathlib.Path(__file__).resolve().parents[3]
    sql = (root / "scripts" / "sql" / "anonymize_dev.sql").read_text()
    assert "UPDATE cappe_signup_grants SET" in sql and "token = replace(gen_random_uuid()" in sql
    assert "FROM cappe_signup_grants WHERE (email IS NOT NULL" in (
        root / "scripts" / "refresh-dev-from-prod.sh").read_text()


# ── subscribing before the free days run out ─────────────────────────────────

from app.cappe.services import billing as billing_svc  # noqa: E402
from app.cappe.services import stripe_connect  # noqa: E402


def _comp(until):
    return {"source": "comp", "comped_until": until, "plan_code": "business"}


def test_a_comp_with_days_left_bills_from_its_end():
    until = NOW + timedelta(days=10)
    assert billing_svc.comp_trial_end(_comp(until), now=NOW) == until


@pytest.mark.parametrize("subscription", [
    None,
    {"source": "stripe", "comped_until": None},
    _comp(None),                        # no end date: nothing to wait for
    _comp(NOW + timedelta(hours=30)),   # too soon for Stripe to take as a trial
])
def test_otherwise_billing_starts_at_checkout(subscription):
    assert billing_svc.comp_trial_end(subscription, now=NOW) is None


class _FakeStripeModule:
    def __init__(self):
        self.created = []
        self.checkout = type("checkout", (), {"Session": type("Session", (), {"create": self._create})})

    def _create(self, **kw):
        self.created.append(kw)
        return {"id": "cs_1", "url": "https://pay"}


def _subscription_checkout(monkeypatch, **kw):
    fake = _FakeStripeModule()
    monkeypatch.setattr(stripe_connect, "stripe", fake)
    client = stripe_connect.CappeStripe.__new__(stripe_connect.CappeStripe)
    client._ensure_key = lambda: None
    import asyncio
    asyncio.run(client.create_subscription_checkout_session(
        customer_id="cus_1", price_id="price_1", success_url="https://s", cancel_url="https://c",
        metadata={}, **kw,
    ))
    return fake.created[0]["subscription_data"]


def test_stripe_is_given_the_comps_end_as_the_trial_end_and_no_intro(monkeypatch):
    until = NOW + timedelta(days=10)
    data = _subscription_checkout(monkeypatch, trial_end=until, intro_price_id="price_intro", trial_days=30)
    assert data["trial_end"] == int(until.timestamp())
    assert "trial_period_days" not in data and "add_invoice_items" not in data
    assert data["trial_settings"] == {"end_behavior": {"missing_payment_method": "cancel"}}


def test_the_intro_trial_is_unchanged_without_a_comp(monkeypatch):
    data = _subscription_checkout(monkeypatch, intro_price_id="price_intro", trial_days=30)
    assert data["trial_period_days"] == 30 and "trial_end" not in data


@pytest.mark.asyncio
async def test_checkout_during_a_comp_keeps_its_free_days(monkeypatch):
    from unittest.mock import AsyncMock

    from app.cappe.models.cappe import CappeAccount, CappePlanCheckoutRequest
    from app.cappe.routes import billing as billing_routes

    class _ProductConn:
        async def fetchrow(self, sql, *args):
            return {"code": "business", "name": "Business", "status": "active", "kind": "plan"}

    until = datetime.now(timezone.utc) + timedelta(days=12)
    stripe_client = AsyncMock()
    stripe_client.create_subscription_checkout_session = AsyncMock(return_value={"url": "https://pay"})
    intro_eligible = AsyncMock(return_value=True)
    monkeypatch.setattr(billing_routes, "get_connection", lambda: _ConnCtx(_ProductConn()))
    monkeypatch.setattr(billing_routes, "get_cappe_stripe", lambda: stripe_client)
    monkeypatch.setattr(billing_svc, "current_subscription", AsyncMock(return_value=_comp(until)))
    monkeypatch.setattr(billing_svc, "resolve_price", AsyncMock(return_value={"stripe_price_id": "price_1"}))
    monkeypatch.setattr(billing_svc, "intro_eligible", intro_eligible)
    monkeypatch.setattr(billing_svc, "get_or_create_customer", AsyncMock(return_value="cus_1"))

    account = CappeAccount(id=uuid.uuid4(), email="new@example.com", plan="business")
    res = await billing_routes.start_checkout(
        CappePlanCheckoutRequest(
            plan_code="business", interval="month",
            success_url="https://gummfit.com/cappe/billing", cancel_url="https://gummfit.com/cappe/billing",
        ),
        account=account,
    )

    assert res.checkout_url == "https://pay" and res.intro_applied is False
    kwargs = stripe_client.create_subscription_checkout_session.call_args.kwargs
    assert kwargs["trial_end"] == until and kwargs["intro_price_id"] is None
    intro_eligible.assert_not_awaited()
