"""Writers, follows and email issues (cappemag04).

What each block pins:

  * the Writer plan is offered only to writers, and a writer only it, Free
    and Business — in lists, on the public pricing page and at checkout;
  * a writer's magazine lives at exactly the handle they chose (reserved,
    malformed and taken handles are refused, never quietly "-2"'d), on a
    magazine-only site created under the account lock and site limit;
  * a magazine site publishes with a published story on a plan with
    magazines — without the plan, a 402 naming the Writer plan — and is never
    sent for business-listing inference;
  * following is double opt-in: one answer for everyone, a subscribed address
    is never touched, at most three confirmation emails a day per address;
  * unsubscribing: the GET page changes nothing, the POST and the RFC 8058
    one-click do it, whatever the site's status;
  * an issue is our template: credits from the library, the AI label, a paid
    story's paid part never in the email; each reader gets their own links and
    the List-Unsubscribe headers; issues share the newsletter's send budget.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_magazine_writers.py -q
"""
import asyncio
import inspect
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.routes import billing, magazine as magazine_routes, magazine_issues, render, sites  # noqa: E402
from app.cappe.routes.public import magazine as public_magazine, pricing  # noqa: E402
from app.cappe.services import campaigns, readiness  # noqa: E402
from app.cappe.services.catalog import plan_offered  # noqa: E402
from app.cappe.services.magazine import issue_email, writers  # noqa: E402
from app.workers.tasks import cappe_campaign_send as campaign_worker  # noqa: E402
from tests._helpers.routes import QueryConn, Queue, route_client  # noqa: E402

WRITER = SimpleNamespace(id=uuid4(), email="writer@example.com", name="Ana", plan="writer", account_type="writer",
                         status="active")
BUSINESS = SimpleNamespace(id=uuid4(), email="shop@example.com", name="Shop", plan="business",
                           account_type="business", status="active")
SITE_ID, POST_ID, COVER, PIC, AI = uuid4(), uuid4(), str(uuid4()), str(uuid4()), str(uuid4())
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def _site_row(**over):
    base = {
        "id": SITE_ID, "account_id": WRITER.id, "name": "The Harbour Review", "slug": "harbour",
        "subdomain": "harbour", "custom_domain": None, "source_type": "magazine", "template_id": None,
        "template_slug": None, "status": "draft", "theme_config": "{}", "meta_config": "{}", "timezone": "UTC",
        "is_multi_location": False, "tax_rate_bps": 0, "tax_label": "Tax", "shipping_flat_cents": 0,
        "shipping_free_threshold_cents": None, "shipping_label": "Shipping", "receipt_prefix": "ORDER",
        "listed": False, "directory_category": None, "directory_tags": [], "directory_blurb": None,
        "directory_confirmed_at": None, "published_at": None, "created_at": NOW, "updated_at": NOW,
    }
    return {**base, **over}


# ── the Writer plan ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("code, features, account_type, offered", [
    ("writer", {"audience": "writer"}, "writer", True),
    ("free", {}, "writer", True),
    ("business", {}, "writer", True),
    ("creator", {}, "writer", False),
    ("writer", {"audience": "writer"}, "business", False),
    ("writer", {"audience": "writer"}, "creator", False),
    ("writer", {"audience": "writer"}, None, False),
    ("creator", {}, "creator", True),
    ("business", None, "business", True),
])
def test_who_is_offered_which_plan(code, features, account_type, offered):
    assert plan_offered(code, features, account_type) is offered


def _plan(code, **features):
    return SimpleNamespace(code=code, features=features)


def test_the_billing_catalog_and_public_pricing_filter_by_audience(monkeypatch):
    plans = [_plan("free"), _plan("creator"), _plan("writer", audience="writer", magazine=True), _plan("business")]

    async def build_catalog(conn):
        return plans, []

    async def intro_eligible(conn, account_id):
        return True

    monkeypatch.setattr(billing, "build_catalog", build_catalog)
    monkeypatch.setattr(billing.billing_svc, "intro_eligible", intro_eligible)
    monkeypatch.setattr(billing, "get_connection", lambda *a, **k: QueryConn())
    monkeypatch.setattr(billing, "CappeCatalog", lambda **kw: kw)
    assert [p.code for p in run(billing.get_catalog(WRITER))["plans"]] == ["free", "writer", "business"]
    assert [p.code for p in run(billing.get_catalog(BUSINESS))["plans"]] == ["free", "creator", "business"]

    async def no_limit(*a, **k):
        return None

    monkeypatch.setattr(pricing, "build_catalog", build_catalog)
    monkeypatch.setattr(pricing, "check_rate_limit", no_limit)
    monkeypatch.setattr(pricing, "client_ip", lambda r: "1.2.3.4")
    monkeypatch.setattr(pricing, "get_connection", lambda *a, **k: QueryConn())
    monkeypatch.setattr(pricing, "_public_plan", lambda p: p)
    monkeypatch.setattr(pricing, "CappePublicPricing", lambda **kw: kw)
    assert [p.code for p in run(pricing.public_pricing(SimpleNamespace(), None))["plans"]] == \
        ["free", "creator", "business"]
    assert [p.code for p in run(pricing.public_pricing(SimpleNamespace(), "writer"))["plans"]] == \
        ["free", "writer", "business"]


