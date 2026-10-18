import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.core.services.email import client as email_client
from app.matcha.services.matcha_work.agent_tasks import mail
from app.matcha.services.matcha_work.recaps import delivery, settings, transport

from .test_lifecycle import RECAP, Conn, row, wire


class Client:
    def __init__(self, responses):
        self.responses = list(responses); self.calls = []
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return None
    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, Exception): raise value
        return value


def response(status, **kwargs):
    return httpx.Response(status, **kwargs)


def service(**over):
    made = email_client.EmailService.__new__(email_client.EmailService)
    made.from_email = made.mailersend_from_email = "espresso@example.com"
    made.from_name, made.api_key, made.base_url = "Matcha", "unit-key", "https://mailer.test"
    made.is_gmail_configured = lambda: True
    made._get_access_token = AsyncMock(return_value="token")
    for key, value in over.items():
        setattr(made, key, value)
    return made


def legacy(title="Apartments in SF", status="done"):
    return mail.compose({"title": title, "status": status, "progress": {}}, summary={"headline": "Two fit"},
                        top=[{"id": "a", "title": "Sunny 1bd", "url": "https://listing.example.com/a", "fields": {}}], columns=[])


@pytest.mark.parametrize("status,state", [(200,"sent"),(202,"sent"),(400,"failed"),(401,"failed"),(429,"retry_wait"),(408,"unknown"),(500,"unknown")])
def test_provider_acceptance_and_uncertainty(status, state):
    result = email_client.send_result(response(status, json={"id": "provider-id"}), "gmail")
    assert result.state == state
    if state == "sent": assert result.message_id == "provider-id"


@pytest.mark.asyncio
@pytest.mark.parametrize("first,expected,count", [
    (response(200,json={"id":"accepted"}),"sent",1),
    (response(403),"sent",2),
    (response(500),"unknown",1),
    (httpx.ReadTimeout("lost response"),"unknown",1),
    (httpx.ConnectError("not connected"),"sent",2),
])
async def test_fallback_only_after_definite_non_delivery(monkeypatch, first, expected, count):
    client = Client([first,response(202,headers={"x-message-id":"mailer-id"})])
    monkeypatch.setattr(email_client.httpx,"AsyncClient",lambda **_: client)
    # Mock the domain guard for this pure unit test; no network client exists.
    monkeypatch.setattr(email_client,"_is_reserved_test_domain",lambda _: False)
    result = await service().send_with_result("owner@example.com", None, "Task done", "<p>Done</p>", "Done", from_name="Espresso")
    assert result.state == expected and len(client.calls) == count
    # One sender identity for both providers, built where the boolean sends build it.
    assert client.calls[-1][1]["json"].get("from", {"name": "Espresso"})["name"] == "Espresso"


@pytest.mark.asyncio
async def test_no_mailersend_keeps_gmails_definite_answer(monkeypatch):
    client = Client([response(400)])
    monkeypatch.setattr(email_client.httpx,"AsyncClient",lambda **_: client)
    monkeypatch.setattr(email_client,"_is_reserved_test_domain",lambda _: False)
    assert (await service(api_key="").send_with_result("owner@example.com", None, "s", "<p>h</p>", "t")).state == "failed"
    assert (await service(api_key="", is_gmail_configured=lambda: False)
            .send_with_result("owner@example.com", None, "s", "<p>h</p>", "t")).state == "retry_wait"


@pytest.mark.asyncio
async def test_reserved_domains_never_reach_a_provider(monkeypatch):
    client = Client([]); monkeypatch.setattr(email_client.httpx,"AsyncClient",lambda **_: client)
    made = service()
    assert (await made.send_with_result("owner@example.com", None, "s", "<p>h</p>", "t")).state == "suppressed"
    made._get_access_token.assert_not_awaited(); assert client.calls == []


@pytest.mark.asyncio
async def test_transport_is_the_shared_structured_send(monkeypatch):
    made = SimpleNamespace(send_with_result=AsyncMock(return_value=transport.SendResult("sent","gmail","id")))
    monkeypatch.setattr(transport,"get_email_service",lambda: made)
    await transport.send("owner@example.com", {"subject":"S","html":"<p>H</p>","text":"T"})
    assert made.send_with_result.await_args.kwargs == {"to_email":"owner@example.com","to_name":None,"subject":"S",
        "html_content":"<p>H</p>","text_content":"T","from_name":"Espresso"}


