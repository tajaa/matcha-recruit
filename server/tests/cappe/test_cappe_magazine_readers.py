"""Reader accounts and their dashboard (cappemag06).

What each block pins:

  * a reader account is offered no plan and can't make a site;
  * only a confirmed email is matched to a reader's rows on magazines, and it
    is matched lower-cased;
  * the shelf lists each magazine held (a subscription still paying or live
    free months), keeps a magazine that is down so it can be cancelled, and
    shows the latest story of a live one;
  * one magazine: 404 unless published and live; what the reader holds; the
    price only while it takes subscribers; stories a page at a time;
  * reading: a reader with paid access gets the whole story, anyone else the
    part before the paywall; always `no-store`;
  * subscribing makes the reader's row on the magazine and checks out back to
    the dashboard; a checkout's returns may be the dashboard only when the
    caller says so;
  * cancel and resume only touch the reader's own magazine subscriptions, and
    resume needs a magazine still taking subscribers;
  * the paywall on a magazine's own page links to the dashboard.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_magazine_readers.py -q
"""
import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import reader as reader_mod  # noqa: E402
from app.cappe.routes import sites as sites_mod  # noqa: E402
from app.cappe.services import recurring  # noqa: E402
from app.cappe.services.catalog import plan_offered  # noqa: E402
from app.cappe.services.email import app_origin, dashboard_url  # noqa: E402
from app.cappe.services.magazine import billing  # noqa: E402
from app.cappe.services.magazine import pages  # noqa: E402
from app.cappe.services.magazine import shelf  # noqa: E402
from app.cappe.services.magazine.figures import card_image  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402

SITE, ACCOUNT_ID, SHOPPER, SUB = uuid4(), uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 21, 9, tzinfo=timezone.utc)
SITE_ROW = {"id": SITE, "name": "Salt & Light", "slug": "salt", "subdomain": "salt", "custom_domain": None,
            "account_id": uuid4(), "status": "published", "currency": "USD", "meta_config": "{}",
            "theme_config": "{}", "timezone": "UTC"}
MAG = {"site_id": SITE, "enabled": True, "name": "Salt & Light", "tagline": "Sea stories", "accent": "#0ea5e9",
       "front_at_root": True, "paid_enabled": True, "price_cents": 500, "paid_pitch": "Every week.",
       "preview_blocks": 3, "lapsed_at": None, "follow_enabled": True, "masthead_style": "classic", "topics": []}
READER = SimpleNamespace(id=ACCOUNT_ID, plan="free", account_type="reader", email="Rae@Example.com", name="Rae")
CONFIRMED = {"email": "Rae@Example.com", "email_verified_at": NOW}
SHOPPER_ROW = {"id": SHOPPER, "site_id": SITE, "email": "rae@example.com", "deleting": False}
SENTINEL = "ZXQ-for-subscribers-ZXQ"
POST = {"id": uuid4(), "slug": "low-tide", "title": "Low tide", "access": "paid", "format": "blocks",
        "excerpt": "The water goes out.", "kicker": "Coast", "topic": None, "published_at": NOW, "updated_at": NOW,
        "layout": "standard", "reading_minutes": 4,
        "content": {"blocks": [{"type": "text", "md": "Free opening.", "dropcap": True},
                               {"type": "paywall"},
                               {"type": "text", "md": SENTINEL}]}}
COVER = {"id": uuid4(), "url": "https://cdn.test/full.jpg", "alt": "Tide pools", "credit_line": "Photo: Ana",
         "variants": {"webp": [{"w": 480, "url": "https://cdn.test/480.webp"},
                               {"w": 960, "url": "https://cdn.test/960.webp"}]}}


class Conn(QueryConn):
    def transaction(self):
        return self


async def _noop(*a, **k):
    return None


async def _value(v):
    return v


# ── the account type ─────────────────────────────────────────────────────────

def test_a_reader_is_offered_no_plan():
    assert not plan_offered("free", {}, "reader")
    assert not plan_offered("business", {}, "reader")
    assert not plan_offered("writer", {"audience": "writer"}, "reader")
    assert plan_offered("business", {}, "business")


def test_a_reader_cant_make_a_site():
    with pytest.raises(HTTPException) as err:
        asyncio.run(sites_mod._enforce_site_limit(Conn(), READER))
    assert err.value.status_code == 403 and err.value.detail["code"] == "reader_account"