def test_a_business_cant_check_out_the_writer_plan(monkeypatch):
    conn = QueryConn(fetchrow={"FROM cappe_billing_products": {
        "code": "writer", "name": "Writer", "status": "active", "kind": "plan", "features": '{"audience": "writer"}'}})
    monkeypatch.setattr(billing, "get_connection", lambda *a, **k: conn)
    body = SimpleNamespace(plan_code="writer", interval="month")
    with pytest.raises(HTTPException) as caught:
        run(billing.start_checkout(body, BUSINESS))
    assert caught.value.status_code == 404

    async def current(conn_, account_id):
        return {"source": "stripe", "stripe_subscription_id": "sub_1", "plan_code": "business", "interval": "month"}

    monkeypatch.setattr(billing.billing_svc, "current_subscription", current)
    with pytest.raises(HTTPException) as caught:
        run(billing.change_plan(SimpleNamespace(plan_code="writer", interval="month"), BUSINESS))
    assert caught.value.status_code == 404


# ── a writer's magazine site ─────────────────────────────────────────────────

@pytest.mark.parametrize("handle, problem", [
    ("harbour", None), ("the-harbour-review", None), ("a1b", None),
    ("ab", writers.BAD_HANDLE), ("-harbour", writers.BAD_HANDLE), ("harbour-", writers.BAD_HANDLE),
    ("har--bour", writers.BAD_HANDLE), ("har_bour", writers.BAD_HANDLE), ("x" * 31, writers.BAD_HANDLE),
    ("www", writers.RESERVED), ("admin", writers.RESERVED), ("blog", writers.RESERVED),
])
def test_handle_rules(handle, problem):
    assert writers.handle_problem(handle) == problem
    assert writers.normalize_handle("  Harbour ") == "harbour"


@pytest.fixture
def mag_routes(monkeypatch):
    state = SimpleNamespace(conn=None, saved=None, events=[])

    async def no_limit(*a, **k):
        return None

    async def lock(conn, account_id):
        state.events.append("lock")

    async def enforce(conn, account):
        state.events.append("limit")

    async def save(conn, site_id, fields, *, default_name):
        state.saved = fields
        return fields

    monkeypatch.setattr(magazine_routes, "check_rate_limit", no_limit)
    monkeypatch.setattr(magazine_routes, "_lock_account_for_site_creation", lock)
    monkeypatch.setattr(magazine_routes, "_enforce_site_limit", enforce)
    monkeypatch.setattr(magazine_routes, "save_magazine", save)
    monkeypatch.setattr(magazine_routes, "get_connection", lambda *a, **k: state.conn)
    return state


class TxQueryConn(QueryConn):
    def transaction(self):
        class _Tx:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *exc):
                return False

        return _Tx()


def _client(account=WRITER):
    return route_client(magazine_routes.router, overrides={magazine_routes.require_cappe_account: account})


def test_handle_availability(mag_routes):
    mag_routes.conn = QueryConn(fetchval={"FROM cappe_sites WHERE slug": None})
    with _client() as client:
        assert client.get("/magazine/handle-available", params={"handle": " Harbour "}).json() == \
            {"handle": "harbour", "available": True, "reason": None}
        assert client.get("/magazine/handle-available", params={"handle": "www"}).json()["reason"] == writers.RESERVED
    mag_routes.conn = QueryConn(fetchval={"FROM cappe_sites WHERE slug": 1})
    with _client() as client:
        assert client.get("/magazine/handle-available", params={"handle": "harbour"}).json()["reason"] == writers.TAKEN


BODY = {"name": "The Harbour Review", "handle": "Harbour", "tagline": "Stories from the water",
        "topics": ["travel", "food"], "masthead_style": "modern", "accent": "#0f766e"}


def test_a_writer_gets_a_magazine_site_at_their_handle(mag_routes):
    conn = TxQueryConn(fetchval={"FROM cappe_sites WHERE slug": None},
                       fetchrow={"INSERT INTO cappe_sites": _site_row()})
    mag_routes.conn = conn
    with _client() as client:
        res = client.post("/magazine/sites", json=BODY)
    assert res.status_code == 201, res.text
    assert res.json()["source_type"] == "magazine" and res.json()["subdomain"] == "harbour"
    args = conn.args_for("INSERT INTO cappe_sites")
    assert args[2] == "harbour" and json.loads(args[3]) == {"fonts": {"heading": "Archivo Black",
                                                                     "body": "Libre Franklin"}}
    assert "'magazine'" in conn.sql_for("fetchrow")[0]
    assert mag_routes.saved == {"enabled": True, "name": "The Harbour Review", "tagline": "Stories from the water",
                                "masthead_style": "modern", "accent": "#0f766e", "topics": ["travel", "food"],
                                "front_at_root": True}
    assert any("'About', 'about'" in sql for sql in conn.sql_for("execute"))
    assert mag_routes.events == ["lock", "limit"]