def test_message_contains_stable_auth_link_not_signed_poster(monkeypatch):
    monkeypatch.setattr(delivery,"get_settings",lambda: SimpleNamespace(app_base_url="https://espresso.example.com/"))
    message = delivery.compose(row(state="rendering"),[{"text":"<private> result"}],recap_email=True)
    assert f"https://espresso.example.com/espresso/recaps/{RECAP}" in message["text"]
    assert "preparing" in message["text"] and "&lt;private&gt;" in message["html"]
    assert "<private>" not in message["html"]
    assert "recaps/" not in delivery.compose(row(state="failed"),[],recap_email=True)["text"]
    assert "recaps/" not in delivery.compose(row(state="ready"),[],recap_email=False)["text"]


def test_a_handed_over_task_email_keeps_its_own_subject_and_formatting(monkeypatch):
    monkeypatch.setattr(delivery,"get_settings",lambda: SimpleNamespace(app_base_url="https://espresso.example.com"))
    original = legacy()
    message = delivery.compose(row(state="ready", title="Assistant task recap"), [original], recap_email=True)
    assert message["subject"] == original["subject"] == "Done: Apartments in SF"
    # The composer's own markup (clickable listing, styled picks) survives, in one document.
    assert 'href="https://listing.example.com/a"' in message["html"]
    assert message["html"].count("<html") == 1 and message["html"].count("<body") == 1
    assert "Watch recap: https://espresso.example.com/espresso/recaps/" in message["text"]
    assert original["text"] in message["text"]
    two = delivery.compose(row(state="ready"), [original, legacy("Jobs", "failed")], recap_email=False)
    assert two["subject"] == "Done: Apartments in SF and 1 more" and "recaps/" not in two["text"]


def test_stored_payload_fits_its_column_without_losing_the_words():
    small = legacy()
    assert json.loads(delivery._payload(small)) == small
    huge = {"subject": "Done: x", "html": "<p>" + "x" * 70_000 + "</p>", "text": "words " * 100}
    kept = json.loads(delivery._payload(huge))
    assert "html" not in kept and kept["text"] == huge["text"]
    assert len(delivery._payload({"subject": "s", "text": "y" * 200_000}).encode()) <= delivery.PAYLOAD_BYTES


