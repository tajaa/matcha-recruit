"""Following magazines from a Gummfit account (cappemag08).

What each block pins:

  * which followed magazines are live is `live_magazine`'s rule, applied to
    many sites with each owner plan resolved once;
  * following is idempotent and capped; unfollowing works on a magazine that
    is down (or gone);
  * only a live, published magazine can be followed;
  * the Following list keeps a magazine that is down, marked so;
  * the feed reads only live followed magazines, newest first, a page at a
    time, each story naming its magazine;
  * the owner sees a count, never who;
  * the follow box on a magazine's page links to the dashboard to follow there.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_magazine_follows.py -q
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

from app.cappe.routes import magazine as magazine_routes  # noqa: E402
from app.cappe.routes import reader as reader_mod  # noqa: E402
from app.cappe.services.email import dashboard_url  # noqa: E402
from app.cappe.services.magazine import follows, magazines, pages, shelf  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402

NOW = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
ACCOUNT = SimpleNamespace(id=uuid4(), plan="free", account_type="reader", email="rae@example.com", name="Rae")
OWNER_A, OWNER_B = uuid4(), uuid4()


def _site(slug, owner=OWNER_A, status="published"):
    return {"id": uuid4(), "slug": slug, "name": slug.title(), "subdomain": slug, "custom_domain": None,
            "account_id": owner, "status": status, "followed_at": NOW}


def _mag(site, **over):
    return {"site_id": site["id"], "enabled": True, "name": site["name"] + " Mag", "tagline": "t", "accent": "#123456",
            "paid_enabled": False, "lapsed_at": None, **over}


class Ent:
    def __init__(self, magazine):
        self.magazine = magazine

    def has(self, feature):
        return feature == "magazine" and self.magazine


def _entitlements(monkeypatch, by_plan):
    calls = []

    async def resolve(plan, conn=None):
        calls.append(plan)
        return Ent(by_plan.get(plan, False))

    monkeypatch.setattr(magazines, "resolve_entitlements", resolve)
    return calls


# ── which followed magazines are live ────────────────────────────────────────

def test_live_magazines_resolves_each_plan_once(monkeypatch):
    a, b, c = _site("a"), _site("b"), _site("c", owner=OWNER_B)
    conn = QueryConn(fetch={"FROM cappe_magazines": [_mag(a), _mag(b), _mag(c)],
                            "FROM cappe_accounts": [{"id": OWNER_A, "plan": "writer"},
                                                    {"id": OWNER_B, "plan": "free"}]})
    calls = _entitlements(monkeypatch, {"writer": True})
    live = asyncio.run(magazines.live_magazines(conn, [a, b, c]))
    assert set(live) == {a["id"], b["id"]} and live[a["id"]]["name"] == "A Mag"
    assert sorted(calls) == ["free", "writer"]


def test_a_magazine_without_the_plan_stays_live_in_grace_with_readers(monkeypatch):
    a = _site("a")
    conn = QueryConn(fetch={"FROM cappe_magazines": [_mag(a, paid_enabled=True)],
                            "FROM cappe_accounts": [{"id": OWNER_A, "plan": "free"}]},
                     fetchval={"FROM cappe_shopper_subscriptions": 1})
    _entitlements(monkeypatch, {})
    assert set(asyncio.run(magazines.live_magazines(conn, [a]))) == {a["id"]}


def test_no_sites_asks_nothing():
    conn = QueryConn()
    assert asyncio.run(magazines.live_magazines(conn, [])) == {} and conn.calls == []


def test_a_magazine_turned_off_is_never_asked_about_its_owner(monkeypatch):
    a = _site("a")
    conn = QueryConn(fetch={"FROM cappe_magazines": []})
    _entitlements(monkeypatch, {})
    assert asyncio.run(magazines.live_magazines(conn, [a])) == {}
    assert "WHERE site_id = ANY($1::uuid[]) AND enabled" in conn.calls[0][1]


# ── follow and unfollow ──────────────────────────────────────────────────────

def test_following_is_one_row_and_idempotent():
    site = _site("a")
    conn = QueryConn(fetchval={"COUNT(*)": 3})
    asyncio.run(follows.follow(conn, ACCOUNT.id, site))
    sql, args = [(c[1], c[2]) for c in conn.calls if c[0] == "execute"][0]
    assert "ON CONFLICT DO NOTHING" in sql and args == (ACCOUNT.id, site["id"])


def test_the_cap_refuses_a_new_follow_but_not_a_repeat():
    site = _site("a")
    at_cap = QueryConn(fetchval={"COUNT(*)": follows.FOLLOW_LIMIT, "SELECT 1 FROM": None})
    with pytest.raises(HTTPException) as err:
        asyncio.run(follows.follow(at_cap, ACCOUNT.id, site))
    assert err.value.status_code == 409 and err.value.detail["code"] == "follow_limit"
    again = QueryConn(fetchval={"COUNT(*)": follows.FOLLOW_LIMIT, "SELECT 1 FROM": 1})
    asyncio.run(follows.follow(again, ACCOUNT.id, site))


def _client(monkeypatch, conn):
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(reader_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(reader_mod, "check_rate_limit", _noop)
    return route_client(reader_mod.router, overrides={reader_mod.require_cappe_account: ACCOUNT})


def test_a_live_magazine_is_followed(monkeypatch):
    site = _site("salt")
    conn = QueryConn(fetchrow={"FROM cappe_sites": site}, fetchval={"COUNT(*)": 0})

    async def live(c, s):
        return _mag(site)

    monkeypatch.setattr(shelf, "live_magazine", live)
    with _client(monkeypatch, conn) as client:
        res = client.put("/reader/magazines/salt/follow")
    assert res.status_code == 200 and res.json() == {"following": True}
    assert any(k == "execute" and "INSERT INTO cappe_magazine_follows" in sql for k, sql, _ in conn.calls)


@pytest.mark.parametrize("site", [None, "down"])
def test_a_magazine_that_isnt_up_cant_be_followed(monkeypatch, site):
    row = _site("salt") if site else None
    conn = QueryConn(fetchrow={"FROM cappe_sites": row})

    async def live(c, s):
        return None

    monkeypatch.setattr(shelf, "live_magazine", live)
    with _client(monkeypatch, conn) as client:
        assert client.put("/reader/magazines/salt/follow").status_code == 404
    assert not any(k == "execute" for k, _sql, _ in conn.calls)


@pytest.mark.parametrize("site_id", [uuid4(), None])
def test_unfollowing_works_whatever_the_magazine_is_doing(monkeypatch, site_id):
    conn = QueryConn(fetchval={"FROM cappe_sites": site_id})
    with _client(monkeypatch, conn) as client:
        res = client.delete("/reader/magazines/salt/follow")
    assert res.status_code == 200 and res.json() == {"following": False}
    deletes = [args for k, sql, args in conn.calls if k == "execute" and "DELETE FROM cappe_magazine_follows" in sql]
    assert deletes == ([(ACCOUNT.id, site_id)] if site_id else [])


# ── the list and the feed ────────────────────────────────────────────────────

def test_the_following_list_keeps_a_magazine_thats_down(monkeypatch):
    up, down, draft = _site("up"), _site("down"), _site("draft", status="draft")
    conn = QueryConn(fetch={"FROM cappe_magazine_follows f": [up, down, draft]})
    seen = {}

    async def live(c, sites):
        seen["ids"] = [s["id"] for s in sites]
        return {up["id"]: _mag(up)}

    monkeypatch.setattr(follows, "live_magazines", live)
    with _client(monkeypatch, conn) as client:
        res = client.get("/reader/following")
    out = res.json()["magazines"]
    assert res.headers["cache-control"] == "no-store, private"
    assert seen["ids"] == [up["id"], down["id"]]  # a draft site is never live
    assert [(m["slug"], m["live"], m["name"]) for m in out] == [
        ("up", True, "Up Mag"), ("down", False, "Down"), ("draft", False, "Draft")]
    assert out[0]["origin"] and out[0]["accent"] == "#123456" and out[1]["accent"] is None


def test_an_empty_feed_reads_no_stories(monkeypatch):
    conn = QueryConn(fetch={"FROM cappe_magazine_follows f": [_site("a")]})

    async def live(c, sites):
        return {}

    monkeypatch.setattr(follows, "live_magazines", live)
    assert asyncio.run(follows.feed(conn, ACCOUNT.id)) == {"stories": [], "has_more": False, "page": 1}
    assert not any("FROM cappe_posts" in sql for _k, sql, _a in conn.calls)


def _post(site, slug):
    return {"id": uuid4(), "site_id": site["id"], "slug": slug, "title": slug, "excerpt": None, "kicker": None,
            "topic": None, "access": "free", "published_at": NOW, "reading_minutes": 3, "content": {"blocks": []},
            "cover_asset_id": None, "format": "blocks"}


def test_the_feed_is_live_followed_stories_newest_first_a_page_at_a_time(monkeypatch):
    a, b, gone = _site("a"), _site("b", owner=OWNER_B), _site("gone")
    posts = [_post(a if i % 2 else b, f"s{i}") for i in range(follows.FEED_PAGE + 1)]
    conn = QueryConn(fetch={"FROM cappe_magazine_follows f": [a, b, gone], "FROM cappe_posts": posts})
    cover_calls = []

    async def live(c, sites):
        return {a["id"]: _mag(a), b["id"]: _mag(b, accent=None)}

    async def covers(c, site_id, ps):
        cover_calls.append((site_id, len(ps)))
        return {}

    monkeypatch.setattr(follows, "live_magazines", live)
    monkeypatch.setattr(follows, "covers", covers)
    monkeypatch.setattr(follows, "post_row", lambda r: dict(r))
    out = asyncio.run(follows.feed(conn, ACCOUNT.id, page=2))
    sql, args = next((sql, args) for k, sql, args in conn.calls if "FROM cappe_posts" in sql)
    assert "ORDER BY published_at DESC NULLS LAST" in sql and "hidden_at IS NULL" in sql
    assert set(args[0]) == {a["id"], b["id"]} and args[1:] == (follows.FEED_PAGE + 1, follows.FEED_PAGE)
    assert out["has_more"] is True and out["page"] == 2 and len(out["stories"]) == follows.FEED_PAGE
    first = out["stories"][0]
    assert first["slug"] == "s0" and first["magazine"] == {"slug": "b", "name": "B Mag", "accent": None}
    assert sorted(n for _s, n in cover_calls) == [6, 6]  # one covers read per magazine on the page


def test_the_feed_route_pages(monkeypatch):
    got = {}

    async def feed(c, account_id, page=1):
        got["args"] = (account_id, page)
        return {"stories": [], "has_more": False, "page": page}

    monkeypatch.setattr(follows, "feed", feed)
    with _client(monkeypatch, QueryConn()) as client:
        assert client.get("/reader/feed?page=3").json()["page"] == 3
        assert client.get("/reader/feed?page=0").status_code == 422
    assert got["args"] == (ACCOUNT.id, 3)


# ── the owner's count ────────────────────────────────────────────────────────

def test_the_owner_sees_how_many_never_who(monkeypatch):
    site_id = uuid4()
    conn = QueryConn(fetchval={"FROM cappe_magazine_follows": 7})
    owned = []

    async def get_owned(c, sid, account_id):
        owned.append((sid, account_id))
        return {"id": sid}

    monkeypatch.setattr(magazine_routes, "get_connection", lambda: conn)
    monkeypatch.setattr(magazine_routes, "get_owned_site", get_owned)
    owner = SimpleNamespace(id=uuid4(), plan="writer", account_type="writer")
    with route_client(magazine_routes.router, overrides={magazine_routes.require_cappe_account: owner}) as client:
        res = client.get(f"/sites/{site_id}/magazine/follows")
    assert res.json() == {"accounts": 7} and owned == [(site_id, owner.id)]


# ── the follow box on the magazine's page ────────────────────────────────────

def test_the_follow_box_links_to_following_on_the_dashboard():
    mag = {"name": "Salt", "follow_enabled": True}
    html = pages.follow_html(mag, "salt")
    assert f'href="{dashboard_url("/reader/m/salt")}?follow=1"' in html and "data-mz-alt" in html
    assert "data-mz-alt" not in pages.follow_html(mag)
    assert pages.follow_html({**mag, "follow_enabled": False}, "salt") == ""


def test_every_page_with_the_box_passes_its_slug():
    import inspect
    from app.cappe.services.magazine import issue_pages

    for mod in (pages, issue_pages):
        assert "follow_html(mag)" not in inspect.getsource(mod)


