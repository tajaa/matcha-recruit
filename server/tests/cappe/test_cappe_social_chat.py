"""Cappe social — the chat composer: reading "2pm tomorrow", turning the
model's plan into one the store can post, confirming it into posts, and the
routes around it.

The model is never called: `turn.think` is exercised with `generate_text`
faked, and the routes with `think` faked. The time parser and the plan
resolver are pure and tested directly.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_social_chat.py -q
"""
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.dependencies import require_cappe_account  # noqa: E402
from app.cappe.models.auth import CappeAccount  # noqa: E402
from app.cappe.routes import social_chat  # noqa: E402
from app.cappe.services.merlin import store as convo_store  # noqa: E402
from app.cappe.services.social import ai as social_ai  # noqa: E402
from app.cappe.services.social import assets as asset_store  # noqa: E402
from app.cappe.services.social import connections as conn_store  # noqa: E402
from app.cappe.services.social import inbox as inbox_store  # noqa: E402
from app.cappe.services.social import outbound  # noqa: E402
from app.cappe.services.social import posts as post_store  # noqa: E402
from app.cappe.services.social.chat import confirm as confirmer  # noqa: E402
from app.cappe.services.social.chat import plan as planner  # noqa: E402
from app.cappe.services.social.chat import turn as chat  # noqa: E402
from app.cappe.services.social.chat import when as when_parse  # noqa: E402
from app.cappe.services.social.providers import meta  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 20, 11, 42, tzinfo=LA)  # a Tuesday
SITE, CONVO, POST, ASSET = uuid4(), uuid4(), uuid4(), uuid4()
IG_ID, FB_ID = uuid4(), uuid4()
ACCOUNT = CappeAccount(id=uuid4(), email="owner@example.com", name="Owner", plan="business")
SITE_ROW = {"id": SITE, "name": "Po Coffee", "subdomain": "po", "custom_domain": "po.example.test",
            "account_id": ACCOUNT.id, "timezone": "America/Los_Angeles"}
IMG = "https://cdn.example.test/cappe/social/a.jpg"
IMG2 = "https://cdn.example.test/cappe/social/b.jpg"
ACCOUNTS = [
    {"id": IG_ID, "platform": "instagram", "handle": "pocoffee", "display_name": "pocoffee", "status": "connected"},
    {"id": FB_ID, "platform": "facebook", "handle": None, "display_name": "Po Coffee", "status": "connected"},
]
PRODUCTS = [
    {"id": uuid4(), "name": "Oat Latte", "slug": "oat-latte", "price_cents": 550, "currency": "USD"},
    {"id": uuid4(), "name": "Gift Card", "slug": None, "price_cents": None, "currency": "USD"},
]


# ── the time parser ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expect", [
    ("post across all socials at 2pm tomorrow", (date(2026, 10, 21), time(14, 0))),
    ("tomorrow at 9:30 a.m.", (date(2026, 10, 21), time(9, 30))),
    ("day after tomorrow at noon", (date(2026, 10, 22), time(12, 0))),
    ("friday at 9am", (date(2026, 10, 23), time(9, 0))),
    ("next tuesday", (date(2026, 10, 27), None)),
    ("tuesday at 10am", (date(2026, 10, 27), time(10, 0))),  # 10am already passed today
    ("tuesday at 3pm", (date(2026, 10, 20), time(15, 0))),
    ("Oct 25 at 14:30", (date(2026, 10, 25), time(14, 30))),
    ("25th of december 6pm", (date(2026, 12, 25), time(18, 0))),
    ("march 3", (date(2027, 3, 3), None)),
    ("12/24", (date(2026, 12, 24), None)),
    ("1/2/27", (date(2027, 1, 2), None)),
    ("in 2 hours", (date(2026, 10, 20), time(13, 42))),
    ("in an hour", (date(2026, 10, 20), time(12, 42))),
    ("in 3 days", (date(2026, 10, 23), time(11, 42))),
    ("in 30 minutes", (date(2026, 10, 20), time(12, 12))),
    ("tonight", (date(2026, 10, 20), time(19, 0))),
    ("tomorrow morning", (date(2026, 10, 21), time(9, 0))),
    ("at 2 tomorrow", (date(2026, 10, 21), time(14, 0))),
    ("at 9", (date(2026, 10, 21), time(9, 0))),  # 9am has passed: the next one
    ("at 5", (date(2026, 10, 20), time(17, 0))),
    ("at 12", (date(2026, 10, 20), time(12, 0))),
    ("2 pm", (date(2026, 10, 20), time(14, 0))),
    ("18:00 today", (date(2026, 10, 20), time(18, 0))),
    ("noon on saturday", (date(2026, 10, 24), time(12, 0))),
    # The hour named beats the part of the day, which picks am or pm.
    ("post tonight at 8", (date(2026, 10, 20), time(20, 0))),
    ("tomorrow morning at 10", (date(2026, 10, 21), time(10, 0))),
    ("friday afternoon at 3", (date(2026, 10, 23), time(15, 0))),
    ("this evening at 6:30", (date(2026, 10, 20), time(18, 30))),
    # A bare H:MM is daytime, like "at 2".
    ("post at 2:30 tomorrow", (date(2026, 10, 21), time(14, 30))),
    ("at 3:00", (date(2026, 10, 20), time(15, 0))),
    ("post this 9:16 video tomorrow", (date(2026, 10, 21), None)),
    # Short day names only as days; "1/2 off" and "24/7" aren't dates.
    ("she sat by the window, post at 3pm", (date(2026, 10, 20), time(15, 0))),
    ("1/2 off lattes friday", (date(2026, 10, 23), None)),
    ("we're open 24/7, post this friday", (date(2026, 10, 23), None)),
    ("on sat at noon", (date(2026, 10, 24), time(12, 0))),
    ("fri 3pm", (date(2026, 10, 23), time(15, 0))),
    ("next sun", (date(2026, 10, 25), None)),
])
def test_parse_reads_the_owners_words(text, expect):
    found = when_parse.parse(text, NOW)
    assert (found.day, found.clock) == expect and not found.now


