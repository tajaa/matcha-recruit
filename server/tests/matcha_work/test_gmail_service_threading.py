"""GmailService reply threading: Gmail's threadId and the RFC Message-ID
header are different identifiers. The old code used one message id for
both, which wrote an In-Reply-To no mail client could match."""

import base64
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.gmail_service import GmailService


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _svc():
    svc = GmailService(uuid4())
    svc._gmail_post = AsyncMock(return_value={"id": "gmail-1"})
    svc._check_send_rate = lambda: None
    return svc


def _decoded_raw(raw: str) -> str:
    return base64.urlsafe_b64decode(raw.encode()).decode()


@pytest.mark.asyncio
async def test_get_message_returns_thread_id_and_message_id_header():
    svc = GmailService(uuid4())
    svc._gmail_get = AsyncMock(return_value={
        "threadId": "t1",
        "payload": {
            "mimeType": "text/plain",
            "body": {"data": _b64("hello")},
            "headers": [
                {"name": "Message-ID", "value": "<abc@mail.example.com>"},
                {"name": "Subject", "value": "Hi"},
                {"name": "From", "value": "alice@example.com"},
            ],
        },
    })
    msg = await svc.get_message("m1")
    assert msg["id"] == "m1"
    assert msg["thread_id"] == "t1"
    assert msg["message_id_header"] == "<abc@mail.example.com>"
    assert msg["body"] == "hello"
    assert msg["attachments"] == []


@pytest.mark.asyncio
async def test_create_draft_threads_by_thread_id_and_rfc_message_id():
    svc = _svc()
    await svc.create_draft(
        to="alice@example.com", subject="Re: Hi", body="Yes.",
        thread_id="t1", in_reply_to="<abc@mail.example.com>",
    )
    path, payload = svc._gmail_post.await_args.args
    assert path == "/users/me/drafts"
    assert payload["message"]["threadId"] == "t1"
    raw = _decoded_raw(payload["message"]["raw"])
    assert "In-Reply-To: <abc@mail.example.com>" in raw
    assert "References: <abc@mail.example.com>" in raw
    assert raw.endswith("\r\n\r\nYes.")


@pytest.mark.asyncio
async def test_send_email_legacy_reply_to_id_threads_without_a_bogus_header():
    svc = _svc()
    await svc.send_email(to="alice@example.com", subject="Re: Hi", body="Yes.", reply_to_id="m1")
    path, payload = svc._gmail_post.await_args.args
    assert path == "/users/me/messages/send"
    assert payload["threadId"] == "m1"
    assert "In-Reply-To" not in _decoded_raw(payload["raw"])
    assert len(svc._send_timestamps) == 1


@pytest.mark.asyncio
async def test_unthreaded_send_has_no_thread_id():
    svc = _svc()
    await svc.send_email(to="alice@example.com", subject="Hi", body="Hello")
    _, payload = svc._gmail_post.await_args.args
    assert "threadId" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [
    {"subject": "Hi\r\nBcc: evil@example.com"},
    {"to": "alice@example.com\nBcc: evil@example.com"},
    {"in_reply_to": "<a@example.com>\r\nBcc: evil@example.com"},
])
async def test_header_injection_is_still_rejected(kwargs):
    svc = _svc()
    args = {"to": "alice@example.com", "subject": "Hi", "body": "b", **kwargs}
    with pytest.raises(ValueError):
        await svc.create_draft(**args)
    with pytest.raises(ValueError):
        await svc.send_email(**args)
    svc._gmail_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_draft_calls_the_drafts_endpoint():
    svc = GmailService(uuid4())
    svc._gmail_delete = AsyncMock(return_value=None)
    await svc.delete_draft("r-123_abc")
    svc._gmail_delete.assert_awaited_once_with("/users/me/drafts/r-123_abc")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "../messages/1", "a/b", "x" * 200])
async def test_delete_draft_rejects_path_like_ids(bad):
    svc = GmailService(uuid4())
    svc._gmail_delete = AsyncMock()
    with pytest.raises(ValueError):
        await svc.delete_draft(bad)
    svc._gmail_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_gmail_delete_issues_an_authorized_delete(monkeypatch):
    import httpx

    from app.matcha.services.matcha_work import gmail_service

    seen = []

    def handler(request):
        seen.append((request.method, str(request.url), request.headers.get("authorization")))
        return httpx.Response(204)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gmail_service.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler)),
    )
    svc = GmailService(uuid4())
    svc._get_headers = AsyncMock(return_value={"Authorization": "Bearer tok"})
    await svc._gmail_delete("/users/me/drafts/d1")
    assert seen == [("DELETE", f"{gmail_service.GMAIL_API_BASE}/users/me/drafts/d1", "Bearer tok")]
