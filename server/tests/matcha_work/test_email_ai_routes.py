"""/matcha-work/agent/email/* — the AI quick actions and message read.

`workspace.router` is mounted alone (no pool, no settings); the caller's
Gmail is a fake returned from a patched `_connected_gmail`, and the Lite
plan gate is patched at `entitlements_service.require_plan`, so the test
proves the route actually calls it.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.matcha.dependencies import require_admin_or_client
from app.matcha.routes.matcha_work import workspace
from app.matcha.services.billing import entitlements_service
from app.matcha.services.matcha_work import email_ai_service
from tests._helpers.routes import iter_api_routes, route_client

USER = SimpleNamespace(id=uuid4(), role="client", email="owner@example.com")

MSG = {
    "id": "18c3f0a1b2c3",
    "thread_id": "thr-9",
    "message_id_header": "<abc@mail.example.com>",
    "subject": "Friday sync",
    "from": "Alice <alice@example.com>",
    "date": "Thu, 10 Sep 2026",
    "body": "Can you confirm Friday?",
    "attachments": [],
}


@pytest.fixture
def gmail(monkeypatch):
    fake = SimpleNamespace(
        get_message=AsyncMock(return_value=dict(MSG)),
        fetch_unread=AsyncMock(return_value=[dict(MSG)]),
        create_draft=AsyncMock(return_value={"id": "draft-1"}),
        send_email=AsyncMock(return_value={"id": "sent-1"}),
    )
    monkeypatch.setattr(workspace, "_connected_gmail", AsyncMock(return_value=fake))
    return fake


@pytest.fixture
def plan(monkeypatch):
    gate = AsyncMock(return_value="lite")
    monkeypatch.setattr(entitlements_service, "require_plan", gate)
    return gate


def _client():
    return route_client(workspace.router, overrides={require_admin_or_client: USER})


def test_email_routes_exist_and_require_admin_or_client():
    wanted = {
        ("GET", "/agent/email/messages/{email_id}"),
        ("POST", "/agent/email/summarize"),
        ("POST", "/agent/email/triage"),
        ("POST", "/agent/email/draft"),
        ("POST", "/agent/email/send"),
    }
    found = {}
    for route in iter_api_routes(workspace.router):
        for method in getattr(route, "methods", set()) or set():
            if (method, route.path) in wanted:
                found[(method, route.path)] = route
    assert set(found) == wanted
    for key, route in found.items():
        calls = {d.call for d in route.dependant.dependencies}
        assert require_admin_or_client in calls, key


# --- GET message ---------------------------------------------------------------

def test_get_message_returns_thread_id_without_a_plan_gate(gmail, plan):
    with _client() as client:
        resp = client.get("/agent/email/messages/18c3f0a1b2c3")
    assert resp.status_code == 200
    assert resp.json()["thread_id"] == "thr-9"
    gmail.get_message.assert_awaited_once_with("18c3f0a1b2c3", include_html=True)
    plan.assert_not_awaited()


def test_get_message_404s_when_gmail_does(gmail):
    request = httpx.Request("GET", "https://gmail.googleapis.com/x")
    gmail.get_message.side_effect = httpx.HTTPStatusError(
        "nf", request=request, response=httpx.Response(404, request=request)
    )
    with _client() as client:
        resp = client.get("/agent/email/messages/missing")
    assert resp.status_code == 404


# --- summarize -----------------------------------------------------------------

def test_summarize_gates_on_lite_and_returns_summary(gmail, plan, monkeypatch):
    monkeypatch.setattr(email_ai_service, "summarize_email", AsyncMock(return_value="Confirm Friday."))
    with _client() as client:
        resp = client.post("/agent/email/summarize", json={"email_id": "18c3f0a1b2c3"})
    assert resp.status_code == 200
    assert resp.json() == {"email_id": "18c3f0a1b2c3", "summary": "Confirm Friday."}
    plan.assert_awaited_once_with(USER.id, entitlements_service.PLAN_LITE, "email_ai")


def test_summarize_400_without_email_id(gmail, plan):
    with _client() as client:
        assert client.post("/agent/email/summarize", json={}).status_code == 400
        assert client.post("/agent/email/summarize", json={"email_id": 7}).status_code == 400


def test_summarize_403_below_lite_before_touching_gmail(gmail, plan):
    plan.side_effect = HTTPException(status_code=403, detail={"code": "plan_required", "feature": "email_ai"})
    with _client() as client:
        resp = client.post("/agent/email/summarize", json={"email_id": "18c3f0a1b2c3"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["feature"] == "email_ai"
    gmail.get_message.assert_not_awaited()


# --- triage --------------------------------------------------------------------

def test_triage_defaults_to_the_unread_list(gmail, plan, monkeypatch):
    triage = AsyncMock(return_value=[{"email_id": "18c3f0a1b2c3", "bucket": "needs_reply", "reason": "q"}])
    monkeypatch.setattr(email_ai_service, "triage_emails", triage)
    with _client() as client:
        resp = client.post("/agent/email/triage", json={})
    assert resp.status_code == 200
    assert resp.json()["buckets"][0]["bucket"] == "needs_reply"
    gmail.fetch_unread.assert_awaited_once_with(max_results=email_ai_service.TRIAGE_MAX_EMAILS)
    plan.assert_awaited_once()


def test_triage_by_ids_dedupes_and_tolerates_a_failed_fetch(gmail, plan, monkeypatch):
    triage = AsyncMock(return_value=[])
    monkeypatch.setattr(email_ai_service, "triage_emails", triage)
    gmail.get_message.side_effect = [dict(MSG), RuntimeError("gone")]
    with _client() as client:
        resp = client.post("/agent/email/triage", json={"email_ids": ["a", "b", "a"]})
    assert resp.status_code == 200
    assert gmail.get_message.await_count == 2
    (msgs,), _ = triage.call_args
    assert [m["id"] for m in msgs] == ["18c3f0a1b2c3"]


def test_triage_400_on_malformed_ids(gmail, plan):
    with _client() as client:
        assert client.post("/agent/email/triage", json={"email_ids": "abc"}).status_code == 400
        assert client.post("/agent/email/triage", json={"email_ids": ["ok", 3]}).status_code == 400


# --- draft ---------------------------------------------------------------------

def test_draft_saves_a_threaded_gmail_draft(gmail, plan, monkeypatch):
    monkeypatch.setattr(email_ai_service, "draft_reply", AsyncMock(return_value="Friday works."))
    with _client() as client:
        resp = client.post("/agent/email/draft", json={"email_id": "18c3f0a1b2c3", "instructions": "yes"})
    assert resp.status_code == 200
    body = resp.json()
    # The response carries exactly what was saved on the draft, so the client
    # never re-derives the recipient or the Re: rule.
    assert body == {
        "draft_id": "draft-1",
        "to": "alice@example.com",
        "subject": "Re: Friday sync",
        "body": "Friday works.",
        "thread_id": "thr-9",
        "in_reply_to": "<abc@mail.example.com>",
    }
    kwargs = gmail.create_draft.await_args.kwargs
    assert kwargs["to"] == "alice@example.com"
    assert kwargs["subject"] == "Re: Friday sync"
    assert kwargs["thread_id"] == "thr-9"
    assert kwargs["in_reply_to"] == "<abc@mail.example.com>"
    plan.assert_awaited_once()


def test_draft_keeps_an_existing_re_prefix(gmail, plan, monkeypatch):
    gmail.get_message.return_value = {**MSG, "subject": "RE: Friday sync"}
    monkeypatch.setattr(email_ai_service, "draft_reply", AsyncMock(return_value="ok"))
    with _client() as client:
        client.post("/agent/email/draft", json={"email_id": "x"})
    assert gmail.create_draft.await_args.kwargs["subject"] == "RE: Friday sync"


def test_draft_502_when_the_model_returns_nothing(gmail, plan, monkeypatch):
    monkeypatch.setattr(email_ai_service, "draft_reply", AsyncMock(return_value=""))
    with _client() as client:
        resp = client.post("/agent/email/draft", json={"email_id": "18c3f0a1b2c3"})
    assert resp.status_code == 502
    gmail.create_draft.assert_not_awaited()


def test_draft_400_on_bad_input(gmail, plan):
    with _client() as client:
        assert client.post("/agent/email/draft", json={}).status_code == 400
        assert client.post("/agent/email/draft", json={"email_id": "x", "instructions": 5}).status_code == 400


@pytest.mark.parametrize("sender, expected", [
    ("Alice <alice@example.com>, harvest@evil.example.net", "alice@example.com"),
    ("alice@example.com", "alice@example.com"),
])
def test_draft_replies_to_exactly_one_parsed_address(gmail, plan, monkeypatch, sender, expected):
    gmail.get_message.return_value = {**MSG, "from": sender}
    monkeypatch.setattr(email_ai_service, "draft_reply", AsyncMock(return_value="ok"))
    with _client() as client:
        resp = client.post("/agent/email/draft", json={"email_id": "x"})
    assert resp.status_code == 200
    assert resp.json()["to"] == expected
    assert gmail.create_draft.await_args.kwargs["to"] == expected


@pytest.mark.parametrize("sender", [
    "", "undisclosed-recipients:;", "Alice <alice@example.com\r\nBcc: x@example.net>",
])
def test_draft_422s_without_a_replyable_sender_before_the_model_call(gmail, plan, monkeypatch, sender):
    draft = AsyncMock(return_value="ok")
    monkeypatch.setattr(email_ai_service, "draft_reply", draft)
    gmail.get_message.return_value = {**MSG, "from": sender}
    with _client() as client:
        resp = client.post("/agent/email/draft", json={"email_id": "x"})
    assert resp.status_code == 422
    draft.assert_not_awaited()
    gmail.create_draft.assert_not_awaited()


def test_draft_flattens_a_sender_written_subject_and_drops_a_bad_message_id(gmail, plan, monkeypatch):
    gmail.get_message.return_value = {
        **MSG,
        "subject": "Hi\r\nBcc: x@example.net",
        "message_id_header": "<a@b.example.com>\r\nBcc: y@example.net",
    }
    monkeypatch.setattr(email_ai_service, "draft_reply", AsyncMock(return_value="ok"))
    with _client() as client:
        assert client.post("/agent/email/draft", json={"email_id": "x"}).status_code == 200
    kwargs = gmail.create_draft.await_args.kwargs
    assert kwargs["subject"] == "Re: Hi Bcc: x@example.net"
    assert kwargs["in_reply_to"] is None
    assert kwargs["thread_id"] == "thr-9"  # still threads in Gmail


def test_draft_422s_when_the_gmail_service_refuses_a_header(gmail, plan, monkeypatch):
    monkeypatch.setattr(email_ai_service, "draft_reply", AsyncMock(return_value="ok"))
    gmail.create_draft.side_effect = ValueError("Email to contains newline characters")
    with _client() as client:
        resp = client.post("/agent/email/draft", json={"email_id": "x"})
    assert resp.status_code == 422


def _gmail_404():
    request = httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages/gone")
    return httpx.HTTPStatusError("not found", request=request, response=httpx.Response(404, request=request))


@pytest.mark.parametrize("path", ["/agent/email/summarize", "/agent/email/draft"])
def test_ai_actions_404_on_a_message_gmail_no_longer_has(gmail, plan, monkeypatch, path):
    model = AsyncMock(return_value="ok")
    monkeypatch.setattr(email_ai_service, "summarize_email", model)
    monkeypatch.setattr(email_ai_service, "draft_reply", model)
    gmail.get_message.side_effect = _gmail_404()
    with _client() as client:
        resp = client.post(path, json={"email_id": "gone123"})
    assert resp.status_code == 404
    model.assert_not_awaited()


def test_triage_with_an_empty_selection_triages_nothing(gmail, plan, monkeypatch):
    triage = AsyncMock(return_value=[{"email_id": "x", "bucket": "fyi", "reason": ""}])
    monkeypatch.setattr(email_ai_service, "triage_emails", triage)
    with _client() as client:
        resp = client.post("/agent/email/triage", json={"email_ids": []})
    assert resp.status_code == 200
    assert resp.json() == {"buckets": []}
    gmail.fetch_unread.assert_not_awaited()
    triage.assert_not_awaited()


# --- send ----------------------------------------------------------------------

def test_send_passes_threading_through(gmail):
    with _client() as client:
        resp = client.post("/agent/email/send", json={
            "to": "alice@example.com", "subject": "Re: Friday sync", "body": "Yes.",
            "thread_id": "thr-9", "in_reply_to": "<abc@mail.example.com>",
        })
    assert resp.status_code == 200
    assert resp.json()["message_id"] == "sent-1"
    kwargs = gmail.send_email.await_args.kwargs
    assert kwargs["thread_id"] == "thr-9"
    assert kwargs["in_reply_to"] == "<abc@mail.example.com>"
    assert kwargs["reply_to_id"] is None


def test_send_400_on_missing_fields_and_rejected_headers(gmail):
    with _client() as client:
        assert client.post("/agent/email/send", json={"to": "alice@example.com"}).status_code == 400
        gmail.send_email.side_effect = ValueError("Email subject contains newline characters")
        resp = client.post("/agent/email/send", json={"to": "a@example.com", "subject": "x", "body": "y"})
    assert resp.status_code == 400
    assert "newline" in resp.json()["detail"]


@pytest.mark.parametrize("extra", [
    {"in_reply_to": 123},
    {"thread_id": 5},
    {"thread_id": "thr/../x"},
    {"reply_to_id": ["m1"]},
    {"subject": 7},
    {"body": "   "},
])
def test_send_400s_on_mistyped_fields_instead_of_a_500(gmail, extra):
    body = {"to": "alice@example.com", "subject": "Re: Hi", "body": "Yes.", **extra}
    with _client() as client:
        resp = client.post("/agent/email/send", json=body)
    assert resp.status_code == 400
    gmail.send_email.assert_not_awaited()


def test_send_429s_when_the_per_user_ceiling_trips(gmail):
    from app.matcha.services.matcha_work.gmail_service import GmailSendRateLimited

    gmail.send_email.side_effect = GmailSendRateLimited("Send rate limit: max 5 emails per minute")
    with _client() as client:
        resp = client.post("/agent/email/send", json={"to": "alice@example.com", "subject": "Hi", "body": "b"})
    assert resp.status_code == 429
    assert "5 emails per minute" in resp.json()["detail"]


# --- helper --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connected_gmail_400s_when_not_connected(monkeypatch):
    from app.matcha.services.matcha_work import gmail_service

    class Unconnected:
        def __init__(self, user_id):
            self.user_id = user_id
            self.is_configured = False

        async def load_token(self):
            return None

    monkeypatch.setattr(gmail_service, "GmailService", Unconnected)
    with pytest.raises(HTTPException) as exc:
        await workspace._connected_gmail(USER)
    assert exc.value.status_code == 400


def test_status_carries_the_snapshot_limit(monkeypatch):
    from app.matcha.services.matcha_work import gmail_service

    class Connected:
        def __init__(self, user_id):
            self.user_id = user_id

        async def get_status(self):
            return {"connected": True, "email": "owner@example.com"}

    monkeypatch.setattr(gmail_service, "GmailService", Connected)
    with _client() as client:
        body = client.get("/agent/email/status").json()
    assert body == {
        "connected": True,
        "email": "owner@example.com",
        "snapshot_max_emails": workspace.SNAPSHOT_MAX_EMAILS,
    }


def test_reply_subject():
    assert workspace._reply_subject("Hello") == "Re: Hello"
    assert workspace._reply_subject("re: Hello") == "re: Hello"
    assert workspace._reply_subject(None) == "Re: "
    assert workspace._reply_subject("Hi\r\nBcc: x") == "Re: Hi Bcc: x"


def test_clean_message_id_header():
    assert workspace._clean_message_id_header(" <a@b.example.com> ") == "<a@b.example.com>"
    for bad in [None, 5, "", "a@b.example.com", "<a@b>\r\nBcc: x", "<a b>"]:
        assert workspace._clean_message_id_header(bad) is None


def test_send_removes_the_ai_draft_it_replaced(gmail):
    gmail.delete_draft = AsyncMock(return_value=None)
    with _client() as client:
        resp = client.post("/agent/email/send", json={
            "to": "alice@example.com", "subject": "Re: Hi", "body": "Yes.", "draft_id": "r-1",
        })
    assert resp.status_code == 200
    gmail.delete_draft.assert_awaited_once_with("r-1")


def test_send_succeeds_even_when_draft_cleanup_fails(gmail):
    gmail.delete_draft = AsyncMock(side_effect=RuntimeError("gmail down"))
    with _client() as client:
        resp = client.post("/agent/email/send", json={
            "to": "alice@example.com", "subject": "Re: Hi", "body": "Yes.", "draft_id": "r-1",
        })
    assert resp.status_code == 200
    assert resp.json()["message_id"] == "sent-1"


def test_send_400_on_non_string_draft_id(gmail):
    with _client() as client:
        resp = client.post("/agent/email/send", json={
            "to": "alice@example.com", "subject": "Re: Hi", "body": "Yes.", "draft_id": 5,
        })
    assert resp.status_code == 400
    gmail.send_email.assert_not_awaited()


# --- snapshot (email kanban cards) ---------------------------------------------

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
TASK_ID = "22222222-2222-4222-8222-222222222222"
COMPANY_ID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def board(monkeypatch):
    """Access guards and the file-row/storage sinks are fakes; the real
    `store_project_file_bytes` runs, so its upload policy is exercised."""
    from app.matcha.routes.matcha_work import _shared
    from app.matcha.services.matcha_work import project_file_service

    state = SimpleNamespace(
        access=AsyncMock(return_value=({"company_id": COMPANY_ID}, "owner")),
        owns=AsyncMock(return_value=None),
        existing=AsyncMock(return_value=[]),
        add=AsyncMock(side_effect=lambda **kw: {"id": "f-" + kw["filename"], **kw}),
        upload=AsyncMock(side_effect=lambda content, filename, **kw: f"https://cdn.example.com/{filename}"),
    )
    monkeypatch.setattr(_shared, "_verify_project_access", state.access)
    monkeypatch.setattr(_shared, "_verify_task_belongs_to_project", state.owns)
    monkeypatch.setattr(_shared, "_resolve_file_urls", lambda files: files)
    monkeypatch.setattr(project_file_service, "list_task_files", state.existing)
    monkeypatch.setattr(project_file_service, "add_project_file", state.add)
    monkeypatch.setattr(project_file_service, "get_storage", lambda: SimpleNamespace(upload_file=state.upload))
    return state


def _snap(client, **overrides):
    body = {"email_ids": ["18c3f0a1b2c3"], "project_id": PROJECT_ID, "task_id": TASK_ID, **overrides}
    return client.post("/agent/email/snapshot", json=body)


def test_snapshot_route_requires_admin_or_client():
    route = next(
        r for r in iter_api_routes(workspace.router)
        if r.path == "/agent/email/snapshot" and "POST" in r.methods
    )
    assert require_admin_or_client in {d.call for d in route.dependant.dependencies}


def test_snapshot_uploads_markdown_and_records_a_task_file(gmail, board):
    with _client() as client:
        resp = _snap(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["skipped"] == []
    assert [f["filename"] for f in body["files"]] == ["email-18c3f0a1b2c3.md"]

    content, filename = board.upload.await_args.args
    assert filename == "email-18c3f0a1b2c3.md"
    assert board.upload.await_args.kwargs == {
        "prefix": f"matcha-work/{COMPANY_ID}/{PROJECT_ID}/tasks/{TASK_ID}/files",
        "content_type": "text/markdown",
    }
    assert b'email_id: "18c3f0a1b2c3"' in content and b"Can you confirm Friday?" in content

    kwargs = board.add.await_args.kwargs
    assert str(kwargs["task_id"]) == TASK_ID and str(kwargs["project_id"]) == PROJECT_ID
    assert kwargs["uploaded_by"] == USER.id
    assert kwargs["file_size"] == len(content)
    board.access.assert_awaited_once()
    board.owns.assert_awaited_once()


def test_snapshot_skips_already_attached_unread_and_unreadable_messages(gmail, board):
    board.existing.return_value = [{"filename": "email-18c3f0a1b2c3.md"}]
    gmail.get_message.side_effect = [RuntimeError("gone")]
    with _client() as client:
        resp = _snap(client, email_ids=["18c3f0a1b2c3", "ffff0000aaaa"])
    assert resp.status_code == 200
    assert resp.json() == {
        "files": [],
        "skipped": [
            {"email_id": "18c3f0a1b2c3", "reason": "already_attached"},
            {"email_id": "ffff0000aaaa", "reason": "fetch_failed"},
        ],
    }
    # The attached one is known by its filename, so it is never fetched.
    gmail.get_message.assert_awaited_once_with("ffff0000aaaa")
    board.upload.assert_not_awaited()


def test_snapshot_dedupes_ids_within_one_request(gmail, board):
    with _client() as client:
        resp = _snap(client, email_ids=["18c3f0a1b2c3", "18c3f0a1b2c3"])
    assert resp.status_code == 200
    assert gmail.get_message.await_count == 1


def test_snapshot_keeps_two_messages_whose_ids_share_a_prefix(gmail, board):
    board.existing.return_value = [{"filename": "email-18c3f0a1aaaa.md"}]
    gmail.get_message.side_effect = lambda i: {**MSG, "id": i}
    with _client() as client:
        body = _snap(client, email_ids=["18c3f0a1aaaa", "18c3f0a1bbbb"]).json()
    assert [f["filename"] for f in body["files"]] == ["email-18c3f0a1bbbb.md"]
    assert body["skipped"] == [{"email_id": "18c3f0a1aaaa", "reason": "already_attached"}]


def test_snapshot_reads_messages_concurrently(gmail, board):
    # Each read waits until the other has started; read one at a time, the
    # first would time out and be reported as fetch_failed.
    started, state = [], {}

    async def get(email_id):
        both = state.setdefault("both", asyncio.Event())
        started.append(email_id)
        if len(started) == 2:
            both.set()
        await asyncio.wait_for(both.wait(), 1)
        return {**MSG, "id": email_id}

    gmail.get_message.side_effect = get
    with _client() as client:
        body = _snap(client, email_ids=["aaaa1111", "bbbb2222"]).json()
    assert body["skipped"] == []
    assert [f["filename"] for f in body["files"]] == ["email-aaaa1111.md", "email-bbbb2222.md"]


def test_snapshot_goes_through_the_project_file_upload_policy(gmail, board, monkeypatch):
    from app.matcha.services.matcha_work import project_file_service

    monkeypatch.setattr(project_file_service, "PROJECT_FILE_MAX_BYTES", 10)
    with _client() as client:
        assert _snap(client).status_code == 400
    board.upload.assert_not_awaited()


@pytest.mark.parametrize("overrides", [
    {"email_ids": []},
    {"email_ids": "18c3f0a1b2c3"},
    {"email_ids": ["ok", 3]},
    {"email_ids": [f"id{n}" for n in range(11)]},
    {"project_id": "not-a-uuid"},
    {"task_id": None},
])
def test_snapshot_400s_on_bad_input_before_any_access_check(gmail, board, overrides):
    with _client() as client:
        assert _snap(client, **overrides).status_code == 400
    board.access.assert_not_awaited()


def test_snapshot_404s_when_the_task_is_not_on_the_board(gmail, board):
    board.owns.side_effect = HTTPException(status_code=404, detail="Task not found")
    with _client() as client:
        resp = _snap(client)
    assert resp.status_code == 404
    gmail.get_message.assert_not_awaited()
    board.upload.assert_not_awaited()


# --- message-id hygiene ----------------------------------------------------------

@pytest.mark.parametrize("bad", ["x/attachments/y", "..", "abc?format=raw", "a b", "x" * 129])
def test_body_message_ids_that_would_splice_the_gmail_path_are_refused(gmail, plan, board, bad):
    with _client() as client:
        assert client.post("/agent/email/summarize", json={"email_id": bad}).status_code == 400
        assert client.post("/agent/email/draft", json={"email_id": bad}).status_code == 400
        assert client.post("/agent/email/triage", json={"email_ids": ["ok123", bad]}).status_code == 400
        assert _snap(client, email_ids=[bad]).status_code == 400
    gmail.get_message.assert_not_awaited()


def test_path_message_id_with_bad_characters_is_refused(gmail):
    with _client() as client:
        assert client.get("/agent/email/messages/abc%3Fformat=raw").status_code == 400
    gmail.get_message.assert_not_awaited()