@pytest.mark.parametrize("text", ["post this now", "right now please", "share them now", "ASAP",
                                  "the sun is out, post it now", "c'mon post it now",
                                  "the friday special is back, post it now"])
def test_parse_now(text):
    assert when_parse.parse(text, NOW) == when_parse.When(now=True)


@pytest.mark.parametrize("text", ["", "new menu now available", "link the oat latte", "20% off at 3 items",
                                  "at 30", "13pm", "2/30", "feb 30"])
def test_parse_leaves_out_what_it_cant_read(text):
    assert when_parse.parse(text, NOW) is None


def test_parse_internals():
    assert when_parse._hour(13, 0, "pm") is None and when_parse._hour(25, 0, None) is None
    assert when_parse._hour(10, 75, None) is None
    assert when_parse._business_hour(0) is None and when_parse._business_hour(20) is None
    assert when_parse._future_date(2, 30, NOW.date()) is None
    assert when_parse.When().empty


# ── resolving a plan ────────────────────────────────────────────────────────

def test_resolve_when_prefers_the_owner_then_the_model():
    owner = planner.resolve_when("at 2pm tomorrow", {"date": "2026-11-05", "time": "09:00"}, NOW, "America/Los_Angeles")
    assert owner["local"] == "2026-10-21T14:00" and owner["source"] == "owner"
    assert owner["scheduled_at"] == "2026-10-21T21:00:00+00:00" and owner["label"].endswith("PDT")
    model = planner.resolve_when("post the latte", {"mode": "at", "date": "2026-10-22", "time": "08:15"}, NOW, "UTC")
    assert model["local"] == "2026-10-22T08:15" and model["source"] == "model"
    words = planner.resolve_when("go", {"words": "friday 5pm"}, NOW, "UTC")
    assert words["local"] == "2026-10-23T17:00"
    assert planner.resolve_when("post it now", {}, NOW, "UTC")["mode"] == "now"
    assert planner.resolve_when("go", {"mode": "now"}, NOW, "UTC")["source"] == "model"
    assert planner.resolve_when("go", {"date": "nope", "time": "25:00"}, NOW, "UTC")["mode"] == "unset"
    day_only = planner.resolve_when("thursday", {}, NOW, "UTC")
    assert day_only["local"] == "2026-10-22T10:00" and day_only["defaulted_clock"]
    clock_only = planner.resolve_when("go", {"time": "09:00"}, NOW, "UTC")
    assert clock_only["local"] == "2026-10-21T09:00"
    past = planner.resolve_when("go", {"date": "2026-10-19", "time": "09:00"}, NOW, "UTC")
    assert past["mode"] == "unset" and past["past"]


def test_resolve_when_across_the_clock_change():
    # US clocks go back on Sunday 1 Nov 2026: 2pm that day is PST (UTC-8).
    eve = datetime(2026, 10, 31, 10, 0, tzinfo=LA)
    out = planner.resolve_when("tomorrow at 2pm", {}, eve, "America/Los_Angeles")
    assert out["scheduled_at"] == "2026-11-01T22:00:00+00:00" and out["label"].endswith("PST")


def _model(**plan):
    base = {"when": {"mode": "at", "date": None, "time": None}, "networks": [], "link": {"kind": "store"},
            "posts": [{"items": [1, 2], "instagram": {"caption": "New latte", "hashtags": ["oat", "#Coffee", "oat"]},
                       "facebook": {"text": "Our oat latte is back"}, "alt_text": "A latte"}]}
    return {"reply": "Planned.", "needs": [], "plan": {**base, **plan}}


ITEMS = [{"kind": "image", "url": IMG}, {"kind": "image", "url": IMG2}]


def resolve(out, message="post these tomorrow at 2pm", items=ITEMS, accounts=ACCOUNTS):
    return planner.resolve(out, message=message, items=items, accounts=accounts, products=PRODUCTS,
                           origin="https://po.example.test", now_local=NOW, tz_name="America/Los_Angeles")


def test_resolve_builds_a_postable_plan():
    plan = resolve(_model(link={"kind": "product", "product_id": str(PRODUCTS[0]["id"])}))
    assert plan["when"]["local"] == "2026-10-21T14:00"
    assert [a["platform"] for a in plan["accounts"]] == ["instagram", "facebook"]
    assert plan["link"] == {"kind": "product", "product_id": str(PRODUCTS[0]["id"]), "product_name": "Oat Latte",
                            "url": "https://po.example.test/shop/oat-latte"}
    post = plan["posts"][0]
    assert post["items"] == [1, 2] and post["media"] == ITEMS
    assert post["instagram"]["hashtags"] == ["#oat", "#coffee"] and post["offset_days"] == 0
    assert plan["warnings"] == [] and plan["needs"] == []
    assert planner.summary(plan) == "Planned 1 post to Facebook, Instagram, Wed, Oct 21 · 2:00 PM PDT"


