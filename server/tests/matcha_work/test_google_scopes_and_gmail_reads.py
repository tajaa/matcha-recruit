from uuid import uuid4

import pytest

from app.matcha.services.matcha_work import gmail_service
from app.matcha.services.matcha_work.gmail_service import (
    GMAIL_SCOPES,
    SCOPE_CALENDAR_EVENTS,
    SCOPE_GMAIL_MODIFY,
    GmailService,
    addresses_in,
    parse_granted_scopes,
    scopes_for,
)

from tests.agent_runtime.helpers import FakeConn, connection


def test_connect_requests_the_union_for_the_named_abilities():
    assert scopes_for(None) == GMAIL_SCOPES and scopes_for([]) == GMAIL_SCOPES
    assert scopes_for(["email"]) == GMAIL_SCOPES
    assert scopes_for(["email_organize", "calendar", "calendar", "made_up"]) == [
        *GMAIL_SCOPES, SCOPE_GMAIL_MODIFY, SCOPE_CALENDAR_EVENTS]
    assert scopes_for(None) is not GMAIL_SCOPES  # a copy: the base list is never grown


def test_the_callback_stores_what_google_granted():
    granted = parse_granted_scopes(
        {"scope": f"{GMAIL_SCOPES[0]} {SCOPE_CALENDAR_EVENTS} openid"}, GMAIL_SCOPES)
    # The person unticked compose; what is stored is what they left ticked.
    assert granted == sorted([GMAIL_SCOPES[0], SCOPE_CALENDAR_EVENTS, "openid"])
    assert GMAIL_SCOPES[1] not in granted
    assert parse_granted_scopes({}, GMAIL_SCOPES) == GMAIL_SCOPES
    assert parse_granted_scopes({"scope": "  "}, GMAIL_SCOPES) == GMAIL_SCOPES
    assert parse_granted_scopes({"scope": None}, ["a"]) == ["a"]


def test_addresses_are_read_out_of_header_values():
    assert addresses_in('Dana Smith <Dana@Example.org>, "Lee, Sam" <sam@example.net>') == {
        "dana@example.org", "sam@example.net"}
    assert addresses_in("no address here") == set() and addresses_in(None) == set()


@pytest.mark.asyncio
async def test_load_and_save_work_without_a_pool(monkeypatch):
    """A Celery worker has no pool: the token is read and written on a
    connection that works in both worlds."""
    monkeypatch.setattr(gmail_service, "encrypt_secret", lambda value: f"enc:{value}")
    monkeypatch.setattr(gmail_service, "decrypt_secret", lambda value: value.removeprefix("enc:"))
    stored = {"token": "enc:t", "refresh_token": "enc:r", "client_id": "cid",
              "client_secret": "enc:s", "scopes": [SCOPE_GMAIL_MODIFY]}
    conn = FakeConn([("SELECT gmail_token", {"gmail_token": stored})])
    monkeypatch.setattr(gmail_service, "connection_or_direct", connection(conn))
    assert not hasattr(gmail_service, "get_connection")
    user = uuid4()
    gmail = GmailService(user)
    assert gmail.granted_scopes == frozenset() and gmail.missing_scopes(["x"]) == ["x"]
    await gmail.load_token()
    await gmail.load_token()  # read once
    assert len(conn.ran("SELECT gmail_token")) == 1
    assert gmail.is_configured and gmail.granted_scopes == frozenset({SCOPE_GMAIL_MODIFY})
    assert gmail.missing_scopes([SCOPE_GMAIL_MODIFY, SCOPE_CALENDAR_EVENTS]) == [SCOPE_CALENDAR_EVENTS]
    await gmail.save_token({"token": "t2", "refresh_token": "r", "client_id": "cid",
                            "client_secret": "s", "scopes": ["a"]})
    saved = conn.ran("UPDATE users SET gmail_token")[0]
    assert saved[2][1] == user and '"scopes": ["a"]' in saved[2][0] and "enc:t2" in saved[2][0]

    async def token(self):
        return "access"

    monkeypatch.setattr(GmailService, "_get_access_token", token)
    assert await gmail.access_token() == "access"


def _gmail(monkeypatch, responses):
    gmail = GmailService(uuid4())
    gmail._loaded = True
    gmail._token_data = {"refresh_token": "r", "scopes": []}
    calls = []

    async def get(path, params=None):
        calls.append(("GET", path, params))
        return responses[path]

    async def post(path, body):
        calls.append(("POST", path, body))
        return {}

    monkeypatch.setattr(gmail, "_gmail_get", get)
    monkeypatch.setattr(gmail, "_gmail_post", post)
    return gmail, calls


