"""Cappe social — the Meta Graph provider (`services/social/providers/meta.py`).

Every call goes through an `httpx.MockTransport` that plays the Graph API, so
these pin the wire shapes we send (paths, form fields, the link appended to a
caption, carousel children, the DM envelope) and how each kind of failure is
classified (retryable or not). No network.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_social_meta.py -q
"""
import hashlib
import hmac
import json
import os
from types import SimpleNamespace
from urllib.parse import parse_qsl

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.social.providers import meta, provider_for  # noqa: E402
from app.cappe.services.social.providers.base import InboundEvent, ProviderError  # noqa: E402

_ASYNC_CLIENT = httpx.AsyncClient
CFG = meta.MetaConfig(app_id="app1", app_secret="shh", verify_token="vt", version="v21.0")
IMG = {"url": "https://cdn.example.test/a.jpg", "kind": "image"}
IMG2 = {"url": "https://cdn.example.test/b.jpg", "kind": "image"}


class Graph:
    """Plays the Graph API: answers from a `(method, path) → body` table and
    records every request (path without the version, query, form body)."""

    def __init__(self, routes):
        self.routes = routes
        self.requests: list[tuple[str, str, dict, dict]] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix(f"/{CFG.version}/")
        form = dict(parse_qsl(request.content.decode())) if request.content else {}
        self.requests.append((request.method, path, dict(request.url.params), form))
        answer = self.routes.get((request.method, path))
        if answer is None:
            return httpx.Response(400, json={"error": {"message": f"no route {path}", "code": 100}})
        if callable(answer):
            answer = answer(request, form)
        status, body = answer if isinstance(answer, tuple) else (200, answer)
        return httpx.Response(status, json=body)

    def client(self) -> httpx.AsyncClient:
        # The real class, captured at import: two tests patch httpx.AsyncClient.
        return _ASYNC_CLIENT(transport=httpx.MockTransport(self._handle))

    def paths(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p, _, _ in self.requests]

    def form(self, method: str, path: str) -> dict:
        for m, p, _, f in self.requests:
            if (m, p) == (method, path):
                return f
        raise AssertionError(f"no {method} {path}")


# ── config ──────────────────────────────────────────────────────────────────

def test_unconfigured_until_both_app_credentials_are_set(monkeypatch):
    monkeypatch.setattr(meta, "get_settings", lambda: SimpleNamespace(
        cappe_meta_app_id="a", cappe_meta_app_secret=None, cappe_meta_verify_token=None,
        cappe_meta_graph_version="v21.0"))
    assert meta.MetaConfig.from_settings() is None
    assert meta.configured() is False
    monkeypatch.setattr(meta, "get_settings", lambda: SimpleNamespace(
        cappe_meta_app_id="a", cappe_meta_app_secret="b", cappe_meta_verify_token="v",
        cappe_meta_graph_version=None))
    cfg = meta.MetaConfig.from_settings()
    assert cfg.app_id == "a" and cfg.version == "v21.0" and meta.configured() is True
    assert cfg.graph("/me/accounts") == "https://graph.facebook.com/v21.0/me/accounts"


def test_settings_not_loaded_reads_as_unconfigured(monkeypatch):
    def boom():
        raise RuntimeError("not loaded")

    monkeypatch.setattr(meta, "get_settings", boom)
    assert meta.MetaConfig.from_settings() is None


def test_authorize_url_asks_for_every_scope_with_our_state():
    url = meta.authorize_url(CFG, redirect_uri="https://app.example.test/cb", state="st.sig")
    assert url.startswith("https://www.facebook.com/v21.0/dialog/oauth?")
    query = dict(parse_qsl(url.split("?", 1)[1]))
    assert query["client_id"] == "app1" and query["state"] == "st.sig"
    assert query["redirect_uri"] == "https://app.example.test/cb"
    assert set(query["scope"].split(",")) == set(meta.SCOPES)
    assert "instagram_content_publish" in meta.SCOPES and "pages_messaging" in meta.SCOPES