def test_resolve_names_networks_and_says_what_it_cant_do():
    plan = resolve(_model(networks=["instagram", "tiktok", "youtube"]))
    assert [a["platform"] for a in plan["accounts"]] == ["instagram"]
    assert "TikTok and YouTube can't be posted to yet" in plan["warnings"][0]
    lonely = resolve(_model(networks=["facebook"]), accounts=[ACCOUNTS[0]])
    assert any("Facebook isn't connected" in w for w in lonely["warnings"]) and lonely["accounts"] == []
    nobody = resolve(_model(), accounts=[])
    assert any("No account is connected" in w for w in nobody["warnings"])


@pytest.mark.parametrize("link,kind,warning", [
    ({"kind": "product", "product_id": "nope"}, "store", "couldn't match"),
    ({"kind": "product", "product_id": str(PRODUCTS[1]["id"])}, "store", "Gift Card has no page"),
    ({"kind": "none"}, "none", None),
    ("garbage", "store", None),
])
def test_resolve_link(link, kind, warning):
    plan = resolve(_model(link=link))
    assert plan["link"]["kind"] == kind
    assert (warning in " ".join(plan["warnings"])) if warning else not plan["warnings"]
    assert planner._link({"kind": "store"}, {}, None, [])["kind"] == "none"  # no public origin


def test_resolve_keeps_videos_alone_and_carousels_small():
    items = [{"kind": "image", "url": f"{IMG}?{i}"} for i in range(12)] + [{"kind": "video", "asset_id": "v1"}]
    plan = resolve(_model(posts=[{"items": list(range(1, 14)), "instagram": {"caption": "All of it"}}]), items=items)
    assert [p["items"] for p in plan["posts"]] == [list(range(1, 11)), [11, 12], [13]]
    assert all(p["instagram"]["caption"] == "All of it" for p in plan["posts"])


def test_resolve_never_drops_an_item():
    items = ITEMS + [{"kind": "video", "asset_id": "v1"}]
    plan = resolve(_model(posts=[{"items": [1, 1, 99], "instagram": {"caption": "One"}}, "junk"]), items=items)
    assert [p["items"] for p in plan["posts"]] == [[1], [2], [3]]
    assert "weren't in the plan" in plan["warnings"][0]
    spare = resolve(_model(posts=[{"items": [], "instagram": {"caption": "Words only"}}]), items=items)
    assert [p["instagram"]["caption"] for p in spare["posts"]] == ["Words only"] * 3 and not spare["warnings"]
    silent = resolve(_model(posts=[]), items=items)
    assert "no words yet" in silent["warnings"][0]


def test_resolve_needs_and_spread():
    plan = resolve(_model(spread_days=2, posts=[{"items": [1]}, {"items": [2]}]), message="post these")
    assert plan["when"]["mode"] == "unset" and plan["needs"] == ["when"]
    assert [p["offset_days"] for p in plan["posts"]] == [0, 2]
    words_only = resolve(_model(posts=[{"items": [], "facebook": {"text": "Back Monday"}}]), items=[])
    assert words_only["posts"][0]["items"] == [] and words_only["posts"][0]["media"] == []
    empty = resolve({**_model(posts=[]), "needs": ["what", "bogus"]}, items=[])
    assert empty["needs"] == ["what"] and empty["posts"] == []
    assert resolve(_model(spread_days="x"))["spread_days"] == 0
    assert resolve({"reply": "Hi"}) is None
    past = resolve(_model(when={"mode": "at", "date": "2026-10-01", "time": "10:00"}), message="go")
    assert any("already passed" in w for w in past["warnings"])
    day = resolve(_model(), message="thursday")
    assert any("10:00 AM" in w for w in day["warnings"])


def test_utm_caption_prompt_and_reply_parsing():
    assert planner.with_utm(None, "instagram") is None
    tagged = planner.with_utm("https://po.example.test/shop/x?ref=a&utm_source=keep", "facebook")
    assert "ref=a" in tagged and "utm_source=keep" in tagged and "utm_medium=social" in tagged
    assert planner.compose_caption({"caption": "Hi #oat", "hashtags": ["#oat", "#latte"]}) == "Hi #oat\n\n#latte"
    assert planner.compose_caption({"caption": "Hi", "hashtags": []}) == "Hi"
    assert planner.summary(None) is None
    assert planner.parse_reply('```json\n{"reply": "ok"}\n```') == {"reply": "ok"}
    items = [{"kind": "image", "url": IMG}, {"kind": "video", "duration_ms": 14200, "shape": "vertical"},
             {"kind": "video", "poster": "p"}]
    prompt = planner.build_prompt(
        site=SITE_ROW, settings={"tone": "playful", "signature": "— Po", "default_hashtags": ["#po"],
                                 "business_facts": "Oat milk is free."},
        accounts=ACCOUNTS, products=PRODUCTS, items=items, pictures=[1, 3],
        history=[{"role": "user", "content": "post these"}, {"role": "assistant", "content": "Planned.",
                                                            "ops_summary": "Planned 1 post"}],
        current_plan={"posts": [{"items": [1], "instagram": {"caption": "Old"}}]}, message="make it funnier",
        now_local=NOW)
    for part in ("Voice: playful", "— Po", "#po", "Oat milk is free.", "Tuesday, October 20, 2026",
                 "instagram @pocoffee", f"id={PRODUCTS[0]['id']}: Oat Latte ($5.50)", "#2 video, 14 s, vertical, still being prepared",
                 "Pictures attached, in order: #1, #3", "You: Planned. [Planned 1 post]", "Post 1: items [1]",
                 "Owner's message: make it funnier"):
        assert part in prompt, part
    bare = planner.build_prompt(site={}, settings={}, accounts=[], products=[], items=[], pictures=[], history=[],
                                current_plan=None, message="hi", now_local=NOW)
    assert "No accounts are connected yet." in bare and "Nothing dropped yet." in bare