def test_only_a_confirmed_email_is_matched():
    assert asyncio.run(shelf.confirmed_email(Conn(fetchrow={"FROM cappe_accounts": CONFIRMED}), ACCOUNT_ID)) \
        == "rae@example.com"
    for row in (None, {**CONFIRMED, "email_verified_at": None}):
        with pytest.raises(HTTPException) as err:
            asyncio.run(shelf.confirmed_email(Conn(fetchrow={"FROM cappe_accounts": row}), ACCOUNT_ID))
        assert err.value.status_code == 403 and err.value.detail["code"] == "email_unverified"


def test_a_card_picture_is_the_first_size_wide_enough():
    assert card_image(COVER) == {"url": "https://cdn.test/960.webp", "alt": "Tide pools", "credit": "Photo: Ana"}
    assert card_image(COVER, width=2000)["url"] == "https://cdn.test/960.webp"
    assert card_image({**COVER, "variants": {}, "ai_generated": True})["credit"] == "AI illustration"
    assert card_image(None) is None


# ── the shelf ────────────────────────────────────────────────────────────────

def _held(**kw):
    return {"site_id": SITE, "slug": "salt", "subdomain": "salt", "custom_domain": None, "site_status": "published",
            "account_id": SITE_ROW["account_id"], "site_name": "Salt site", "name": "Salt & Light",
            "tagline": "Sea stories", "accent": "#0ea5e9", "sub_id": SUB, "status": "active",
            "current_period_end": NOW, "cancel_at_period_end": False, "total_cents": 500, "currency": "USD",
            "comp_id": None, "comp_expires_at": None, **kw}


