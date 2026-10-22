"""Cappe social — the services under the routes.

What each block pins:

  * the Connect state is signed, expires, and only counts from the browser
    holding its nonce cookie;
  * request models clean hashtags and refuse non-https media;
  * posts: what may go where, the retry backoff, how a post's status rolls up
    from its targets, and the SQL the store and the publisher's claim send;
  * tokens are encrypted at rest and only decrypted for a call;
  * the inbox stores each delivery once and settings fall back to defaults;
  * the Claude gate: Haiku by default, nothing without a key, nothing when
    the bucket is full;
  * the reply policy: deterministic hard stops before any model call, the
    grounded draft's parse, and when a draft is sent by itself vs held;
  * metrics and the two network writes record what happened.

No database, no network: SQL goes to `QueryConn`, models and networks are faked.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_social_core.py -q
"""
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models.social import (  # noqa: E402
    CappeSocialCaptionOption,
    CappeSocialMediaItem,
    CappeSocialPostInput,
    CappeSocialSettings,
    CappeSocialSettingsUpdate,
)
from app.cappe.services.social import ai, autoreply, captions, metrics, oauth, outbound  # noqa: E402
from app.cappe.services.social import connections as conn_store  # noqa: E402
from app.cappe.services.social import inbox as inbox_store  # noqa: E402
from app.cappe.services.social import posts as post_store  # noqa: E402
from app.cappe.services.social.providers.base import (  # noqa: E402
    ConnectionDraft,
    InboundEvent,
    ProviderError,
    PublishResult,
)
from app.core.services.secret_crypto import decrypt_secret  # noqa: E402
from tests._helpers.routes import QueryConn, Queue  # noqa: E402

SITE, ACCOUNT, POST, CONN = uuid4(), uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
IMG = {"url": "https://cdn.example.test/a.jpg", "kind": "image", "alt": None}


def post_row(**over):
    return {"id": POST, "site_id": SITE, "caption": "Fresh", "media": json.dumps([IMG]), "link_url": None,
            "product_id": None, "status": "draft", "scheduled_at": None, "published_at": None,
            "ai_meta": "{}", "created_at": NOW, "updated_at": NOW, **over}


def target_row(**over):
    return {"id": uuid4(), "post_id": POST, "connection_id": CONN, "platform": "instagram", "handle": "pocoffee",
            "status": "pending", "external_post_id": None, "permalink": None, "error": None, "attempts": 0,
            "next_attempt_at": None, "published_at": None, "metrics": "{}", **over}


# ── OAuth state ─────────────────────────────────────────────────────────────

def test_state_round_trips_for_the_browser_holding_the_nonce():
    nonce = oauth.new_nonce()
    state = oauth.make_state(SITE, ACCOUNT, nonce)
    assert oauth.read_state(state, nonce_cookie=nonce) == {"site_id": SITE, "account_id": ACCOUNT}


@pytest.mark.parametrize("mutate", [
    lambda s, n: (s, "other-nonce"),                            # another browser
    lambda s, n: (s, None),                                     # no cookie at all
    lambda s, n: (s[:-2] + ("00" if s[-2:] != "00" else "11"), n),  # signature tampered
    lambda s, n: ("not-a-state", n),
    lambda s, n: (None, n),
    lambda s, n: ("bm90IGpzb24." + s.rpartition(".")[2], n),     # payload swapped
])
def test_state_refused(mutate):
    nonce = "n1"
    state, cookie = mutate(oauth.make_state(SITE, ACCOUNT, nonce), nonce)
    assert oauth.read_state(state, nonce_cookie=cookie) is None


def test_state_expires_and_is_bound_to_the_signing_secret():
    nonce = "n1"
    state = oauth.make_state(SITE, ACCOUNT, nonce, now=1_000.0)
    assert oauth.read_state(state, nonce_cookie=nonce, now=1_000.0 + oauth.STATE_TTL_SECONDS - 1)
    assert oauth.read_state(state, nonce_cookie=nonce, now=1_000.0 + oauth.STATE_TTL_SECONDS + 1) is None
    other = oauth.make_state(SITE, ACCOUNT, nonce, seed="another-secret")
    assert oauth.read_state(other, nonce_cookie=nonce) is None


def test_a_signed_payload_with_a_bad_body_is_refused():
    import base64

    payload = base64.urlsafe_b64encode(b'{"s":"x"}').decode().rstrip("=")
    state = f"{payload}.{oauth._sign(payload.encode(), oauth._seed())}"
    assert oauth.read_state(state, nonce_cookie="n") is None


def test_seed_falls_back_when_settings_are_not_loaded(monkeypatch):
    def boom():
        raise RuntimeError("not loaded")

    monkeypatch.setattr(oauth, "get_settings", boom)
    monkeypatch.setenv("JWT_SECRET_KEY", "env-seed")
    assert oauth._seed() == "env-seed"


# ── models ──────────────────────────────────────────────────────────────────

def test_hashtags_are_normalized_and_deduplicated():
    option = CappeSocialCaptionOption(text="x", hashtags=["#Coffee", "coffee", "cold brew", "#", "  latte!  "])
    assert option.hashtags == ["#coffee", "#coldbrew", "#latte"]
    assert CappeSocialSettingsUpdate(default_hashtags=None).default_hashtags is None


def test_media_and_links_must_be_https():
    with pytest.raises(ValidationError):
        CappeSocialMediaItem(url="http://cdn.example.test/a.jpg")
    with pytest.raises(ValidationError):
        CappeSocialPostInput(link_url="javascript:alert(1)")
    assert CappeSocialPostInput(media=[IMG]).media[0].kind == "image"


def test_escalation_words_are_trimmed_and_lowercased():
    assert CappeSocialSettings(escalate_words=["  Refund ", "", "LAWYER"]).escalate_words == ["refund", "lawyer"]
    assert CappeSocialSettingsUpdate(escalate_words=[" X "]).escalate_words == ["x"]
    assert CappeSocialSettingsUpdate().escalate_words is None


# ── posts: pure rules ───────────────────────────────────────────────────────

@pytest.mark.parametrize("caption,media,platforms,reason", [
    ("", [], ["facebook"], "Add a caption"),
    ("Hello", [], ["instagram"], "need a photo or a video"),
    ("Hello", [{"asset_id": "a1", "kind": "video"}], ["instagram", "facebook"], None),
    ("Hello", [{"asset_id": "a1", "kind": "video"}, IMG], ["facebook"], "goes out on its own"),
    ("Hello", [], ["facebook"], None),
    ("", [IMG], ["instagram", "facebook"], None),
])
def test_what_may_go_where(caption, media, platforms, reason):
    result = post_store.validate_for_targets(caption, media, platforms)
    assert (result is None) if reason is None else (reason in result)