@pytest.mark.parametrize("account, body, code", [
    (BUSINESS, BODY, 403),
    (WRITER, {**BODY, "handle": "www"}, 422),
    (WRITER, {**BODY, "handle": "har--bour"}, 422),
    (WRITER, {**BODY, "topics": ["astrology"]}, 422),
    (WRITER, {**BODY, "topics": ["a", "b", "c", "d"]}, 422),
])
def test_magazine_sites_refused(mag_routes, account, body, code):
    mag_routes.conn = TxQueryConn(fetchval={"FROM cappe_sites WHERE slug": None})
    with _client(account) as client:
        assert client.post("/magazine/sites", json=body).status_code == code


def test_a_taken_handle_is_a_409_never_a_new_suffix(mag_routes):
    mag_routes.conn = TxQueryConn(fetchval={"FROM cappe_sites WHERE slug": 1})
    with _client() as client:
        res = client.post("/magazine/sites", json=BODY)
    assert res.status_code == 409 and res.json()["detail"] == writers.TAKEN

    class Racing(TxQueryConn):
        async def fetchrow(self, sql, *args):
            raise asyncpg.UniqueViolationError("duplicate key")

    mag_routes.conn = Racing(fetchval={"FROM cappe_sites WHERE slug": None})
    with _client() as client:
        assert client.post("/magazine/sites", json=BODY).status_code == 409


# ── publishing a magazine site ───────────────────────────────────────────────

class ReadyConn:
    def __init__(self, *, story=True, about=False, plan="writer"):
        self.story, self.about, self.plan = story, about, plan

    async def fetchrow(self, sql, *args):
        return {"has_story": self.story, "has_about": self.about}

    async def fetchval(self, sql, *args):
        return self.plan


def test_a_magazine_sites_checklist(monkeypatch):
    async def entitlements(plan, *, conn=None):
        return SimpleNamespace(has=lambda f: plan == "writer")

    monkeypatch.setattr(readiness, "resolve_entitlements", entitlements)
    result = run(readiness.compute_readiness(ReadyConn(), SITE_ID, _site_row()))
    assert [i["key"] for i in result["items"]] == ["story", "magazine_plan", "about", "branding"]
    assert result["ready"] is True
    assert run(readiness.compute_readiness(ReadyConn(story=False), SITE_ID, _site_row()))["ready"] is False
    assert run(readiness.compute_readiness(ReadyConn(plan="free"), SITE_ID, _site_row()))["ready"] is False


@pytest.fixture
def publish(monkeypatch):
    state = SimpleNamespace(plan_ok=True, inferred=[])
    conn = TxQueryConn(fetchrow={"FROM cappe_sites WHERE id": _site_row(),
                                 "UPDATE cappe_sites": _site_row(status="published", published_at=NOW)})

    async def plan_has(conn_, account_id):
        return state.plan_ok

    async def ready(conn_, site_id, site):
        return {"ready": True, "items": []}

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(sites, "get_connection", lambda *a, **k: conn)
    monkeypatch.setattr(sites, "plan_has_magazine", plan_has)
    monkeypatch.setattr(sites, "compute_readiness", ready)
    monkeypatch.setattr(sites, "refresh_site_search", nothing)
    monkeypatch.setattr(sites, "invalidate_render_cache", nothing)
    monkeypatch.setattr(sites, "_infer_listing_after_publish", lambda site_id: state.inferred.append(site_id))
    return state


def test_a_magazine_site_needs_a_plan_with_magazines_to_publish(publish):
    publish.plan_ok = False
    with route_client(sites.router, overrides={sites.require_cappe_account: WRITER}) as client:
        res = client.post(f"/sites/{SITE_ID}/publish")
    assert res.status_code == 402
    assert res.json()["detail"]["code"] == "plan_required" and res.json()["detail"]["plan"] == "writer"


def test_a_published_magazine_isnt_sent_for_business_listing(publish):
    with route_client(sites.router, overrides={sites.require_cappe_account: WRITER}) as client:
        res = client.post(f"/sites/{SITE_ID}/publish")
    assert res.status_code == 200, res.text
    assert publish.inferred == []


# ── following ────────────────────────────────────────────────────────────────

@pytest.fixture
def follow(monkeypatch):
    state = SimpleNamespace(mag={"follow_enabled": True}, capped=False, dispatched=[], conn=None)

    async def limit(key, action, n, window):
        if action == "cappe_follow_email" and state.capped:
            raise HTTPException(status_code=429, detail="Too many")

    async def live(conn, site):
        return state.mag

    monkeypatch.setattr(public_magazine, "check_rate_limit", limit)
    monkeypatch.setattr(public_magazine, "client_ip", lambda r: "1.2.3.4")
    monkeypatch.setattr(public_magazine, "live_magazine", live)
    monkeypatch.setattr(public_magazine, "_dispatch_confirm", lambda site_id: state.dispatched.append(site_id))
    monkeypatch.setattr(public_magazine, "get_connection", lambda *a, **k: state.conn)
    return state


