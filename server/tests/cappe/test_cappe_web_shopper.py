"""Shopper accounts and subscribing on the web — the 2026-10 commerce readiness review, PR 8.

Sign-in and subscriptions existed only in the iOS app. What each block pins:

  * the web session: the refresh token only ever in a host-only, HttpOnly,
    Secure, SameSite=Strict `__Host-` cookie — never in a response body —
    and every cookie endpoint behind the `X-Cappe-Web` header;
  * refresh rotates the cookie, and a dead session clears it;
  * signing out on the web ends THAT session only (the app's logout ends
    every session and device);
  * the card-update portal on the store's own Stripe account, set up once;
  * the `/account` page, the "Subscribe" button and when the store offers it;
  * subscription emails link to the account page.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_web_shopper.py -q
"""
import asyncio
import os
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.cappe.models.shopper import ShopperVerify  # noqa: E402
from app.cappe.routes import render as render_mod  # noqa: E402
from app.cappe.routes.public import shop as public_shop  # noqa: E402
from app.cappe.routes.public import shopper_web as web  # noqa: E402
from app.cappe.services import email as mail  # noqa: E402
from app.cappe.services import recurring  # noqa: E402
from app.cappe.services.render import account_page  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402

SITE = {"id": uuid4(), "account_id": uuid4(), "slug": "lumiere", "subdomain": "lumiere", "custom_domain": None,
        "name": "Lumière"}
SID, SHOPPER_ID = uuid4(), uuid4()
ASSETS = pathlib.Path(account_page.__file__).parent / "assets"
MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "zzzzcappe46_web_shopper.py"


def _request(headers=None, cookies=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        raw.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw, "client": ("127.0.0.1", 1)})


WEB = {"X-Cappe-Web": "1"}


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Conn:
    def __init__(self, answers=()):
        self.answers, self.calls = list(answers), []

    def _answer(self, sql, args):
        self.calls.append((sql, args))
        for needle, value in self.answers:
            if needle in sql:
                return value
        return None

    async def fetchrow(self, sql, *args):
        return self._answer(sql, args)

    async def fetchval(self, sql, *args):
        return self._answer(sql, args)

    async def execute(self, sql, *args):
        self._answer(sql, args)

    def transaction(self):
        return Ctx(self)


SESSION = {"access_token": "acc", "refresh_token": "ref-1", "token_type": "bearer", "expires_in": 900,
           "shopper": {"id": str(SHOPPER_ID), "email": "b@example.com"}}