# ── confirming ──────────────────────────────────────────────────────────────

PLAN = resolve(_model(link={"kind": "product", "product_id": str(PRODUCTS[0]["id"])}))


def test_apply_edits_and_schedule():
    edited = confirmer.apply_edits(PLAN, [{"instagram": {"caption": "Mine", "hashtags": ["#mine"]},
                                           "facebook": {"text": "Mine too"}, "alt_text": None}], keep_link=False)
    assert edited["posts"][0]["instagram"] == {"caption": "Mine", "hashtags": ["#mine"]}
    assert edited["link"]["url"] is None and PLAN["link"]["url"]  # the original isn't touched
    with pytest.raises(confirmer.PlanError, match="plan changed"):
        confirmer.apply_edits(PLAN, [], keep_link=True)
    assert confirmer.apply_edits(PLAN, None, keep_link=True)["posts"][0]["instagram"]["caption"] == "New latte"
    now = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)
    assert confirmer.schedule("draft", None, LA, now) is None
    assert confirmer.schedule("now", None, LA, now) == now
    assert confirmer.schedule("at", "2026-10-21T14:00", LA, now) == datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)
    for when, message in (("bad", "Pick a time"), ("2026-10-01T10:00", "already passed"), ("2028-01-01T10:00", "year")):
        with pytest.raises(confirmer.PlanError, match=message):
            confirmer.schedule("at", when, LA, now)


def test_check_refuses_what_cant_go_out():
    confirmer.check(PLAN, ["instagram", "facebook"], mode="at")
    confirmer.check({**PLAN, "posts": [{"media": [], "instagram": {}, "facebook": {}}]}, [], mode="draft")
    with pytest.raises(confirmer.PlanError, match="nothing to post"):
        confirmer.check({**PLAN, "posts": []}, ["instagram"], mode="at")
    with pytest.raises(confirmer.PlanError, match="at least one account"):
        confirmer.check(PLAN, [], mode="now")
    two = {**PLAN, "posts": [PLAN["posts"][0], {"media": [], "instagram": {"caption": "x"}, "facebook": {}}]}
    with pytest.raises(confirmer.PlanError, match="Post 2: Instagram posts need a photo or a video"):
        confirmer.check(two, ["instagram"], mode="at")
    with pytest.raises(confirmer.PlanError, match="^Instagram posts need"):
        confirmer.check({**PLAN, "posts": [two["posts"][1]]}, ["instagram"], mode="at")


@pytest.mark.asyncio
async def test_create_posts_writes_each_network_its_copy(monkeypatch):
    created = []

    async def create_post(conn, **kw):
        created.append(kw)
        return {"id": uuid4()}

    monkeypatch.setattr(post_store, "create_post", create_post)
    targets, content, now = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(post_store, "set_targets", targets)
    monkeypatch.setattr(post_store, "set_content", content)
    monkeypatch.setattr(post_store, "publish_now", now)
    video = {"kind": "video", "asset_id": "v1", "poster": "p"}
    plan = {**PLAN, "posts": [PLAN["posts"][0], {**PLAN["posts"][0], "media": [video], "offset_days": 2,
                                                  "facebook": {"text": ""}, "alt_text": None}]}
    accounts = [{"connection_id": str(IG_ID), "platform": "instagram"}]
    first = datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)
    out = await confirmer.create_posts(QueryConn(), site_id=SITE, plan=plan, accounts=accounts, first_at=first,
                                       publish_now=True, provenance={"plan_id": "p1"})
    assert [o["publish_now"] for o in out] == [True, False]
    assert created[0]["scheduled_at"] is None and created[1]["scheduled_at"] == first + timedelta(days=2)
    assert created[0]["caption"] == "New latte\n\n#oat #coffee"
    assert created[0]["media"] == [{"kind": "image", "url": IMG, "alt": "A latte"}, {"kind": "image", "url": IMG2, "alt": "A latte"}]
    assert created[1]["media"] == [{"kind": "video", "asset_id": "v1", "alt": None}]
    assert created[0]["product_id"] == PRODUCTS[0]["id"] and created[1]["ai_meta"] == {"chat": {"plan_id": "p1"}}
    by_platform = content.await_args_list[1].args[2]
    # Facebook falls back to the Instagram words when it has none of its own.
    assert by_platform["facebook"]["text"] == "New latte\n\n#oat #coffee"
    assert "utm_source=instagram" in by_platform["instagram"]["link_url"]
    assert targets.await_args_list[0].args[2] == [IG_ID] and now.await_count == 1