@pytest.mark.asyncio
async def test_legacy_sender_suppressed_only_after_durable_ownership(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    conn=Conn(); conn.fetchrow.return_value={"id":uuid4(),"recap_id":RECAP,"completion_mail_owner":"recap"}
    conn.fetchval.return_value=True
    assert await delivery.own_mail(conn,kind="research",source_id=uuid4(),message={"text":"result"})
    sql = conn.fetchval.await_args.args[0]
    # One statement takes the payload only while the recap's sender will still send it.
    assert "mail_payload" in sql and "state IN ('pending','retry_wait')" in sql
    assert "NOT IN ('deleted','expired')" in sql and "deadline_at=COALESCE" in sql and "NOT x.enabled" in sql
    conn.fetchrow.return_value=None
    assert not await delivery.own_mail(conn,kind="jobs",source_id=uuid4(),message={})


@pytest.mark.asyncio
async def test_a_tombstoned_or_sent_recap_never_takes_the_task_email(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    conn=Conn(); conn.fetchrow.return_value={"id":uuid4(),"recap_id":RECAP,"completion_mail_owner":"recap"}
    conn.fetchval.return_value=None  # no pending delivery left to hand it to
    assert not await delivery.own_mail(conn,kind="research",source_id=uuid4(),message=legacy())
    conn.fetchrow.return_value={"id":uuid4(),"recap_id":RECAP,"completion_mail_owner":"legacy"}
    conn.fetchval.reset_mock()
    assert not await delivery.own_mail(conn,kind="research",source_id=uuid4(),message=legacy())
    conn.fetchval.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport_state,attempts,expected",[("sent",1,"sent"),("unknown",1,"unknown"),("retry_wait",1,"retry_wait"),("retry_wait",3,"failed")])
async def test_delivery_claim_and_outcome_are_fenced(monkeypatch,transport_state,attempts,expected):
    conn=Conn(); wire(monkeypatch,delivery,conn)
    delivery_id=uuid4()
    conn.fetchrow.side_effect=[{"recap_id":RECAP,"attempts":attempts},row(state="ready",email="owner@example.com",email_enabled=True)]
    conn.fetch.return_value=[]
    conn.fetchval.return_value=True
    sender=AsyncMock(return_value=transport.SendResult(transport_state,"gmail","receipt"))
    monkeypatch.setattr(transport,"send",sender)
    monkeypatch.setattr(settings,"enabled",lambda:True)
    monkeypatch.setattr(delivery,"get_settings",lambda: SimpleNamespace(app_base_url="https://espresso.example.com"))
    await delivery.deliver(delivery_id)
    sender.assert_awaited_once()
    sql,*args=conn.fetchval.await_args.args
    assert "claim_token=$2" in sql and args[2]==expected
    assert sender.await_args.args[0]=="owner@example.com"
    cleared = any("mail_payload=NULL" in call.args[0] for call in conn.execute.await_args_list)
    assert cleared == (expected != "retry_wait")


@pytest.mark.asyncio
async def test_revoked_owner_or_email_preference_suppresses_pending_notification(monkeypatch):
    conn=Conn();wire(monkeypatch,delivery,conn)
    conn.fetchrow.side_effect=[{"recap_id":RECAP,"attempts":1},None]
    conn.fetch.return_value=[]
    sender=AsyncMock();monkeypatch.setattr(transport,"send",sender)
    await delivery.deliver(uuid4())
    sender.assert_not_awaited()
    assert any("suppressed" in call.args[0] for call in conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_deleting_the_video_still_sends_the_task_email_it_was_handed(monkeypatch):
    conn=Conn();wire(monkeypatch,delivery,conn)
    payload = legacy()
    conn.fetchrow.side_effect=[{"recap_id":RECAP,"attempts":1},row(state="deleted",email="owner@example.com",email_enabled=True)]
    conn.fetch.return_value=[{"kind":"research","mail_payload":json.dumps(payload)}]
    conn.fetchval.return_value=True
    sender=AsyncMock(return_value=transport.SendResult("sent","gmail","id"));monkeypatch.setattr(transport,"send",sender)
    monkeypatch.setattr(settings,"enabled",lambda:True)
    await delivery.deliver(uuid4())
    sent = sender.await_args.args[1]
    assert sent["subject"] == payload["subject"] and "recaps/" not in sent["text"]
    assert "r.state<>'expired'" in conn.fetchrow.await_args_list[1].args[0]
    # Deleted with nothing handed over: no standalone recap email.
    conn.fetchrow.side_effect=[{"recap_id":RECAP,"attempts":1},row(state="deleted",email="owner@example.com",email_enabled=True)]
    conn.fetch.return_value=[]; sender.reset_mock()
    await delivery.deliver(uuid4())
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_structured_send_edges_never_risk_a_second_copy(monkeypatch):
    monkeypatch.setattr(email_client,"_is_reserved_test_domain",lambda _: False)
    # Token refresh failed: no Gmail request was made, so MailerSend is safe.
    client = Client([response(202)]); monkeypatch.setattr(email_client.httpx,"AsyncClient",lambda **_: client)
    made = service(_get_access_token=AsyncMock(side_effect=RuntimeError("expired grant")))
    assert (await made.send_with_result("owner@example.com", None, "s", "<p>h</p>", "t")).state == "sent"
    assert client.calls[0][0] == "https://mailer.test/email"
    # A message that cannot be encoded is a definite failure, sent nowhere.
    made = service(); made._mime_raw = lambda *_, **__: (_ for _ in ()).throw(ValueError("bad header"))
    client = Client([]); monkeypatch.setattr(email_client.httpx,"AsyncClient",lambda **_: client)
    assert (await made.send_with_result("owner@example.com", None, "s", "<p>h</p>", "t")).state == "failed"
    assert client.calls == []
    # MailerSend never connected: retry later; lost mid-request: unknown.
    for error, state in ((httpx.ConnectTimeout("no route"), "retry_wait"), (httpx.ReadTimeout("lost"), "unknown")):
        client = Client([error]); monkeypatch.setattr(email_client.httpx,"AsyncClient",lambda **_: client)
        assert (await service(is_gmail_configured=lambda: False)
                .send_with_result("owner@example.com", None, "s", "<p>h</p>", "t")).state == state


def test_shared_builders_keep_the_boolean_sends_wire_format():
    import base64, email
    made = service()
    attachment = {"filename": "receipt.pdf", "content": base64.b64encode(b"%PDF").decode()}
    raw = made._mime_raw("owner@example.com", "Owner", "Subject", "<p>h</p>", "t",
                         attachments=[attachment], extra_headers={"List-Unsubscribe": "<mailto:u@example.com>"},
                         from_name="Espresso")
    parsed = email.message_from_bytes(base64.urlsafe_b64decode(raw))
    assert parsed["From"] == "Espresso <espresso@example.com>" and parsed["To"] == "Owner <owner@example.com>"
    assert parsed["List-Unsubscribe"] and parsed.get_content_type() == "multipart/mixed"
    assert [part.get_filename() for part in parsed.walk() if part.get_filename()] == ["receipt.pdf"]
    payload = made._mailersend_payload("owner@example.com", None, "Subject", "<p>h</p>", None, attachments=[attachment])
    assert payload["to"] == [{"email": "owner@example.com", "name": "owner@example.com"}]
    assert payload["from"]["name"] == "Matcha" and payload["text"] == ""
    assert payload["attachments"][0] == {**attachment, "disposition": "attachment"}
