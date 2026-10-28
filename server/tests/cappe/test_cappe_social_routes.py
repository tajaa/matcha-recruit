"""Cappe social — the HTTP surface and the three worker tasks.

Owner routes (`routes/social.py`) are mounted alone with the auth dependency
overridden; the stores beneath them are faked so each test pins one route's
decision: ownership 404s, the two plan gates (402), schedule validation, which
posts may be edited / published / deleted, the one-row-per-send rule for
replies, and that no pooled connection is held while a model or the network
is called. The public Meta routes (`routes/public/social_meta.py`) pin the
OAuth state + browser-nonce check and the webhook signature. The worker
tasks pin the single-chain guard, the plan re-check before auto-replying and
that one bad item never drops a batch.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_social_routes.py -q
"""
import asyncio
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qs, urlsplit
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.dependencies import require_cappe_account  # noqa: E402
from app.cappe.models.auth import CappeAccount  # noqa: E402
from app.cappe.routes import social as social_routes  # noqa: E402
from app.cappe.routes.public import social_meta  # noqa: E402
from app.cappe.services.social import ai as social_ai  # noqa: E402
from app.cappe.services.social import autoreply, captions, oauth, outbound  # noqa: E402
from app.cappe.services.social import connections as conn_store  # noqa: E402
from app.cappe.services.social import inbox as inbox_store  # noqa: E402
from app.cappe.services.social import posts as post_store  # noqa: E402
from app.cappe.services.social.providers import meta  # noqa: E402
from app.cappe.services.social.providers.base import ConnectionDraft, InboundEvent, ProviderError  # noqa: E402
from app.workers.tasks import cappe_social_inbound as inbound_task  # noqa: E402
from app.workers.tasks import cappe_social_metrics as metrics_task  # noqa: E402
from app.workers.tasks import cappe_social_publisher as publisher_task  # noqa: E402
from tests._helpers.routes import QueryConn, Queue, route_client  # noqa: E402