@pytest.fixture
def deliverable(monkeypatch):
    """Reserved test domains are refused at follow (that is tested below);
    the happy path switches the guard off rather than invent a real domain."""
    monkeypatch.setattr(public_magazine, "_reject_reserved", lambda email: None)


def _site_conn(staged=True):
    return QueryConn(fetchrow={"FROM cappe_sites WHERE slug": {"id": SITE_ID, "account_id": WRITER.id,
                                                                 "status": "published"}},
                     fetchval={"INSERT INTO cappe_subscribers": uuid4() if staged else None})


def test_following_stages_a_confirmation_and_answers_the_same_for_everyone(follow, deliverable):
    follow.conn = _site_conn()
    with route_client(public_magazine.router) as client:
        first = client.post("/public/sites/harbour/follow", json={"email": "Reader@Example.com", "name": " Jo "})
        assert first.status_code == 202 and follow.dispatched == [SITE_ID]
        sql = follow.conn.sql_for("fetchval")[0]
        assert "'follow', 'pending_confirmation'" in sql
        assert "WHERE cappe_subscribers.status IN ('unsubscribed', 'pending_confirmation', 'pending')" in sql
        assert follow.conn.args_for("INSERT INTO cappe_subscribers")[1:] == ("reader@example.com", "Jo")

        follow.conn, follow.dispatched = _site_conn(staged=False), []  # already subscribed: untouched
        again = client.post("/public/sites/harbour/follow", json={"email": "reader@example.com"})
        assert again.status_code == 202 and again.json() == first.json() and follow.dispatched == []

        follow.capped, follow.conn = True, _site_conn()
        capped = client.post("/public/sites/harbour/follow", json={"email": "reader@example.com"})
        assert capped.status_code == 202 and capped.json() == first.json()
        assert follow.conn.calls[-1][1].startswith("SELECT id, account_id")  # nothing written


def test_a_reserved_test_address_is_refused(follow):
    follow.conn = _site_conn()
    with route_client(public_magazine.router) as client:
        assert client.post("/public/sites/harbour/follow", json={"email": "r@example.com"}).status_code == 400


def test_following_is_refused_where_it_isnt_offered(follow, deliverable):
    follow.conn = _site_conn()
    with route_client(public_magazine.router) as client:
        follow.mag = {"follow_enabled": False}
        assert client.post("/public/sites/harbour/follow", json={"email": "r@example.com"}).status_code == 404
        follow.mag = None
        assert client.post("/public/sites/harbour/follow", json={"email": "r@example.com"}).status_code == 404


# ── leaving ──────────────────────────────────────────────────────────────────

def test_one_click_unsubscribe(monkeypatch):
    async def no_limit(request):
        return None

    conn = QueryConn()
    monkeypatch.setattr(public_magazine, "_read_rate_limit", no_limit)
    monkeypatch.setattr(public_magazine, "get_connection", lambda *a, **k: conn)
    with route_client(public_magazine.router) as client:
        res = client.post("/public/sites/harbour/unsubscribe/tok123/one-click", data={"List-Unsubscribe": "One-Click"})
        assert res.status_code == 200
        assert client.post(f"/public/sites/harbour/unsubscribe/{'x' * 80}/one-click").status_code == 200
    assert conn.args_for("UPDATE cappe_subscribers") == ("tok123", "harbour")
    assert len(conn.sql_for("execute")) == 1


@pytest.fixture
def unsub(monkeypatch):
    state = SimpleNamespace(site={"id": SITE_ID, "name": "The Harbour Review"}, conn=None)

    async def resolve(conn, host):
        return state.site

    async def no_limit(*a, **k):
        return None

    monkeypatch.setattr(render, "_resolve_site_any_status", resolve)
    monkeypatch.setattr(render, "check_rate_limit", no_limit)
    monkeypatch.setattr(render, "client_ip", lambda r: "1.2.3.4")
    monkeypatch.setattr(render, "get_connection", lambda *a, **k: state.conn)
    return state


def _request(path="/unsubscribe/tok1"):
    return SimpleNamespace(headers={"host": "harbour.gummfit.test"}, url=SimpleNamespace(path=path))


def test_the_unsubscribe_link_changes_nothing_until_the_button(unsub):
    unsub.conn = QueryConn(fetchval={"FROM cappe_subscribers": "subscribed"})
    page = run(render.unsubscribe_page("tok1", _request()))
    body = page.body.decode()
    assert page.status_code == 200 and '<form method="post" action="/unsubscribe/tok1">' in body
    assert "Stop emails from The Harbour Review?" in body
    assert unsub.conn.sql_for("execute") == [] and page.headers["cache-control"] == "no-store"
    done = run(render.unsubscribe("tok1", _request()))
    assert done.status_code == 200 and "unsubscribed" in done.body.decode()
    assert unsub.conn.args_for("UPDATE cappe_subscribers") == (SITE_ID, "tok1")