def test_backoff_grows_then_holds():
    assert [post_store.backoff_after(n) for n in (0, 1, 2, 3, 9)] == [
        timedelta(minutes=2), timedelta(minutes=2), timedelta(minutes=10), timedelta(minutes=30), timedelta(minutes=30)]


@pytest.mark.parametrize("statuses,expected", [
    ([], "failed"),
    (["cancelled"], "cancelled"),
    (["published", "pending"], "publishing"),
    (["publishing"], "publishing"),
    (["published", "published", "cancelled"], "published"),
    (["published", "failed"], "partial"),
    (["failed", "failed"], "failed"),
])
def test_post_status_rolls_up_from_its_targets(statuses, expected):
    assert post_store.rollup_status(statuses) == expected


# ── posts: the store ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_post_is_scheduled_only_with_a_time():
    conn = QueryConn(fetchrow={"INSERT INTO cappe_social_posts": post_row(status="scheduled", scheduled_at=NOW)})
    post = await post_store.create_post(conn, site_id=SITE, caption="Fresh", media=[IMG], link_url=None,
                                        product_id=None, scheduled_at=NOW, ai_meta={"alt_text": "a cup"})
    args = conn.args_for("INSERT INTO cappe_social_posts")
    assert args[5] == "scheduled" and json.loads(args[2]) == [IMG] and json.loads(args[7]) == {"alt_text": "a cup"}
    assert post["media"] == [IMG] and post["ai_meta"] == {}
    await post_store.create_post(conn, site_id=SITE, caption="", media=[], link_url=None, product_id=None,
                                 scheduled_at=None)
    assert conn.calls[-1][2][5] == "draft"


@pytest.mark.asyncio
async def test_set_targets_drops_unsent_extras_and_upserts_the_rest():
    conn = QueryConn()
    other = uuid4()
    await post_store.set_targets(conn, POST, [CONN, other], due_at=NOW)
    sql = conn.sql_for("execute")
    assert "DELETE FROM cappe_social_post_targets" in sql[0] and "NOT (connection_id = ANY" in sql[0]
    assert conn.calls[0][2] == (POST, [CONN, other])
    assert sum("INSERT INTO cappe_social_post_targets" in s for s in sql) == 2
    assert conn.calls[1][2] == (POST, CONN, NOW)


@pytest.mark.asyncio
async def test_get_and_list_posts_carry_their_targets():
    t1, t2 = target_row(), target_row(post_id=uuid4())
    conn = QueryConn(
        fetchrow={"FROM cappe_social_posts WHERE id = $1": Queue([post_row(), None])},
        fetch={"FROM cappe_social_post_targets t": [t1, t2], "ORDER BY COALESCE(scheduled_at": [post_row()]},
    )
    post = await post_store.get_post(conn, SITE, POST)
    assert post["targets"][0]["metrics"] == {} and post["media"] == [IMG]
    assert await post_store.get_post(conn, SITE, POST) is None
    listed = await post_store.list_posts(conn, SITE, status="draft", limit=10, offset=5)
    assert [t["id"] for t in listed[0]["targets"]] == [t1["id"]]
    assert conn.args_for("ORDER BY COALESCE(scheduled_at") == (SITE, "draft", 10, 5)
    assert await post_store.targets_for(conn, []) == []


@pytest.mark.asyncio
async def test_update_post_encodes_json_columns_and_refuses_sent_posts():
    conn = QueryConn(
        fetchrow={"UPDATE cappe_social_posts SET": Queue([post_row(caption="New"), None]),
                  "SET status = 'rendering'": None,
                  "FROM cappe_social_posts WHERE id = $1": post_row()},
        fetch={"FROM cappe_social_post_targets t": [], "SET status = 'failed'": [], "SET status = 'scheduled'": []},
        fetchval={"SELECT status": "scheduled"},
    )
    post = await post_store.update_post(conn, SITE, POST, {"caption": "New", "media": [IMG], "ai_meta": {"a": 1}})
    # New media: the render hold is taken again from scratch and settled.
    assert any("status = 'rendering'" in sql for _, sql, _ in conn.calls)
    assert post["status"] == "scheduled"
    sql = conn.sql_for("fetchrow")[0]
    assert "caption = $4" in sql and "media = $5::jsonb" in sql and "ai_meta = $6::jsonb" in sql
    assert "status = ANY($3::text[])" in sql
    assert conn.calls[0][2][2] == ["draft", "scheduled", "rendering", "failed"]
    assert post["caption"] == "New"
    assert await post_store.update_post(conn, SITE, POST, {"caption": "x"}) is None
    assert (await post_store.update_post(conn, SITE, POST, {}))["id"] == POST


@pytest.mark.asyncio
async def test_schedule_publish_cancel_and_delete():
    conn = QueryConn(fetchrow={
        "SET status = $3": Queue([{"id": POST}, None, {"id": POST}]),
        "SET status = 'cancelled'": Queue([None, {"id": POST}]),
        "DELETE FROM cappe_social_posts": Queue([{"id": POST}, None]),
        "SET status = 'rendering'": None,
    })
    assert await post_store.set_schedule(conn, SITE, POST, NOW) is True
    assert conn.args_for("SET status = $3") == (POST, SITE, "scheduled", NOW, ["draft", "scheduled", "rendering", "failed"])
    # A post whose video isn't cut yet waits as `rendering`.
    assert conn.args_for("SET status = 'rendering'") == (POST,)
    assert any("next_attempt_at = $2" in s for s in conn.sql_for("execute"))
    assert await post_store.set_schedule(conn, SITE, POST, None) is False
    assert await post_store.publish_now(conn, SITE, POST) is True
    # Post now is also the retry for a post one network took and another didn't.
    assert "partial" in conn.calls[-3][2][4]
    assert "status IN ('pending', 'failed', 'cancelled')" in conn.sql_for("execute")[-1]
    assert "state = '{}'::jsonb" in conn.sql_for("execute")[-1]
    assert await post_store.cancel_post(conn, SITE, POST) is False
    assert await post_store.cancel_post(conn, SITE, POST) is True
    assert await post_store.delete_post(conn, SITE, POST) is True
    assert await post_store.delete_post(conn, SITE, POST) is False


