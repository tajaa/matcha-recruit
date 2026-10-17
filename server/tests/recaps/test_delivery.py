from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.matcha.services.matcha_work.recaps import delivery, settings, transport

from .test_lifecycle import COMPANY, RECAP, USER, Conn, row, wire


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


@pytest.mark.parametrize("status,state", [(200,"sent"),(202,"sent"),(400,"failed"),(401,"failed"),(429,"retry_wait"),(408,"unknown"),(500,"unknown")])
def test_provider_acceptance_and_uncertainty(status, state):
    result = transport.response_result(response(status, json={"id": "provider-id"}), "gmail")
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
    service = SimpleNamespace(is_gmail_configured=lambda: True, _get_access_token=AsyncMock(return_value="token"),
        from_email="espresso@example.com", api_key="unit-key", base_url="https://mailer.test", mailersend_from_email="espresso@example.com")
    monkeypatch.setattr(transport,"get_email_service",lambda: service)
    client = Client([first,response(202,headers={"x-message-id":"mailer-id"})])
    monkeypatch.setattr(transport.httpx,"AsyncClient",lambda **_: client)
    # Mock the domain guard for this pure unit test; no network client exists.
    monkeypatch.setattr(transport,"_is_reserved_test_domain",lambda _: False)
    result = await transport.send("owner@example.com", {"subject":"Task done","html":"<p>Done</p>","text":"Done"})
    assert result.state == expected and len(client.calls) == count


@pytest.mark.asyncio
async def test_reserved_domains_never_reach_transport(monkeypatch):
    service = AsyncMock(); monkeypatch.setattr(transport,"get_email_service",service)
    assert (await transport.send("owner@example.com",{})).state == "suppressed"
    service.assert_not_called()


def test_message_contains_stable_auth_link_not_signed_poster(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL","https://espresso.example.com")
    message = delivery.compose(row(state="rendering"),[{"text":"<private> result"}],recap_email=True)
    assert f"/espresso/recaps/{RECAP}" in message["text"]
    assert "preparing" in message["text"] and "&lt;private&gt;" in message["html"]
    assert "<private>" not in message["html"]
    assert "recaps/" not in delivery.compose(row(state="failed"),[],recap_email=True)["text"]
    assert "recaps/" not in delivery.compose(row(state="ready"),[],recap_email=False)["text"]


@pytest.mark.asyncio
async def test_legacy_sender_suppressed_only_after_durable_ownership(monkeypatch):
    monkeypatch.setattr(settings,"enabled",lambda:True)
    conn=Conn(); conn.fetchrow.return_value={"id":uuid4(),"completion_mail_owner":"recap"}
    assert await delivery.own_mail(conn,kind="research",source_id=uuid4(),message={"text":"result"})
    assert "mail_payload" in conn.execute.await_args.args[0]
    conn.fetchrow.return_value=None
    assert not await delivery.own_mail(conn,kind="jobs",source_id=uuid4(),message={})


@pytest.mark.asyncio
@pytest.mark.parametrize("transport_state,attempts,expected",[("sent",1,"sent"),("unknown",1,"unknown"),("retry_wait",1,"retry_wait"),("retry_wait",3,"failed")])
async def test_delivery_claim_and_outcome_are_fenced(monkeypatch,transport_state,attempts,expected):
    conn=Conn(); wire(monkeypatch,delivery,conn)
    delivery_id=uuid4()
    conn.fetchrow.side_effect=[{"recap_id":RECAP,"attempts":attempts},row(state="ready",email="owner@example.com",email_enabled=True)]
    conn.fetch.return_value=[]
    sender=AsyncMock(return_value=transport.SendResult(transport_state,"gmail","receipt"))
    monkeypatch.setattr(transport,"send",sender)
    monkeypatch.setattr(settings,"enabled",lambda:True)
    await delivery.deliver(delivery_id)
    sender.assert_awaited_once()
    sql,*args=conn.execute.await_args.args
    assert "claim_token=$2" in sql and args[2]==expected
    assert sender.await_args.args[0]=="owner@example.com"


@pytest.mark.asyncio
async def test_revoked_owner_or_email_preference_suppresses_pending_notification(monkeypatch):
    conn=Conn();wire(monkeypatch,delivery,conn)
    conn.fetchrow.side_effect=[{"recap_id":RECAP,"attempts":1},None]
    conn.fetch.return_value=[]
    sender=AsyncMock();monkeypatch.setattr(transport,"send",sender)
    await delivery.deliver(uuid4())
    sender.assert_not_awaited()
    assert "suppressed" in conn.execute.await_args.args[0]