def test_unsubscribe_pages_for_a_used_or_unknown_link(unsub):
    unsub.conn = QueryConn(fetchval={"FROM cappe_subscribers": "unsubscribed"})
    assert "<form" not in run(render.unsubscribe_page("tok1", _request())).body.decode()
    unsub.conn = QueryConn(fetchval={"FROM cappe_subscribers": None})
    assert run(render.unsubscribe_page("tok1", _request())).status_code == 404
    assert run(render.unsubscribe("tok1", _request())).status_code == 404
    unsub.site = None
    assert run(render.unsubscribe_page("tok1", _request())).status_code == 404


# ── the issue email ──────────────────────────────────────────────────────────

def _asset(asset_id, **over):
    return {"id": asset_id, "url": f"https://cdn.example.test/{asset_id}.jpg", "alt": "Boats at dawn",
            "credit_line": "“Harbour” by Ana / CC BY 2.0 via Flickr", "license": "by", "ai_generated": False,
            "variants": {"share": {"w": 1200, "url": f"https://cdn.example.test/{asset_id}/share.jpg"}}, **over}


ASSETS = {COVER: _asset(COVER), PIC: _asset(PIC), AI: _asset(AI, ai_generated=True, credit_line="AI illustration")}
SENTINEL = "PAID-SENTINEL-7781"


def _story(**over):
    blocks = [
        {"type": "cover", "asset_id": COVER},
        {"type": "text", "md": "The harbour wakes **before** the town does."},
        {"type": "photo", "asset_id": PIC, "caption": "The first boat out."},
        {"type": "photo", "asset_id": AI, "caption": "How it might have looked."},
        {"type": "paywall"},
        {"type": "text", "md": f"Only subscribers read this: {SENTINEL}"},
    ]
    return {"id": POST_ID, "slug": "before-the-town", "title": "Before the town wakes", "excerpt": "A morning out.",
            "kicker": "Dispatch", "byline": "Ana Ruiz", "format": "blocks", "content": {"blocks": blocks},
            "access": "free", **over}


MAG = {"name": "The Harbour Review", "accent": "#0f766e"}


def test_an_issue_prints_every_credit_and_the_ai_label():
    subject, html, text = issue_email.build_issue(site_name="Harbour", mag=MAG, post=_story(), assets=ASSETS,
                                                  origin="https://harbour.gummfit.test", include_body=True)
    assert subject == "Before the town wakes"
    assert f"https://cdn.example.test/{COVER}/share.jpg" in html  # the JPEG, not WebP
    assert html.count("CC BY 2.0 via Flickr") == 2 and "AI illustration" in html
    assert "https://harbour.gummfit.test/stories/before-the-town" in html and issue_email.UNSUBSCRIBE in html
    assert "<strong>before</strong>" in html and "<script" not in html
    assert issue_email.UNSUBSCRIBE in text and "Read the whole story" in text


def test_a_paid_storys_paid_part_is_never_in_an_issue():
    for include_body in (True, False):
        subject, html, text = issue_email.build_issue(
            site_name="Harbour", mag=MAG, post=_story(access="paid"), assets=ASSETS,
            origin="https://harbour.gummfit.test", include_body=include_body, subject="  Dawn  ")
        assert SENTINEL not in html and SENTINEL not in text
        assert "Read the whole story" in html


def test_the_opening_is_a_few_blocks_not_the_whole_story():
    _, html, _ = issue_email.build_issue(site_name="Harbour", mag=MAG, post=_story(), assets=ASSETS,
                                         origin="https://harbour.gummfit.test", include_body=False)
    assert "The first boat out." in html and SENTINEL not in html  # opening stops before the paywall
    assert issue_email.personalize('<a href="__CZ_UNSUBSCRIBE__">', "https://x.test/u?a=1&b=2", html=True) == \
        '<a href="https://x.test/u?a=1&amp;b=2">'
    assert issue_email.personalize("Leave: __CZ_UNSUBSCRIBE__", "https://x.test/u?a=1&b=2", html=False) == \
        "Leave: https://x.test/u?a=1&b=2"


# ── sending issues ───────────────────────────────────────────────────────────