@pytest.mark.asyncio
async def test_set_content_and_outbound_use_each_networks_copy(monkeypatch):
    conn = QueryConn()
    await post_store.set_content(conn, POST, {"instagram": {"text": "IG"}, "facebook": {"text": "FB"}})
    assert [c[2][1] for c in conn.calls] == ["instagram", "facebook"]
    assert json.loads(conn.calls[0][2][2]) == {"text": "IG"}
    post_row = {"id": POST, "site_id": SITE, "caption": "Shared", "media": [{"kind": "image", "url": IMG}],
                "link_url": "https://po.example.test", "status": "publishing"}
    conn = QueryConn(fetchrow={"FROM cappe_social_posts WHERE id": post_row})
    monkeypatch.setattr(conn_store, "credentials", AsyncMock(return_value={
        "id": IG_ID, "platform": "instagram", "external_id": "ig1", "token": "t", "status": "connected"}))
    publish = AsyncMock(return_value=SimpleNamespace(external_post_id="m1", permalink=None))
    monkeypatch.setattr(meta, "publish", publish)
    monkeypatch.setattr(post_store, "record_success", AsyncMock())
    monkeypatch.setattr(post_store, "rollup_post", AsyncMock())
    claim = {"id": uuid4(), "post_id": POST, "connection_id": IG_ID, "attempts": 1,
             "content": {"text": "IG words", "link_url": "https://po.example.test/?utm_source=instagram"}}
    await outbound.publish_target(conn, object(), claim)
    assert publish.await_args.kwargs["caption"] == "IG words"
    assert publish.await_args.kwargs["link_url"].endswith("utm_source=instagram")
    await outbound.publish_target(conn, object(), {**claim, "content": {}})
    assert publish.await_args.kwargs["caption"] == "Shared"


# ── a turn ──────────────────────────────────────────────────────────────────

def test_items_pictures_and_staged_actions(monkeypatch):
    monkeypatch.setattr(chat, "get_storage", lambda: SimpleNamespace(cloudfront_domain="cdn.example.test"))
    assert chat.own_image(IMG) and not chat.own_image("https://evil.example.test/a.jpg") and not chat.own_image(None)
    frames = [{"url": "f0", "t_ms": 1}, {"url": "f1", "t_ms": 2}]
    assets = {"v1": {"status": "ready", "frames": frames, "duration_ms": 9000, "width": 1080, "height": 1920},
              "v2": {"status": "failed"},
              "v3": {"status": "rendering", "frames": [], "width": 1920, "height": 1080},
              "v4": {"status": "ready", "frames": [], "width": None, "height": None}}
    messages = [
        {"role": "user", "attachments": [{"kind": "image", "url": IMG}, {"kind": "video", "asset_id": "v1"}, "junk",
                                         {"kind": "image"}]},
        {"role": "assistant", "attachments": [{"kind": "image", "url": IMG2}]},
        {"role": "user", "attachments": [{"kind": "image", "url": IMG}, {"kind": "video", "asset_id": "v2"},
                                         {"kind": "video", "asset_id": "v3"}, {"kind": "video", "asset_id": "v4"},
                                         {"kind": "video", "asset_id": "gone"}]},
    ]
    items = chat.items_from(messages, assets)
    assert [i.get("url") or i.get("asset_id") for i in items] == [IMG, "v1", "v3", "v4"]
    assert items[1]["poster"] == "f1" and items[1]["shape"] == "vertical" and items[2]["shape"] == "landscape"
    assert items[3]["shape"] is None
    assert chat._shape({"width": 100, "height": 100}) == "square"
    # A chat that goes on after a confirm plans only what's new.
    done = {**chat.staged({"posts": [{"media": [{"kind": "image", "url": IMG}, {"kind": "video", "asset_id": "v1"},
                                                 {"kind": "image"}]}]}, revision=1, model="m"), "status": "executed"}
    keys = chat.posted_keys([done, chat.staged({"posts": [{"media": [{"url": IMG2}]}]}, revision=2, model="m"),
                             {"kind": "other", "status": "executed"}])
    assert keys == {IMG, "v1"}
    assert [i.get("url") or i.get("asset_id") for i in chat.items_from(messages, assets, exclude=keys)] == ["v3", "v4"]
    blocks, numbers = chat.pictures(items)
    assert numbers == [1, 2] and blocks[1]["source"]["url"] == "f1"
    many = [{"kind": "image", "url": f"u{i}"} for i in range(12)]
    assert len(chat.pictures(many)[0]) == planner.MAX_PICTURES
    first = chat.staged({"posts": []}, revision=1, model="m")
    second = chat.staged({"posts": []}, revision=2, model="m")
    actions = chat.replace_proposed(second)([first, {"kind": "setup_x", "status": "proposed"}])
    assert [a["status"] for a in actions] == ["replaced", "proposed", "proposed"]
    assert chat.latest(actions)["id"] == second["id"] and chat.proposed(actions)["id"] == second["id"]
    assert chat.next_revision(actions) == 3 and chat.next_revision([]) == 1
    assert chat.latest([]) is None and chat.proposed([{**first, "status": "executed"}]) is None


@pytest.mark.asyncio
async def test_think_calls_claude_once_with_the_pictures(monkeypatch):
    monkeypatch.setattr(chat, "model_for", AsyncMock(return_value="claude-haiku-5-5"))
    generate = AsyncMock(return_value=json.dumps(_model()))
    monkeypatch.setattr(chat.anthropic_messages, "generate_text", generate)
    reply, plan, model = await chat.think(
        site=SITE_ROW, settings={}, accounts=ACCOUNTS, products=PRODUCTS, items=ITEMS, history=[],
        current_plan=None, message="tomorrow at 2pm", now_local=NOW, tz_name="America/Los_Angeles",
        origin="https://po.example.test")
    assert reply == "Planned." and plan["when"]["local"] == "2026-10-21T14:00" and model == "claude-haiku-5-5"
    kwargs = generate.await_args.kwargs
    assert kwargs["system"] == planner.SYSTEM and kwargs["json_output"] and len(kwargs["attachments"]) == 2
    generate.return_value = "{}"
    reply, plan, _ = await chat.think(site=SITE_ROW, settings={}, accounts=[], products=[], items=[], history=[],
                                      current_plan=None, message="hi", now_local=NOW, tz_name="UTC", origin=None)
    assert plan is None and reply == "What would you like to post?"
    generate.return_value = json.dumps({**_model(), "reply": ""})
    assert (await chat.think(site=SITE_ROW, settings={}, accounts=[], products=[], items=ITEMS, history=[],
                             current_plan=None, message="go", now_local=NOW, tz_name="UTC",
                             origin=None))[0] == chat.FALLBACK_REPLY
    monkeypatch.setattr(chat, "model_for", AsyncMock(return_value=None))
    with pytest.raises(social_ai.AiUnavailable):
        await chat.think(site=SITE_ROW, settings={}, accounts=[], products=[], items=[], history=[], current_plan=None,
                         message="hi", now_local=NOW, tz_name="UTC", origin=None)