@pytest.mark.asyncio
async def test_claim_takes_due_targets_with_skip_locked_and_marks_posts():
    claimed = [{"id": uuid4(), "post_id": POST, "connection_id": CONN, "attempts": 1, "state": '{"container_id": "c1"}'}]
    conn = QueryConn(fetch={"SET status = 'publishing', attempts": Queue([claimed, []])})
    assert await post_store.claim_due_targets(conn, 25, post_id=str(POST)) == [
        {**claimed[0], "state": {"container_id": "c1"}, "content": {}}]
    sql = conn.sql_for("fetch")[0]
    assert "FOR UPDATE SKIP LOCKED" in sql and "next_attempt_at <= NOW()" in sql
    assert conn.args_for("SET status = 'publishing', attempts") == (25, POST)
    assert "SET status = 'publishing', updated_at" in conn.sql_for("execute")[0]
    assert await post_store.claim_due_targets(conn, 25) == []
    assert conn.calls[-1][2] == (25, None)


@pytest.mark.asyncio
async def test_outcomes_retry_retryable_failures_until_the_cap():
    conn = QueryConn()
    target = uuid4()
    await post_store.record_success(conn, target, PublishResult(external_post_id="m1", permalink="https://x.test/p"))
    assert conn.calls[-1][2] == (target, "m1", "https://x.test/p")
    assert await post_store.record_failure(conn, target, 1, ProviderError("slow", retryable=True)) == "pending"
    assert conn.calls[-1][2] == (target, "slow", timedelta(minutes=2))
    assert await post_store.record_failure(conn, target, post_store.MAX_ATTEMPTS,
                                           ProviderError("slow", retryable=True)) == "failed"
    assert await post_store.record_failure(conn, target, 1, ProviderError("bad image")) == "failed"
    assert await post_store.record_failure(conn, target, 1, ValueError("bug")) == "failed"


@pytest.mark.asyncio
async def test_rollup_post_writes_the_rolled_status():
    conn = QueryConn(fetch={"SELECT status FROM cappe_social_post_targets": [{"status": "published"},
                                                                            {"status": "failed"}]})
    assert await post_store.rollup_post(conn, POST) == "partial"
    assert conn.calls[-1][2] == (POST, "partial")


# ── connections ─────────────────────────────────────────────────────────────

def conn_row(**over):
    return {"id": CONN, "site_id": SITE, "account_id": ACCOUNT, "platform": "instagram", "external_id": "ig1",
            "handle": "pocoffee", "display_name": "pocoffee", "avatar_url": None, "status": "connected",
            "last_error": None, "followers_count": 10, "metrics": '{"followers_count": 10}', "metrics_at": None,
            "token_expires_at": None, "connected_at": NOW, "updated_at": NOW, **over}


@pytest.mark.asyncio
async def test_tokens_are_encrypted_at_rest_and_never_returned():
    conn = QueryConn(fetchrow={"INSERT INTO cappe_social_connections": conn_row()})
    draft = ConnectionDraft(platform="instagram", external_id="ig1", access_token="EAAB-secret", scopes=("a",))
    rows = await conn_store.save_drafts(conn, site_id=SITE, account_id=ACCOUNT, drafts=[draft])
    stored = conn.args_for("INSERT INTO cappe_social_connections")[7]
    assert stored != "EAAB-secret" and decrypt_secret(stored) == "EAAB-secret"
    assert "access_token_enc" not in conn_store.PUBLIC_COLUMNS
    assert rows[0]["metrics"] == {"followers_count": 10}


@pytest.mark.asyncio
async def test_connection_reads_and_writes():
    from app.core.services.secret_crypto import encrypt_secret

    conn = QueryConn(
        fetch={"ORDER BY platform, connected_at": [conn_row()], "WHERE platform = $1 AND external_id": [conn_row()]},
        # DELETE first: its SQL also contains the get query's needle.
        fetchrow={
            "DELETE FROM cappe_social_connections": Queue([{"id": CONN}, None]),
            "FROM cappe_social_connections WHERE id = $1 AND site_id": Queue([conn_row(), None]),
            "access_token_enc, status": Queue([{**conn_row(), "access_token_enc": encrypt_secret("tok")}, None]),
        },
    )
    assert (await conn_store.list_connections(conn, SITE))[0]["metrics"] == {"followers_count": 10}
    assert (await conn_store.get_connection(conn, SITE, CONN))["id"] == CONN
    assert await conn_store.get_connection(conn, SITE, CONN) is None
    assert await conn_store.delete_connection(conn, SITE, CONN) is True
    assert await conn_store.delete_connection(conn, SITE, CONN) is False
    cred = await conn_store.credentials(conn, CONN)
    assert cred["token"] == "tok" and cred["platform"] == "instagram"
    assert await conn_store.credentials(conn, CONN) is None
    assert len(await conn_store.by_external_id(conn, "instagram", "ig1")) == 1
    await conn_store.mark_status(conn, CONN, "expired", "x" * 900)
    assert conn.calls[-1][2] == (CONN, "expired", "x" * 500)
    await conn_store.mark_status(conn, CONN, "connected")
    assert conn.calls[-1][2] == (CONN, "connected", None)
    await conn_store.record_metrics(conn, CONN, {"followers_count": 12, "media_count": 3})
    assert conn.calls[-1][2] == (CONN, json.dumps({"followers_count": 12, "media_count": 3}), 12)
    await conn_store.record_metrics(conn, CONN, {})
    assert conn.calls[-1][2][2] is None


# ── inbox ───────────────────────────────────────────────────────────────────

def item(**over):
    return {"id": uuid4(), "site_id": SITE, "connection_id": CONN, "platform": "instagram", "handle": "pocoffee",
            "kind": "comment", "external_id": "c1", "external_parent_id": "m1", "author_external_id": "u1",
            "author_name": "maya", "text": "Do you have oat milk?", "received_at": NOW, "status": "new",
            "classification": "{}", **over}


def reply_row(**over):
    return {"id": uuid4(), "inbox_id": uuid4(), "site_id": SITE, "body": "Yes!", "mode": "approved",
            "status": "draft", "model": "claude-haiku-5-5", "grounding": '{"facts_used": []}',
            "external_reply_id": None, "error": None, "created_at": NOW, "sent_at": None, **over}


