"""Gmail drafts in Espresso's Email: list, open, edit, send, delete, and the
job that made one hearing about it."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.matcha.dependencies import require_admin_or_client
from app.matcha.routes.matcha_work import workspace
from app.matcha.services.matcha_work import gmail_service
from app.matcha.services.matcha_work.gmail_service import DraftNotEditable, GmailSendRateLimited, GmailService
from app.matcha.services.matcha_work.job_search import service as job_service
from tests._helpers.routes import iter_api_routes, route_client

USER = SimpleNamespace(id=uuid4(), role="individual", email="owner@example.com")


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _draft(draft_id="r-1", *, to="hiring@example.com", subject="COO role", body="Hello there",
           when="1792000000000", thread="t-1", extra_headers=()):
    return {"id": draft_id, "message": {
        "id": f"m-{draft_id}", "threadId": thread, "snippet": "Hello &amp; welcome", "internalDate": when,
        "payload": {"mimeType": "text/plain", "body": {"data": _b64(body)},
                    "headers": [{"name": "To", "value": to}, {"name": "Subject", "value": subject},
                                {"name": "Date", "value": "Wed, 14 Oct 2026"}, *extra_headers]},
    }}


def _reply_with_attachment():
    """A reply drafted in Gmail: HTML and text, a Cc, a PDF attached."""
    return {"id": "r-2", "message": {
        "id": "m-2", "threadId": "t-2", "snippet": "See attached",
        "payload": {"mimeType": "multipart/mixed", "headers": [
            {"name": "To", "value": "a@example.com"}, {"name": "Cc", "value": "b@example.com"},
            {"name": "Subject", "value": "Re: Offer"}, {"name": "In-Reply-To", "value": "<orig@mail.example.com>"}],
            "parts": [
                {"mimeType": "multipart/alternative", "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("See attached")}},
                    {"mimeType": "text/html", "body": {"data": _b64("<p>See <b>attached</b></p>")}}]},
                {"mimeType": "application/pdf", "filename": "offer.pdf", "body": {"attachmentId": "att-1"}}]},
    }}


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://gmail.googleapis.com/x")
    return httpx.HTTPStatusError("x", request=request, response=httpx.Response(status, request=request))


# ── GmailService ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_drafts_are_listed_newest_first_and_a_vanished_one_is_skipped():
    svc = GmailService(uuid4())
    svc.load_token = AsyncMock()
    reads = {"/users/me/drafts": {"drafts": [{"id": "old"}, {"id": "gone"}, {"id": "new"}]},
             "/users/me/drafts/old": _draft("old", when="1000"),
             "/users/me/drafts/new": _draft("new", when="2000")}

    async def get(path, params=None):
        if path == "/users/me/drafts/gone":
            raise _http_error(404)
        return reads[path]

    svc._gmail_get = get
    page = await svc.list_drafts()
    drafts = page["drafts"]
    assert [d["id"] for d in drafts] == ["new", "old"] and page["next_page_token"] is None
    assert drafts[0]["to"] == "hiring@example.com" and drafts[0]["snippet"] == "Hello & welcome"
    assert "body" not in drafts[0] and drafts[0]["editable"] is True

    # The next page, by Gmail's token.
    seen = []

    async def paged(path, params=None):
        seen.append(params)
        return {"drafts": [], "nextPageToken": "p3"}

    svc._gmail_get = paged
    assert (await svc.list_drafts(page_token="p2"))["next_page_token"] == "p3"
    assert seen[-1] == {"maxResults": "25", "pageToken": "p2"}
    with pytest.raises(ValueError):
        await svc.list_drafts(page_token="../x")

    async def broken(path, params=None):
        if path == "/users/me/drafts":
            return {"drafts": [{"id": "x"}]}
        raise _http_error(500)

    svc._gmail_get = broken
    with pytest.raises(httpx.HTTPStatusError):
        await svc.list_drafts()


@pytest.mark.asyncio
async def test_a_draft_is_read_updated_in_its_thread_and_sent_within_the_ceilings():
    svc = GmailService(uuid4())
    svc.load_token = AsyncMock()
    reply = _draft(extra_headers=[{"name": "Cc", "value": "cc@example.com"}, {"name": "Bcc", "value": "bcc@example.com"},
                                  {"name": "In-Reply-To", "value": "<orig@mail.example.com>"},
                                  {"name": "References", "value": "<first@mail.example.com> <orig@mail.example.com>"}])
    svc._gmail_get = AsyncMock(return_value=reply)
    got = await svc.get_draft("r-1")
    assert got["body"] == "Hello there" and got["thread_id"] == "t-1" and got["updated_ms"] == 1792000000000
    assert got["cc"] == "cc@example.com" and got["bcc"] == "bcc@example.com" and got["editable"] is True
    assert GmailService.draft_recipients({**got, "to": "a@example.com, b@example.com"}) == 4

    # Saving keeps who else it goes to and the reply headers, so it stays in its thread.
    svc._gmail_put = AsyncMock(return_value={"id": "r-1"})
    await svc.update_draft("r-1", to="a@example.com", subject="Hi", body="Body")
    path, body = svc._gmail_put.await_args.args
    assert path == "/users/me/drafts/r-1" and body["id"] == "r-1" and body["message"]["threadId"] == "t-1"
    raw = base64.urlsafe_b64decode(body["message"]["raw"]).decode()
    assert "To: a@example.com" in raw and "Cc: cc@example.com" in raw and "Bcc: bcc@example.com" in raw
    assert "In-Reply-To: <orig@mail.example.com>" in raw and "References: <first@mail.example.com> <orig@" in raw
    assert raw.endswith("Body")
    # A partial save changes only what it names.
    await svc.update_draft("r-1", subject="Only this")
    raw = base64.urlsafe_b64decode(svc._gmail_put.await_args.args[1]["message"]["raw"]).decode()
    assert "Subject: Only this" in raw and "To: hiring@example.com" in raw and raw.endswith("Hello there")
    svc._gmail_get = AsyncMock(return_value=_draft(thread=None, body=""))
    assert (await svc.get_draft("r-1"))["body"] == ""  # empty stays empty, never "(no readable body)"
    await svc.update_draft("r-1", to="")
    assert "threadId" not in svc._gmail_put.await_args.args[1]["message"]

    # A draft with an attachment or formatting is never rewritten as plain text.
    svc._gmail_get = AsyncMock(return_value=_reply_with_attachment())
    rich = await svc.get_draft("r-2")
    assert rich["editable"] is False and rich["has_attachments"] and rich["formatted"]
    assert rich["body"] == "See attached" and rich["cc"] == "b@example.com"
    svc._gmail_put.reset_mock()
    with pytest.raises(DraftNotEditable):
        await svc.update_draft("r-2", body="typo fixed")
    svc._gmail_put.assert_not_awaited()

    svc._check_send_rate = AsyncMock()
    svc._check_recipient_rate = AsyncMock()
    svc._gmail_post = AsyncMock(return_value={"id": "sent-1"})
    assert (await svc.send_draft("r-1", recipients=2))["id"] == "sent-1"
    svc._check_recipient_rate.assert_awaited_once_with(2)
    assert svc._gmail_post.await_args.args == ("/users/me/drafts/send", {"id": "r-1"})

    for bad in ("../x", "", "a/b"):
        with pytest.raises(ValueError):
            await svc.get_draft(bad)


@pytest.mark.asyncio
async def test_put_goes_to_gmail_with_the_token(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["url"] = request.method, str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"id": "r-1"}) if "full" not in seen else httpx.Response(204)

    real = httpx.AsyncClient
    monkeypatch.setattr(gmail_service.httpx, "AsyncClient", lambda: real(transport=httpx.MockTransport(handler)))
    svc = GmailService(uuid4())
    svc._get_headers = AsyncMock(return_value={"Authorization": "Bearer tok"})
    assert await svc._gmail_put("/users/me/drafts/r-1", {"id": "r-1"}) == {"id": "r-1"}
    assert seen["method"] == "PUT" and seen["url"].endswith("/users/me/drafts/r-1") and seen["auth"] == "Bearer tok"
    seen["full"] = True
    assert await svc._gmail_put("/users/me/drafts/r-1", {}) == {}


# ── routes ───────────────────────────────────────────────────────────────────

@pytest.fixture
def gmail(monkeypatch):
    fake = SimpleNamespace(
        list_drafts=AsyncMock(return_value={"drafts": [{"id": "r-1"}], "next_page_token": "p2"}),
        get_draft=AsyncMock(return_value={"id": "r-1", "to": "a@example.com, b@example.com", "subject": "Hi",
                                          "body": "Body", "thread_id": "t-1"}),
        update_draft=AsyncMock(return_value={"id": "r-1"}),
        send_draft=AsyncMock(return_value={"id": "sent-1"}),
        delete_draft=AsyncMock(return_value=None),
        draft_recipients=GmailService.draft_recipients,
    )
    monkeypatch.setattr(workspace, "_connected_gmail", AsyncMock(return_value=fake))
    return fake


@pytest.fixture
def noted(monkeypatch):
    note = AsyncMock()
    monkeypatch.setattr(job_service, "note_email_draft", note)
    return note


def _client():
    return route_client(workspace.router, overrides={require_admin_or_client: USER})


def test_draft_routes_exist_behind_the_usual_gate():
    wanted = {("GET", "/agent/email/drafts"), ("GET", "/agent/email/drafts/{draft_id}"),
              ("PUT", "/agent/email/drafts/{draft_id}"), ("POST", "/agent/email/drafts/{draft_id}/send"),
              ("DELETE", "/agent/email/drafts/{draft_id}")}
    found = {(m, r.path): r for r in iter_api_routes(workspace.router)
             for m in (getattr(r, "methods", set()) or set()) if (m, r.path) in wanted}
    assert set(found) == wanted
    assert all(require_admin_or_client in {d.call for d in r.dependant.dependencies} for r in found.values())


def test_list_and_open(gmail, noted):
    with _client() as client:
        assert client.get("/agent/email/drafts").json() == {"drafts": [{"id": "r-1"}], "next_page_token": "p2"}
        client.get("/agent/email/drafts", params={"page_token": "p2"})
        assert gmail.list_drafts.await_args.kwargs == {"page_token": "p2"}
        assert client.get("/agent/email/drafts", params={"page_token": "../x"}).status_code == 422
        assert client.get("/agent/email/drafts/r-1").json()["body"] == "Body"
        assert client.get("/agent/email/drafts/bad..id").status_code == 400
        # Gone from Gmail (sent or deleted there): the job that drafted it lets it go.
        gmail.get_draft.side_effect = _http_error(404)
        assert client.get("/agent/email/drafts/r-1").status_code == 404
        noted.assert_awaited_once_with(USER.id, "r-1", sent=False)


def test_saving_checks_its_input_and_refuses_what_it_would_lose(gmail):
    with _client() as client:
        resp = client.put("/agent/email/drafts/r-1", json={"to": " c@example.com ", "subject": "New", "body": "Text"})
        assert resp.status_code == 200
        assert gmail.update_draft.await_args.kwargs == {"to": "c@example.com", "subject": "New", "body": "Text"}
        client.put("/agent/email/drafts/r-1", json={"subject": "Only"})
        assert gmail.update_draft.await_args.kwargs == {"to": None, "subject": "Only", "body": None}
        for bad in ({"to": 5}, {"cc": "x@example.com"}, {"subject": "x" * 999}):
            assert client.put("/agent/email/drafts/r-1", json=bad).status_code == 422
        gmail.update_draft.side_effect = ValueError("Email subject contains newline characters")
        assert client.put("/agent/email/drafts/r-1", json={"subject": "a\nb"}).status_code == 400
        gmail.update_draft.side_effect = DraftNotEditable("Edit it in Gmail.")
        resp = client.put("/agent/email/drafts/r-1", json={"body": "x"})
        assert resp.status_code == 409 and resp.json()["detail"]["code"] == "draft_not_editable"
        gmail.update_draft.side_effect = _http_error(404)
        assert client.put("/agent/email/drafts/r-1", json={"body": "x"}).status_code == 404
        gmail.update_draft.side_effect = _http_error(500)
        with pytest.raises(httpx.HTTPStatusError):
            client.put("/agent/email/drafts/r-1", json={"body": "x"})


def test_sending_needs_a_recipient_respects_the_ceiling_and_tells_the_job(gmail, noted):
    with _client() as client:
        resp = client.post("/agent/email/drafts/r-1/send")
        assert resp.status_code == 200 and resp.json()["message_id"] == "sent-1"
        assert gmail.send_draft.await_args.kwargs == {"recipients": 2}
        noted.assert_awaited_once_with(USER.id, "r-1", sent=True)
        # Cc and Bcc count too: a draft can't slip a list past the ceiling.
        gmail.get_draft.return_value = {"id": "r-1", "to": "a@example.com", "cc": "b@example.com, c@example.com",
                                        "bcc": "d@example.com", "subject": "Hi", "body": "x"}
        client.post("/agent/email/drafts/r-1/send")
        assert gmail.send_draft.await_args.kwargs == {"recipients": 4}

        gmail.send_draft.side_effect = GmailSendRateLimited("Send rate limit: max 20/hour")
        assert client.post("/agent/email/drafts/r-1/send").status_code == 429

        gmail.get_draft.return_value = {"id": "r-1", "to": "", "subject": "Hi", "body": "x"}
        resp = client.post("/agent/email/drafts/r-1/send")
        assert resp.status_code == 422 and "who it goes to" in resp.json()["detail"]


def test_deleting_tells_the_job_even_when_gmail_already_lost_it(gmail, noted):
    with _client() as client:
        assert client.delete("/agent/email/drafts/r-1").json() == {"deleted": True}
        noted.assert_awaited_with(USER.id, "r-1", sent=False)
        gmail.delete_draft.side_effect = _http_error(404)
        assert client.delete("/agent/email/drafts/r-1").status_code == 200
        gmail.delete_draft.side_effect = _http_error(500)
        with pytest.raises(httpx.HTTPStatusError):
            client.delete("/agent/email/drafts/r-1")