def _shelf_client(monkeypatch, rows, *, live=MAG):
    conn = Conn(fetchrow={"FROM cappe_accounts": CONFIRMED}, fetch={"FROM cappe_shoppers sh": rows})

    async def live_mag(c, site):
        return live

    async def stories(c, site_id, **kw):
        return [POST]

    async def covers(c, site_id, posts):
        return {str(POST["id"]): COVER}

    monkeypatch.setattr(reader_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(shelf, "live_magazine", live_mag)
    monkeypatch.setattr(shelf, "live_stories", stories)
    monkeypatch.setattr(shelf, "covers", covers)
    return conn, route_client(reader_mod.router, overrides={reader_mod.require_cappe_account: READER})


def test_the_shelf_lists_what_the_reader_holds(monkeypatch):
    conn, client = _shelf_client(monkeypatch, [_held()])
    with client as client:
        res = client.get("/reader/magazines")
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store, private"
    [mag] = res.json()["magazines"]
    assert mag["name"] == "Salt & Light" and mag["live"] is True and mag["slug"] == "salt"
    assert mag["subscription"]["status"] == "active" and mag["subscription"]["total_cents"] == 500
    assert mag["comp"] is None and mag["origin"].startswith("https://salt.")
    assert mag["latest"]["title"] == "Low tide" and mag["latest"]["cover"]["url"] == "https://cdn.test/960.webp"
    args = conn.args_for("FROM cappe_shoppers sh")
    assert args[0] == "rae@example.com" and set(args[1]) == {"active", "trialing", "past_due"}
    sql = conn.sql_for("fetch")[0]
    assert "kind = 'magazine'" in sql and "NOT sh.deleting" in sql and "revoked_at IS NULL" in sql


def test_a_magazine_thats_down_stays_so_it_can_be_cancelled(monkeypatch):
    rows = [_held(site_status="draft"), _held(sub_id=None, comp_id=uuid4(), comp_expires_at=NOW, name=None)]
    _conn, client = _shelf_client(monkeypatch, rows, live=None)
    with client as client:
        down, comp = client.get("/reader/magazines").json()["magazines"]
    assert down["live"] is False and down["latest"] is None and down["subscription"]["id"] == str(SUB)
    assert comp["subscription"] is None and comp["comp"] == {"expires_at": NOW.isoformat()}
    assert comp["name"] == "Salt site"


def test_an_unconfirmed_account_sees_nothing(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_accounts": {**CONFIRMED, "email_verified_at": None}})
    monkeypatch.setattr(reader_mod, "get_connection", lambda: conn)
    with route_client(reader_mod.router, overrides={reader_mod.require_cappe_account: READER}) as client:
        assert client.get("/reader/magazines").status_code == 403
    assert not conn.sql_for("fetch")


# ── one magazine ─────────────────────────────────────────────────────────────

def _mag_client(monkeypatch, *, site=SITE_ROW, mag=MAG, shopper=SHOPPER_ROW, held=None, open_=True,
                posts=(POST,), post=POST, access=True, following=None):
    conn = Conn(fetchrow={"FROM cappe_accounts": CONFIRMED, "FROM cappe_sites": site,
                          "FROM cappe_shoppers": shopper},
                fetch={"FROM cappe_pages": []}, fetchval={"FROM cappe_magazine_follows": following})

    async def live_mag(c, s):
        return mag

    async def status(c, site_id, shopper_id):
        return held or {"has_access": True, "subscription": {"id": SUB, "status": "active"}, "comp": None}

    async def ready(c, s):
        if not open_:
            raise HTTPException(409, "no")
        return mag, {}

    async def stories(c, site_id, **kw):
        return list(posts)[: kw.get("limit", 99)]

    async def one(c, site_id, slug=None, post_id=None):
        return post

    async def covers(c, site_id, ps):
        return {}

    async def has_access(c, site_id, shopper_id):
        return access

    monkeypatch.setattr(reader_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(reader_mod, "check_rate_limit", _noop)
    monkeypatch.setattr(shelf, "live_magazine", live_mag)
    monkeypatch.setattr(reader_mod, "reader_status", status)
    monkeypatch.setattr(reader_mod, "has_paid_access", has_access)
    monkeypatch.setattr(reader_mod.mag_billing, "paid_ready", ready)
    monkeypatch.setattr(reader_mod.mag_reader, "live_stories", stories)
    monkeypatch.setattr(reader_mod.mag_reader, "live_story", one)
    monkeypatch.setattr(reader_mod.mag_reader, "covers", covers)
    monkeypatch.setattr(reader_mod.mag_reader, "story_assets", lambda *a: _value({}))
    return conn, route_client(reader_mod.router, overrides={reader_mod.require_cappe_account: READER})


def test_a_magazine_shows_what_the_reader_holds_and_its_stories(monkeypatch):
    _conn, client = _mag_client(monkeypatch)
    with client as client:
        res = client.get("/reader/magazines/salt")
    body = res.json()
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store, private"
    assert body["has_access"] is True and body["subscription"]["status"] == "active"
    assert body["taking_subscribers"] is True and body["price_cents"] == 500 and body["paid_pitch"] == "Every week."
    assert [s["slug"] for s in body["stories"]] == ["low-tide"] and body["has_more"] is False
    assert body["following"] is False
    _conn, client = _mag_client(monkeypatch, following=1)
    with client as client:
        assert client.get("/reader/magazines/salt").json()["following"] is True


def test_a_reader_new_to_a_magazine_holds_nothing_there_yet(monkeypatch):
    _conn, client = _mag_client(monkeypatch, shopper=None, open_=False)
    with client as client:
        body = client.get("/reader/magazines/salt").json()
    assert body["has_access"] is False and body["subscription"] is None and body["comp"] is None
    assert body["taking_subscribers"] is False and body["price_cents"] is None and body["paid_pitch"] is None


def test_stories_come_a_page_at_a_time(monkeypatch):
    many = [{**POST, "id": uuid4(), "slug": f"s{i}"} for i in range(reader_mod.PAGE_SIZE + 1)]
    _conn, client = _mag_client(monkeypatch, posts=many)
    with client as client:
        body = client.get("/reader/magazines/salt").json()
    assert len(body["stories"]) == reader_mod.PAGE_SIZE and body["has_more"] is True


@pytest.mark.parametrize("kw", [{"site": None}, {"mag": None}])
def test_a_magazine_that_isnt_up_is_a_404(monkeypatch, kw):
    _conn, client = _mag_client(monkeypatch, **kw)
    with client as client:
        assert client.get("/reader/magazines/salt").status_code == 404
        assert client.get("/reader/magazines/salt/stories/low-tide").status_code == 404


# ── reading ──────────────────────────────────────────────────────────────────

def test_a_subscriber_reads_the_whole_story(monkeypatch):
    _conn, client = _mag_client(monkeypatch)
    with client as client:
        res = client.get("/reader/magazines/salt/stories/low-tide")
    body = res.json()
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store, private"
    assert body["paid"] is True and body["has_access"] is True
    assert "Free opening." in body["html"] and SENTINEL in body["html"] and 'id="mz-paywall"' not in body["html"]


@pytest.mark.parametrize("kw", [{"access": False}, {"shopper": None}])
def test_without_access_the_story_stops_at_the_paywall(monkeypatch, kw):
    _conn, client = _mag_client(monkeypatch, **kw)
    with client as client:
        body = client.get("/reader/magazines/salt/stories/low-tide").json()
    assert body["has_access"] is False and "Free opening." in body["html"]
    assert SENTINEL not in body["html"] and 'id="mz-paywall"' in body["html"]


def test_a_free_story_is_whole_for_anyone(monkeypatch):
    free = {**POST, "access": "free"}
    _conn, client = _mag_client(monkeypatch, post=free, shopper=None, access=False)
    with client as client:
        body = client.get("/reader/magazines/salt/stories/low-tide").json()
    assert body["paid"] is False and body["has_access"] is True and SENTINEL in body["html"]


def test_a_missing_story_is_a_404(monkeypatch):
    _conn, client = _mag_client(monkeypatch, post=None)
    with client as client:
        assert client.get("/reader/magazines/salt/stories/nope").status_code == 404


# ── subscribing ──────────────────────────────────────────────────────────────

def test_subscribing_makes_the_readers_row_and_returns_to_the_dashboard(monkeypatch):
    conn, client = _mag_client(monkeypatch)
    conn.set("fetchrow", "INSERT INTO cappe_shoppers", SHOPPER_ROW)
    seen = {}

    async def start(site, shopper, body, *, return_origins=None):
        seen.update(site=site["id"], shopper=shopper["id"], origins=return_origins, success=body.success_url)
        return {"checkout_url": "https://checkout.stripe.test/x", "subscription_id": str(SUB)}

    monkeypatch.setattr(reader_mod.mag_billing, "checkout", start)
    url = dashboard_url("/reader/m/salt")
    with client as client:
        res = client.post("/reader/magazines/salt/subscribe", json={"success_url": url + "?subscribed=1",
                                                                    "cancel_url": url})
    assert res.status_code == 201 and res.json()["checkout_url"] == "https://checkout.stripe.test/x"
    assert seen == {"site": SITE, "shopper": SHOPPER, "origins": [app_origin()], "success": url + "?subscribed=1"}
    assert conn.args_for("INSERT INTO cappe_shoppers") == (SITE, "rae@example.com")
    # Somewhere else becomes the magazine's page on the dashboard.
    with client as client:
        client.post("/reader/magazines/salt/subscribe", json={"success_url": "https://evil.test/",
                                                              "cancel_url": "https://evil.test/"})
    assert seen["success"] == url + "?subscribed=1"


def test_a_reader_leaving_the_magazine_cant_subscribe_there(monkeypatch):
    conn, client = _mag_client(monkeypatch)
    conn.set("fetchrow", "INSERT INTO cappe_shoppers", {**SHOPPER_ROW, "deleting": True})
    with client as client:
        res = client.post("/reader/magazines/salt/subscribe", json={"success_url": "x", "cancel_url": "y"})
    assert res.status_code == 409


def test_a_checkout_returns_to_the_dashboard_only_when_asked(monkeypatch):
    calls = []

    class Stripe:
        async def create_subscription_checkout(self, **kw):
            calls.append(kw)
            return {"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"}

    conn = Conn(fetchrow={"FROM cappe_accounts": {"stripe_account_id": "acct_w", "stripe_charges_enabled": True,
                                                  "plan": "writer"},
                          "FROM cappe_shoppers": {"deleting": False},
                          "INSERT INTO cappe_shopper_subscriptions": {"id": SUB, "site_id": SITE}},
                fetchval={"FROM cappe_marketplace_settings": None},
                fetch={"FROM cappe_shopper_subscriptions": []})

    async def live(c, site):
        return MAG

    monkeypatch.setattr(billing, "get_connection", lambda: conn)
    monkeypatch.setattr(billing, "live_magazine", live)
    monkeypatch.setattr(billing, "has_paid_access", lambda *a: _value(False))
    monkeypatch.setattr(billing, "resolve_entitlements",
                        lambda plan, conn=None: _value(SimpleNamespace(has=lambda f: True)))
    monkeypatch.setattr(billing, "connected_customer", lambda *a: _value("cus_1"))
    monkeypatch.setattr(billing, "get_cappe_stripe", lambda: Stripe())
    monkeypatch.setattr(recurring, "_attach_checkout_session", lambda *a: _value(True))
    home = dashboard_url("/reader/m/salt")
    body = SimpleNamespace(success_url=home, cancel_url=home)
    with pytest.raises(HTTPException) as err:
        asyncio.run(billing.checkout(SITE_ROW, SHOPPER_ROW, body))
    assert err.value.status_code == 422
    out = asyncio.run(billing.checkout(SITE_ROW, SHOPPER_ROW, body, return_origins=[app_origin()]))
    assert out["subscription_id"] == str(SUB) and calls[0]["success_url"] == home


# ── cancel and resume ────────────────────────────────────────────────────────

def _change_client(monkeypatch, *, row, site=SITE_ROW, open_=True):
    conn = Conn(fetchrow={"FROM cappe_accounts": CONFIRMED, "FROM cappe_shopper_subscriptions sub": row,
                          "FROM cappe_sites": site})
    changes = []

    async def change(r, cancel, **kw):
        changes.append((r["id"], cancel))
        return {"status": "active", "cancel_at_period_end": cancel}

    async def ready(c, s):
        if not open_:
            raise HTTPException(402, "no")
        return MAG, {}

    monkeypatch.setattr(reader_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(reader_mod, "check_rate_limit", _noop)
    monkeypatch.setattr(reader_mod.recurring, "change_subscription", change)
    monkeypatch.setattr(reader_mod.mag_billing, "paid_ready", ready)
    return conn, changes, route_client(reader_mod.router, overrides={reader_mod.require_cappe_account: READER})


def test_a_reader_cancels_and_keeps_their_own_subscription(monkeypatch):
    conn, changes, client = _change_client(monkeypatch, row={"id": SUB, "site_id": SITE})
    with client as client:
        assert client.post(f"/reader/subscriptions/{SUB}/cancel").json()["cancel_at_period_end"] is True
        assert client.post(f"/reader/subscriptions/{SUB}/resume").status_code == 200
    assert changes == [(SUB, True), (SUB, False)]
    sql = next(s for s in conn.sql_for("fetchrow") if "FROM cappe_shopper_subscriptions sub" in s)
    assert "sh.email = $2" in sql and "kind = 'magazine'" in sql
    assert conn.args_for("FROM cappe_shopper_subscriptions sub") == (SUB, "rae@example.com")


def test_someone_elses_subscription_is_a_404(monkeypatch):
    _conn, changes, client = _change_client(monkeypatch, row=None)
    with client as client:
        assert client.post(f"/reader/subscriptions/{SUB}/cancel").status_code == 404
    assert changes == []


@pytest.mark.parametrize("kw", [{"open_": False}, {"site": None}])
def test_resume_needs_a_magazine_still_taking_subscribers(monkeypatch, kw):
    _conn, changes, client = _change_client(monkeypatch, row={"id": SUB, "site_id": SITE}, **kw)
    with client as client:
        assert client.post(f"/reader/subscriptions/{SUB}/resume").status_code == 409
        assert client.post(f"/reader/subscriptions/{SUB}/cancel").status_code == 200
    assert changes == [(SUB, True)]


# ── the magazine's own page ──────────────────────────────────────────────────

def test_the_paywall_links_to_the_dashboard():
    page = pages.render_story({"name": "Salt", "slug": "salt", "theme_config": {}, "meta_config": {}}, [], MAG,
                              POST, {}, more=[], more_covers={}, origin="https://salt.gummfit.com", currency="USD")
    assert f'href="{dashboard_url("/reader/m/salt")}"' in page and "data-mz-alt" in page
    assert "data-mz-alt" not in pages.paywall_html(MAG, POST, currency="USD")
    assert pages.reader_path("a b/c") == "/reader/m/a%20b%2Fc"


@pytest.mark.parametrize("extra", [{"intended_plan": "writer"}, {"grant_token": "g" * 43}])
def test_a_reader_signup_takes_no_plan_or_grant(monkeypatch, extra):
    # A single-use grant redeemed onto a reader (who can hold no plan) would be
    # spent for nothing: refused before it is looked up.
    from unittest.mock import AsyncMock

    from app.cappe.models.auth import CappeSignup
    from app.cappe.routes import auth as auth_mod

    monkeypatch.setattr(auth_mod, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(auth_mod, "hash_password", lambda p: "hash")
    monkeypatch.setattr(auth_mod, "get_connection", lambda *a, **k: pytest.fail("no database for a refusal"))
    fields = {"email": "reader@example.com", "password": "longenough1", "name": None, "account_type": "reader",
              "intended_plan": None, "intended_interval": None, "grant_token": None, **extra}
    body = CappeSignup.model_construct(**fields)
    with pytest.raises(HTTPException) as err:
        asyncio.run(auth_mod.signup(body, SimpleNamespace(headers={}, client=None), None))
    assert err.value.status_code == 400 and "reader account" in err.value.detail