@pytest.mark.asyncio
async def test_settings_default_then_merge_and_upsert():
    stored = {**inbox_store.SETTINGS_DEFAULTS, "autoreply_mode": "auto", "default_hashtags": ["#a"],
              "escalate_words": None, "signature": None}
    conn = QueryConn(fetchrow={"FROM cappe_social_settings": Queue([None, stored, None])})
    assert await inbox_store.get_settings(conn, SITE) == inbox_store.SETTINGS_DEFAULTS
    merged = await inbox_store.get_settings(conn, SITE)
    assert merged["autoreply_mode"] == "auto" and merged["escalate_words"] == []
    out = await inbox_store.upsert_settings(conn, SITE, {"tone": "playful", "max_auto_per_hour": 5, "junk": 1})
    assert out["tone"] == "playful" and "junk" not in out
    args = conn.args_for("INSERT INTO cappe_social_settings")
    assert args[0] == SITE and args[4] == "playful" and args[8] == 5


@pytest.mark.asyncio
async def test_ingest_stores_each_delivery_once():
    events = [InboundEvent(platform="instagram", recipient_external_id="ig1", kind="comment", external_id=f"c{i}",
                           text="hi", raw={"i": i}) for i in range(2)]
    conn = QueryConn(fetchrow={"INSERT INTO cappe_social_inbox": Queue([item(), None])})
    stored = await inbox_store.ingest_events(conn, connection={"id": CONN, "site_id": SITE, "platform": "instagram",
                                                               "handle": "pocoffee"}, events=events)
    assert len(stored) == 1 and stored[0]["platform"] == "instagram" and stored[0]["classification"] == {}
    assert "ON CONFLICT (connection_id, external_id) DO NOTHING" in conn.sql_for("fetchrow")[0]


@pytest.mark.asyncio
async def test_inbox_lists_with_replies_and_records_outcomes():
    first = item()
    conn = QueryConn(
        fetch={"FROM cappe_social_inbox i": [first], "FROM cappe_social_replies WHERE inbox_id": [
            reply_row(inbox_id=first["id"])]},
        fetchrow={
            "WHERE i.id = $1 AND i.site_id": Queue([first, None]),
            "INSERT INTO cappe_social_replies": reply_row(),
            "FROM cappe_social_replies WHERE id = $1": Queue([reply_row(), None]),
            "count(*) FILTER": Queue([{"new_items": 3, "waiting": 1}, None]),
        },
        fetchval={"mode = 'auto'": 4},
    )
    listed = await inbox_store.list_inbox(conn, SITE, status="new")
    assert listed[0]["replies"][0]["grounding"] == {"facts_used": []}
    assert (await inbox_store.get_item(conn, SITE, first["id"]))["id"] == first["id"]
    assert await inbox_store.get_item(conn, SITE, first["id"]) is None
    created = await inbox_store.create_reply(conn, inbox_id=first["id"], site_id=SITE, body="Yes!", mode="auto",
                                             status="draft", model="m", grounding={"facts_used": ["x"]})
    assert created["body"] == "Yes!"
    assert (await inbox_store.get_reply(conn, SITE, uuid4()))["status"] == "draft"
    assert await inbox_store.get_reply(conn, SITE, uuid4()) is None
    await inbox_store.mark_reply(conn, created["id"], status="sent", external_reply_id="r1")
    assert conn.calls[-1][2] == (created["id"], "sent", "r1", None)
    await inbox_store.set_item_status(conn, first["id"], "replied")
    assert conn.calls[-1][2] == (first["id"], "replied", None)
    await inbox_store.set_item_status(conn, first["id"], "drafted", {"intent": "praise"})
    assert json.loads(conn.calls[-1][2][2]) == {"intent": "praise"}
    assert await inbox_store.auto_replies_last_hour(conn, SITE) == 4
    assert await inbox_store.counts(conn, SITE) == {"new": 3, "waiting": 1}
    assert await inbox_store.counts(conn, SITE) == {"new": 0, "waiting": 0}
    assert await inbox_store.replies_for(conn, []) == {}


# ── the Claude gate ─────────────────────────────────────────────────────────

class Bucket:
    def __init__(self, check=None, record=None):
        self.check, self.record, self.calls = check, record, []

    async def check_limit(self, service, endpoint):
        self.calls.append(("check", service, endpoint))
        if self.check:
            raise self.check

    async def record_call(self, service, endpoint):
        self.calls.append(("record", service, endpoint))
        if self.record:
            raise self.record


@pytest.mark.asyncio
async def test_model_for_defaults_to_haiku_and_counts_the_call(monkeypatch):
    from app.core.services import anthropic_messages, rate_limiter

    bucket = Bucket()
    monkeypatch.setattr(anthropic_messages, "claude_default", AsyncMock(return_value=anthropic_messages.CLAUDE_HAIKU))
    monkeypatch.setattr(rate_limiter, "get_rate_limiter", lambda provider="gemini": bucket)
    assert await ai.model_for("reply") == "claude-haiku-5-5"
    assert bucket.calls == [("check", "cappe_social", "reply"), ("record", "cappe_social", "reply")]
    assert await ai.available() is True


@pytest.mark.asyncio
async def test_model_for_is_none_without_a_key_or_with_a_full_bucket(monkeypatch):
    from app.core.services import anthropic_messages, rate_limiter

    monkeypatch.setattr(anthropic_messages, "claude_default", AsyncMock(return_value=None))
    assert await ai.model_for("reply") is None
    assert await ai.available() is False
    monkeypatch.setattr(anthropic_messages, "claude_default", AsyncMock(return_value="claude-haiku-5-5"))
    full = Bucket(check=rate_limiter.RateLimitExceeded("full", "hourly", 10, 10))
    monkeypatch.setattr(rate_limiter, "get_rate_limiter", lambda provider="gemini": full)
    assert await ai.model_for("captions") is None
    flaky = Bucket(check=RuntimeError("db down"), record=RuntimeError("db down"))
    monkeypatch.setattr(rate_limiter, "get_rate_limiter", lambda provider="gemini": flaky)
    assert await ai.model_for("captions") == "claude-haiku-5-5"


# ── captions ────────────────────────────────────────────────────────────────

def test_caption_prompt_carries_the_facts_and_nothing_invented():
    prompt = captions.build_prompt(
        site_name="Po Coffee", product={"name": "Oat Latte", "price_cents": 550, "currency": "USD",
                                        "description": "Single origin"},
        brief="launch day", tone="playful", default_hashtags=["#pocoffee"], store_url="https://po.example.test",
        image_count=2,
    )
    for needle in ("Po Coffee", "Oat Latte — $5.50", "Single origin", "launch day", "#pocoffee",
                   "https://po.example.test", "2 photo(s)", "playful"):
        assert needle in prompt
    bare = captions.build_prompt(site_name="X", product=None, brief=None, tone=None, default_hashtags=[],
                                 store_url=None, image_count=0)
    assert "No photo attached" in bare and "friendly" in bare