# ── routes ──────────────────────────────────────────────────────────────────

class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TxConn(QueryConn):
    def transaction(self):
        return _Tx()


def ent(*features):
    return SimpleNamespace(has=lambda f: f in features)


def message(role="assistant", content="Planned.", attachments=None):
    return {"id": uuid4(), "role": role, "content": content, "attachments": attachments or [],
            "created_at": datetime.now(timezone.utc)}


def convo(**over):
    return {"id": CONVO, "account_id": ACCOUNT.id, "site_id": SITE, "page_id": None, "kind": "social",
            "staged_actions": [], "title": "Latte", "created_at": NOW, "updated_at": NOW, **over}


@pytest.fixture
def world(monkeypatch):
    conn = TxConn(fetchrow={"FROM cappe_sites WHERE id = $1 AND account_id": SITE_ROW},
                  fetch={"FROM cappe_products": PRODUCTS,
                         "FROM cappe_merlin_conversations": [{"id": CONVO, "title": "Latte", "updated_at": NOW}],
                         "ai_meta->'chat'->>'conversation_id'": []})
    depth = SimpleNamespace(n=0)

    class Ctx:
        async def __aenter__(self):
            depth.n += 1
            return conn

        async def __aexit__(self, *exc):
            depth.n -= 1
            return False

    monkeypatch.setattr(social_chat, "get_connection", lambda: Ctx())
    monkeypatch.setattr(social_chat, "resolve_entitlements", AsyncMock(return_value=ent("social", "social_video")))
    monkeypatch.setattr(social_chat, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(convo_store, "get_owned_conversation", AsyncMock(return_value=convo()))
    monkeypatch.setattr(convo_store, "create_conversation", AsyncMock(return_value={
        "id": CONVO, "title": "Post", "created_at": NOW, "updated_at": NOW}))
    monkeypatch.setattr(convo_store, "load_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(convo_store, "add_message", AsyncMock(side_effect=lambda conn, cid, **kw: message(
        kw["role"], kw["content"], kw.get("attachments"))))
    monkeypatch.setattr(convo_store, "get_messages", AsyncMock(return_value=[
        message("user", "post this", [{"kind": "image", "url": IMG}])]))
    monkeypatch.setattr(convo_store, "mutate_staged_actions", AsyncMock())
    monkeypatch.setattr(asset_store, "load_many", AsyncMock(return_value={}))
    monkeypatch.setattr(inbox_store, "get_settings", AsyncMock(return_value=dict(inbox_store.SETTINGS_DEFAULTS)))
    monkeypatch.setattr(conn_store, "list_connections", AsyncMock(return_value=ACCOUNTS))
    monkeypatch.setattr(chat, "get_storage", lambda: SimpleNamespace(cloudfront_domain="cdn.example.test"))
    w = SimpleNamespace(conn=conn, mp=monkeypatch, depth=depth)
    with route_client(social_chat.router, overrides={require_cappe_account: ACCOUNT}) as client:
        w.client = client
        yield w


BASE = f"/sites/{SITE}/social/chat"


def test_list_and_get_chats(world):
    assert world.client.get(f"{BASE}/conversations").json()[0]["title"] == "Latte"
    action = chat.staged(PLAN, revision=1, model="m")
    world.mp.setattr(convo_store, "get_owned_conversation", AsyncMock(return_value=convo(staged_actions=[action])))
    body = world.client.get(f"{BASE}/conversations/{CONVO}").json()
    assert body["messages"][0]["attachments"] == [{"kind": "image", "url": IMG}]
    assert body["plan"]["id"] == action["id"] and body["plan"]["plan"]["posts"][0]["instagram"]["caption"] == "New latte"
    world.mp.setattr(convo_store, "get_owned_conversation", AsyncMock(return_value=convo(kind="setup")))
    assert world.client.get(f"{BASE}/conversations/{CONVO}").status_code == 404
    world.mp.setattr(convo_store, "get_owned_conversation", AsyncMock(return_value=convo(site_id=uuid4())))
    assert world.client.get(f"{BASE}/conversations/{CONVO}").status_code == 404


