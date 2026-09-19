from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.cappe.services import push


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, rows=None, order=None):
        self.rows = rows or []
        self.order = order
        self.calls = []

    def transaction(self):
        return _Tx()

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        return args[0]

    async def execute(self, query, *args):
        self.calls.append((query, args))

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self.rows

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return self.order


def _settings(**overrides):
    values = {
        "cappe_apns_bundle_ids": "com.ahnimal.app",
        "cappe_apns_key_id": "KEY", "cappe_apns_team_id": "TEAM",
        "cappe_apns_auth_key_path": "/tmp/key.p8",
        "apns_key_id": None, "apns_team_id": None, "apns_auth_key_path": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_register_token_requires_site_and_global_bundle_allowlist(monkeypatch):
    site_id, shopper_id = uuid4(), uuid4()
    site = {"id": site_id, "app_bundle_id": "com.ahnimal.app"}
    shopper = {"id": shopper_id}
    body = SimpleNamespace(
        token="A" * 64, bundle_id="com.ahnimal.app", environment="sandbox", app_version="2.0",
    )
    conn = _Conn()
    monkeypatch.setattr(push, "get_settings", lambda: _settings())
    monkeypatch.setattr(push, "get_connection", lambda: _Ctx(conn))
    await push.register_token(site, shopper, body)
    sql, args = conn.calls[-1]
    assert "ON CONFLICT(token,bundle_id,environment)" in sql
    assert args[2] == "a" * 64

    body.bundle_id = "com.other.app"
    with pytest.raises(HTTPException) as caught:
        await push.register_token(site, shopper, body)
    assert caught.value.status_code == 422


@pytest.mark.asyncio
async def test_bad_apns_token_is_deleted_and_opt_out_sends_nothing(monkeypatch):
    shopper_id, site_id, device_id = uuid4(), uuid4(), uuid4()
    device = {
        "id": device_id, "token": "a" * 64, "bundle_id": "com.ahnimal.app",
        "environment": "sandbox", "updated_at": "stamp",
    }
    conn = _Conn(rows=[device])

    class _Sender:
        async def send_notification(self, request):
            assert request.device_token == "a" * 64
            assert request.message["type"] == "order"
            return SimpleNamespace(description="BadDeviceToken")

    monkeypatch.setattr(push, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(push, "client", lambda *_args: _Sender())
    await push.send_to_shopper(shopper_id, site_id, "Paid", "Ready", {"type": "order"})
    assert any("DELETE FROM cappe_shopper_devices" in sql for sql, _ in conn.calls)

    conn.rows = []
    conn.calls.clear()
    await push.send_to_shopper(shopper_id, site_id, "Paid", "Ready", {"type": "order"})
    assert len(conn.calls) == 1


@pytest.mark.asyncio
async def test_order_notification_and_request_queue_are_best_effort(monkeypatch):
    shopper_id, site_id, order_id = uuid4(), uuid4(), uuid4()
    conn = _Conn(order={
        "shopper_id": shopper_id, "site_id": site_id, "access_token": "b" * 32, "name": "Ahnimal",
    })
    sent = []

    async def send(*args):
        sent.append(args)

    monkeypatch.setattr(push, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(push, "send_to_shopper", send)
    await push.notify_order_event(order_id, "shipped")
    assert sent[0][4]["order_token"] == "b" * 32

    dispatched = []
    monkeypatch.setattr(push, "get_settings", lambda: _settings())
    monkeypatch.setattr(push, "_dispatch", lambda *args: dispatched.append(args))
    dependency = push.flush_pushes()
    await anext(dependency)
    push.schedule_push(order_id, "fulfilled")
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    assert dispatched == [(order_id, "fulfilled")]

    monkeypatch.setattr(push, "get_settings", lambda: _settings(cappe_apns_bundle_ids=""))
    push.schedule_push(order_id, "paid")
    assert len(dispatched) == 1


def test_apns_client_requires_credentials_and_caches_sender(monkeypatch, tmp_path):
    key = tmp_path / "key.p8"
    key.write_text("private-key", encoding="utf-8")
    monkeypatch.setattr(push, "get_settings", lambda: _settings(cappe_apns_auth_key_path=str(key)))
    created = []

    class _APNs:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr("aioapns.APNs", _APNs)
    push._clients.clear()
    first = push.client("com.ahnimal.app", "sandbox")
    second = push.client("com.ahnimal.app", "sandbox")
    assert first is second and created[0]["use_sandbox"] is True
    assert push.client("com.other.app", "sandbox") is None