@pytest.fixture
def issues(monkeypatch):
    state = SimpleNamespace(mag=dict(MAG), post=_story(), dispatched=[], limits=[], cap=None, sent=[],
                            dispatch_error=None, conn=None)

    async def live(conn, site):
        return state.mag

    async def live_story(conn, site_id, *, post_id=None, slug=None):
        return state.post

    async def story_assets(conn, site_id, post):
        return ASSETS

    async def limit(key, action, n, window):
        state.limits.append((action, n))

    async def cap(conn, account_id, site_id):
        return state.cap

    def delay(campaign_id):
        if state.dispatch_error:
            raise state.dispatch_error
        state.dispatched.append(campaign_id)

    from app.workers.tasks import cappe_campaign_send

    monkeypatch.setattr(magazine_issues, "live_magazine", live)
    monkeypatch.setattr(magazine_issues.mag_reader, "live_story", live_story)
    monkeypatch.setattr(magazine_issues.mag_reader, "story_assets", story_assets)
    monkeypatch.setattr(magazine_issues, "check_rate_limit", limit)
    monkeypatch.setattr(magazine_issues, "send_cap_problem", cap)
    monkeypatch.setattr(cappe_campaign_send.run_cappe_campaign_send, "delay", delay)
    monkeypatch.setattr(magazine_issues, "get_connection", lambda *a, **k: state.conn)
    return state


def _issue_conn(*, followers=12, already=None):
    row = {"id": uuid4(), "story_id": POST_ID, "subject": "Before the town wakes", "status": "sending",
           "include_body": False, "recipient_count": 0, "failed_count": 0, "sent_at": None, "created_at": NOW}
    return TxQueryConn(fetchrow={"FROM cappe_sites": _site_row(status="published"),
                                 "INSERT INTO cappe_campaigns": row},
                       fetchval={"story_id = $1 AND kind = 'issue'": already,
                                 "COUNT(*) FROM cappe_subscribers": followers})


def _issue_client():
    return route_client(magazine_issues.router, overrides={magazine_issues.require_cappe_account: WRITER})


def test_sending_an_issue(issues):
    issues.conn = _issue_conn()
    with _issue_client() as client:
        res = client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue", json={"subject": "Dawn", "include_body": True})
    assert res.status_code == 202, res.text
    assert res.json()["story_title"] == "Before the town wakes" and len(issues.dispatched) == 1
    sql = issues.conn.sql_for("fetchrow")[-1]
    assert "'sending', 'issue'" in sql
    args = issues.conn.args_for("INSERT INTO cappe_campaigns")
    assert args[1] == "Dawn" and issue_email.UNSUBSCRIBE in args[2] and args[4] == "The Harbour Review"
    assert args[5:] == (POST_ID, True)
    assert ("cappe_campaign_send", campaigns.SENDS_PER_DAY) in issues.limits  # the newsletter's budget


@pytest.mark.parametrize("change, code", [
    ({"mag": None}, 409), ({"post": None}, 409), ({"cap": "That would reach more than 5,000 people"}, 429),
])
def test_an_issue_that_cant_go(issues, change, code):
    issues.conn = _issue_conn()
    for k, v in change.items():
        setattr(issues, k, v)
    with _issue_client() as client:
        assert client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue", json={}).status_code == code
    assert issues.dispatched == [] and issues.conn.sql_for("fetchrow")[-1].lstrip().startswith("SELECT")


def test_a_story_goes_out_once_and_needs_followers(issues):
    issues.conn = _issue_conn(already=1)
    with _issue_client() as client:
        assert "already gone" in client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue", json={}).json()["detail"]
    issues.conn = _issue_conn(followers=0)
    with _issue_client() as client:
        assert "No one follows" in client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue", json={}).json()["detail"]


def test_two_sends_at_once_send_the_story_once(issues):
    # The second Send passed the first check while the first was building;
    # under the per-story lock it sees the first's row and stops.
    issues.conn = _issue_conn(already=Queue([None, 1]))
    with _issue_client() as client:
        res = client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue", json={})
    assert res.status_code == 409 and "already gone" in res.json()["detail"]
    assert issues.dispatched == [] and not issues.conn.sql_for("fetchrow")[-1].lstrip().startswith("INSERT")
    lock = [q for q in issues.conn.sql_for("execute") if "pg_advisory_xact_lock" in q]
    assert lock and issues.conn.args_for(lock[0]) == (f"cappe_issue:{POST_ID}",)


def test_an_issue_needs_the_sites_own_address(issues, monkeypatch):
    # Without one, its story and unsubscribe links would go nowhere.
    monkeypatch.setattr(magazine_issues, "site_public_origin", lambda site: None)
    issues.conn = _issue_conn()
    with _issue_client() as client:
        res = client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue", json={})
        assert res.status_code == 409 and "address" in res.json()["detail"]
        assert client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue/test", json={}).status_code == 409
    assert issues.dispatched == []


def test_the_newsletter_routes_leave_issues_alone(monkeypatch):
    # Deleting a sent issue through the newsletter would let the story go out again.
    from app.cappe.routes import newsletter

    conn = QueryConn(fetchrow={"FROM cappe_sites": _site_row(), "FROM cappe_campaigns": None},
                     execute={"DELETE FROM cappe_campaigns": "DELETE 0"})
    monkeypatch.setattr(newsletter, "get_connection", lambda *a, **k: conn)
    campaign = uuid4()
    with route_client(newsletter.router, overrides={newsletter.require_cappe_account: WRITER}) as client:
        assert client.get(f"/sites/{SITE_ID}/campaigns/{campaign}").status_code == 404
        assert client.delete(f"/sites/{SITE_ID}/campaigns/{campaign}").status_code == 404
        client.put(f"/sites/{SITE_ID}/campaigns/{campaign}", json={"subject": "x"})
        client.post(f"/sites/{SITE_ID}/campaigns/{campaign}/send")
    by_id = [q for q in conn.sql_for("fetchrow") + conn.sql_for("execute") if "cappe_campaigns WHERE id = $1" in q]
    assert len(by_id) == 4 and all("kind = 'campaign'" in q for q in by_id)