def _wire(monkeypatch, conn=None):
    conn = conn or Conn()
    monkeypatch.setattr(web, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(web, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(web.auth, "published_shopper_site", AsyncMock(return_value=SITE))
    return conn


def _cookie(response: Response) -> str:
    (header,) = response.headers.getlist("set-cookie")
    return header


# ── signing in ───────────────────────────────────────────────────────────────

def test_a_cookie_endpoint_needs_the_web_header(monkeypatch):
    _wire(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(web.web_verify("lumiere", ShopperVerify(email="b@example.com", code="123456"), _request(), Response()))
    assert exc.value.status_code == 403


def test_signing_in_puts_the_refresh_token_in_a_locked_down_cookie_only(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(web.auth, "verify_login_code", AsyncMock(return_value=dict(SESSION)))
    response = Response()
    out = asyncio.run(web.web_verify("lumiere", ShopperVerify(email="b@example.com", code="123456"),
                                     _request(WEB), response))
    assert out["access_token"] == "acc" and "refresh_token" not in out
    cookie = _cookie(response)
    assert cookie.startswith("__Host-cz_shopper=ref-1;")
    for flag in ("HttpOnly", "Secure", "Path=/", "SameSite=strict"):
        assert flag in cookie
    assert "Domain" not in cookie                       # host-only: the `__Host-` rule


def test_a_wrong_code_is_401_and_sets_nothing(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(web.auth, "verify_login_code", AsyncMock(return_value=None))
    response = Response()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(web.web_verify("lumiere", ShopperVerify(email="b@example.com", code="000000"),
                                   _request(WEB), response))
    assert exc.value.status_code == 401 and not response.headers.getlist("set-cookie")


# ── staying signed in ────────────────────────────────────────────────────────

def test_refresh_rotates_the_cookie_and_hands_back_an_access_token(monkeypatch):
    _wire(monkeypatch)
    shopper = {"id": SHOPPER_ID, "email": "b@example.com", "site_id": SITE["id"]}
    resolve = AsyncMock(return_value=(shopper, {"sid": str(SID), "session_started_at": 1}))
    monkeypatch.setattr(web.auth, "resolve_shopper", resolve)
    monkeypatch.setattr(web.auth, "issue_session", AsyncMock(return_value={**SESSION, "refresh_token": "ref-2"}))
    response = Response()
    out = asyncio.run(web.web_refresh("lumiere", _request(WEB, {web.COOKIE: "ref-1"}), response))
    assert out["access_token"] == "acc" and "refresh_token" not in out
    assert _cookie(response).startswith("__Host-cz_shopper=ref-2;")
    assert resolve.await_args.args[2:] == ("ref-1", "refresh")


def test_refresh_without_a_cookie_is_401(monkeypatch):
    _wire(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(web.web_refresh("lumiere", _request(WEB), Response()))
    assert exc.value.status_code == 401


def test_a_dead_session_is_401_and_clears_the_cookie(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(web.auth, "resolve_shopper", AsyncMock(side_effect=HTTPException(401, "Shopper session expired")))
    response = Response()
    out = asyncio.run(web.web_refresh("lumiere", _request(WEB, {web.COOKIE: "old"}), response))
    assert response.status_code == 401 and out == {"detail": "Shopper session expired"}
    cookie = _cookie(response)
    assert cookie.startswith('__Host-cz_shopper="";') and "Max-Age=0" in cookie


def test_a_store_that_turned_accounts_off_is_not_a_signed_out_shopper(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(web.auth, "published_shopper_site", AsyncMock(side_effect=HTTPException(402, "off")))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(web.web_refresh("lumiere", _request(WEB, {web.COOKIE: "ref"}), Response()))
    assert exc.value.status_code == 402


# ── signing out ──────────────────────────────────────────────────────────────

def test_signing_out_on_the_web_ends_this_session_only(monkeypatch):
    conn = _wire(monkeypatch)
    monkeypatch.setattr(web.auth, "token_helpers", lambda: SimpleNamespace(
        decode_token=lambda token, kind: {"sid": str(SID), "sub": str(SHOPPER_ID)}))
    out = asyncio.run(web.web_logout("lumiere", _request(WEB, {web.COOKIE: "ref"})))
    assert out.status_code == 204 and "Max-Age=0" in out.headers["set-cookie"]
    ((sql, args),) = conn.calls
    assert sql.startswith("DELETE FROM cappe_shopper_sessions WHERE id = $1") and args == (SID, SHOPPER_ID)
    # Not the app's sign-out: no other session, no device, no token revocation.
    assert "tokens_valid_after" not in sql and "devices" not in sql


@pytest.mark.parametrize("cookies,payload", [({}, None), ({web.COOKIE: "junk"}, None)])
def test_signing_out_without_a_live_cookie_still_clears_it(monkeypatch, cookies, payload):
    conn = _wire(monkeypatch)
    monkeypatch.setattr(web.auth, "token_helpers", lambda: SimpleNamespace(decode_token=lambda *a: payload))
    out = asyncio.run(web.web_logout("lumiere", _request(WEB, cookies)))
    assert out.status_code == 204 and conn.calls == []


# ── updating the card ────────────────────────────────────────────────────────

def _portal(monkeypatch, *, shopper=None, owner=None, stripe=None):
    conn = Conn([("FROM cappe_accounts", owner if owner is not None else
                  {"id": SITE["account_id"], "stripe_account_id": "acct_1", "stripe_portal_config_id": None})])
    monkeypatch.setattr(web, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(web, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(web, "site_origins", lambda _site: ["https://lumiere.gummfit.com"])
    stripe = stripe or SimpleNamespace(
        create_portal_configuration=AsyncMock(return_value="bpc_1"),
        create_connected_portal_session=AsyncMock(return_value={"url": "https://billing.stripe.test/s"}),
    )
    monkeypatch.setattr(web, "get_cappe_stripe", lambda: stripe)
    shopper = shopper if shopper is not None else {"id": SHOPPER_ID, "stripe_customer_id": "cus_1"}
    return conn, stripe, (SITE, shopper)


def _go_portal(context, url="https://lumiere.gummfit.com/account"):
    return asyncio.run(web.billing_portal(web.PortalRequest(return_url=url), _request(), context))


def test_the_card_portal_is_set_up_once_on_the_stores_account(monkeypatch):
    conn, stripe, context = _portal(monkeypatch)
    assert _go_portal(context) == {"url": "https://billing.stripe.test/s"}
    stripe.create_portal_configuration.assert_awaited_once_with("acct_1")
    kw = stripe.create_connected_portal_session.await_args.kwargs
    assert kw == {"account_id": "acct_1", "customer_id": "cus_1",
                  "return_url": "https://lumiere.gummfit.com/account", "configuration_id": "bpc_1"}
    assert any("SET stripe_portal_config_id" in sql for sql, _a in conn.calls)


def test_an_existing_portal_setup_is_reused(monkeypatch):
    _conn, stripe, context = _portal(monkeypatch, owner={"id": SITE["account_id"], "stripe_account_id": "acct_1",
                                                         "stripe_portal_config_id": "bpc_old"})
    _go_portal(context)
    stripe.create_portal_configuration.assert_not_awaited()
    assert stripe.create_connected_portal_session.await_args.kwargs["configuration_id"] == "bpc_old"


@pytest.mark.parametrize("kw,url,code", [
    ({}, "https://evil.example.com/account", 422),
    ({"shopper": {"id": SHOPPER_ID, "stripe_customer_id": None}}, None, 409),
    ({"owner": {"id": SITE["account_id"], "stripe_account_id": None, "stripe_portal_config_id": None}}, None, 409),
])
def test_the_card_portal_refuses_what_it_cant_do(monkeypatch, kw, url, code):
    _conn, _stripe, context = _portal(monkeypatch, **kw)
    with pytest.raises(HTTPException) as exc:
        _go_portal(context, url or "https://lumiere.gummfit.com/account")
    assert exc.value.status_code == code


def test_a_stripe_failure_opening_the_portal_is_502(monkeypatch):
    stripe = SimpleNamespace(create_portal_configuration=AsyncMock(side_effect=CappeStripeError("down")),
                             create_connected_portal_session=AsyncMock())
    _conn, _stripe, context = _portal(monkeypatch, stripe=stripe)
    with pytest.raises(HTTPException) as exc:
        _go_portal(context)
    assert exc.value.status_code == 502


# ── the account page ─────────────────────────────────────────────────────────

def test_the_account_page_is_a_shell_that_never_holds_a_secret():
    html = account_page.render_account_page({"id": SITE["id"], "name": "Lumière", "theme_config": {}, "meta_config": {}}, [])
    assert "data-czaccount" in html and 'name="robots" content="noindex,nofollow"' in html
    js = (ASSETS / "account.js").read_text()
    # The refresh token is the cookie's; the page never sees or stores it.
    assert "refresh_token" not in js and "localStorage" not in js and "sessionStorage" not in js
    assert "'X-Cappe-Web':'1'" in js and "credentials:'same-origin'" in js
    assert "/web/refresh" in js and "/web/logout" in js and "/me/billing-portal" in js


def test_the_account_page_route_serves_tenant_hosts_without_caching(monkeypatch):
    conn = Conn()

    async def _fetch(sql, *args):
        return [{"title": "Shop", "slug": "shop"}]

    conn.fetch = _fetch
    monkeypatch.setattr(render_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(render_mod, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(render_mod, "_resolve_site_any_status", AsyncMock(return_value={
        "id": SITE["id"], "name": "Lumière", "timezone": "UTC", "theme_config": "{}", "meta_config": "{}",
        "slug": "lumiere", "subdomain": "lumiere", "custom_domain": None, "status": "draft"}))
    resp = asyncio.run(render_mod.account_page(_request({"host": "lumiere.gummfit.com"})))
    assert resp.status_code == 200 and b"data-czaccount" in resp.body
    assert resp.headers["cache-control"] == "no-store" and resp.headers["referrer-policy"] == "no-referrer"
    # An unpublished store still serves it: a shopper must be able to cancel.
    monkeypatch.setattr(render_mod, "_resolve_site_any_status", AsyncMock(return_value=None))
    gone = asyncio.run(render_mod.account_page(_request({"host": "lumiere.gummfit.com"})))
    assert b"Site not found" in gone.body


# ── "Subscribe" ──────────────────────────────────────────────────────────────

def test_the_product_panel_sends_a_subscriber_to_the_account_page():
    js = (ASSETS / "store.js").read_text()
    assert "window.location='/account?subscribe='" in js and "data-sub" in js
    assert "if(!iv.length||RT.preview)return '';" in js


@pytest.mark.parametrize("owner,features,expected", [
    ({"plan": "business", "status": "active", "stripe_account_id": "acct", "stripe_charges_enabled": True},
     {"recurring_orders", "shopper_accounts"}, True),
    ({"plan": "business", "status": "active", "stripe_account_id": None, "stripe_charges_enabled": False},
     {"recurring_orders", "shopper_accounts"}, False),
    ({"plan": "creator", "status": "active", "stripe_account_id": "acct", "stripe_charges_enabled": True},
     {"recurring_orders"}, False),
    ({"plan": "business", "status": "suspended", "stripe_account_id": "acct", "stripe_charges_enabled": True},
     {"recurring_orders", "shopper_accounts"}, False),
    (None, set(), False),
])
def test_subscribe_is_offered_only_where_it_can_be_completed(monkeypatch, owner, features, expected):
    monkeypatch.setattr(public_shop, "resolve_entitlements",
                        AsyncMock(return_value=SimpleNamespace(has=lambda f: f in features)))
    assert asyncio.run(public_shop._sells_subscriptions(Conn([("FROM cappe_sites", owner)]), SITE["id"])) is expected


def test_the_product_list_drops_subscribe_options_a_store_cant_fulfil(monkeypatch):
    row = {"id": uuid4(), "subscription_intervals": ["month"], "subscription_discount_bps": 1000,
           "price_cents": 1000, "intake_fields": "[]"}
    conn = Conn([("SELECT NOW()", None)])

    async def _fetch(sql, *args):
        return [row]

    conn.fetch = _fetch
    monkeypatch.setattr(public_shop, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(public_shop, "_read_rate_limit", AsyncMock())
    monkeypatch.setattr(public_shop, "_published_site", AsyncMock(return_value={"id": SITE["id"], "timezone": "UTC"}))
    monkeypatch.setattr(public_shop, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(public_shop, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(public_shop, "site_today", lambda *_a: None)
    monkeypatch.setattr(public_shop, "_sells_subscriptions", AsyncMock(return_value=False))
    (out,) = asyncio.run(public_shop.public_products("lumiere", _request()))
    assert out["subscription_intervals"] == [] and out["subscription_discount_bps"] == 0
    monkeypatch.setattr(public_shop, "_sells_subscriptions", AsyncMock(return_value=True))
    (out,) = asyncio.run(public_shop.public_products("lumiere", _request()))
    assert out["subscription_intervals"] == ["month"]


# ── emails point at the account page ─────────────────────────────────────────

@pytest.mark.parametrize("send,args,label", [
    (mail.send_cappe_subscription_started_email, ("Mug", 1200, "USD", "month"), "Manage your subscription"),
    (mail.send_cappe_subscription_payment_failed_email, ("Mug",), "Update your card"),
])
def test_subscription_emails_link_to_the_account_page(monkeypatch, send, args, label):
    sent = []

    async def _send(to, name, subject, html, text, *, label):
        sent.append((html, text))

    monkeypatch.setattr(mail, "_send", _send)
    asyncio.run(send("b@example.com", "B", "Lumière", *args, "https://lumiere.gummfit.com/account"))
    ((html, text),) = sent
    assert label in html and "https://lumiere.gummfit.com/account" in html and "/account" in text
    sent.clear()
    asyncio.run(send("b@example.com", "B", "Lumière", *args))           # no link: as before
    assert "/account" not in sent[0][0]


def test_the_renewal_worker_builds_the_account_link():
    import inspect
    src = inspect.getsource(recurring._schedule_subscription_emails)
    assert 'account_url = f"{origin}/account" if origin else None' in src


def test_the_migration_chains():
    src = MIGRATION.read_text()
    assert 'down_revision = "zzzzcappe45"' in src and 'revision = "zzzzcappe46"' in src
    assert "stripe_portal_config_id" in src