def test_turn_plans_with_no_connection_held_during_the_model_call(world):
    seen = []

    async def think(**kw):
        seen.append((world.depth.n, kw))
        return "Planned.", PLAN, "claude-haiku-5-5"

    world.mp.setattr(chat, "think", think)
    res = world.client.post(f"{BASE}/turns", json={"message": "post this tomorrow at 2pm",
                                                   "attachments": [{"kind": "image", "url": IMG, "name": "a.jpg"}]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["conversation_id"] == str(CONVO) and body["message"]["content"] == "Planned."
    assert body["plan"]["revision"] == 1 and body["plan"]["status"] == "proposed"
    depth, kw = seen[0]
    assert depth == 0 and kw["items"] == [{"kind": "image", "url": IMG, "name": None}]
    assert kw["origin"] == "https://po.example.test" and kw["tz_name"] == "America/Los_Angeles"
    user_save = convo_store.add_message.await_args_list[0].kwargs
    assert user_save["attachments"] == [{"kind": "image", "url": IMG, "name": "a.jpg"}]
    assert convo_store.add_message.await_args_list[1].kwargs["results"] == [{"summary": planner.summary(PLAN)}]
    convo_store.create_conversation.assert_awaited_once()
    assert convo_store.mutate_staged_actions.await_count == 1


def test_turn_continues_a_chat_and_refines_the_open_plan(world):
    open_plan = chat.staged(PLAN, revision=4, model="m")
    world.mp.setattr(convo_store, "get_owned_conversation", AsyncMock(return_value=convo(staged_actions=[open_plan])))
    think = AsyncMock(return_value=("What should it say?", None, "m"))
    world.mp.setattr(chat, "think", think)
    res = world.client.post(f"{BASE}/turns", json={"conversation_id": str(CONVO), "message": "make it funnier"})
    assert res.status_code == 200 and res.json()["plan"] is None
    assert think.await_args.kwargs["current_plan"] == PLAN
    assert convo_store.create_conversation.await_count == 0 and convo_store.mutate_staged_actions.await_count == 0


@pytest.mark.parametrize("body,code,detail", [
    ({"message": "  "}, 422, "Say what to post"),
    ({"attachments": [{"kind": "image", "url": "https://evil.example.test/x.jpg"}]}, 422, "through the Social page"),
    ({"attachments": [{"kind": "video", "asset_id": str(ASSET)}]}, 422, "isn't ready"),
])
def test_turn_refusals(world, body, code, detail):
    res = world.client.post(f"{BASE}/turns", json=body)
    assert res.status_code == code and detail in res.json()["detail"]


def test_turn_video_gates_and_model_failures(world):
    body = {"attachments": [{"kind": "video", "asset_id": str(ASSET)}]}
    world.mp.setattr(social_chat, "resolve_entitlements", AsyncMock(return_value=ent("social")))
    assert world.client.post(f"{BASE}/turns", json=body).status_code == 402
    world.mp.setattr(social_chat, "resolve_entitlements", AsyncMock(return_value=ent("social", "social_video")))
    world.mp.setattr(asset_store, "load_many", AsyncMock(return_value={str(ASSET): {
        "site_id": SITE, "status": "rendering", "error": None, "frames": [], "width": 1080, "height": 1920}}))
    world.mp.setattr(chat, "think", AsyncMock(side_effect=social_ai.AiUnavailable("Needs Claude")))
    assert world.client.post(f"{BASE}/turns", json=body).status_code == 503
    world.mp.setattr(chat, "think", AsyncMock(side_effect=RuntimeError("overloaded")))
    res = world.client.post(f"{BASE}/turns", json=body)
    assert res.status_code == 502 and "try again" in res.json()["detail"]
    world.mp.setattr(asset_store, "load_many", AsyncMock(return_value={str(ASSET): {
        "site_id": uuid4(), "status": "ready", "error": None}}))
    assert world.client.post(f"{BASE}/turns", json=body).status_code == 422


def _confirm_world(world, actions):
    from app.cappe.routes import social_chat as module

    world.mp.setattr(convo_store, "lock_conversation_actions", AsyncMock(return_value=actions))
    world.mp.setattr(module.confirmer, "create_posts", AsyncMock(return_value=[
        {"id": POST, "publish_now": True}, {"id": uuid4(), "publish_now": False}]))
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value={
        "id": POST, "site_id": SITE, "caption": "x", "media": [], "link_url": None, "product_id": None,
        "status": "publishing", "scheduled_at": None, "published_at": None, "ai_meta": {}, "targets": [],
        "created_at": NOW, "updated_at": NOW}))


CONFIRM = {"revision": 1, "mode": "now", "connection_ids": [str(IG_ID)]}


def test_confirm_makes_posts_and_publishes_the_due_ones(world):
    action = chat.staged(PLAN, revision=1, model="m")
    _confirm_world(world, [action])
    from app.workers.tasks import cappe_social_publisher as publisher

    delay = Mock()
    world.mp.setattr(publisher.run_cappe_social_publish_post, "delay", delay)
    res = world.client.post(f"{BASE}/conversations/{CONVO}/plans/{action['id']}/confirm", json={
        **CONFIRM, "posts": [{"instagram": {"caption": "Mine", "hashtags": ["mine"]}, "facebook": {"text": ""}}]})
    assert res.status_code == 200, res.text
    assert res.json()["plan"]["status"] == "executed" and len(res.json()["posts"]) == 2
    delay.assert_called_once_with(str(POST))
    kwargs = social_chat.confirmer.create_posts.await_args.kwargs
    assert kwargs["plan"]["posts"][0]["instagram"] == {"caption": "Mine", "hashtags": ["#mine"]}
    assert kwargs["accounts"] == [{"connection_id": str(IG_ID), "platform": "instagram"}] and kwargs["publish_now"]
    flip = convo_store.mutate_staged_actions.await_args.args[2]
    assert flip([action])[0]["status"] == "executed"
    world.mp.setattr(publisher.run_cappe_social_publish_post, "delay", Mock(side_effect=RuntimeError("broker")))
    _confirm_world(world, [chat.staged(PLAN, revision=1, model="m")])
    plan_id = convo_store.lock_conversation_actions.return_value[0]["id"]
    assert world.client.post(f"{BASE}/conversations/{CONVO}/plans/{plan_id}/confirm", json=CONFIRM).status_code == 200