def test_caption_reply_parse_keeps_three_good_options():
    raw = json.dumps({"options": [{"text": " A ", "hashtags": ["#a", " "]}, {"text": ""}, "junk", {"text": "B"},
                                  {"text": "C"}, {"text": "D"}], "alt_text": " a cup "})
    parsed = captions.parse_reply(raw)
    assert parsed == {"options": [{"text": "A", "hashtags": ["#a"]}, {"text": "B", "hashtags": []},
                                  {"text": "C", "hashtags": []}], "alt_text": "a cup"}
    assert captions.parse_reply('{"options": []}')["alt_text"] is None
    with pytest.raises(ValueError):
        captions.parse_reply("not json")


@pytest.mark.asyncio
async def test_draft_captions_attaches_photos_by_url(monkeypatch):
    from app.core.services import anthropic_messages

    sent = {}

    async def fake_generate(prompt, **kwargs):
        sent.update(kwargs, prompt=prompt)
        return json.dumps({"options": [{"text": "Hello", "hashtags": ["#x"]}], "alt_text": "cup"})

    monkeypatch.setattr(captions, "model_for", AsyncMock(return_value="claude-haiku-5-5"))
    monkeypatch.setattr(anthropic_messages, "generate_text", fake_generate)
    urls = [f"https://cdn.example.test/{i}.jpg" for i in range(6)]
    out = await captions.draft_captions(site_name="Po", media_urls=urls, product=None, brief=None, tone=None,
                                        default_hashtags=[], store_url=None)
    assert out["model"] == "claude-haiku-5-5" and out["options"][0]["text"] == "Hello"
    assert len(sent["attachments"]) == captions.MAX_IMAGES
    assert sent["attachments"][0] == {"type": "image", "source": {"type": "url", "url": urls[0]}}
    assert sent["model"] == "claude-haiku-5-5" and sent["json_output"] is True and sent["effort"] == "low"

    monkeypatch.setattr(captions, "model_for", AsyncMock(return_value=None))
    with pytest.raises(ai.AiUnavailable):
        await captions.draft_captions(site_name="Po", media_urls=[], product=None, brief=None, tone=None,
                                      default_hashtags=[], store_url=None)


# ── the reply policy ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("", ("skip", "empty")),
    ("   ", ("skip", "empty")),
    ("I want a refund now", ("escalate", "refund")),
    ("They REFUNDED me twice??", ("escalate", "refund")),
    ("my kid is allergic to nuts", ("escalate", "allerg")),
    ("I will sue you", ("escalate", "sue")),
    ("Love the suede jacket", ("consider", None)),
    ("Do you have an issue tracker", ("consider", None)),
    ("When do you open?", ("consider", None)),
])
def test_prefilter_hard_stops_whole_words_and_stems(text, expected):
    assert autoreply.prefilter(text) == expected


def test_prefilter_adds_the_owners_words():
    assert autoreply.prefilter("is the wholesale price lower?", escalate_words=["wholesale"]) == ("escalate", "wholesale")
    assert autoreply.prefilter("wholesalers welcome?", escalate_words=["wholesale*"]) == ("escalate", "wholesale")
    assert autoreply.prefilter("hi", escalate_words=["", "*"]) == ("consider", None)


def test_grounding_facts_list_what_the_model_may_say():
    g = autoreply.Grounding(
        site_name="Po Coffee", store_url="https://po.example.test",
        products=[{"name": "Oat Latte", "price_cents": 550, "currency": "USD", "inventory": 0, "category": "Drinks"},
                  {"name": "Beans", "price_cents": 1800, "currency": "USD", "inventory": None}],
        contact={"hours": "7-3 daily", "email": "hi@po.example.test"}, notes="We ship Mon-Thu.",
    )
    facts = g.facts()
    assert facts[:4] == ["Business: Po Coffee", "Store: https://po.example.test", "Hours: 7-3 daily",
                         "Email: hi@po.example.test"]
    assert "Product: Oat Latte — $5.50 — sold out — Drinks" in facts
    assert "Product: Beans — $18.00 — available" in facts
    assert facts[-1] == "Owner's notes: We ship Mon-Thu."


@pytest.mark.asyncio
async def test_load_grounding_reads_the_catalog_contact_and_notes():
    conn = QueryConn(
        fetchrow={
            "FROM cappe_sites WHERE id = $1": {"id": SITE, "name": "Po Coffee", "subdomain": "po", "custom_domain": None,
                                               "meta_config": json.dumps({"contact_email": "hi@po.example.test",
                                                                          "business_hours": "7-3"})},
            "FROM cappe_social_settings": {**inbox_store.SETTINGS_DEFAULTS, "business_facts": "Ships Mon"},
        },
        fetch={"FROM cappe_products": [{"name": "Beans", "description": None, "price_cents": 1800, "currency": "USD",
                                        "inventory": 3, "category": None}]},
    )
    g = await autoreply.load_grounding(conn, SITE)
    assert g.site_name == "Po Coffee" and g.store_url.startswith("https://po.")
    assert g.contact == {"email": "hi@po.example.test", "hours": "7-3"} and g.notes == "Ships Mon"
    assert conn.args_for("FROM cappe_products") == (SITE, autoreply.MAX_PRODUCTS)
    assert "status = 'active'" in conn.sql_for("fetch")[0]


def test_reply_prompt_puts_facts_before_the_message():
    g = autoreply.Grounding(site_name="Po", store_url=None, notes="")
    prompt = autoreply.build_prompt(item(kind="message", author_name=None, text="hi " * 2000),
                                    g, {"tone": "minimal", "signature": "— Po team"})
    assert prompt.index("FACTS:") < prompt.index("a direct message from a customer")
    assert "Sign off with: — Po team" in prompt and "Tone: brief." in prompt
    assert len(prompt) < 7_000


def test_draft_parse_clamps_and_defaults():
    d = autoreply.parse_draft(json.dumps({"intent": "made_up", "sentiment": "positive", "reply": "  Yes we do!  ",
                                          "confidence": 1.7, "needs_human": 0, "facts_used": ["Product: Beans", ""]}),
                              model="m")
    assert (d.intent, d.reply, d.confidence, d.needs_human, d.facts_used) == ("other", "Yes we do!", 1.0, False,
                                                                              ["Product: Beans"])
    d = autoreply.parse_draft('{"reply": null, "confidence": "high"}', model="m")
    assert d.reply is None and d.confidence == 0.0 and d.intent == "other"