# ── call() and error classification ─────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,retryable,code", [
    (400, {"error": {"message": "Application request limit reached", "code": 4}}, True, 4),
    (400, {"error": {"message": "Media ID is not available", "code": 9007}}, True, 9007),
    (400, {"error": {"message": "Error validating access token", "code": 190}}, False, 190),
    (500, {"error": {"message": "Unknown", "code": 100}}, True, 100),
    (503, ["not", "an", "object"], True, None),
    (403, ["nope"], False, None),
])
async def test_errors_are_classified(status, body, retryable, code):
    graph = Graph({("GET", "me"): (status, body)})
    async with graph.client() as client:
        with pytest.raises(ProviderError) as info:
            await meta.call(CFG, "GET", "me", token="t", client=client)
    assert info.value.retryable is retryable
    assert info.value.code == code


@pytest.mark.asyncio
async def test_a_200_carrying_an_error_envelope_is_still_an_error():
    graph = Graph({("GET", "me"): (200, {"error": {"message": "weird", "code": 2}})})
    async with graph.client() as client:
        with pytest.raises(ProviderError) as info:
            await meta.call(CFG, "GET", "me", client=client)
    assert info.value.retryable is True


@pytest.mark.asyncio
async def test_network_failure_is_retryable_and_token_rides_the_query():
    def broken(request):
        raise httpx.ConnectError("down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as client:
        with pytest.raises(ProviderError) as info:
            await meta.call(CFG, "GET", "me", token="t", client=client)
    assert info.value.retryable is True

    graph = Graph({("GET", "me"): {"id": "1"}})
    async with graph.client() as client:
        assert await meta.call(CFG, "GET", "me", token="tok", params={"fields": "id"}, client=client) == {"id": "1"}
    assert graph.requests[0][2] == {"fields": "id", "access_token": "tok"}


@pytest.mark.asyncio
async def test_call_opens_and_closes_its_own_client_when_none_is_given(monkeypatch):
    graph = Graph({("GET", "me"): {"id": "1"}})
    made = []

    def factory(timeout):
        client = graph.client()
        made.append(client)
        return client

    monkeypatch.setattr(meta.httpx, "AsyncClient", factory)
    assert await meta.call(CFG, "GET", "me") == {"id": "1"}
    assert made and made[0].is_closed


@pytest.mark.asyncio
async def test_non_json_success_body_reads_as_empty():
    def plain(request):
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(plain)) as client:
        assert await meta.call(CFG, "POST", "x", client=client) == {}


# ── OAuth ───────────────────────────────────────────────────────────────────

def _token(request, form):
    grant = request.url.params.get("grant_type")
    if grant == "fb_exchange_token":
        assert request.url.params["fb_exchange_token"] == "short"
        return {"access_token": "long", "expires_in": 5_184_000}
    assert request.url.params["code"] == "the-code"
    return {"access_token": "short"}


@pytest.mark.asyncio
async def test_exchange_code_yields_each_page_and_its_instagram_account():
    graph = Graph({
        ("GET", "oauth/access_token"): _token,
        ("GET", "me/accounts"): {"data": [
            {"id": "p1", "name": "Po Coffee", "access_token": "pt1", "picture": {"data": {"url": "https://x.test/p.png"}},
             "instagram_business_account": {"id": "ig1", "username": "pocoffee",
                                            "profile_picture_url": "https://x.test/i.png", "followers_count": 812}},
            {"id": "p2", "name": "No IG", "access_token": "pt2"},
            {"id": "p3", "name": "No token"},
        ]},
    })
    async with graph.client() as client:
        drafts = await meta.exchange_code(CFG, "the-code", redirect_uri="https://app.example.test/cb", client=client)
    assert [(d.platform, d.external_id, d.access_token) for d in drafts] == [
        ("facebook", "p1", "pt1"), ("instagram", "ig1", "pt1"), ("facebook", "p2", "pt2"),
    ]
    assert drafts[0].display_name == "Po Coffee" and drafts[0].avatar_url == "https://x.test/p.png"
    assert drafts[1].handle == "pocoffee" and drafts[1].followers_count == 812
    assert all(d.token_expires_at is not None for d in drafts)
    assert graph.requests[-1][2]["access_token"] == "long"