@pytest.mark.parametrize("actions,body,code,detail", [
    ([], CONFIRM, 404, "Plan not found"),
    ([{**chat.staged(PLAN, revision=1, model="m"), "id": "p1", "status": "executed"}], CONFIRM, 409, "already executed"),
    ([{**chat.staged(PLAN, revision=2, model="m"), "id": "p1"}], CONFIRM, 409, "plan changed"),
    ([{**chat.staged(PLAN, revision=1, model="m"), "id": "p1"}], {**CONFIRM, "mode": "at", "when_local": "garbage"},
     422, "Pick a time"),
    ([{**chat.staged(PLAN, revision=1, model="m"), "id": "p1"}], {**CONFIRM, "connection_ids": [str(uuid4())]},
     404, "Account not found"),
])
def test_confirm_refusals(world, actions, body, code, detail):
    _confirm_world(world, actions)
    res = world.client.post(f"{BASE}/conversations/{CONVO}/plans/p1/confirm", json=body)
    assert res.status_code == code and detail in res.json()["detail"]


def test_confirm_refuses_what_this_chat_already_posted(world):
    """A confirm made while a turn was running (or after old plans were
    pruned) can't post the same photos again: the posts table says what went."""
    action = {**chat.staged(PLAN, revision=1, model="m"), "id": "p1"}
    _confirm_world(world, [action])
    first = PLAN["posts"][0]["media"][0]
    world.mp.setattr(confirmer, "posted_from_chat", AsyncMock(return_value={str(first.get("asset_id") or first["url"])}))
    res = world.client.post(f"{BASE}/conversations/{CONVO}/plans/p1/confirm", json=CONFIRM)
    assert res.status_code == 409 and "already posted" in res.json()["detail"]
    assert not confirmer.create_posts.await_count


@pytest.mark.asyncio
async def test_posted_from_chat_and_check_media():
    conn = QueryConn(fetch={"ai_meta->'chat'->>'conversation_id'": [
        {"media": json.dumps([{"kind": "image", "url": "https://cdn.example.test/a.jpg"},
                              {"kind": "video", "asset_id": "v1"}])}]})
    assert await confirmer.posted_from_chat(conn, SITE, CONVO) == {"https://cdn.example.test/a.jpg", "v1"}
    assert conn.args_for("ai_meta->'chat'->>'conversation_id'") == (SITE, str(CONVO))
    plan = {"posts": [{"media": [{"kind": "image", "url": "https://cdn.example.test/a.jpg"}]}]}
    with pytest.raises(confirmer.AlreadyPosted):
        await confirmer.check_media(conn, SITE, CONVO, plan)
    fresh = QueryConn(fetch={"ai_meta->'chat'->>'conversation_id'": []})
    video = {"posts": [{"media": [{"kind": "video", "asset_id": "v2"}]}]}
    import app.cappe.services.social.assets as assets_module

    for found, ok in (({"v2": {"site_id": SITE, "status": "ready"}}, True),
                      ({"v2": {"site_id": SITE, "status": "failed", "error": "Too short"}}, False),
                      ({"v2": {"site_id": uuid4(), "status": "ready"}}, False), ({}, False)):
        original = assets_module.load_many
        assets_module.load_many = AsyncMock(return_value=found)
        try:
            if ok:
                await confirmer.check_media(fresh, SITE, CONVO, video)
            else:
                with pytest.raises(confirmer.PlanError):
                    await confirmer.check_media(fresh, SITE, CONVO, video)
        finally:
            assets_module.load_many = original


@pytest.mark.asyncio
async def test_spread_posts_keep_the_stores_hour_across_the_clock_change(monkeypatch):
    made = []

    async def create_post(conn, **kw):
        made.append(kw["scheduled_at"])
        return {"id": uuid4()}

    monkeypatch.setattr(post_store, "create_post", create_post)
    for name in ("set_targets", "set_content", "publish_now"):
        monkeypatch.setattr(post_store, name, AsyncMock())
    la = ZoneInfo("America/Los_Angeles")
    first = datetime(2026, 10, 31, 9, 0, tzinfo=la).astimezone(timezone.utc)
    plan = {"link": {}, "posts": [{"offset_days": 0, "media": []}, {"offset_days": 2, "media": []}]}
    await confirmer.create_posts(None, site_id=SITE, plan=plan, accounts=[], first_at=first, publish_now=False,
                                 provenance={}, tz=la)
    assert [d.astimezone(la).hour for d in made] == [9, 9]  # Nov 2 is after the change: still 9 AM


def test_confirm_a_video_plan_needs_the_video_feature(world):
    video_plan = {**PLAN, "posts": [{**PLAN["posts"][0], "media": [{"kind": "video", "asset_id": "v1"}]}]}
    _confirm_world(world, [{**chat.staged(video_plan, revision=1, model="m"), "id": "p1"}])
    world.mp.setattr(social_chat, "resolve_entitlements", AsyncMock(return_value=ent("social")))
    assert world.client.post(f"{BASE}/conversations/{CONVO}/plans/p1/confirm", json=CONFIRM).status_code == 402


def test_dismiss(world):
    action = {**chat.staged(PLAN, revision=1, model="m"), "id": "p1"}

    async def mutate(conn, cid, fn):
        return fn([action])

    world.mp.setattr(convo_store, "mutate_staged_actions", mutate)
    res = world.client.post(f"{BASE}/conversations/{CONVO}/plans/p1/dismiss")
    assert res.status_code == 200 and res.json()["status"] == "dismissed"
    assert world.client.post(f"{BASE}/conversations/{CONVO}/plans/other/dismiss").status_code == 404