def draft(**over):
    base = dict(intent="product_question", sentiment="neutral", reply="Yes, oat milk is $0.50 extra.",
                confidence=0.9, needs_human=False, facts_used=["Product: Oat Latte"], model="claude-haiku-5-5")
    return autoreply.Draft(**{**base, **over})


AUTO = {"autoreply_mode": "auto", "max_auto_per_hour": 20}


@pytest.mark.parametrize("settings,d,pre,sent,expected", [
    (AUTO, draft(), "consider", 0, "send"),
    (AUTO, draft(intent="spam"), "consider", 0, "skip"),
    (AUTO, draft(), "escalate", 0, "escalate"),
    # A hard-stop hit escalates even when the model calls it spam.
    (AUTO, draft(intent="spam"), "escalate", 0, "escalate"),
    (AUTO, draft(needs_human=True), "consider", 0, "escalate"),
    (AUTO, draft(reply=None), "consider", 0, "escalate"),
    ({**AUTO, "autoreply_mode": "review"}, draft(), "consider", 0, "draft"),
    (AUTO, draft(intent="complaint"), "consider", 0, "draft"),
    (AUTO, draft(intent="order_issue"), "consider", 0, "draft"),
    (AUTO, draft(confidence=0.5), "consider", 0, "draft"),
    (AUTO, draft(), "consider", 20, "draft"),
    ({"autoreply_mode": "auto", "max_auto_per_hour": 0}, draft(), "consider", 0, "draft"),
])
def test_decide(settings, d, pre, sent, expected):
    assert autoreply.decide(settings, d, pre, auto_sent_last_hour=sent) == expected


G = autoreply.Grounding(site_name="Po", store_url="https://po.example.test",
                       contact={"email": "hi@po.example.test", "phone": "+1 (415) 555-0100"})


@pytest.mark.parametrize("reply,reason", [
    ("Yes! Order at https://po.example.test/shop", None),
    ("See https://po.example.test.", None),
    ("Email hi@po.example.test or call +1 415 555 0100", None),
    ("Grab it at https://evil.example.test/deal", "link"),
    ("Visit www.cheap-knockoffs.test", "link"),
    ("Yes, see https://po.example.test.evil.test", "link"),
    ("DM me at someone@else.test", "email"),
    ("Text 555 867 5309 for a deal", "phone"),
    ("We'll refund you right away", "hard_stop"),
])
def test_reply_guard_holds_what_a_commenter_could_have_planted(reply, reason):
    assert autoreply.reply_guard(reply, G) == reason


def test_reply_guard_without_a_store_url_holds_every_link():
    assert autoreply.reply_guard("https://po.example.test", autoreply.Grounding("Po", None)) == "link"
    assert autoreply.reply_guard("Thanks!", autoreply.Grounding("Po", None)) is None


class InboxSpy:
    """The inbox store calls `handle_item` makes, recorded."""

    def __init__(self, monkeypatch, *, sent_last_hour=0):
        self.statuses, self.replies, self.marks = [], [], []
        monkeypatch.setattr(inbox_store, "set_item_status", self._status)
        monkeypatch.setattr(inbox_store, "create_reply", self._create)
        monkeypatch.setattr(inbox_store, "mark_reply", self._mark)
        monkeypatch.setattr(inbox_store, "auto_replies_last_hour", AsyncMock(return_value=sent_last_hour))

    async def _status(self, conn, inbox_id, status, classification=None):
        self.statuses.append((status, classification))

    async def _create(self, conn, **kw):
        row = {"id": uuid4(), **kw}
        self.replies.append(row)
        return row

    async def _mark(self, conn, reply_id, **kw):
        self.marks.append(kw)


def _wire(monkeypatch, *, model="claude-haiku-5-5", result=None, error=None):
    monkeypatch.setattr(autoreply, "model_for", AsyncMock(return_value=model))
    monkeypatch.setattr(autoreply, "load_grounding", AsyncMock(return_value=autoreply.Grounding("Po", None)))
    if error:
        monkeypatch.setattr(autoreply, "draft_reply", AsyncMock(side_effect=error))
    else:
        monkeypatch.setattr(autoreply, "draft_reply", AsyncMock(return_value=result or draft()))


@pytest.mark.asyncio
@pytest.mark.parametrize("settings,it,reason", [
    ({"autoreply_mode": "off"}, item(), "off"),
    ({**AUTO, "reply_to_comments": False}, item(), "comments_off"),
    ({**AUTO, "reply_to_messages": False}, item(kind="message"), "messages_off"),
])
async def test_handle_item_leaves_what_the_owner_turned_off(monkeypatch, settings, it, reason):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch)
    assert await autoreply.handle_item(None, it, settings, send=AsyncMock()) == {"outcome": "left", "reason": reason}
    assert spy.statuses == [] and autoreply.model_for.await_count == 0


@pytest.mark.asyncio
async def test_handle_item_skips_empty_text_before_any_model_call(monkeypatch):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch)
    out = await autoreply.handle_item(None, item(text=" "), AUTO, send=AsyncMock())
    assert out == {"outcome": "skipped", "reason": "empty"} and spy.statuses[0][0] == "skipped"
    assert autoreply.model_for.await_count == 0


@pytest.mark.asyncio
async def test_without_a_model_a_hard_stop_still_escalates_and_the_rest_waits(monkeypatch):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch, model=None)
    out = await autoreply.handle_item(None, item(text="refund please"), AUTO, send=AsyncMock())
    assert out == {"outcome": "escalated", "reason": "refund"} and spy.statuses == [("escalated", {"escalated_on": "refund"})]
    out = await autoreply.handle_item(None, item(), AUTO, send=AsyncMock())
    assert out == {"outcome": "left", "reason": "no_model"}


@pytest.mark.asyncio
async def test_a_failed_draft_never_sends(monkeypatch):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch, error=RuntimeError("declined"))
    send = AsyncMock()
    assert (await autoreply.handle_item(None, item(), AUTO, send=send))["reason"] == "draft_failed"
    assert (await autoreply.handle_item(None, item(text="I'm injured"), AUTO, send=send))["outcome"] == "escalated"
    send.assert_not_awaited()
    assert spy.replies == []