def test_a_writers_site_takes_no_single_opt_in_subscribers(monkeypatch):
    from app.cappe.routes.public import newsletter as public_newsletter

    async def no_limit(*a, **k):
        return None

    conn = QueryConn(fetchrow={"FROM cappe_sites": _site_row(status="published", home_country="US", currency="usd")},
                     fetchval={"a.account_type = 'writer'": 1})
    monkeypatch.setattr(public_newsletter, "check_rate_limit", no_limit)
    monkeypatch.setattr(public_newsletter, "_reject_reserved", lambda email: None)
    monkeypatch.setattr(public_newsletter, "get_connection", lambda *a, **k: conn)
    with route_client(public_newsletter.router) as client:
        res = client.post("/public/sites/harbour/subscribe", json={"email": "reader@example.com"})
    assert res.status_code == 404
    assert not any("INSERT INTO cappe_subscribers" in q for q in conn.sql_for("execute"))


def test_a_dispatch_that_fails_takes_the_issue_back(issues):
    issues.conn = _issue_conn()
    issues.dispatch_error = ConnectionError()
    with _issue_client() as client:
        assert client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue", json={}).status_code == 503
    assert any("DELETE FROM cappe_campaigns" in s for s in issues.conn.sql_for("execute"))


def test_a_test_issue_goes_to_the_writer_alone(monkeypatch, issues):
    issues.conn = _issue_conn()
    sent = []

    class Mail:
        async def send_email_with_fallback(self, **kw):
            sent.append(kw)
            return True

    import app.core.services.email as email_pkg
    monkeypatch.setattr(email_pkg, "EmailService", Mail)
    with _issue_client() as client:
        res = client.post(f"/sites/{SITE_ID}/posts/{POST_ID}/issue/test", json={})
        assert res.json() == {"ok": True, "to": WRITER.email}
    assert sent[0]["to_email"] == WRITER.email and sent[0]["subject"].startswith("[Test] ")
    assert issue_email.UNSUBSCRIBE not in sent[0]["html_content"]
    assert ("cappe_issue_test", magazine_issues.TESTS_PER_DAY) in issues.limits
    assert issues.dispatched == []


def test_listing_issues(issues):
    issues.conn = QueryConn(fetchrow={"FROM cappe_sites": _site_row()}, fetch={"FROM cappe_campaigns c": [{
        "id": uuid4(), "story_id": POST_ID, "story_title": "Before the town wakes", "subject": "Dawn", "status": "sent",
        "include_body": False, "recipient_count": 40, "failed_count": 1, "sent_at": NOW, "created_at": NOW}]})
    with _issue_client() as client:
        res = client.get(f"/sites/{SITE_ID}/issues")
    assert res.json()[0]["recipient_count"] == 40
    assert "c.kind = 'issue'" in issues.conn.sql_for("fetch")[0]


# ── the send worker's issue copy ─────────────────────────────────────────────

class WorkerConn:
    def __init__(self, camp, subs):
        self.camp, self.subs, self.executed = camp, subs, []

    async def fetchrow(self, sql, *a):
        return self.camp

    async def fetch(self, sql, *a):
        return self.subs

    async def execute(self, sql, *a):
        self.executed.append((sql, a))

    async def close(self):
        pass