SITE, CONN_ID, POST_ID, INBOX_ID = uuid4(), uuid4(), uuid4(), uuid4()
ACCOUNT = CappeAccount(id=uuid4(), email="owner@example.com", name="Owner", plan="business")
NOW = datetime.now(timezone.utc).replace(microsecond=0)
CFG = meta.MetaConfig(app_id="app1", app_secret="shh", verify_token="vt")
IMG = {"url": "https://cdn.example.test/a.jpg", "kind": "image", "alt": None}
SITE_ROW = {"id": SITE, "name": "Po Coffee", "subdomain": "po", "custom_domain": None, "account_id": ACCOUNT.id}
BASE = f"/sites/{SITE}/social"


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TxConn(QueryConn):
    """QueryConn plus the two things routes and tasks also call."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.closed = False

    def transaction(self):
        return _Tx()

    async def close(self):
        self.closed = True


def ent(*features):
    return SimpleNamespace(has=lambda f: f in features)


def connection(**over):
    return {"id": CONN_ID, "site_id": SITE, "account_id": ACCOUNT.id, "platform": "instagram", "external_id": "ig1",
            "handle": "pocoffee", "display_name": "pocoffee", "avatar_url": None, "status": "connected",
            "last_error": None, "followers_count": 812, "metrics": {}, "metrics_at": None, "token_expires_at": None,
            "connected_at": NOW, "updated_at": NOW, **over}


def post(**over):
    return {"id": POST_ID, "site_id": SITE, "caption": "Fresh roast", "media": [IMG], "link_url": None,
            "product_id": None, "status": "draft", "scheduled_at": None, "published_at": None, "ai_meta": {},
            "created_at": NOW, "updated_at": NOW,
            "targets": [{"id": uuid4(), "post_id": POST_ID, "connection_id": CONN_ID, "platform": "instagram",
                         "handle": "pocoffee", "status": "pending", "attempts": 0, "metrics": {}}], **over}


def inbox_item(**over):
    return {"id": INBOX_ID, "site_id": SITE, "connection_id": CONN_ID, "platform": "instagram", "handle": "pocoffee",
            "kind": "comment", "external_id": "c1", "external_parent_id": "m1", "author_external_id": "u1",
            "author_name": "maya", "text": "Do you have oat milk?", "received_at": NOW, "status": "new",
            "classification": {}, "replies": [], **over}


def reply(**over):
    return {"id": uuid4(), "inbox_id": INBOX_ID, "site_id": SITE, "body": "Yes, oat milk is free.", "mode": "approved",
            "status": "draft", "model": "claude-haiku-5-5", "grounding": {}, "external_reply_id": None, "error": None,
            "created_at": NOW, "sent_at": None, **over}


@pytest.fixture
def world(monkeypatch):
    """Owner routes against faked stores. `world.conn` answers ownership and
    counts; tests swap any store function they care about."""
    conn = TxConn(fetchrow={
        "FROM cappe_sites WHERE id = $1 AND account_id": SITE_ROW,
        "count(*) FILTER (WHERE status = 'scheduled')": {"scheduled": 2, "published_30d": 5},
    })
    opened = []

    def get_connection():
        opened.append(conn)
        return conn

    monkeypatch.setattr(social_routes, "get_connection", get_connection)
    monkeypatch.setattr(social_routes, "resolve_entitlements", AsyncMock(return_value=ent("social", "social_autoreply")))
    monkeypatch.setattr(social_routes, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(social_ai, "available", AsyncMock(return_value=True))
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: CFG))
    monkeypatch.setattr(conn_store, "list_connections", AsyncMock(return_value=[connection()]))
    monkeypatch.setattr(inbox_store, "counts", AsyncMock(return_value={"new": 3, "waiting": 1}))
    monkeypatch.setattr(inbox_store, "get_settings", AsyncMock(return_value=dict(inbox_store.SETTINGS_DEFAULTS)))
    w = SimpleNamespace(conn=conn, opened=opened, mp=monkeypatch)
    with route_client(social_routes.router, overrides={require_cappe_account: ACCOUNT}) as client:
        w.client = client
        yield w


def plan(world, *features):
    world.mp.setattr(social_routes, "resolve_entitlements", AsyncMock(return_value=ent(*features)))


def unconfigured(world):
    world.mp.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))


# ── helpers ─────────────────────────────────────────────────────────────────

def test_check_schedule_accepts_the_future_only():
    assert social_routes.check_schedule(None) is None
    naive = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    assert social_routes.check_schedule(naive).tzinfo is not None
    for when in (datetime.now(timezone.utc) - timedelta(hours=1),
                 datetime.now(timezone.utc) + timedelta(days=400)):
        with pytest.raises(HTTPException) as info:
            social_routes.check_schedule(when)
        assert info.value.status_code == 422


def test_redirect_uri_is_the_public_callback():
    assert social_routes.oauth_redirect_uri().endswith("/api/cappe/public/social/meta/callback")


# ── overview / accounts / settings ──────────────────────────────────────────

def test_overview(world):
    body = world.client.get(f"{BASE}/overview").json()
    assert body["connections"] == 1 and body["scheduled"] == 2 and body["published_30d"] == 5
    assert body["inbox_new"] == 3 and body["drafts_waiting"] == 1 and body["meta_configured"] is True
    assert body["followers"] == [{"platform": "instagram", "handle": "pocoffee", "followers_count": 812}]


def test_someone_elses_site_is_404(world):
    world.conn.set("fetchrow", "FROM cappe_sites WHERE id = $1 AND account_id", None)
    assert world.client.get(f"{BASE}/overview").status_code == 404
    assert world.client.get(f"{BASE}/connections").status_code == 404


def test_connections_never_carry_a_token(world):
    body = world.client.get(f"{BASE}/connections").json()
    assert body["configured"] is True and body["connections"][0]["handle"] == "pocoffee"
    assert "access_token" not in json.dumps(body)


def test_connect_start_sets_the_nonce_cookie_inside_the_state(world):
    resp = world.client.post(f"{BASE}/connections/meta/start")
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{oauth.NONCE_COOKIE}=") and "HttpOnly" in cookie and "Secure" in cookie
    assert f"Path={oauth.NONCE_COOKIE_PATH}" in cookie and "samesite=lax" in cookie.lower()
    nonce = cookie.split(";")[0].split("=", 1)[1]
    from urllib.parse import parse_qsl
    state = dict(parse_qsl(resp.json()["authorize_url"].split("?", 1)[1]))["state"]
    assert oauth.read_state(state, nonce_cookie=nonce) == {"site_id": SITE, "account_id": ACCOUNT.id}


def test_connect_start_refusals(world):
    plan(world)
    assert world.client.post(f"{BASE}/connections/meta/start").status_code == 402
    unconfigured(world)
    assert world.client.post(f"{BASE}/connections/meta/start").status_code == 503


def test_disconnect(world):
    world.mp.setattr(conn_store, "delete_connection", AsyncMock(side_effect=[True, False]))
    assert world.client.delete(f"{BASE}/connections/{CONN_ID}").status_code == 204
    assert world.client.delete(f"{BASE}/connections/{CONN_ID}").status_code == 404


def test_an_accounts_inbox_is_switched_on_its_own_site(world):
    setter = AsyncMock(side_effect=[connection(inbox_enabled=False), None])
    world.mp.setattr(conn_store, "set_inbox_enabled", setter)
    resp = world.client.patch(f"{BASE}/connections/{CONN_ID}", json={"inbox_enabled": False})
    assert resp.status_code == 200 and resp.json()["inbox_enabled"] is False
    assert setter.await_args.args[1:] == (SITE, CONN_ID, False)
    assert world.client.patch(f"{BASE}/connections/{CONN_ID}", json={"inbox_enabled": True}).status_code == 404
    assert world.client.patch(f"{BASE}/connections/{CONN_ID}", json={}).status_code == 422


def test_settings_read_and_the_ai_inbox_gate(world):
    upsert = AsyncMock()
    world.mp.setattr(inbox_store, "upsert_settings", upsert)
    body = world.client.get(f"{BASE}/settings").json()
    assert body["autoreply_mode"] == "off" and body["autoreply_available"] is True and body["ai_available"] is True
    assert world.client.put(f"{BASE}/settings", json={"autoreply_mode": "auto", "tone": "playful"}).status_code == 200
    assert upsert.await_args.args[2] == {"autoreply_mode": "auto", "tone": "playful"}
    plan(world, "social")
    assert world.client.put(f"{BASE}/settings", json={"autoreply_mode": "review"}).status_code == 402
    # Downgraded with review still stored: saving the form (which sends the
    # stored mode back) works; switching to another paid mode doesn't.
    world.mp.setattr(inbox_store, "get_settings", AsyncMock(return_value={"autoreply_mode": "review"}))
    assert world.client.put(f"{BASE}/settings", json={"autoreply_mode": "review", "tone": "playful"}).status_code == 200
    assert world.client.put(f"{BASE}/settings", json={"autoreply_mode": "auto"}).status_code == 402
    assert world.client.put(f"{BASE}/settings", json={"business_facts": "Ships Mon"}).status_code == 200
    assert world.client.get(f"{BASE}/settings").json()["autoreply_available"] is False
    assert world.client.put(f"{BASE}/settings", json={}).status_code == 200
    assert upsert.await_count == 3


# ── posts ───────────────────────────────────────────────────────────────────

def _in(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def test_list_posts_passes_the_filter(world):
    listed = AsyncMock(return_value=[post()])
    world.mp.setattr(post_store, "list_posts", listed)
    body = world.client.get(f"{BASE}/posts?status=scheduled&limit=5").json()
    assert body[0]["targets"][0]["platform"] == "instagram"
    assert listed.await_args.kwargs == {"status": "scheduled", "limit": 5, "offset": 0}
    assert world.client.get(f"{BASE}/posts?status=bogus").status_code == 422


def test_create_a_scheduled_post(world):
    created = AsyncMock(return_value=post())
    targets = AsyncMock()
    world.mp.setattr(post_store, "create_post", created)
    world.mp.setattr(post_store, "set_targets", targets)
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=post(status="scheduled")))
    resp = world.client.post(f"{BASE}/posts", json={
        "caption": "Fresh roast", "media": [IMG], "connection_ids": [str(CONN_ID)], "scheduled_at": _in(),
        "alt_text": "a cup",
    })
    assert resp.status_code == 201 and resp.json()["status"] == "scheduled"
    kw = created.await_args.kwargs
    assert kw["scheduled_at"] is not None and kw["ai_meta"] == {"alt_text": "a cup"} and kw["media"][0]["url"] == IMG["url"]
    assert targets.await_args.args[2] == [CONN_ID]


def test_a_draft_needs_no_account_but_a_schedule_does(world):
    world.mp.setattr(post_store, "create_post", AsyncMock(return_value=post()))
    world.mp.setattr(post_store, "set_targets", AsyncMock())
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=post()))
    assert world.client.post(f"{BASE}/posts", json={"caption": "Idea"}).status_code == 201
    resp = world.client.post(f"{BASE}/posts", json={"caption": "x", "scheduled_at": _in()})
    assert resp.status_code == 422 and "account" in resp.json()["detail"]


def test_create_refusals(world):
    resp = world.client.post(f"{BASE}/posts", json={"caption": "No photo", "connection_ids": [str(CONN_ID)],
                                                     "scheduled_at": _in()})
    assert resp.status_code == 422 and "photo" in resp.json()["detail"]
    assert world.client.post(f"{BASE}/posts", json={"caption": "x", "connection_ids": [str(uuid4())]}).status_code == 404
    plan(world)
    assert world.client.post(f"{BASE}/posts", json={"caption": "x"}).status_code == 402


def test_get_post(world):
    world.mp.setattr(post_store, "get_post", AsyncMock(side_effect=[post(), None]))
    assert world.client.get(f"{BASE}/posts/{POST_ID}").status_code == 200
    assert world.client.get(f"{BASE}/posts/{POST_ID}").status_code == 404


def test_edit_reschedule_and_retarget(world):
    update, targets, schedule = AsyncMock(), AsyncMock(), AsyncMock(return_value=True)
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=post()))
    world.mp.setattr(post_store, "update_post", update)
    world.mp.setattr(post_store, "set_targets", targets)
    world.mp.setattr(post_store, "set_schedule", schedule)
    resp = world.client.patch(f"{BASE}/posts/{POST_ID}", json={
        "caption": None, "media": [IMG], "connection_ids": [str(CONN_ID)], "scheduled_at": _in(), "alt_text": "cup",
    })
    assert resp.status_code == 200
    fields = update.await_args.args[3]
    assert fields["caption"] == "" and fields["media"][0]["url"] == IMG["url"] and fields["ai_meta"] == {"alt_text": "cup"}
    assert targets.await_args.args[2] == [CONN_ID] and schedule.await_args.args[3] is not None
    resp = world.client.patch(f"{BASE}/posts/{POST_ID}", json={"scheduled_at": None})
    assert resp.status_code == 200 and schedule.await_args.args[3] is None


def test_edit_refusals(world):
    world.mp.setattr(post_store, "get_post", AsyncMock(side_effect=[None, post(status="published"),
                                                                    post(targets=[]), post(media=[])]))
    assert world.client.patch(f"{BASE}/posts/{POST_ID}", json={"caption": "x"}).status_code == 404
    assert world.client.patch(f"{BASE}/posts/{POST_ID}", json={"caption": "x"}).status_code == 409
    assert world.client.patch(f"{BASE}/posts/{POST_ID}", json={"scheduled_at": _in()}).status_code == 422
    resp = world.client.patch(f"{BASE}/posts/{POST_ID}", json={"scheduled_at": _in()})
    assert resp.status_code == 422 and "photo" in resp.json()["detail"]


def test_publish_now_dispatches_the_post(world):
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=post()))
    now = AsyncMock(return_value=True)
    world.mp.setattr(post_store, "publish_now", now)
    delay = Mock()
    world.mp.setattr(publisher_task.run_cappe_social_publish_post, "delay", delay)
    assert world.client.post(f"{BASE}/posts/{POST_ID}/publish").status_code == 200
    now.assert_awaited_once()
    delay.assert_called_once_with(str(POST_ID))
    world.mp.setattr(publisher_task.run_cappe_social_publish_post, "delay", Mock(side_effect=RuntimeError("no broker")))
    assert world.client.post(f"{BASE}/posts/{POST_ID}/publish").status_code == 200


def test_a_partial_post_retries_only_what_didnt_go_out(world):
    ig_done = {"id": uuid4(), "post_id": POST_ID, "connection_id": uuid4(), "platform": "instagram", "handle": "po",
               "status": "published", "attempts": 1, "metrics": {}}
    fb_failed = {"id": uuid4(), "post_id": POST_ID, "connection_id": CONN_ID, "platform": "facebook", "handle": None,
                 "status": "failed", "attempts": 3, "metrics": {}, "error": "Meta: down"}
    # Caption-only is fine for the Facebook retry even though Instagram (already out) needed a photo.
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=post(status="partial", media=[],
                                                                        targets=[ig_done, fb_failed])))
    world.mp.setattr(post_store, "publish_now", AsyncMock(return_value=True))
    world.mp.setattr(publisher_task.run_cappe_social_publish_post, "delay", Mock())
    assert world.client.post(f"{BASE}/posts/{POST_ID}/publish").status_code == 200


@pytest.mark.parametrize("current,code", [
    (None, 404),
    (post(status="published"), 409),
    (post(targets=[]), 422),
    (post(media=[]), 422),
])
def test_publish_refusals(world, current, code):
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=current))
    assert world.client.post(f"{BASE}/posts/{POST_ID}/publish").status_code == code


def test_publish_refusals_by_plan_and_setup(world):
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=post()))
    unconfigured(world)
    assert world.client.post(f"{BASE}/posts/{POST_ID}/publish").status_code == 503
    plan(world)
    assert world.client.post(f"{BASE}/posts/{POST_ID}/publish").status_code == 402


def test_cancel_and_delete(world):
    world.mp.setattr(post_store, "cancel_post", AsyncMock(side_effect=[True, False]))
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=post(status="cancelled")))
    assert world.client.post(f"{BASE}/posts/{POST_ID}/cancel").json()["status"] == "cancelled"
    assert world.client.post(f"{BASE}/posts/{POST_ID}/cancel").status_code == 409
    world.mp.setattr(post_store, "delete_post", AsyncMock(side_effect=[True, False]))
    assert world.client.delete(f"{BASE}/posts/{POST_ID}").status_code == 204
    assert world.client.delete(f"{BASE}/posts/{POST_ID}").status_code == 409


def test_dropped_photos_are_normalized_and_cataloged(world):
    from io import BytesIO

    from PIL import Image

    from app.cappe.services import cappe_assets

    buf = BytesIO()
    Image.new("RGB", (600, 1600), (10, 120, 200)).save(buf, format="PNG")
    stored = {}

    class Storage:
        async def upload_file(self, **kw):
            stored.update(kw)
            return "https://cdn.example.test/cappe/social/photo.jpg"

    world.mp.setattr(social_routes, "get_storage", lambda: Storage())
    record = AsyncMock(side_effect=RuntimeError("catalog down"))
    world.mp.setattr(cappe_assets, "record", record)
    resp = world.client.post(f"{BASE}/media", files={"file": ("story.png", buf.getvalue(), "image/png")})
    assert resp.status_code == 200
    assert resp.json() == {"url": "https://cdn.example.test/cappe/social/photo.jpg", "width": 1152, "height": 1440,
                           "padded": True}
    assert stored["content_type"] == "image/jpeg" and stored["filename"] == "story.jpg" and stored["prefix"] == "cappe/social"
    record.assert_awaited_once()


def test_photo_upload_refusals(world):
    assert world.client.post(f"{BASE}/media", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 400
    assert world.client.post(f"{BASE}/media", files={"file": ("a.png", b"", "image/png")}).status_code == 400
    plan(world)
    assert world.client.post(f"{BASE}/media", files={"file": ("a.png", b"x", "image/png")}).status_code == 402


def test_captions(world):
    world.conn.set("fetchrow", "FROM cappe_products WHERE id = $1", {"name": "Beans", "description": None,
                                                                     "price_cents": 1800, "currency": "USD"})
    drafted = AsyncMock(return_value={"options": [{"text": "Hi", "hashtags": ["#a"]}], "alt_text": None,
                                      "model": "claude-haiku-5-5"})
    world.mp.setattr(captions, "draft_captions", drafted)
    resp = world.client.post(f"{BASE}/captions", json={"media": [IMG], "product_id": str(uuid4()), "brief": "launch"})
    assert resp.status_code == 200 and resp.json()["options"][0]["text"] == "Hi"
    kw = drafted.await_args.kwargs
    assert kw["product"]["name"] == "Beans" and kw["tone"] == "friendly" and kw["store_url"].startswith("https://po.")
    social_routes.check_rate_limit.assert_awaited()
    world.mp.setattr(captions, "draft_captions", AsyncMock(side_effect=social_ai.AiUnavailable("no key")))
    assert world.client.post(f"{BASE}/captions", json={}).status_code == 503
    world.mp.setattr(captions, "draft_captions", AsyncMock(side_effect=RuntimeError("declined")))
    assert world.client.post(f"{BASE}/captions", json={}).status_code == 502
    plan(world)
    assert world.client.post(f"{BASE}/captions", json={}).status_code == 402


# ── inbox ───────────────────────────────────────────────────────────────────

def test_list_inbox(world):
    world.mp.setattr(inbox_store, "list_inbox", AsyncMock(return_value=[inbox_item(replies=[reply()])]))
    body = world.client.get(f"{BASE}/inbox?status=new").json()
    assert body[0]["replies"][0]["status"] == "draft"


class Held:
    """Counts how many connections are open when a fake network call runs."""

    def __init__(self, world):
        self.world, self.depth, self.seen = world, 0, []
        conn = world.conn

        class Ctx:
            async def __aenter__(_):
                self.depth += 1
                return conn

            async def __aexit__(_, *exc):
                self.depth -= 1
                return False

        world.mp.setattr(social_routes, "get_connection", lambda: Ctx())

    def probe(self, result=None, error=None):
        async def call(*a, **kw):
            self.seen.append(self.depth)
            if error:
                raise error
            return result
        return call


def test_draft_on_demand_holds_no_connection_during_the_model_call(world):
    held = Held(world)
    world.mp.setattr(inbox_store, "get_item", AsyncMock(return_value=inbox_item()))
    world.mp.setattr(autoreply, "load_grounding", AsyncMock(return_value=autoreply.Grounding("Po", None)))
    world.mp.setattr(social_ai, "model_for", AsyncMock(return_value="claude-haiku-5-5"))
    d = autoreply.Draft("product_question", "neutral", "Yes!", 0.9, False, ["x"], "claude-haiku-5-5")
    world.mp.setattr(autoreply, "draft_reply", held.probe(result=d))
    created, status = AsyncMock(), AsyncMock()
    world.mp.setattr(inbox_store, "create_reply", created)
    world.mp.setattr(inbox_store, "set_item_status", status)
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/draft").status_code == 200
    assert held.seen == [0]
    assert created.await_args.kwargs["mode"] == "approved" and created.await_args.kwargs["status"] == "draft"
    assert status.await_args.args[2] == "drafted"


def test_draft_on_demand_escalates_when_the_model_wants_a_person(world):
    world.mp.setattr(inbox_store, "get_item", AsyncMock(return_value=inbox_item()))
    world.mp.setattr(autoreply, "load_grounding", AsyncMock(return_value=autoreply.Grounding("Po", None)))
    world.mp.setattr(social_ai, "model_for", AsyncMock(return_value="m"))
    world.mp.setattr(autoreply, "draft_reply", AsyncMock(return_value=autoreply.Draft(
        "complaint", "negative", None, 0.2, True, [], "m")))
    created, status = AsyncMock(), AsyncMock()
    world.mp.setattr(inbox_store, "create_reply", created)
    world.mp.setattr(inbox_store, "set_item_status", status)
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/draft").status_code == 200
    created.assert_not_awaited()
    assert status.await_args.args[2] == "escalated"


def test_draft_on_demand_refusals(world):
    world.mp.setattr(inbox_store, "get_item", AsyncMock(side_effect=[None, inbox_item(), inbox_item()]))
    world.mp.setattr(autoreply, "load_grounding", AsyncMock(return_value=autoreply.Grounding("Po", None)))
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/draft").status_code == 404
    world.mp.setattr(social_ai, "model_for", AsyncMock(return_value=None))
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/draft").status_code == 503
    world.mp.setattr(social_ai, "model_for", AsyncMock(return_value="m"))
    world.mp.setattr(autoreply, "draft_reply", AsyncMock(side_effect=RuntimeError("declined")))
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/draft").status_code == 502
    plan(world, "social")
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/draft").status_code == 402


@pytest.fixture
def replying(world):
    marks, created = [], []

    async def mark(conn, reply_id, **kw):
        marks.append((reply_id, kw["status"]))

    async def create(conn, **kw):
        row = reply(id=uuid4(), **{k: kw[k] for k in ("body", "mode", "status")})
        created.append(row)
        return row

    world.mp.setattr(inbox_store, "get_item", AsyncMock(return_value=inbox_item()))
    world.mp.setattr(inbox_store, "mark_reply", mark)

    async def claim(conn, reply_id):
        marks.append((reply_id, "sending"))
        return True
    world.mp.setattr(inbox_store, "claim_draft", claim)
    world.mp.setattr(inbox_store, "create_reply", create)
    world.mp.setattr(inbox_store, "set_item_status", AsyncMock())
    world.mp.setattr(outbound, "reply_credentials", AsyncMock(return_value={"id": CONN_ID, "platform": "instagram"}))
    world.mp.setattr(outbound, "note_send_failure", AsyncMock())
    world.marks, world.created = marks, created
    return world


def test_an_unedited_draft_carries_its_own_send(replying):
    draft = reply()
    replying.mp.setattr(inbox_store, "get_reply", AsyncMock(return_value=draft))
    held = Held(replying)
    replying.mp.setattr(outbound, "send_with", held.probe(result="r9"))
    resp = replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply", json={"body": draft["body"], "reply_id": str(draft["id"])})
    assert resp.status_code == 200 and held.seen == [0]
    assert replying.created == []
    assert replying.marks == [(draft["id"], "sending"), (draft["id"], "sent")]


def test_an_edited_draft_is_rejected_and_the_edit_is_what_is_sent(replying):
    draft = reply()
    replying.mp.setattr(inbox_store, "get_reply", AsyncMock(return_value=draft))
    replying.mp.setattr(outbound, "send_with", AsyncMock(return_value="r9"))
    resp = replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply", json={"body": "Yes — and it's free!",
                                                                        "reply_id": str(draft["id"])})
    assert resp.status_code == 200
    assert replying.marks[0] == (draft["id"], "rejected")
    assert replying.created[0]["mode"] == "approved" and replying.created[0]["body"] == "Yes — and it's free!"
    assert replying.marks[-1] == (replying.created[0]["id"], "sent")


def test_the_owners_own_words_and_a_failed_send(replying):
    replying.mp.setattr(outbound, "send_with", AsyncMock(side_effect=ProviderError("token", code=190)))
    resp = replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply", json={"body": "Thanks!"})
    assert resp.status_code == 502
    assert replying.created[0]["mode"] == "manual" and replying.marks[-1][1] == "failed"
    outbound.note_send_failure.assert_awaited_once()


def test_a_draft_already_taken_is_not_sent_twice(replying):
    draft = reply()
    replying.mp.setattr(inbox_store, "get_reply", AsyncMock(return_value=draft))
    replying.mp.setattr(inbox_store, "claim_draft", AsyncMock(return_value=False))
    send = AsyncMock(return_value="r9")
    replying.mp.setattr(outbound, "send_with", send)
    resp = replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply", json={"body": draft["body"], "reply_id": str(draft["id"])})
    assert resp.status_code == 409 and not send.await_count


def test_reply_refusals(replying):
    replying.mp.setattr(inbox_store, "get_reply", AsyncMock(return_value=reply(inbox_id=uuid4())))
    assert replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply",
                                json={"body": "x", "reply_id": str(uuid4())}).status_code == 404
    replying.mp.setattr(outbound, "reply_credentials", AsyncMock(side_effect=ProviderError("reconnect")))
    assert replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply", json={"body": "x"}).status_code == 409
    replying.mp.setattr(inbox_store, "get_item", AsyncMock(return_value=None))
    assert replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply", json={"body": "x"}).status_code == 404
    unconfigured(replying)
    assert replying.client.post(f"{BASE}/inbox/{INBOX_ID}/reply", json={"body": "x"}).status_code == 503


def test_skip_rejects_open_drafts(world):
    d = reply()
    world.mp.setattr(inbox_store, "get_item", AsyncMock(side_effect=[
        inbox_item(replies=[d, reply(status="sent")]), inbox_item(status="skipped"), None]))
    marks, status = AsyncMock(), AsyncMock()
    world.mp.setattr(inbox_store, "mark_reply", marks)
    world.mp.setattr(inbox_store, "set_item_status", status)
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/skip").json()["status"] == "skipped"
    assert marks.await_count == 1 and marks.await_args.args[1] == d["id"]
    assert world.client.post(f"{BASE}/inbox/{INBOX_ID}/skip").status_code == 404


# ── public Meta routes ──────────────────────────────────────────────────────

@pytest.fixture
def public(monkeypatch):
    conn = TxConn(fetchrow={"FROM cappe_sites WHERE id = $1 AND account_id": {"id": SITE}})
    monkeypatch.setattr(social_meta, "get_connection", lambda: conn)
    monkeypatch.setattr(social_meta, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: CFG))
    drafts = [ConnectionDraft("facebook", "p1", "pt", scopes=meta.SCOPES),
              ConnectionDraft("instagram", "ig1", "pt", scopes=meta.SCOPES)]
    monkeypatch.setattr(meta, "exchange_code", AsyncMock(return_value=drafts))
    monkeypatch.setattr(meta, "subscribe_page", AsyncMock(return_value=True))
    monkeypatch.setattr(conn_store, "save_drafts", AsyncMock(return_value=[{"platform": "facebook"},
                                                                            {"platform": "instagram"}]))
    delay = Mock()
    monkeypatch.setattr(inbound_task.run_cappe_social_inbound, "delay", delay)
    with route_client(social_meta.router) as client:
        yield SimpleNamespace(client=client, conn=conn, mp=monkeypatch, delay=delay)


def _callback(public, *, nonce="n1", cookie="n1", **params):
    state = oauth.make_state(SITE, ACCOUNT.id, nonce)
    query = {"state": state, **params}
    headers = {"cookie": f"{oauth.NONCE_COOKIE}={cookie}"} if cookie else {}
    return public.client.get("/public/social/meta/callback", params=query, headers=headers, follow_redirects=False)


def test_callback_connects_and_sends_the_owner_back(public):
    resp = _callback(public, code="the-code")
    assert resp.status_code == 302
    assert resp.headers["location"].endswith(f"/cappe/sites/{SITE}/social?connected=facebook%2Cinstagram")
    assert f"{oauth.NONCE_COOKIE}=" in resp.headers["set-cookie"] and "Max-Age=0" in resp.headers["set-cookie"]
    kw = conn_store.save_drafts.await_args.kwargs
    assert kw["site_id"] == SITE and kw["account_id"] == ACCOUNT.id
    meta.subscribe_page.assert_awaited_once_with(CFG, "p1", "pt")


def test_callback_says_what_wasnt_granted_and_which_inboxes_start_off(public):
    drafts = [ConnectionDraft("facebook", "p1", "pt", scopes=("pages_show_list", "pages_manage_posts")),
              ConnectionDraft("instagram", "ig1", "pt", scopes=("instagram_basic", "instagram_content_publish"))]
    public.mp.setattr(meta, "exchange_code", AsyncMock(return_value=drafts))
    public.mp.setattr(conn_store, "save_drafts", AsyncMock(return_value=[
        {"platform": "facebook", "inbox_enabled": False, "is_new": True},
        {"platform": "facebook", "inbox_enabled": False, "is_new": True},
        {"platform": "instagram", "inbox_enabled": True, "is_new": True}]))
    location = _callback(public, code="the-code").headers["location"]
    query = parse_qs(urlsplit(location).query)
    # Codes, never prose: the page words them, so a crafted link can't speak for us.
    assert query["social_missing"] == ["instagram_manage_comments,instagram_manage_messages,"
                                       "pages_manage_engagement,pages_messaging"]
    assert query["social_inbox_off"] == ["2"] and "social_warning" not in query


def test_connect_notes_are_empty_when_all_is_well():
    drafts = [ConnectionDraft("facebook", "p1", "pt", scopes=meta.SCOPES)]
    assert social_meta.connect_notes(drafts, [{"inbox_enabled": True, "is_new": True}]) == {}


def test_connect_notes_count_only_the_accounts_this_connect_added_with_their_inbox_off():
    drafts = [ConnectionDraft("facebook", "p1", "pt", scopes=meta.SCOPES)]
    rows = [{"inbox_enabled": False, "is_new": False},   # the owner's own earlier choice
            {"inbox_enabled": False, "is_new": True},
            {"inbox_enabled": True, "is_new": True}]
    assert social_meta.connect_notes(drafts, rows) == {"social_inbox_off": "1"}


def test_callback_from_another_browser_is_refused(public):
    assert _callback(public, code="c", cookie="someone-else").status_code == 400
    assert _callback(public, code="c", cookie=None).status_code == 400
    conn_store.save_drafts.assert_not_awaited()


@pytest.mark.parametrize("setup,params,fragment", [
    (None, {"error": "access_denied", "error_description": "User denied"}, "social_error=User%20denied"),
    (None, {}, "social_error="),
    ("exchange_fails", {"code": "c"}, "social_error=Meta%3A%20bad"),
    ("no_pages", {"code": "c"}, "No%20Facebook%20Page"),
    ("unconfigured", {"code": "c"}, "set%20up"),
])
def test_callback_failures_return_to_the_page(public, setup, params, fragment):
    if setup == "exchange_fails":
        public.mp.setattr(meta, "exchange_code", AsyncMock(side_effect=ProviderError("Meta: bad")))
    elif setup == "no_pages":
        public.mp.setattr(meta, "exchange_code", AsyncMock(return_value=[]))
    elif setup == "unconfigured":
        public.mp.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    resp = _callback(public, **params)
    assert resp.status_code == 302 and fragment in resp.headers["location"]
    conn_store.save_drafts.assert_not_awaited()


def test_callback_for_a_site_the_account_lost_is_404(public):
    public.conn.set("fetchrow", "FROM cappe_sites WHERE id = $1 AND account_id", None)
    assert _callback(public, code="c").status_code == 404


def test_webhook_challenge(public):
    ok = {"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"}
    resp = public.client.get("/public/social/meta/webhook", params=ok)
    assert resp.status_code == 200 and resp.text == "42"
    assert public.client.get("/public/social/meta/webhook", params={**ok, "hub.verify_token": "x"}).status_code == 403
    public.mp.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    assert public.client.get("/public/social/meta/webhook", params=ok).status_code == 403


def _signed(body: bytes, secret=b"shh"):
    return {"x-hub-signature-256": "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest(),
            "content-type": "application/json"}


COMMENT = {"object": "instagram", "entry": [{"id": "ig1", "changes": [
    {"field": "comments", "value": {"id": "c1", "text": "Oat milk?", "from": {"id": "u1", "username": "maya"}}}]}]}


def test_webhook_hands_verified_events_to_the_worker(public):
    body = json.dumps(COMMENT).encode()
    resp = public.client.post("/public/social/meta/webhook", content=body, headers=_signed(body))
    assert resp.status_code == 200 and resp.json() == {"received": 1}
    events = public.delay.call_args.args[0]
    assert events[0]["external_id"] == "c1" and events[0]["kind"] == "comment"
    empty = json.dumps({"object": "instagram", "entry": []}).encode()
    assert public.client.post("/public/social/meta/webhook", content=empty, headers=_signed(empty)).json() == {"received": 0}
    assert public.delay.call_count == 1


def test_webhook_refusals(public):
    body = json.dumps(COMMENT).encode()
    assert public.client.post("/public/social/meta/webhook", content=body, headers=_signed(body, b"wrong")).status_code == 403
    bad = b"{not json"
    assert public.client.post("/public/social/meta/webhook", content=bad, headers=_signed(bad)).status_code == 400
    big = b"x" * (social_meta.MAX_WEBHOOK_BYTES + 1)
    assert public.client.post("/public/social/meta/webhook", content=big, headers=_signed(big)).status_code == 413
    public.delay.assert_not_called()
    public.mp.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    assert public.client.post("/public/social/meta/webhook", content=body, headers=_signed(body)).status_code == 503


def test_a_dead_broker_still_answers_200(public):
    public.mp.setattr(inbound_task.run_cappe_social_inbound, "delay", Mock(side_effect=RuntimeError("no broker")))
    body = json.dumps(COMMENT).encode()
    assert public.client.post("/public/social/meta/webhook", content=body, headers=_signed(body)).status_code == 200


# ── workers ─────────────────────────────────────────────────────────────────

def _scheduler(mp, module, *, enabled=True, max_per_cycle=10):
    mp.setattr(module, "scheduler_enabled", AsyncMock(return_value=enabled), raising=False)
    mp.setattr(module, "scheduler_settings_row", AsyncMock(
        return_value={"enabled": enabled, "max_per_cycle": max_per_cycle} if enabled is not None else None))


@pytest.mark.asyncio
async def test_publisher_sweep_claims_and_publishes(monkeypatch):
    conn = TxConn(fetchval={"UPDATE scheduler_settings SET last_run_at": True})
    monkeypatch.setattr(publisher_task, "get_db_connection", AsyncMock(return_value=conn))
    _scheduler(monkeypatch, publisher_task)
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: CFG))
    claims = [{"id": uuid4(), "post_id": POST_ID, "connection_id": CONN_ID, "attempts": 1} for _ in range(3)]
    claim = AsyncMock(return_value=claims)
    monkeypatch.setattr(post_store, "claim_due_targets", claim)
    monkeypatch.setattr(outbound, "publish_target", AsyncMock(side_effect=["published", "pending", "failed"]))
    result = await publisher_task._run_sweep()
    assert result == {"claimed": 3, "published": 1, "pending": 1, "failed": 1, "reschedule": True}
    assert claim.await_args.args[1] == 10 and conn.closed
    assert conn.args_for("UPDATE scheduler_settings SET last_run_at") == ("cappe_social_publisher", publisher_task.MIN_GAP)


@pytest.mark.asyncio
async def test_publisher_sweep_stops_the_extra_chain_and_waits_for_setup(monkeypatch):
    conn = TxConn(fetchval={"UPDATE scheduler_settings SET last_run_at": Queue([None, True])})
    monkeypatch.setattr(publisher_task, "get_db_connection", AsyncMock(return_value=conn))
    _scheduler(monkeypatch, publisher_task, enabled=False)
    assert (await publisher_task._run_sweep())["reason"] == "disabled"
    _scheduler(monkeypatch, publisher_task)
    assert await publisher_task._run_sweep() == {"skipped": True, "reason": "another_chain", "reschedule": False}
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    out = await publisher_task._run_sweep()
    assert out["reason"] == "meta_not_configured" and out["reschedule"] is True


def test_publisher_task_reschedules_itself_while_enabled(monkeypatch):
    async def sweep():
        return {"claimed": 0, "reschedule": True}

    monkeypatch.setattr(publisher_task, "_run_sweep", sweep)
    apply_async = Mock()
    monkeypatch.setattr(publisher_task.run_cappe_social_publisher, "apply_async", apply_async)
    assert publisher_task.run_cappe_social_publisher()["status"] == "success"
    apply_async.assert_called_once_with(countdown=publisher_task.SWEEP_SECONDS)

    async def stop():
        return {"skipped": True, "reschedule": False}

    monkeypatch.setattr(publisher_task, "_run_sweep", stop)
    publisher_task.run_cappe_social_publisher()
    assert apply_async.call_count == 1
    monkeypatch.setattr(publisher_task.run_cappe_social_publisher, "apply_async", Mock(side_effect=RuntimeError("x")))
    publisher_task._reschedule(60)  # logged, not raised


def test_publisher_task_failure_is_retried(monkeypatch):
    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(publisher_task, "_run_sweep", boom)
    with pytest.raises(RuntimeError):
        publisher_task.run_cappe_social_publisher()


@pytest.mark.asyncio
async def test_publish_one_post(monkeypatch):
    conn = TxConn()
    monkeypatch.setattr(publisher_task, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: CFG))
    claim = AsyncMock(return_value=[{"id": uuid4(), "post_id": POST_ID, "connection_id": CONN_ID, "attempts": 1}])
    monkeypatch.setattr(post_store, "claim_due_targets", claim)
    monkeypatch.setattr(outbound, "publish_target", AsyncMock(return_value="published"))
    assert await publisher_task._run_one(str(POST_ID)) == {"claimed": 1, "published": 1, "pending": 0, "failed": 0}
    assert claim.await_args.kwargs == {"post_id": str(POST_ID)}
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    assert (await publisher_task._run_one(str(POST_ID)))["reason"] == "meta_not_configured"


def test_publish_one_post_task(monkeypatch):
    async def one(post_id):
        return {"claimed": 0}

    monkeypatch.setattr(publisher_task, "_run_one", one)
    assert publisher_task.run_cappe_social_publish_post(str(POST_ID)) == {"status": "success", "claimed": 0}

    async def boom(post_id):
        raise RuntimeError("x")

    monkeypatch.setattr(publisher_task, "_run_one", boom)
    with pytest.raises(RuntimeError):
        publisher_task.run_cappe_social_publish_post(str(POST_ID))


@pytest.mark.asyncio
async def test_the_plan_decides_whether_the_model_runs(monkeypatch):
    settings = {**inbox_store.SETTINGS_DEFAULTS, "autoreply_mode": "auto"}
    monkeypatch.setattr(inbox_store, "get_settings", AsyncMock(return_value=settings))
    conn = TxConn(fetchval={"SELECT a.plan FROM cappe_sites": Queue(["business", "free", None])})
    resolve = AsyncMock(side_effect=[ent("social_autoreply"), ent("social")])
    monkeypatch.setattr(inbound_task, "resolve_entitlements", resolve)
    assert (await inbound_task.effective_settings(conn, SITE))["autoreply_mode"] == "auto"
    assert (await inbound_task.effective_settings(conn, SITE))["autoreply_mode"] == "off"
    assert (await inbound_task.effective_settings(conn, SITE))["autoreply_mode"] == "off"
    monkeypatch.setattr(inbox_store, "get_settings", AsyncMock(return_value=dict(inbox_store.SETTINGS_DEFAULTS)))
    assert (await inbound_task.effective_settings(conn, SITE))["autoreply_mode"] == "off"
    assert resolve.await_count == 2


@pytest.mark.asyncio
async def test_inbound_stores_handles_and_survives_a_bad_item(monkeypatch):
    events = [InboundEvent("instagram", "ig1", "comment", "c1", "hi"), InboundEvent("instagram", "ig1", "comment", "c2", "yo"),
              InboundEvent("facebook", "nobody", "comment", "c3", "?")]
    monkeypatch.setattr(conn_store, "by_external_id", AsyncMock(side_effect=lambda conn, platform, ext: (
        [connection()] if ext == "ig1" else [])))
    new = [inbox_item(id=uuid4()), inbox_item(id=uuid4())]
    monkeypatch.setattr(inbox_store, "ingest_events", AsyncMock(return_value=new))
    monkeypatch.setattr(inbox_store, "without_own", AsyncMock(side_effect=lambda conn, connections, events: events))
    monkeypatch.setattr(inbound_task, "effective_settings", AsyncMock(return_value={"autoreply_mode": "auto"}))
    send = AsyncMock(return_value="r1")
    monkeypatch.setattr(outbound, "send_reply", send)

    async def handle(conn, it, settings, *, send):
        if it is new[1]:
            raise RuntimeError("bug")
        await send(it, "Yes")
        return {"outcome": "sent"}

    monkeypatch.setattr(autoreply, "handle_item", handle)
    out = await inbound_task.process_events(object(), CFG, events)
    assert out == {"stored": 2, "unmatched": 1, "own": 0, "sent": 1, "error": 1}
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_page_on_two_sites_is_answered_once(monkeypatch):
    first, second = connection(), connection(id=uuid4(), site_id=uuid4())
    monkeypatch.setattr(conn_store, "by_external_id", AsyncMock(return_value=[first, second]))
    ingest = AsyncMock(side_effect=lambda conn, connection, events: [inbox_item(id=uuid4())])
    monkeypatch.setattr(inbox_store, "ingest_events", ingest)
    monkeypatch.setattr(inbox_store, "without_own", AsyncMock(side_effect=lambda conn, connections, events: events))
    monkeypatch.setattr(inbound_task, "effective_settings", AsyncMock(return_value={"autoreply_mode": "auto"}))
    handle = AsyncMock(return_value={"outcome": "sent"})
    monkeypatch.setattr(autoreply, "handle_item", handle)
    out = await inbound_task.process_events(object(), CFG, [InboundEvent("instagram", "ig1", "comment", "c", "x")])
    assert out == {"stored": 2, "unmatched": 0, "own": 0, "sent": 1}
    assert ingest.await_count == 2 and handle.await_count == 1


@pytest.mark.asyncio
async def test_inbound_with_nothing_new_handles_nothing(monkeypatch):
    monkeypatch.setattr(conn_store, "by_external_id", AsyncMock(return_value=[connection()]))
    monkeypatch.setattr(inbox_store, "ingest_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(inbox_store, "without_own", AsyncMock(side_effect=lambda conn, connections, events: events))
    handle = AsyncMock()
    monkeypatch.setattr(autoreply, "handle_item", handle)
    assert await inbound_task.process_events(object(), CFG, [InboundEvent("instagram", "ig1", "comment", "c", "x")]) == {
        "stored": 0, "unmatched": 0, "own": 0}
    handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_our_own_reply_coming_back_is_never_stored_or_answered(monkeypatch):
    monkeypatch.setattr(conn_store, "by_external_id", AsyncMock(return_value=[connection()]))
    own = InboundEvent("instagram", "ig1", "comment", "r9", "Thanks so much!", author_name="pocoffee")
    theirs = InboundEvent("instagram", "ig1", "comment", "c5", "Do you ship?", author_name="maya")
    conn = TxConn(fetch={"FROM cappe_social_replies WHERE external_reply_id": []})
    ingest = AsyncMock(return_value=[])
    monkeypatch.setattr(inbox_store, "ingest_events", ingest)
    out = await inbound_task.process_events(conn, CFG, [own, theirs])
    assert out == {"stored": 0, "unmatched": 0, "own": 1}
    assert ingest.await_args.kwargs["events"] == [theirs]
    # Nothing left once ours is dropped: nothing to ingest.
    ingest.reset_mock()
    assert (await inbound_task.process_events(conn, CFG, [own]))["own"] == 1
    ingest.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_inbox_sweep_retries_what_the_policy_left(monkeypatch):
    other_site = uuid4()
    items = [inbox_item(id=uuid4()), inbox_item(id=uuid4()), inbox_item(id=uuid4(), site_id=other_site),
             inbox_item(id=uuid4())]
    unhandled = AsyncMock(return_value=items)
    monkeypatch.setattr(inbox_store, "unhandled", unhandled)
    settings = AsyncMock(return_value={"autoreply_mode": "auto"})
    monkeypatch.setattr(inbound_task, "effective_settings", settings)
    attempts = []
    monkeypatch.setattr(inbox_store, "note_attempt", AsyncMock(side_effect=lambda c, i, r: attempts.append(r)))
    results = iter([{"outcome": "sent"}, RuntimeError("bug"), {"outcome": "left", "reason": "off"},
                    {"outcome": "left", "reason": "no_model"}])

    async def handle(conn, it, s, *, send):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(autoreply, "handle_item", handle)
    out = await inbound_task.sweep(object(), CFG, limit=50)
    assert out == {"items": 4, "sent": 1, "error": 1, "left": 2}
    assert unhandled.await_args.kwargs == {"limit": 50, "within_hours": inbound_task.SWEEP_WINDOW_HOURS,
                                           "max_attempts": autoreply.MAX_ATTEMPTS,
                                           "model_cap": autoreply.MODEL_CALLS_PER_HOUR}
    assert settings.await_count == 2  # once per site
    # A plan that no longer includes replies turns the item away every hour:
    # counted, so it ages out instead of heading the list for 12 hours. A wait
    # for the model isn't counted here (the policy counted it itself).
    assert attempts == ["off"]

    # "No model" is the same for everyone after it: the sweep stops there.
    results = iter([{"outcome": "left", "reason": "no_model"}, {"outcome": "sent"}])
    monkeypatch.setattr(inbox_store, "unhandled", AsyncMock(return_value=items[:2]))
    assert await inbound_task.sweep(object(), CFG, limit=50) == {"items": 2, "left": 1}


@pytest.mark.asyncio
async def test_inbox_sweep_run_respects_its_row_and_the_meta_setup(monkeypatch):
    conn = TxConn()
    monkeypatch.setattr(inbound_task, "get_db_connection", AsyncMock(return_value=conn))
    row = AsyncMock(return_value={"enabled": False, "max_per_cycle": 50})
    monkeypatch.setattr(inbound_task, "scheduler_settings_row", row)
    assert await inbound_task._run_sweep() == {"skipped": True} and conn.closed
    row.return_value = {"enabled": True, "max_per_cycle": 9999}
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    assert (await inbound_task._run_sweep())["reason"] == "meta_not_configured"
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: CFG))
    sweep = AsyncMock(return_value={"items": 0})
    monkeypatch.setattr(inbound_task, "sweep", sweep)
    assert await inbound_task._run_sweep() == {"items": 0}
    assert sweep.await_args.kwargs == {"limit": 500}


def test_inbox_sweep_task_wrapper(monkeypatch):
    async def run():
        return {"items": 3}

    monkeypatch.setattr(inbound_task, "_run_sweep", run)
    assert inbound_task.run_cappe_social_inbox_sweep() == {"status": "success", "items": 3}

    async def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(inbound_task, "_run_sweep", boom)
    with pytest.raises(RuntimeError):
        inbound_task.run_cappe_social_inbox_sweep()


@pytest.mark.asyncio
async def test_inbound_run_and_task(monkeypatch):
    conn = TxConn()
    monkeypatch.setattr(inbound_task, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: CFG))
    monkeypatch.setattr(inbound_task, "process_events", AsyncMock(return_value={"stored": 1}))
    raw = [InboundEvent("instagram", "ig1", "comment", "c", "x").as_dict()]
    assert await inbound_task._run(raw) == {"stored": 1} and conn.closed
    assert await inbound_task._run([]) == {"stored": 0}
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    assert (await inbound_task._run(raw))["reason"] == "meta_not_configured"


def test_inbound_task_wrapper(monkeypatch):
    async def run(raw):
        return {"stored": len(raw)}

    monkeypatch.setattr(inbound_task, "_run", run)
    assert inbound_task.run_cappe_social_inbound([{}, {}]) == {"status": "success", "stored": 2}

    async def boom(raw):
        raise RuntimeError("x")

    monkeypatch.setattr(inbound_task, "_run", boom)
    with pytest.raises(RuntimeError):
        inbound_task.run_cappe_social_inbound([])


@pytest.mark.asyncio
async def test_metrics_task(monkeypatch):
    conn = TxConn()
    monkeypatch.setattr(metrics_task, "get_db_connection", AsyncMock(return_value=conn))
    _scheduler(monkeypatch, metrics_task, enabled=None)
    assert await metrics_task._run() == {"skipped": True}
    _scheduler(monkeypatch, metrics_task, max_per_cycle=7)
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: None))
    assert (await metrics_task._run())["reason"] == "meta_not_configured"
    monkeypatch.setattr(meta.MetaConfig, "from_settings", staticmethod(lambda: CFG))
    refresh = AsyncMock(return_value={"connections": 1, "accounts": 1, "posts": 2})
    from app.cappe.services.social import metrics as metrics_service
    monkeypatch.setattr(metrics_service, "refresh_all", refresh)
    assert (await metrics_task._run())["posts"] == 2
    assert refresh.await_args.kwargs == {"limit": 7} and conn.closed


def test_metrics_task_wrapper(monkeypatch):
    async def run():
        return {"accounts": 0}

    monkeypatch.setattr(metrics_task, "_run", run)
    assert metrics_task.run_cappe_social_metrics() == {"status": "success", "accounts": 0}

    async def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(metrics_task, "_run", boom)
    with pytest.raises(RuntimeError):
        metrics_task.run_cappe_social_metrics()


def test_inbound_events_parse_back_before_the_worker_sees_them():
    raw = InboundEvent("instagram", "ig1", "comment", "c", "x", received_at=NOW).as_dict()
    assert asyncio.run(asyncio.sleep(0, result=InboundEvent.from_dict(raw))).received_at == NOW