@pytest.mark.asyncio
async def test_spam_is_skipped_and_escalations_keep_their_draft(monkeypatch):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch, result=draft(intent="spam"))
    assert (await autoreply.handle_item(None, item(), AUTO, send=AsyncMock()))["outcome"] == "skipped"
    _wire(monkeypatch, result=draft())
    out = await autoreply.handle_item(None, item(text="this is a scam"), AUTO, send=AsyncMock())
    assert out["outcome"] == "escalated" and spy.replies[-1]["mode"] == "approved"
    assert spy.statuses[-1][1]["escalated_on"] == "scam"


@pytest.mark.asyncio
async def test_review_mode_drafts_and_auto_mode_sends(monkeypatch):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch)
    send = AsyncMock(return_value="r1")
    out = await autoreply.handle_item(None, item(), {**AUTO, "autoreply_mode": "review"}, send=send)
    assert out["outcome"] == "drafted" and spy.replies[-1]["status"] == "draft"
    send.assert_not_awaited()

    it = item()
    out = await autoreply.handle_item(None, it, AUTO, send=send)
    assert out["outcome"] == "sent"
    send.assert_awaited_once_with(it, "Yes, oat milk is $0.50 extra.")
    assert spy.replies[-1]["mode"] == "auto" and spy.replies[-1]["grounding"]["decision"] == "send"
    assert [m["status"] for m in spy.marks] == ["sending", "sent"] and spy.marks[-1]["external_reply_id"] == "r1"
    assert spy.statuses[-1][0] == "replied" and spy.statuses[-1][1]["intent"] == "product_question"


@pytest.mark.asyncio
async def test_a_planted_link_is_held_for_the_owner_not_sent(monkeypatch):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch, result=draft(reply="Best price at https://evil.example.test"))
    send = AsyncMock()
    out = await autoreply.handle_item(None, item(), AUTO, send=send)
    assert out["outcome"] == "drafted"
    send.assert_not_awaited()
    assert spy.statuses[-1][1]["held_for"] == "link" and spy.replies[-1]["mode"] == "approved"


@pytest.mark.asyncio
async def test_a_failed_send_leaves_a_draft_to_resend(monkeypatch):
    spy = InboxSpy(monkeypatch)
    _wire(monkeypatch)
    out = await autoreply.handle_item(None, item(), AUTO, send=AsyncMock(side_effect=ProviderError("down")))
    assert out["outcome"] == "failed"
    assert spy.marks[-1]["status"] == "failed" and spy.statuses[-1][0] == "drafted"


@pytest.mark.asyncio
async def test_the_hourly_cap_turns_sends_into_drafts(monkeypatch):
    InboxSpy(monkeypatch, sent_last_hour=20)
    _wire(monkeypatch)
    send = AsyncMock()
    assert (await autoreply.handle_item(None, item(), AUTO, send=send))["outcome"] == "drafted"
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_draft_reply_runs_one_low_effort_json_call(monkeypatch):
    from app.core.services import anthropic_messages

    seen = {}

    async def fake_generate(prompt, **kwargs):
        seen.update(kwargs)
        return json.dumps({"intent": "praise", "reply": "Thank you!", "confidence": 0.95})

    monkeypatch.setattr(anthropic_messages, "generate_text", fake_generate)
    d = await autoreply.draft_reply(item(), autoreply.Grounding("Po", None), {"tone": "friendly"}, model="m")
    assert d.intent == "praise" and d.reply == "Thank you!"
    assert seen["model"] == "m" and seen["json_output"] is True and seen["effort"] == "low"
    assert "Never say you are an AI" in seen["system"]


# ── metrics ─────────────────────────────────────────────────────────────────

CRED = {"id": CONN, "site_id": SITE, "platform": "instagram", "external_id": "ig1", "token": "t", "status": "connected"}


@pytest.mark.asyncio
async def test_refresh_connection_records_or_marks_the_failure(monkeypatch):
    provider = SimpleNamespace(account_metrics=AsyncMock(return_value={"followers_count": 5}))
    monkeypatch.setattr(metrics, "provider_for", lambda platform: provider)
    record, mark = AsyncMock(), AsyncMock()
    monkeypatch.setattr(conn_store, "record_metrics", record)
    monkeypatch.setattr(conn_store, "mark_status", mark)
    assert await metrics.refresh_connection(None, object(), CRED) == {"ok": True, "followers_count": 5}
    record.assert_awaited_once()
    for error, status in ((ProviderError("bad token", code=190), "expired"),
                          (ProviderError("unknown field", code=100), "connected"),
                          (ProviderError("busy", retryable=True), "connected")):
        provider.account_metrics = AsyncMock(side_effect=error)
        assert (await metrics.refresh_connection(None, object(), CRED))["ok"] is False
        assert mark.await_args.args[2] == status


@pytest.mark.asyncio
async def test_refresh_recent_posts_and_refresh_all(monkeypatch):
    provider = SimpleNamespace(
        account_metrics=AsyncMock(return_value={"followers_count": 5}),
        post_metrics=AsyncMock(side_effect=[{"likes": 3}, ProviderError("gone")]),
    )
    monkeypatch.setattr(metrics, "provider_for", lambda platform: provider)
    monkeypatch.setattr(conn_store, "record_metrics", AsyncMock())
    monkeypatch.setattr(conn_store, "credentials", AsyncMock(side_effect=[CRED, None]))
    conn = QueryConn(fetch={
        "WHERE connection_id = $1 AND status = 'published'": [{"id": uuid4(), "external_post_id": "m1"},
                                                              {"id": uuid4(), "external_post_id": "m2"}],
        "ORDER BY metrics_at NULLS FIRST": [{"id": CONN}, {"id": uuid4()}],
    })
    assert await metrics.refresh_all(conn, object(), limit=10) == {"connections": 2, "accounts": 1, "posts": 1}
    assert json.loads(conn.args_for("UPDATE cappe_social_post_targets SET metrics")[1]) == {"likes": 3}


# ── the network writes ──────────────────────────────────────────────────────

class OutboundWire:
    def __init__(self, monkeypatch, *, cred=CRED, publish=None):
        self.provider = SimpleNamespace(
            publish=publish or AsyncMock(return_value=PublishResult("m1", "https://x.test/p")),
            reply=AsyncMock(return_value="r1"),
        )
        monkeypatch.setattr(outbound, "provider_for", lambda platform: self.provider)
        monkeypatch.setattr(conn_store, "credentials", AsyncMock(return_value=cred))
        self.mark = AsyncMock()
        monkeypatch.setattr(conn_store, "mark_status", self.mark)
        self.success, self.failure = AsyncMock(), AsyncMock(return_value="failed")
        self.rollup = AsyncMock(return_value="published")
        monkeypatch.setattr(post_store, "record_success", self.success)
        monkeypatch.setattr(post_store, "record_failure", self.failure)
        monkeypatch.setattr(post_store, "rollup_post", self.rollup)


