"""Paid magazine subscriptions (cappemag05).

What each block pins:

  * Gummfit's share is `magazine_fee_bps` (3000 when the setting is missing,
    unreadable or out of range), never the plan's store fee;
  * checkout: only a live magazine taking subscribers, on a plan with
    `magazine_paid`, with Stripe ready; one monthly line at the magazine's
    price, `kind='magazine'`, the fee percent, `cappe_kind` metadata; a reader
    who already has access is refused, and their unfinished checkouts closed;
  * the webhook: a magazine invoice is a ledger row — never an order, stock
    or receipt — a replay records nothing, and the emails are the magazine's;
  * a refund in Stripe reaches the ledger;
  * paid access is a paying subscription or a live comp;
  * the paid part: 404 unless it's a live paid story, 403 `subscribe`
    without access, otherwise the part after the paywall, `no-store`; a
    sentinel after the paywall is in no page, feed, issue email or JSON;
  * the writer's settings: paid on needs the plan, Stripe and a price; off
    stamps `lapsed_at`; a story is paid only while the magazine takes
    subscribers;
  * the lapse: a magazine whose owner lost the plan stays up for the grace,
    its readers' renewals stop (with an email), Stripe failures retry;
  * readers, comps and earnings for the writer;
  * a writer's plan opens reader sign-in; subscription lists carry `kind`.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_magazine_paid.py -q
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import blog as blog_mod  # noqa: E402
from app.cappe.routes import magazine as magazine_mod  # noqa: E402
from app.cappe.routes import magazine_paid as paid_routes  # noqa: E402
from app.cappe.routes import payments as payments_mod  # noqa: E402
from app.cappe.routes import shopper_subscriptions as sub_routes  # noqa: E402
from app.cappe.routes.public import magazine as public_mag  # noqa: E402
from app.cappe.services import email as mail  # noqa: E402
from app.cappe.services import entitlements as ent_mod  # noqa: E402
from app.cappe.services import recurring  # noqa: E402
from app.cappe.services import shopper_auth  # noqa: E402
from app.cappe.services import stripe_connect  # noqa: E402
from app.cappe.services.common import site_public_origin  # noqa: E402
from app.cappe.services.magazine import access as access_mod  # noqa: E402
from app.cappe.services.magazine import billing  # noqa: E402
from app.cappe.services.magazine import issue_email  # noqa: E402
from app.cappe.services.magazine import lapse  # noqa: E402
from app.cappe.services.magazine import magazines as mags  # noqa: E402
from app.cappe.services.magazine import pages  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeError  # noqa: E402
from app.workers.tasks import cappe_comp_expiry  # noqa: E402
from tests._helpers.routes import QueryConn, Queue, route_client  # noqa: E402

SITE, ACCOUNT_ID, SHOPPER, SUB = uuid4(), uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 21, 9, tzinfo=timezone.utc)
SITE_ROW = {"id": SITE, "name": "Salt & Light", "slug": "salt", "subdomain": "salt", "custom_domain": None,
            "account_id": ACCOUNT_ID, "status": "published", "currency": "USD", "meta_config": "{}",
            "theme_config": "{}", "timezone": "UTC"}
MAG = {"site_id": SITE, "enabled": True, "name": "Salt & Light", "front_at_root": True, "paid_enabled": True,
       "price_cents": 500, "paid_pitch": "Every story, every week.", "preview_blocks": 3, "lapsed_at": None,
       "follow_enabled": True, "masthead_style": "classic", "topics": []}
SHOPPER_ROW = {"id": SHOPPER, "site_id": SITE, "email": "reader@example.com", "name": "Rae"}
ACCOUNT = SimpleNamespace(id=ACCOUNT_ID, plan="writer", account_type="writer", email="ana@example.com", name="Ana")
SENTINEL = "ZXQ-for-subscribers-ZXQ"
ORIGIN = site_public_origin(SITE_ROW)  # https://salt.<the Cappe base domain>


def ent(*features):
    return SimpleNamespace(has=lambda f: f in features, platform_fee_bps=200)


def resolver(*features):
    async def resolve(plan, conn=None):
        return ent(*features)
    return resolve


class Conn(QueryConn):
    """A QueryConn that also hands out transactions, and answers callables."""

    def transaction(self):
        return self

    def _dispatch(self, kind, sql, args):
        value = super()._dispatch(kind, sql, args)
        return value(sql, args) if callable(value) else value


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kw):
        self.tasks.append((fn, args, kw))

    def names(self):
        return [fn.__name__ for fn, _, _ in self.tasks]


async def _noop(*a, **k):
    return None


# ── the fee ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    (None, 3000), ('{"bps": 2500}', 2500), ('{"pct": 10}', 3000), ('"garbage"', 3000), ('{"bps": 9000}', 3000),
])
def test_the_fee_is_the_magazine_setting_never_the_plan_fee(raw, expected):
    conn = Conn(fetchval={"FROM cappe_marketplace_settings": raw})
    assert asyncio.run(billing.fee_bps(conn)) == expected


# ── checkout ─────────────────────────────────────────────────────────────────

class FakeStripe:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    async def create_subscription_checkout(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise CappeStripeError("down")
        return {"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"}


def _checkout(monkeypatch, *, mag=MAG, features=("magazine", "magazine_paid"), owner=None, access=False,
              stale=(), stripe=None):
    owner = owner if owner is not None else {"stripe_account_id": "acct_w", "stripe_charges_enabled": True,
                                             "plan": "writer"}
    inserted = {"id": SUB, "site_id": SITE, "checkout_token": "tok"}
    conn = Conn(
        fetchrow={"FROM cappe_accounts": owner, "FROM cappe_shoppers": {"deleting": False},
                  "INSERT INTO cappe_shopper_subscriptions": inserted},
        fetchval={"FROM cappe_marketplace_settings": None},
        fetch={"FROM cappe_shopper_subscriptions": list(stale)},
    )
    stripe = stripe or FakeStripe()
    closed, attached = [], []

    async def live(c, site):
        return mag

    async def has_access(c, site_id, shopper_id):
        return access

    async def change(row, cancel, **kw):
        closed.append(row["id"])

    async def attach(row, shopper, session_id):
        attached.append(session_id)
        return True

    monkeypatch.setattr(billing, "get_connection", lambda: conn)
    monkeypatch.setattr(billing, "live_magazine", live)
    monkeypatch.setattr(billing, "has_paid_access", has_access)
    monkeypatch.setattr(billing, "resolve_entitlements", resolver(*features))
    monkeypatch.setattr(billing, "connected_customer", lambda *a: _value("cus_1"))
    monkeypatch.setattr(billing, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(recurring, "change_subscription", change)
    monkeypatch.setattr(recurring, "_attach_checkout_session", attach)
    return conn, stripe, closed, attached


async def _value(v):
    return v


BODY = SimpleNamespace(success_url=f"{ORIGIN}/stories/x?subscribed=1", cancel_url=f"{ORIGIN}/stories/x")


def _run_checkout(body=BODY):
    return asyncio.run(billing.checkout(SITE_ROW, SHOPPER_ROW, body))


def test_checkout_opens_a_monthly_magazine_subscription_at_thirty_percent(monkeypatch):
    stale = [{"id": uuid4(), "status": "incomplete"}]
    conn, stripe, closed, attached = _checkout(monkeypatch, stale=stale)
    out = _run_checkout()
    assert out == {"checkout_url": "https://checkout.stripe.test/cs_1", "subscription_id": str(SUB)}
    args = conn.args_for("INSERT INTO cappe_shopper_subscriptions")
    assert "'magazine'" in next(s for s in conn.sql_for("fetchrow") if "INSERT INTO cappe_shopper" in s)
    assert 500 in args and "USD" in args and json.loads(args[3]) == [
        {"title": "Salt & Light subscription", "quantity": 1, "unit_price_cents": 500, "fulfillment": "magazine"}]
    call = stripe.calls[0]
    assert call["application_fee_percent"] == 30.0          # not the plan's 2%
    assert call["metadata"] == {"cappe_shopper_subscription_id": str(SUB), "site_id": str(SITE),
                                "cappe_kind": "magazine"}
    assert call["idempotency_key"] == f"mag-sub:{SUB}" and call["collect_shipping"] is False
    assert call["line_items"] == [{"price_data": {"currency": "usd", "unit_amount": 500, "recurring": {"interval": "month"},
                                                  "product_data": {"name": "Salt & Light subscription"}}, "quantity": 1}]
    assert closed == [stale[0]["id"]] and attached == ["cs_1"]


@pytest.mark.parametrize("kw,code", [
    ({"mag": None}, 409),
    ({"mag": {**MAG, "paid_enabled": False}}, 409),
    ({"features": ("magazine",)}, 402),
    ({"owner": {"stripe_account_id": None, "stripe_charges_enabled": False, "plan": "writer"}}, 409),
    ({"access": True}, 409),
])
def test_checkout_refuses(monkeypatch, kw, code):
    _conn, stripe, _closed, _attached = _checkout(monkeypatch, **kw)
    with pytest.raises(HTTPException) as err:
        _run_checkout()
    assert err.value.status_code == code and stripe.calls == []


def test_checkout_returns_must_be_the_magazines_own(monkeypatch):
    _checkout(monkeypatch)
    with pytest.raises(HTTPException) as err:
        _run_checkout(SimpleNamespace(success_url="https://evil.test/", cancel_url=f"{ORIGIN}/"))
    assert err.value.status_code == 422


def test_a_stripe_failure_keeps_the_row_and_says_so(monkeypatch):
    _checkout(monkeypatch, stripe=FakeStripe(fail=True))
    with pytest.raises(HTTPException) as err:
        _run_checkout()
    assert err.value.status_code == 503


# ── the webhook ──────────────────────────────────────────────────────────────

class WebhookStripe:
    async def retrieve_connected_subscription(self, account_id, sid):
        return {"id": sid, "status": "active", "cancel_at_period_end": False, "current_period_end": 1_800_000_000,
                "metadata": {"cappe_shopper_subscription_id": str(SUB)}}

    async def connected_invoice_payment_intent(self, account_id, invoice):
        return "pi_1"


def _webhook(monkeypatch, *, recorded):
    row = {"id": SUB, "site_id": SITE, "shopper_id": SHOPPER, "stripe_account_id": "acct_w", "kind": "magazine",
           "stripe_subscription_id": "sub_1", "status": "active", "total_cents": 500, "currency": "USD",
           "interval": "month", "items": json.dumps([{"title": "Salt & Light subscription", "quantity": 1}])}
    conn = Conn(
        fetchrow={"FROM cappe_shopper_subscriptions sub JOIN cappe_sites": row,
                  "SELECT s.name AS site_name": {"site_name": "Salt & Light", "subdomain": "salt", "custom_domain": None,
                                                 "meta_config": "{}", "owner_email": "ana@example.com",
                                                 "owner_name": "Ana", "shopper_email": "reader@example.com",
                                                 "shopper_name": "Rae"}},
        fetchval={"INSERT INTO cappe_magazine_payments": recorded},
    )

    async def no_order(*a, **k):
        raise AssertionError("a magazine invoice must never become an order")

    monkeypatch.setattr(recurring, "get_connection", lambda: conn)
    monkeypatch.setattr(recurring, "get_cappe_stripe", lambda: WebhookStripe())
    monkeypatch.setattr(recurring, "record_invoice_order", no_order)
    return conn


def _invoice(reason):
    return {"id": "in_1", "status": "paid", "billing_reason": reason, "subscription": "sub_1", "amount_paid": 500,
            "application_fee_amount": 150, "currency": "usd", "status_transitions": {"paid_at": 1_790_000_000}}


def test_a_first_invoice_is_a_ledger_row_and_a_welcome(monkeypatch):
    conn = _webhook(monkeypatch, recorded=uuid4())
    bg = Background()
    out = asyncio.run(recurring.handle_event("invoice.paid", _invoice("subscription_create"),
                                             {"account": "acct_w", "created": 1_790_000_000}, bg))
    assert out == {"received": True}
    args = conn.args_for("INSERT INTO cappe_magazine_payments")
    assert args[:8] == (SITE, SUB, SHOPPER, "acct_w", "in_1", "pi_1", 500, 150)
    assert args[8:10] == ("USD", "subscription_create") and args[10] == datetime.fromtimestamp(1_790_000_000, timezone.utc)
    assert sorted(bg.names()) == ["send_cappe_magazine_new_reader_email", "send_cappe_magazine_welcome_email"]
    welcome = next(t for t in bg.tasks if t[0].__name__ == "send_cappe_magazine_welcome_email")
    assert welcome[1][3] == "Salt & Light subscription" and welcome[1][6] == ORIGIN


def test_a_renewal_or_a_replay_emails_nobody(monkeypatch):
    _webhook(monkeypatch, recorded=uuid4())
    bg = Background()
    asyncio.run(recurring.handle_event("invoice.paid", _invoice("subscription_cycle"), {"account": "acct_w"}, bg))
    assert bg.tasks == []
    _webhook(monkeypatch, recorded=None)  # the invoice was already recorded
    asyncio.run(recurring.handle_event("invoice.paid", _invoice("subscription_create"), {"account": "acct_w"}, bg))
    assert bg.tasks == []


def test_record_magazine_payment_falls_back_to_the_invoice_total():
    conn = Conn(fetchval={"INSERT INTO cappe_magazine_payments": None})
    row = {"id": SUB, "site_id": SITE, "shopper_id": None, "stripe_account_id": "acct_w", "total_cents": 500,
           "currency": "USD"}
    assert asyncio.run(billing.record_magazine_payment(conn, row, {"id": "in_2", "total": 700}, None)) is None
    args = conn.args_for("INSERT INTO cappe_magazine_payments")
    assert args[6] == 700 and args[7] is None and args[8] == "USD"


def test_a_refund_in_stripe_reaches_the_ledger(monkeypatch):
    conn = Conn(fetchval={"UPDATE cappe_magazine_payments": uuid4()})

    async def no_order(*a, **k):
        return None

    monkeypatch.setattr(payments_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(payments_mod, "_order_for_charge", no_order)
    out = asyncio.run(payments_mod._sync_charge_refunded(
        {"payment_intent": "pi_1", "amount": 500, "amount_refunded": 200, "refunded": False},
        {"account": "acct_w"}))
    assert out == {"received": True, "status": "magazine_refund_synced"}
    assert conn.args_for("UPDATE cappe_magazine_payments") == ("acct_w", "pi_1", None, 200)
    assert asyncio.run(billing.sync_refund(conn, account_id="a", payment_intent=None, invoice_id=None,
                                           refunded_cents=5)) is None


# ── access ───────────────────────────────────────────────────────────────────

def test_access_is_a_paying_subscription_or_a_live_comp():
    conn = Conn(fetchval={"FROM cappe_shopper_subscriptions": 1})
    assert asyncio.run(access_mod.has_paid_access(conn, SITE, SHOPPER)) is True
    sql, args = conn.calls[0][1], conn.calls[0][2]
    assert "kind = 'magazine'" in sql and "revoked_at IS NULL" in sql and "expires_at > NOW()" in sql
    assert args[2] == ["active", "trialing", "past_due"]
    none = Conn(fetchrow={"FROM cappe_shopper_subscriptions": None, "FROM cappe_magazine_comps": None})
    assert asyncio.run(access_mod.reader_status(none, SITE, SHOPPER)) == {
        "has_access": False, "subscription": None, "comp": None}
    comp = Conn(fetchrow={"FROM cappe_shopper_subscriptions": None, "FROM cappe_magazine_comps": {"expires_at": NOW}})
    assert asyncio.run(access_mod.reader_status(comp, SITE, SHOPPER))["comp"] == {"expires_at": NOW}


# ── the paid part ────────────────────────────────────────────────────────────

PAID_POST = {"id": uuid4(), "slug": "low-tide", "title": "Low tide", "access": "paid", "format": "blocks",
             "excerpt": "The water goes out.", "published_at": NOW, "updated_at": NOW, "layout": "standard",
             "content": {"blocks": [{"type": "text", "md": "Free opening.", "dropcap": True},
                                    {"type": "paywall"},
                                    {"type": "text", "md": SENTINEL, "dropcap": True}]}}


def _paid_client(monkeypatch, *, post=PAID_POST, access=True, mag=MAG, site=SITE_ROW):
    async def live(conn, s):
        return mag

    async def story(conn, site_id, slug=None, post_id=None):
        return post

    async def has_access(conn, site_id, shopper_id):
        return access

    async def assets(conn, site_id, p):
        return {}

    monkeypatch.setattr(public_mag, "get_connection", lambda: Conn())
    monkeypatch.setattr(public_mag, "check_rate_limit", _noop)
    monkeypatch.setattr(public_mag, "live_magazine", live)
    monkeypatch.setattr(public_mag, "has_paid_access", has_access)
    monkeypatch.setattr(public_mag.mag_reader, "live_story", story)
    monkeypatch.setattr(public_mag.mag_reader, "story_assets", assets)
    return route_client(public_mag.router, overrides={public_mag.require_shopper_session: (site, SHOPPER_ROW)})


def test_a_subscriber_gets_the_rest_never_cached(monkeypatch):
    with _paid_client(monkeypatch) as client:
        res = client.get("/public/sites/salt/stories/low-tide/paid")
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store, private"
    html = res.json()["html"]
    assert SENTINEL in html and "Free opening." not in html and "mz-dropcap" not in html


def test_without_access_the_answer_is_subscribe(monkeypatch):
    with _paid_client(monkeypatch, access=False) as client:
        res = client.get("/public/sites/salt/stories/low-tide/paid")
    assert res.status_code == 403 and res.json()["detail"]["code"] == "subscribe"


@pytest.mark.parametrize("kw", [{"post": None}, {"post": {**PAID_POST, "access": "free"}}, {"mag": None},
                                {"site": {**SITE_ROW, "status": "draft"}}])
def test_the_paid_part_of_anything_else_is_a_404(monkeypatch, kw):
    with _paid_client(monkeypatch, **kw) as client:
        assert client.get("/public/sites/salt/stories/low-tide/paid").status_code == 404


def test_the_readers_own_status(monkeypatch):
    async def status(conn, site_id, shopper_id):
        return {"has_access": True, "subscription": None, "comp": {"expires_at": NOW}}

    monkeypatch.setattr(public_mag, "reader_status", status)
    with _paid_client(monkeypatch) as client:
        res = client.get("/public/sites/salt/magazine/me")
    assert res.status_code == 200 and res.json()["has_access"] is True
    assert res.headers["cache-control"] == "no-store, private"


def test_checkout_route_is_rate_limited_and_hands_over(monkeypatch):
    limits, seen = [], []

    async def limit(key, bucket, n, window):
        limits.append((bucket, n, window))

    async def start(site, shopper, body):
        seen.append(body.success_url)
        return {"checkout_url": "https://checkout.stripe.test/x", "subscription_id": "s"}

    monkeypatch.setattr(public_mag, "check_rate_limit", limit)
    monkeypatch.setattr(public_mag.mag_billing, "checkout", start)
    with route_client(public_mag.router, overrides={public_mag.require_shopper: (SITE_ROW, SHOPPER_ROW)}) as client:
        res = client.post("/public/sites/salt/magazine/checkout",
                          json={"success_url": "https://salt.gummfit.com/a", "cancel_url": "https://salt.gummfit.com/b"})
    assert res.status_code == 201 and limits == [("cappe_mag_checkout", 10, 3600)] and seen == ["https://salt.gummfit.com/a"]


def test_the_paid_part_is_in_no_page_feed_or_email():
    page = pages.render_story({"name": "Salt", "slug": "salt", "theme_config": {}, "meta_config": {}}, [], MAG,
                              PAID_POST, {}, more=[], more_covers={}, origin="https://salt.gummfit.com",
                              currency="USD")
    assert "Free opening." in page and SENTINEL not in page
    assert "$5 a month. Cancel any time." in page and "Every story, every week." in page
    assert 'data-mz-open="1"' in page and 'data-mz-story="low-tide"' in page
    ld = page[page.index('<script type="application/ld+json">'):]
    ld = ld[:ld.index("</script>")]
    assert '"isAccessibleForFree": false' in ld and '"cssSelector": ".mz-paid"' in ld
    feed = pages.render_feed(MAG, [PAID_POST], {}, origin="https://salt.gummfit.com")
    assert SENTINEL not in feed and "The water goes out." in feed
    _subject, html, text = issue_email.build_issue(site_name="Salt", mag=MAG, post=PAID_POST, assets={},
                                                   origin="https://salt.gummfit.com", include_body=True, subject=None)
    assert SENTINEL not in html and SENTINEL not in text


def test_a_closed_magazine_still_lets_its_readers_sign_in():
    page = pages.paywall_html({**MAG, "paid_enabled": False}, PAID_POST, currency="USD")
    assert 'data-mz-open="0"' in page and "a month. Cancel any time." not in page
    assert pages.price_label(550, "EUR") == "€5.50" and pages.price_label(500, "JPY") == "5 JPY"


# ── the writer's settings ────────────────────────────────────────────────────

def _settings(monkeypatch, *, current=None, features=("magazine", "magazine_paid"), stripe_ready=True):
    saved = []
    conn = Conn(fetchrow={"FROM cappe_accounts": {"stripe_account_id": "acct_w" if stripe_ready else None,
                                                  "stripe_charges_enabled": stripe_ready}},
                fetchval={"FROM cappe_marketplace_settings": None})

    async def owned(c, site_id, account_id):
        return SITE_ROW

    async def get_mag(c, site_id):
        return current

    async def save(c, site_id, fields, default_name):
        saved.append(dict(fields))
        return {**(current or MAG), **fields}

    monkeypatch.setattr(magazine_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(magazine_mod, "get_owned_site", owned)
    monkeypatch.setattr(magazine_mod, "get_magazine", get_mag)
    monkeypatch.setattr(magazine_mod, "save_magazine", save)
    monkeypatch.setattr(magazine_mod, "resolve_entitlements", resolver(*features))
    monkeypatch.setattr(magazine_mod, "invalidate_render_cache", _noop)
    client = route_client(magazine_mod.router, overrides={magazine_mod.require_cappe_account: ACCOUNT})
    return client, saved


def test_turning_paid_on_needs_the_plan_stripe_and_a_price(monkeypatch):
    off = {**MAG, "paid_enabled": False, "price_cents": None, "lapsed_at": NOW}
    client, saved = _settings(monkeypatch, current=off, features=("magazine",))
    with client as c:
        assert c.put(f"/sites/{SITE}/magazine", json={"paid_enabled": True}).status_code == 422  # no price yet
        res = c.put(f"/sites/{SITE}/magazine", json={"paid_enabled": True, "price_cents": 500})
    assert res.status_code == 402 and res.json()["detail"]["code"] == "plan_required" and saved == []
    client, saved = _settings(monkeypatch, current=off, stripe_ready=False)
    with client as c:
        res = c.put(f"/sites/{SITE}/magazine", json={"paid_enabled": True, "price_cents": 500})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "stripe_required"
    client, saved = _settings(monkeypatch, current=off)
    with client as c:
        res = c.put(f"/sites/{SITE}/magazine", json={"paid_enabled": True, "price_cents": 500, "paid_pitch": "  "})
    assert res.status_code == 200, res.text
    assert saved == [{"paid_enabled": True, "price_cents": 500, "paid_pitch": None, "lapsed_at": None}]
    body = res.json()
    assert body["plan_includes_paid"] is True and body["stripe_ready"] is True and body["fee_bps"] == 3000


def test_turning_paid_off_stamps_when(monkeypatch):
    client, saved = _settings(monkeypatch, current=MAG)
    with client as c:
        assert c.put(f"/sites/{SITE}/magazine", json={"paid_enabled": False}).status_code == 200
        assert c.put(f"/sites/{SITE}/magazine", json={"price_cents": None}).status_code == 422
        assert c.put(f"/sites/{SITE}/magazine", json={"preview_blocks": 30}).status_code == 422
    assert saved[0]["paid_enabled"] is False and saved[0]["lapsed_at"] is not None


def test_a_story_is_paid_only_while_the_magazine_takes_subscribers(monkeypatch):
    for paid_on, code in ((False, 422), (True, None)):
        conn = Conn(fetchval={"SELECT paid_enabled FROM cappe_magazines": paid_on})
        if code:
            with pytest.raises(HTTPException) as err:
                asyncio.run(blog_mod._check_paid(conn, SITE, "paid"))
            assert err.value.detail == blog_mod.PAID_OFF
        else:
            asyncio.run(blog_mod._check_paid(conn, SITE, "paid"))
    asyncio.run(blog_mod._check_paid(Conn(), SITE, "free"))  # free asks nothing


# ── the lapse ────────────────────────────────────────────────────────────────

def test_the_grace_keeps_a_lapsed_magazine_up_for_a_month():
    assert mags.in_grace({"lapsed_at": NOW - timedelta(days=10)}, now=NOW) is True
    assert mags.in_grace({"lapsed_at": NOW - timedelta(days=40)}, now=NOW) is False
    assert mags.in_grace({"paid_enabled": True}, now=NOW) is True        # the sweep hasn't run yet
    assert mags.in_grace({"paid_enabled": False}, now=NOW) is False
    assert mags.preview_blocks({"preview_blocks": 5}) == 5 and mags.preview_blocks(None) == 3


def test_live_magazine_without_the_plan_only_in_grace(monkeypatch):
    monkeypatch.setattr(mags, "resolve_entitlements", resolver())
    lapsed = {**MAG, "paid_enabled": False, "lapsed_at": datetime.now(timezone.utc) - timedelta(days=2)}
    for mag, live in ((lapsed, True), ({**lapsed, "lapsed_at": None}, False)):
        conn = Conn(fetchrow={"FROM cappe_magazines": mag}, fetchval={"SELECT plan FROM cappe_accounts": "free"})
        assert (asyncio.run(mags.live_magazine(conn, SITE_ROW)) is not None) is live


def test_mark_lapsed_stops_paid_where_the_owner_cant_have_it(monkeypatch):
    kept, free_site, gone_site = uuid4(), uuid4(), uuid4()
    conn = Conn(fetch={"WHERE m.paid_enabled": [
                    {"site_id": kept, "plan": "writer", "status": "active"},
                    {"site_id": free_site, "plan": "free", "status": "active"},
                    {"site_id": gone_site, "plan": "writer", "status": "suspended"}]},
                fetchval={"UPDATE cappe_magazines SET paid_enabled = false": lambda sql, args: args[0]})

    async def resolve(plan, conn=None):
        return ent("magazine_paid") if plan == "writer" else ent()

    monkeypatch.setattr(lapse, "resolve_entitlements", resolve)
    assert asyncio.run(lapse.mark_lapsed(conn)) == 2
    marked = [args[0] for kind, sql, args in conn.calls if "UPDATE cappe_magazines" in sql]
    assert marked == [free_site, gone_site]


class LapseStripe:
    def __init__(self, fail_for=()):
        self.fail_for = set(fail_for)
        self.calls = []

    async def modify_connected_subscription(self, *, account_id, subscription_id, cancel_at_period_end):
        self.calls.append((subscription_id, cancel_at_period_end))
        if subscription_id in self.fail_for:
            raise CappeStripeError("down")
        return {"id": subscription_id, "status": "active", "cancel_at_period_end": True,
                "current_period_end": 1_800_000_000}


def test_wind_down_ends_renewals_and_tells_each_reader_once(monkeypatch):
    end = NOW + timedelta(days=12)
    subs = [{"id": uuid4(), "stripe_account_id": "acct_w", "stripe_subscription_id": sid, "current_period_end": end,
             "site_name": "Salt & Light", "subdomain": "salt", "custom_domain": None, "meta_config": "{}",
             "owner_email": "ana@example.com", "reader_email": "reader@example.com", "reader_name": "Rae"}
            for sid in ("sub_ok", "sub_down")]
    conn = Conn(fetch={"FROM cappe_shopper_subscriptions sub": subs},
                fetchval={"FOR UPDATE": None})
    stripe = LapseStripe(fail_for={"sub_down"})
    sent = []

    async def ending(*args, **kw):
        sent.append((args, kw))

    monkeypatch.setattr(stripe_connect, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(mail, "send_cappe_magazine_ending_email", ending)
    out = asyncio.run(lapse.wind_down(conn))
    assert out == {"stopped": 1, "failed": 1}
    assert stripe.calls == [("sub_ok", True), ("sub_down", True)]
    assert any("UPDATE cappe_shopper_subscriptions SET stripe_subscription_id" in sql for _, sql, _ in conn.calls)
    assert len(sent) == 1 and sent[0][0][:5] == ("reader@example.com", "Rae", "Salt & Light", end, ORIGIN)
    assert sent[0][1] == {"reply_to": "ana@example.com"}
    query = next(sql for kind, sql, _ in conn.calls if kind == "fetch")
    assert "NOT sub.cancel_at_period_end" in query and "NOT m.paid_enabled" in query


def test_the_comp_sweep_runs_the_lapse_and_survives_its_failure(monkeypatch):
    async def boom(conn):
        raise RuntimeError("stripe exploded")

    monkeypatch.setattr(lapse, "sweep", boom)
    assert asyncio.run(cappe_comp_expiry._magazine_lapse(object())) == {"error": True}

    async def fine(conn):
        return {"marked": 1, "stopped": 2, "failed": 0}

    monkeypatch.setattr(lapse, "sweep", fine)
    assert asyncio.run(cappe_comp_expiry._magazine_lapse(object()))["stopped"] == 2


def test_sweep_logs_what_it_did(monkeypatch):
    async def marked(conn):
        return 1

    async def wound(conn, limit=200):
        return {"stopped": 0, "failed": 0}

    monkeypatch.setattr(lapse, "mark_lapsed", marked)
    monkeypatch.setattr(lapse, "wind_down", wound)
    assert asyncio.run(lapse.sweep(object())) == {"marked": 1, "stopped": 0, "failed": 0}


# ── readers, comps and earnings ──────────────────────────────────────────────

def _owner(monkeypatch, conn, *, features=("magazine", "magazine_paid"), balance=None):
    async def owned(c, site_id, account_id):
        return SITE_ROW

    class Bal:
        async def connected_balance(self, account_id):
            if balance is None:
                raise CappeStripeError("down")
            return balance

    monkeypatch.setattr(paid_routes, "get_connection", lambda: conn)
    monkeypatch.setattr(paid_routes, "get_owned_site", owned)
    monkeypatch.setattr(paid_routes, "resolve_entitlements", resolver(*features))
    monkeypatch.setattr(paid_routes, "check_rate_limit", _noop)
    monkeypatch.setattr(paid_routes, "get_cappe_stripe", lambda: Bal())
    return route_client(paid_routes.router, overrides={paid_routes.require_cappe_account: ACCOUNT})


def test_the_readers_list_skips_abandoned_checkouts(monkeypatch):
    conn = Conn(fetch={"FROM cappe_shopper_subscriptions sub": [{"id": SUB, "status": "active", "email": "r@example.com"}],
                       "FROM cappe_magazine_comps c": [{"id": uuid4(), "email": "c@example.com", "expires_at": None}]})
    with _owner(monkeypatch, conn) as client:
        res = client.get(f"/sites/{SITE}/magazine/readers")
    assert res.status_code == 200 and len(res.json()["subscriptions"]) == 1 and len(res.json()["comps"]) == 1
    assert conn.args_for("FROM cappe_shopper_subscriptions sub")[1] == [
        "preparing", "incomplete", "cancel_requested", "incomplete_expired"]


def test_a_comp_is_given_emailed_and_revoked(monkeypatch):
    comp_id = uuid4()
    conn = Conn(fetchrow={"FROM cappe_magazines": {"name": "Salt & Light", "front_at_root": True},
                          "INSERT INTO cappe_shoppers": {"id": SHOPPER, "deleting": False},
                          "INSERT INTO cappe_magazine_comps": {"id": comp_id, "note": "Press", "expires_at": NOW,
                                                               "created_at": NOW}},
                fetchval={"UPDATE cappe_magazine_comps SET revoked_at": Queue([comp_id, None])})
    sent = []

    async def comp_email(*args, **kw):
        sent.append((args, kw))

    monkeypatch.setattr(mail, "send_cappe_magazine_comp_email", comp_email)
    with _owner(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/magazine/comps", json={"email": "Press@Example.com", "months": 3, "note": " Press "})
        assert res.status_code == 201 and res.json()["email"] == "press@example.com"
        assert client.delete(f"/sites/{SITE}/magazine/comps/{comp_id}").status_code == 204
        assert client.delete(f"/sites/{SITE}/magazine/comps/{comp_id}").status_code == 404
    args = conn.args_for("INSERT INTO cappe_magazine_comps")
    assert args[:3] == (SITE, SHOPPER, "Press") and args[3] > datetime.now(timezone.utc) + timedelta(days=89)
    assert sent[0][0][:2] == ("press@example.com", "Salt & Light") and sent[0][0][3] == f"{ORIGIN}/"


def test_comps_need_the_plan_and_a_reader_not_leaving(monkeypatch):
    with _owner(monkeypatch, Conn(), features=("magazine",)) as client:
        assert client.post(f"/sites/{SITE}/magazine/comps", json={"email": "r@example.com"}).status_code == 402
    conn = Conn(fetchrow={"FROM cappe_magazines": None})
    with _owner(monkeypatch, conn) as client:
        assert client.post(f"/sites/{SITE}/magazine/comps", json={"email": "r@example.com"}).status_code == 409
    conn = Conn(fetchrow={"FROM cappe_magazines": {"name": "S", "front_at_root": False},
                          "INSERT INTO cappe_shoppers": {"id": SHOPPER, "deleting": True}})
    with _owner(monkeypatch, conn) as client:
        assert client.post(f"/sites/{SITE}/magazine/comps", json={"email": "r@example.com"}).status_code == 409


def test_earnings_are_the_ledger_and_the_balance(monkeypatch):
    totals = [{"currency": "USD", "payments": 4, "gross_cents": 2000, "fee_cents": 600, "refunded_cents": 500}]
    conn = Conn(fetch={"GROUP BY currency": totals, "FROM cappe_magazine_payments p": [{"amount_cents": 500}]},
                fetchval={"COUNT(*) FROM cappe_shopper_subscriptions": 3, "FROM cappe_marketplace_settings": None,
                          "SELECT stripe_account_id FROM cappe_accounts": "acct_w"})
    with _owner(monkeypatch, conn, balance={"available": [], "pending": [], "payouts": []}) as client:
        body = client.get(f"/sites/{SITE}/magazine/earnings").json()
    assert body["all_time"][0]["net_cents"] == 900 and body["paying_readers"] == 3 and body["fee_bps"] == 3000
    assert body["balance"] == {"available": [], "pending": [], "payouts": []}
    since = [sql for kind, sql, _ in conn.calls if "GROUP BY currency" in sql]
    assert "interval '30 days'" not in since[0] and "interval '30 days'" in since[1]
    with _owner(monkeypatch, conn) as client:  # Stripe down: the ledger still answers
        assert client.get(f"/sites/{SITE}/magazine/earnings").json()["balance"] is None


# ── sign-in, lists, emails, fallback ─────────────────────────────────────────

def test_a_writers_plan_opens_reader_sign_in(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_sites s": {**SITE_ROW, "owner_plan": "writer"}})
    monkeypatch.setattr(shopper_auth, "resolve_entitlements", resolver("magazine_paid"))
    assert asyncio.run(shopper_auth.published_shopper_site(conn, "salt"))["id"] == SITE
    monkeypatch.setattr(shopper_auth, "resolve_entitlements", resolver("magazine"))
    with pytest.raises(HTTPException) as err:
        asyncio.run(shopper_auth.published_shopper_site(conn, "salt"))
    assert err.value.status_code == 402


def test_subscription_lists_carry_and_filter_kind(monkeypatch):
    conn = Conn(fetch={"FROM cappe_shopper_subscriptions": []})
    monkeypatch.setattr(sub_routes, "get_connection", lambda: conn)
    asyncio.run(sub_routes.list_mine(limit=10, offset=0, include_abandoned=False, kind="magazine",
                                     context=(SITE_ROW, SHOPPER_ROW)))
    sql, args = conn.calls[-1][1], conn.calls[-1][2]
    assert ",kind FROM" in sql and "status <> ALL($5::text[])" in sql and "kind = $6" in sql and args[-1] == "magazine"
    asyncio.run(sub_routes.list_mine(limit=10, offset=0, include_abandoned=True, kind="nonsense",
                                     context=(SITE_ROW, SHOPPER_ROW)))
    assert "kind = $" not in conn.calls[-1][1] and len(conn.calls[-1][2]) == 4
    filt, extra = sub_routes._filters(True, "goods", 4, prefix="sub.")
    assert filt == " AND sub.kind = $4" and extra == ["goods"]


def test_the_magazine_emails(monkeypatch):
    sent = []

    async def capture(to, name, subject, html, text, **kw):
        sent.append((to, subject, html, text, kw))
        return True

    monkeypatch.setattr(mail, "_send", capture)
    asyncio.run(mail.send_cappe_magazine_new_reader_email("ana@example.com", "Ana", "Salt", "r@example.com", 500, "USD",
                                                          "https://hey-matcha.test/cappe/sites/s/readers"))
    asyncio.run(mail.send_cappe_magazine_welcome_email("r@example.com", "Rae", "Salt", "Salt subscription", 500, "USD",
                                                       "https://salt.gummfit.com", "https://salt.gummfit.com/account",
                                                       reply_to="ana@example.com"))
    asyncio.run(mail.send_cappe_magazine_ending_email("r@example.com", None, "Salt", NOW, None))
    asyncio.run(mail.send_cappe_magazine_ending_email("r@example.com", None, "Salt", None, None))
    asyncio.run(mail.send_cappe_magazine_comp_email("r@example.com", "Salt", None, "https://salt.gummfit.com"))
    subjects = [s[1] for s in sent]
    assert subjects == ["New paid reader — Salt", "Welcome to Salt", "Your subscription to Salt is ending",
                        "Your subscription to Salt is ending", "A free subscription to Salt"]
    assert "$5.00 a month" in sent[0][3] and sent[0][4]["log_recipient"] is False
    assert "Start reading" in sent[1][2] and sent[1][4]["reply_to"] == "ana@example.com"
    assert "until October 21, 2026" in sent[2][3] and "until the end of the month" in sent[3][3]
    assert "for as long as they keep it on" in sent[4][3]


def test_the_catalog_fallback_lets_paying_plans_charge_readers():
    assert ent_mod._legacy_fallback("writer").features["magazine_paid"] is True
    assert ent_mod._legacy_fallback("free").features["magazine_paid"] is False


def test_admins_set_the_magazine_share(monkeypatch):
    from app.core.routes.admin import cappe_creators as admin

    conn = Conn(fetch={"FROM cappe_marketplace_settings": [{"key": "magazine_fee_bps", "value": '{"bps": 2500}'}]})
    audits = []

    async def audit(c, user, action, target, payload):
        audits.append(payload)

    monkeypatch.setattr(admin, "get_connection", lambda: conn)
    monkeypatch.setattr(admin, "_audit", audit)
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(cappe_platform_fee_bps=200))
    assert asyncio.run(admin.admin_get_marketplace_settings())["magazine_fee_bps"] == 2500
    asyncio.run(admin.admin_patch_marketplace_settings(admin._MarketplaceSettingsPatch(magazine_fee_bps=2000),
                                                        current_user=SimpleNamespace(email="ops@example.com")))
    assert conn.args_for("INSERT INTO cappe_marketplace_settings") == ("magazine_fee_bps", '{"bps": 2000}')
    assert audits[0]["new"] == {"magazine_fee_bps": 2000}
    with pytest.raises(ValueError):
        admin._MarketplaceSettingsPatch(magazine_fee_bps=6000)