def test_each_reader_gets_their_own_links_and_the_one_click_headers(monkeypatch):
    camp = {"id": "c-1", "subject": "Dawn", "body_html": f'<a href="{issue_email.UNSUBSCRIBE}">x</a>',
            "body_text": f"Leave: {issue_email.UNSUBSCRIBE}", "from_name": "The Harbour Review", "status": "sending",
            "site_id": SITE_ID, "kind": "issue", "slug": "harbour", "site_name": "Harbour", "subdomain": "harbour",
            "custom_domain": None, "owner_email": "writer@example.com"}
    subs = [{"id": "s1", "email": "a@reader.test", "name": "A", "unsubscribe_token": "t1"},
            {"id": "s2", "email": "b@reader.test", "name": None, "unsubscribe_token": "t2"}]
    sent = []

    class Mail:
        async def send_email_with_fallback(self, **kw):
            sent.append(kw)
            return True

    async def conn():
        return WorkerConn(camp, subs)

    import app.core.services.email as email_pkg
    monkeypatch.setattr(campaign_worker, "get_db_connection", conn)
    monkeypatch.setattr(campaign_worker, "THROTTLE_SECONDS", 0)
    monkeypatch.setattr(campaign_worker, "deliverable_recipients", lambda rows: [dict(r) for r in rows])
    monkeypatch.setattr(campaign_worker, "site_public_origin", lambda c: "https://harbour.gummfit.test")
    monkeypatch.setattr(email_pkg, "EmailService", Mail)
    monkeypatch.setenv("CAPPE_BASE_DOMAIN", "gummfit.test")
    assert run(campaign_worker._run("c-1"))["sent"] == 2
    first = sent[0]
    assert first["html_content"] == '<a href="https://harbour.gummfit.test/unsubscribe/t1">x</a>'
    assert first["text_content"] == "Leave: https://harbour.gummfit.test/unsubscribe/t1"
    assert first["extra_headers"] == {
        "List-Unsubscribe": "<https://gummfit.test/api/cappe/public/sites/harbour/unsubscribe/t1/one-click>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    assert first["from_name"] == "The Harbour Review" and first["reply_to"] == "writer@example.com"
    assert "t2" in sent[1]["html_content"] and "t1" not in sent[1]["html_content"]


def test_a_newsletter_still_goes_out_as_before(monkeypatch):
    camp = {"id": "c-2", "subject": "News", "body_html": "<p>hi</p>", "from_name": None, "status": "sending",
            "site_id": SITE_ID, "slug": "shop", "site_name": "Shop"}
    sent = []

    class Mail:
        async def send_email_with_fallback(self, **kw):
            sent.append(kw)
            return True

    async def conn():
        return WorkerConn(camp, [{"id": "s1", "email": "a@reader.test", "name": "A", "unsubscribe_token": "t1"}])

    import app.core.services.email as email_pkg
    monkeypatch.setattr(campaign_worker, "get_db_connection", conn)
    monkeypatch.setattr(campaign_worker, "THROTTLE_SECONDS", 0)
    monkeypatch.setattr(campaign_worker, "deliverable_recipients", lambda rows: [dict(r) for r in rows])
    monkeypatch.setattr(email_pkg, "EmailService", Mail)
    run(campaign_worker._run("c-2"))
    assert set(sent[0]) == {"to_email", "to_name", "subject", "html_content", "text_content"}


# ── the shared parts ─────────────────────────────────────────────────────────

def test_the_send_budget_is_shared():
    conn = QueryConn(fetchval={"COALESCE(SUM(": 4990, "COUNT(*) FROM cappe_subscribers": 20})
    assert "5,000 people" in run(campaigns.send_cap_problem(conn, WRITER.id, SITE_ID))
    conn = QueryConn(fetchval={"COALESCE(SUM(": 10, "COUNT(*) FROM cappe_subscribers": 20})
    assert run(campaigns.send_cap_problem(conn, WRITER.id, SITE_ID)) is None
    assert "send_cap_problem" in inspect.getsource(magazine_issues.send_issue)


def test_core_fallback_sender_carries_extra_headers(monkeypatch):
    from app.core.services.email import client as client_mod
    from app.core.services.email.client import EmailService

    monkeypatch.setattr(client_mod, "_is_reserved_test_domain", lambda email: False)
    service = EmailService.__new__(EmailService)
    seen = {}

    async def send_email(**kw):
        seen.update(kw)
        return True

    service._load_token = lambda: {"refresh_token": "x"}
    service.send_email = send_email
    ok = run(service._send_with_fallback(
        to_email="a@reader.test", to_name="A", subject="s", html_content="<p>x</p>", reply_to="writer@gmail.test",
        extra_headers={"List-Unsubscribe": "<https://x.test/u>"}))
    assert ok and seen["extra_headers"] == {"List-Unsubscribe": "<https://x.test/u>", "Reply-To": "writer@gmail.test"}


def test_admins_can_suspend_writers():
    from app.core.routes.admin import cappe_creators

    assert inspect.getsource(cappe_creators.admin_suspend_cappe_account).count('"writer"') == 1


def test_the_follow_confirmation_email_is_worded_as_the_readers_own_ask(monkeypatch):
    from app.cappe.services import email as cappe_email

    sent = []

    async def fake_send(to, name, subject, html, text, **kw):
        sent.append((subject, html, text))
        return True

    monkeypatch.setattr(cappe_email, "_send", fake_send)
    assert run(cappe_email.send_cappe_subscribe_confirm_email("r@reader.test", None, "The Harbour Review",
                                                               "https://x.test/c", follow=True))
    subject, html, text = sent[0]
    assert subject == "Confirm you want to follow The Harbour Review"
    assert "you asked to get new stories" in html and "added you" not in html and "https://x.test/c" in text


def test_onboarding_options_need_no_site(mag_routes):
    with _client() as client:
        body = client.get("/magazine/options").json()
    assert {"key": "travel", "label": "Travel"} in body["topics"]
    assert {"key": "modern", "heading": "Archivo Black", "body": "Libre Franklin"} in body["mastheads"]