@pytest.mark.asyncio
async def test_exchange_code_without_a_token_fails_and_a_missing_expiry_is_none():
    graph = Graph({("GET", "oauth/access_token"): {}})
    async with graph.client() as client:
        with pytest.raises(ProviderError):
            await meta.exchange_code(CFG, "c", redirect_uri="https://app.example.test/cb", client=client)

    def no_expiry(request, form):
        return {"access_token": "short"}

    graph = Graph({("GET", "oauth/access_token"): no_expiry, ("GET", "me/accounts"): {"data": [
        {"id": "p1", "name": "P", "access_token": "pt"}]}})
    async with graph.client() as client:
        drafts = await meta.exchange_code(CFG, "c", redirect_uri="https://app.example.test/cb", client=client)
    assert drafts[0].token_expires_at is None


@pytest.mark.asyncio
async def test_subscribe_page_reports_success_and_swallows_failure():
    graph = Graph({("POST", "p1/subscribed_apps"): {"success": True}})
    async with graph.client() as client:
        assert await meta.subscribe_page(CFG, "p1", "pt", client=client) is True
    assert graph.form("POST", "p1/subscribed_apps") == {"subscribed_fields": "feed,messages"}
    graph = Graph({})
    async with graph.client() as client:
        assert await meta.subscribe_page(CFG, "p1", "pt", client=client) is False


# ── publishing ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instagram_single_photo_with_the_link_in_the_caption():
    graph = Graph({
        ("POST", "ig1/media"): {"id": "c1"},
        ("POST", "ig1/media_publish"): {"id": "m1"},
        ("GET", "m1"): {"permalink": "https://instagram.test/p/m1"},
    })
    async with graph.client() as client:
        result = await meta.publish(CFG, platform="instagram", external_id="ig1", token="t",
                                    caption="New roast", media=[IMG], link_url="https://shop.example.test/x",
                                    client=client)
    assert result.external_post_id == "m1" and result.permalink == "https://instagram.test/p/m1"
    assert graph.form("POST", "ig1/media") == {
        "image_url": IMG["url"], "caption": "New roast\n\nhttps://shop.example.test/x",
    }
    assert graph.form("POST", "ig1/media_publish") == {"creation_id": "c1"}


@pytest.mark.asyncio
async def test_instagram_carousel_builds_children_then_the_album():
    counter = iter(range(1, 10))

    def media(request, form):
        if form.get("media_type") == "CAROUSEL":
            assert form["children"] == "ch1,ch2"
            return {"id": "album"}
        assert form["is_carousel_item"] == "true"
        return {"id": f"ch{next(counter)}"}

    graph = Graph({
        ("POST", "ig1/media"): media,
        ("POST", "ig1/media_publish"): {"id": "m2"},
        ("GET", "m2"): (400, {"error": {"message": "no permalink", "code": 100}}),
    })
    async with graph.client() as client:
        result = await meta.publish(CFG, platform="instagram", external_id="ig1", token="t",
                                    caption="Two", media=[IMG, IMG2], client=client)
    assert result.external_post_id == "m2" and result.permalink is None
    assert graph.form("POST", "ig1/media_publish") == {"creation_id": "album"}