def _headers(**values):
    return {"headers": [{"name": k.rstrip("_").title(), "value": v} for k, v in values.items()]}


@pytest.mark.asyncio
async def test_search_returns_headers_without_bodies(monkeypatch):
    gmail, calls = _gmail(monkeypatch, {
        "/users/me/messages": {"messages": [{"id": "m1"}, {"id": "gone"}]},
        "/users/me/messages/m1": {
            "threadId": "t1", "snippet": "Tom &amp; Dana", "labelIds": ["UNREAD"],
            "payload": _headers(from_="Dana <dana@example.org>", to="me@example.com",
                                subject="Lease", date="Mon, 28 Sep 2026"),
        },
    })
    found = await gmail.search("from:dana " + "x" * 600, max_results=999)
    assert len(found) == 1  # the message that could not be read is left out, not raised
    assert found[0] == {"id": "m1", "thread_id": "t1", "subject": "Lease",
                        "from": "Dana <dana@example.org>", "to": "me@example.com", "cc": "",
                        "date": "Mon, 28 Sep 2026", "snippet": "Tom & Dana", "is_unread": True}
    listing = calls[0][2]
    assert ("maxResults", "50") in listing and len(dict(listing)["q"]) == 500
    assert "body" not in found[0]


@pytest.mark.asyncio
async def test_a_thread_lists_everyone_on_it(monkeypatch):
    gmail, calls = _gmail(monkeypatch, {"/users/me/threads/t1": {"messages": [
        {"id": "m1", "payload": {"headers": [
            {"name": "From", "value": "Dana <dana@example.org>"},
            {"name": "To", "value": "me@example.com, Sam <sam@example.net>"},
            {"name": "Message-ID", "value": "<abc@mail.example.org>"},
            {"name": "Subject", "value": "Lease"}]}},
        {"id": "m2", "payload": {"headers": [
            {"name": "From", "value": "me@example.com"}, {"name": "Cc", "value": "eve@attacker.test"}]}},
    ]}})
    thread = await gmail.get_thread("t1")
    assert thread["participants"] == ["dana@example.org", "eve@attacker.test", "me@example.com", "sam@example.net"]
    assert thread["messages"][0]["message_id_header"] == "<abc@mail.example.org>"
    assert thread["messages"][1]["subject"] == "(no subject)"
    for bad in ("", "t 1", "../x", "a" * 200):
        with pytest.raises(ValueError, match="Invalid thread id"):
            await gmail.get_thread(bad)


@pytest.mark.asyncio
async def test_labels_are_changed_in_one_bounded_call(monkeypatch):
    gmail, calls = _gmail(monkeypatch, {"/users/me/labels": {"labels": [{"id": "L1", "name": "Receipts"}]}})
    await gmail.modify_labels(["m1", "../bad", "m2"], remove=["INBOX"])
    assert calls[0] == ("POST", "/users/me/messages/batchModify",
                        {"ids": ["m1", "m2"], "addLabelIds": [], "removeLabelIds": ["INBOX"]})
    await gmail.modify_labels([f"m{i}" for i in range(80)], add=["L1"])
    assert len(calls[1][2]["ids"]) == 50 and calls[1][2]["addLabelIds"] == ["L1"]
    with pytest.raises(ValueError, match="No valid message ids"):
        await gmail.modify_labels(["../bad"])
    assert await gmail.list_labels() == [{"id": "L1", "name": "Receipts"}]


@pytest.mark.asyncio
async def test_a_message_carries_who_it_was_sent_to(monkeypatch):
    gmail, _ = _gmail(monkeypatch, {"/users/me/messages/m1": {
        "threadId": "t1", "payload": {"mimeType": "text/plain", "body": {},
                                      "headers": [{"name": "To", "value": "me@example.com"},
                                                  {"name": "Cc", "value": "sam@example.net"}]}}})
    message = await gmail.get_message("m1")
    assert message["to"] == "me@example.com" and message["cc"] == "sam@example.net"


@pytest.mark.asyncio
async def test_an_empty_success_body_is_not_a_failure(monkeypatch):
    """batchModify answers 200 with no body; the change already happened."""
    import httpx

    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, content=b"")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(gmail_service.httpx, "AsyncClient",
                        lambda *a, **kw: real_client(transport=transport))
    gmail = GmailService(uuid4())

    async def headers():
        return {"Authorization": "Bearer t"}

    monkeypatch.setattr(gmail, "_get_headers", headers)
    await gmail.modify_labels(["abc123"], remove=["INBOX"])
    assert seen == ["/gmail/v1/users/me/messages/batchModify"]