CLAIM = {"id": uuid4(), "post_id": POST, "connection_id": CONN, "attempts": 1}


@pytest.mark.asyncio
async def test_publish_target_success_rolls_up_the_post(monkeypatch):
    wire = OutboundWire(monkeypatch)
    conn = QueryConn(fetchrow={"FROM cappe_social_posts WHERE id = $1": post_row(link_url="https://po.example.test")})
    assert await outbound.publish_target(conn, object(), CLAIM) == "published"
    kwargs = wire.provider.publish.await_args.kwargs
    assert kwargs["media"] == [IMG] and kwargs["link_url"] == "https://po.example.test" and kwargs["token"] == "t"
    wire.success.assert_awaited_once()
    wire.rollup.assert_awaited_once_with(conn, POST)


@pytest.mark.asyncio
@pytest.mark.parametrize("row,cred", [
    (None, CRED),
    (post_row(status="cancelled"), CRED),
    (post_row(), None),
    (post_row(), {**CRED, "status": "expired"}),
    (post_row(media="[]"), CRED),                 # Instagram with no photo
])
async def test_publish_target_refusals_fail_without_a_network_call(monkeypatch, row, cred):
    wire = OutboundWire(monkeypatch, cred=cred)
    conn = QueryConn(fetchrow={"FROM cappe_social_posts WHERE id = $1": row})
    assert await outbound.publish_target(conn, object(), CLAIM) == "failed"
    wire.provider.publish.assert_not_awaited()
    assert wire.failure.await_args.args[3].retryable is False


@pytest.mark.asyncio
async def test_publish_target_token_errors_mark_the_connection_and_bugs_dont_stop_the_sweep(monkeypatch):
    wire = OutboundWire(monkeypatch, publish=AsyncMock(side_effect=ProviderError("token", code=190)))
    conn = QueryConn(fetchrow={"FROM cappe_social_posts WHERE id = $1": post_row()})
    await outbound.publish_target(conn, object(), CLAIM)
    assert wire.mark.await_args.args[2] == "expired"
    wire = OutboundWire(monkeypatch, publish=AsyncMock(side_effect=KeyError("bug")))
    assert await outbound.publish_target(conn, object(), CLAIM) == "failed"
    wire.rollup.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_reply_checks_the_connection_and_marks_refused_tokens(monkeypatch):
    wire = OutboundWire(monkeypatch)
    it = item()
    assert await outbound.send_reply(None, object(), it, "Yes!") == "r1"
    assert wire.provider.reply.await_args.kwargs["target_external_id"] == "c1"
    wire.provider.reply = AsyncMock(side_effect=ProviderError("token", code=190))
    with pytest.raises(ProviderError):
        await outbound.send_reply(None, object(), it, "Yes!")
    assert wire.mark.await_args.args[2] == "expired"
    for cred in (None, {**CRED, "token": ""}, {**CRED, "status": "revoked"}):
        OutboundWire(monkeypatch, cred=cred)
        with pytest.raises(ProviderError):
            await outbound.reply_credentials(None, it)


# ── what ships with the schema ──────────────────────────────────────────────

def test_migration_seeds_both_scheduler_rows_and_the_plan_features():
    import pathlib

    from app.workers.celery_app import _SCHEDULED_TASKS, celery_app

    root = pathlib.Path(__file__).resolve().parents[2]
    migration = (root / "alembic" / "versions" / "cappesocial01_social_growth.py").read_text()
    assert 'down_revision = "zzzzcappe54"' in migration
    keys = {key for key, _, _ in _SCHEDULED_TASKS}
    for key in ("cappe_social_publisher", "cappe_social_metrics"):
        assert key in keys and f"('{key}'" in migration
    for module in ("cappe_social_publisher", "cappe_social_inbound", "cappe_social_metrics"):
        assert f"app.workers.tasks.{module}" in celery_app.conf.include
    assert "jsonb_build_object('social', true)" in migration
    assert "jsonb_build_object('social_autoreply', true)" in migration
    assert "UNIQUE (connection_id, external_id)" in migration


def test_dev_refresh_scrubs_tokens_and_inbox_identities():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    sql = (root / "scripts" / "sql" / "anonymize_dev.sql").read_text()
    assert "access_token_enc = 'dev_' || replace(id::text, '-', '')" in sql
    assert "author_external_id = NULL" in sql
    refresh = (root / "scripts" / "refresh-dev-from-prod.sh").read_text()
    assert "FROM cappe_social_connections WHERE access_token_enc NOT LIKE 'dev\\_%'" in refresh
    assert "FROM cappe_social_inbox WHERE author_external_id IS NOT NULL" in refresh


# ── dropped photos ──────────────────────────────────────────────────────────

def _image(size, mode="RGB", fmt="PNG", color=(200, 30, 30)):
    import io

    from PIL import Image

    buf = io.BytesIO()
    fill = (*color, 128) if mode == "RGBA" else color
    Image.new(mode, size, fill).save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize("size,canvas", [
    ((1080, 1080), (1080, 1080)),
    ((800, 1000), (800, 1000)),        # exactly 4:5
    ((600, 1600), (1152, 1440)),       # phone story → fitted to 540x1440, padded to 4:5
    ((2000, 500), (1440, 754)),        # panorama → padded to 1.91:1 after fitting
    ((4000, 3000), (1440, 1080)),      # big photo → fitted, ratio kept
])
def test_photos_are_fitted_and_padded_never_cropped(size, canvas):
    from app.cappe.services.social import media

    out = media.prepare_image(_image(size, mode="RGBA"))
    assert (out.width, out.height) == canvas
    assert out.data[:3] == b"\xff\xd8\xff"            # JPEG
    assert out.padded is (canvas[0] / canvas[1] != size[0] / size[1])
    assert media.MIN_RATIO <= out.width / out.height <= media.MAX_RATIO + 0.01


def test_grayscale_is_converted_and_garbage_is_a_400():
    from fastapi import HTTPException

    from app.cappe.services.social import media

    assert media.prepare_image(_image((500, 500), mode="L", fmt="JPEG", color=120)).data[:2] == b"\xff\xd8"
    with pytest.raises(HTTPException) as info:
        media.prepare_image(b"not an image")
    assert info.value.status_code == 400
    assert media.target_canvas(100, 100) == (100, 100)