@pytest.mark.asyncio
@pytest.mark.parametrize("routes,media,retryable", [
    ({}, [], False),
    ({}, [{"url": "https://cdn.example.test/v.mp4", "kind": "video"}], False),
    ({("POST", "ig1/media"): {}}, [IMG], True),
    ({("POST", "ig1/media"): {"id": "c1"}, ("POST", "ig1/media_publish"): {}}, [IMG], True),
])
async def test_instagram_refusals(routes, media, retryable):
    graph = Graph(routes)
    async with graph.client() as client:
        with pytest.raises(ProviderError) as info:
            await meta.publish(CFG, platform="instagram", external_id="ig1", token="t",
                               caption="x", media=media, client=client)
    assert info.value.retryable is retryable


@pytest.mark.asyncio
async def test_facebook_single_photo_multi_photo_and_text_posts():
    graph = Graph({
        ("POST", "p1/photos"): {"id": "ph1", "post_id": "p1_9"},
        ("GET", "p1_9"): {"permalink_url": "https://facebook.test/p1_9"},
    })
    async with graph.client() as client:
        result = await meta.publish(CFG, platform="facebook", external_id="p1", token="t",
                                    caption="Hi", media=[IMG], client=client)
    assert result.external_post_id == "p1_9" and result.permalink == "https://facebook.test/p1_9"
    assert graph.form("POST", "p1/photos") == {"url": IMG["url"], "message": "Hi", "published": "true"}

    ids = iter(["f1", "f2"])
    graph = Graph({
        ("POST", "p1/photos"): lambda r, f: {"id": next(ids)},
        ("POST", "p1/feed"): {"id": "p1_10"},
        ("GET", "p1_10"): {},
    })
    async with graph.client() as client:
        result = await meta.publish(CFG, platform="facebook", external_id="p1", token="t",
                                    caption="Both", media=[IMG, IMG2], client=client)
    assert result.external_post_id == "p1_10" and result.permalink is None
    assert json.loads(graph.form("POST", "p1/feed")["attached_media"]) == [{"media_fbid": "f1"}, {"media_fbid": "f2"}]
    assert all(f.get("published") == "false" for m, p, _, f in graph.requests if p == "p1/photos")

    graph = Graph({("POST", "p1/feed"): {"id": "p1_11"}, ("GET", "p1_11"): {"permalink_url": "u"}})
    async with graph.client() as client:
        await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="Sale",
                           media=[], link_url="https://shop.example.test", client=client)
    assert graph.form("POST", "p1/feed")["link"] == "https://shop.example.test"


@pytest.mark.asyncio
async def test_facebook_needs_something_to_post_and_an_id_back():
    graph = Graph({})
    async with graph.client() as client:
        with pytest.raises(ProviderError):
            await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="", media=[], client=client)
    graph = Graph({("POST", "p1/feed"): {}})
    async with graph.client() as client:
        with pytest.raises(ProviderError) as info:
            await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="x", media=[], client=client)
    assert info.value.retryable is True
    async with graph.client() as client:
        with pytest.raises(ProviderError):
            await meta.publish(CFG, platform="tiktok", external_id="x", token="t", caption="x", media=[], client=client)


@pytest.mark.asyncio
async def test_publish_closes_a_client_it_opened(monkeypatch):
    graph = Graph({("POST", "p1/feed"): {"id": "p1_1"}, ("GET", "p1_1"): {}})
    made = []

    def factory(timeout):
        made.append(graph.client())
        return made[-1]

    monkeypatch.setattr(meta.httpx, "AsyncClient", factory)
    await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="x", media=[])
    assert made[0].is_closed


# ── replies ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replies_thread_under_comments_and_dms_go_through_the_page():
    graph = Graph({
        ("POST", "igc1/replies"): {"id": "r1"},
        ("POST", "fbc1/comments"): {"id": "r2"},
        ("POST", "me/messages"): {"message_id": "mid9"},
    })
    async with graph.client() as client:
        assert await meta.reply(CFG, platform="instagram", external_id="ig1", token="t", kind="comment",
                                target_external_id="igc1", author_external_id="u1", text=" Thanks! ",
                                client=client) == "r1"
        assert await meta.reply(CFG, platform="facebook", external_id="p1", token="t", kind="comment",
                                target_external_id="fbc1", author_external_id="u1", text="Hi", client=client) == "r2"
        assert await meta.reply(CFG, platform="instagram", external_id="ig1", token="t", kind="message",
                                target_external_id="mid1", author_external_id="u7", text="Yes", client=client) == "mid9"
    assert graph.form("POST", "igc1/replies") == {"message": "Thanks!"}
    dm = graph.form("POST", "me/messages")
    assert json.loads(dm["recipient"]) == {"id": "u7"} and json.loads(dm["message"]) == {"text": "Yes"}
    assert dm["messaging_type"] == "RESPONSE"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,author,text,routes", [
    ("comment", "u", "   ", {}),
    ("message", None, "hi", {}),
    ("story", "u", "hi", {}),
    ("comment", "u", "hi", {("POST", "c/replies"): {}}),
])
async def test_reply_refusals(kind, author, text, routes):
    graph = Graph(routes)
    async with graph.client() as client:
        with pytest.raises(ProviderError):
            await meta.reply(CFG, platform="instagram", external_id="ig1", token="t", kind=kind,
                             target_external_id="c", author_external_id=author, text=text, client=client)


# ── metrics ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_account_and_post_metrics():
    graph = Graph({
        ("GET", "ig1"): {"followers_count": 900, "media_count": 40, "id": "ig1"},
        ("GET", "p1"): {"fan_count": 300},
        ("GET", "m1/insights"): {"data": [
            {"name": "reach", "values": [{"value": 120}]},
            {"name": "likes", "total_value": {"value": 14}},
            {"name": "saved", "values": []},
            {"nope": 1},
        ]},
        ("GET", "p1_1"): {"likes": {"summary": {"total_count": 5}}, "comments": {"summary": {"total_count": 2}},
                          "shares": {"count": 1}},
    })
    async with graph.client() as client:
        assert await meta.account_metrics(CFG, platform="instagram", external_id="ig1", token="t", client=client) == {
            "followers_count": 900, "media_count": 40}
        assert await meta.account_metrics(CFG, platform="facebook", external_id="p1", token="t", client=client) == {
            "followers_count": 300}
        assert await meta.post_metrics(CFG, platform="instagram", external_post_id="m1", token="t", client=client) == {
            "reach": 120, "likes": 14}
        assert await meta.post_metrics(CFG, platform="facebook", external_post_id="p1_1", token="t", client=client) == {
            "likes": 5, "comments": 2, "shares": 1}


# ── webhooks ────────────────────────────────────────────────────────────────

def test_challenge_is_echoed_only_for_our_verify_token():
    ok = {"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "123"}
    assert meta.verify_challenge(CFG, ok) == "123"
    assert meta.verify_challenge(CFG, {**ok, "hub.verify_token": "other"}) is None
    assert meta.verify_challenge(CFG, {**ok, "hub.mode": "unsubscribe"}) is None
    no_token = meta.MetaConfig(app_id="a", app_secret="s", verify_token=None)
    assert meta.verify_challenge(no_token, ok) is None


def test_signature_is_an_hmac_of_the_raw_body():
    body = b'{"object":"page"}'
    good = "sha256=" + hmac.new(b"shh", body, hashlib.sha256).hexdigest()
    assert meta.verify_signature("shh", body, good) is True
    assert meta.verify_signature("shh", body + b" ", good) is False
    assert meta.verify_signature("shh", body, good.replace("sha256=", "sha1=")) is False
    assert meta.verify_signature("shh", body, None) is False


def test_instagram_comments_are_parsed_and_our_own_are_left_out():
    payload = {"object": "instagram", "entry": [{"id": "ig1", "time": 1_760_000_000, "changes": [
        {"field": "comments", "value": {"id": "c1", "text": "Do you ship to Canada?",
                                        "from": {"id": "u1", "username": "maya"}, "media": {"id": "m1"}}},
        {"field": "comments", "value": {"id": "c2", "text": "Thanks!", "from": {"id": "ig1"}}},
        {"field": "comments", "value": {"id": "c3", "text": "   ", "from": {"id": "u2"}}},
        {"field": "mentions", "value": {"id": "c4", "text": "hi"}},
        "not a dict",
        {"field": "comments", "value": "nope"},
    ]}]}
    events = meta.parse_webhook(payload)
    assert len(events) == 1
    e = events[0]
    assert (e.platform, e.recipient_external_id, e.kind, e.external_id) == ("instagram", "ig1", "comment", "c1")
    assert e.author_name == "maya" and e.parent_external_id == "m1" and e.received_at.year == 2025


def test_facebook_feed_comments_only_new_and_not_ours():
    payload = {"object": "page", "entry": [{"id": "p1", "changes": [
        {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "fc1", "post_id": "p1_9",
                                    "message": "Is this gluten free?", "from": {"id": "u1", "name": "Sam"},
                                    "created_time": 1_760_000_000}},
        {"field": "feed", "value": {"item": "comment", "verb": "edited", "comment_id": "fc2", "message": "x",
                                    "from": {"id": "u1"}}},
        {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "fc3", "message": "ours",
                                    "from": {"id": "p1"}}},
        {"field": "feed", "value": {"item": "reaction", "verb": "add"}},
        {"field": "feed", "value": {"item": "comment", "verb": "add", "message": "no id", "from": {"id": "u2"}}},
    ]}]}
    events = meta.parse_webhook(payload)
    assert [(e.kind, e.external_id, e.parent_external_id, e.author_name) for e in events] == [
        ("comment", "fc1", "p1_9", "Sam")]


def test_messages_are_parsed_without_echoes_or_our_side():
    payload = {"object": "page", "entry": [{"id": "p1", "messaging": [
        {"sender": {"id": "u9"}, "recipient": {"id": "p1"}, "timestamp": 1_760_000_000_000,
         "message": {"mid": "mid1", "text": "Are you open Sunday?"}},
        {"sender": {"id": "p1"}, "message": {"mid": "mid2", "text": "echo", "is_echo": True}},
        {"sender": {"id": "p1"}, "message": {"mid": "mid3", "text": "from us"}},
        {"sender": {"id": "u9"}, "message": {"mid": "mid4"}},
        {"sender": {"id": "u9"}, "message": "bad"},
        "bad",
    ]}, {"no": "id"}, "junk"]}
    events = meta.parse_webhook(payload)
    assert len(events) == 1
    e = events[0]
    assert (e.kind, e.external_id, e.author_external_id, e.parent_external_id) == ("message", "mid1", "u9", "u9")
    assert e.received_at.year == 2025


def test_other_objects_and_bad_timestamps_parse_to_nothing():
    assert meta.parse_webhook({"object": "user", "entry": [{"id": "1"}]}) == []
    assert meta._ts("2025-10-09T12:00:00+0000").year == 2025
    assert meta._ts("not a date") is None and meta._ts(None) is None


def test_inbound_event_survives_the_celery_hop():
    event = meta.parse_webhook({"object": "page", "entry": [{"id": "p1", "messaging": [
        {"sender": {"id": "u9"}, "timestamp": 1_760_000_000, "message": {"mid": "m", "text": "hi"}}]}]})[0]
    again = InboundEvent.from_dict(json.loads(json.dumps(event.as_dict())))
    assert again == event
    bare = InboundEvent.from_dict({"platform": "facebook", "recipient_external_id": "p1", "kind": "comment",
                                   "external_id": "c"})
    assert bare.text == "" and bare.received_at is None and bare.raw == {}


def test_provider_for_knows_both_networks_and_nothing_else():
    assert provider_for("instagram") is meta and provider_for("facebook") is meta
    with pytest.raises(ProviderError):
        provider_for("myspace")
