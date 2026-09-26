"""One APNs key can send to distinct app topics and environments."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.routes.identity import push as push_routes
from app.core.services import apns_service
from app.werk.routes import inbox as inbox_routes


def _settings(**overrides):
    values = {
        "apns_bundle_id": "com.matchawork.app",
        "apns_bundle_id_schedule": "com.heymatcha.schedule",
        "apns_use_sandbox": True,
        "apns_key_id": "KEY",
        "apns_team_id": "TEAM",
        "apns_auth_key_path": "/tmp/unused-apns-key.p8",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("bundle,kind,expected", [
    (None, "mention", True),
    (None, "inbox_message", True),
    (None, "schedule_published", False),
    ("com.matchawork.app", "schedule_offer_received", False),
    ("com.matchawork.app", "channel_message", True),
    ("com.heymatcha.schedule", "schedule_published", True),
    ("com.heymatcha.schedule", "inbox_message", True),
    ("com.heymatcha.schedule", "mention", False),
    ("com.unknown.app", "inbox_message", False),
])
def test_kind_routing_matrix(monkeypatch, bundle, kind, expected):
    monkeypatch.setattr(apns_service, "get_settings", _settings)
    assert apns_service.kind_allowed(bundle, kind) is expected


@pytest.mark.asyncio
async def test_apns_clients_are_cached_by_topic_and_environment(monkeypatch):
    import aioapns

    created = []

    def make_client(**kwargs):
        client = SimpleNamespace(**kwargs)
        created.append(client)
        return client

    monkeypatch.setattr(apns_service, "get_settings", _settings)
    monkeypatch.setattr(apns_service.Path, "read_text", lambda _path: "test-key")
    monkeypatch.setattr(aioapns, "APNs", make_client)
    apns_service._clients.clear()
    try:
        first = await apns_service._get_client("com.heymatcha.schedule", "sandbox")
        assert first is await apns_service._get_client("com.heymatcha.schedule", "sandbox")
        second = await apns_service._get_client("com.heymatcha.schedule", "production")
        third = await apns_service._get_client("com.matchawork.app", "sandbox")
        assert len(created) == 3
        assert first.use_sandbox is True
        assert second.use_sandbox is False
        assert third.topic == "com.matchawork.app"
    finally:
        apns_service._clients.clear()


class _Connection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []
        self.deleted = []

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        return self.rows

    async def execute(self, query, *args):
        self.queries.append((query, args))
        if "DELETE FROM device_tokens" in query:
            self.deleted.extend(args[0])


@pytest.fixture
def device_env(monkeypatch):
    conn = _Connection()
    senders = {}

    class Sender:
        def __init__(self, bundle, environment):
            self.bundle = bundle
            self.environment = environment
            self.sent = []

        async def send_notification(self, request):
            self.sent.append(request)
            return SimpleNamespace(is_successful=True, description="Success")

    @asynccontextmanager
    async def get_connection():
        yield conn

    async def get_client(bundle, environment):
        return senders.setdefault((bundle, environment), Sender(bundle, environment))

    monkeypatch.setattr(apns_service, "get_settings", _settings)
    monkeypatch.setattr(apns_service, "connection_or_direct", get_connection)
    monkeypatch.setattr(apns_service, "_get_client", get_client)
    return conn, senders


@pytest.mark.asyncio
async def test_send_routes_legacy_and_schedule_topics_with_per_device_environment(device_env):
    conn, senders = device_env
    user_id = uuid4()
    conn.rows = [
        {"user_id": user_id, "token": "a" * 64, "bundle_id": None, "environment": None},
        {"user_id": user_id, "token": "b" * 64, "bundle_id": "com.heymatcha.schedule",
         "environment": "production"},
        {"user_id": user_id, "token": "c" * 64, "bundle_id": "com.unknown.app",
         "environment": "sandbox"},
    ]
    await apns_service.send_to_user(user_id, "Open shift", kind="schedule_published")
    assert set(senders) == {("com.heymatcha.schedule", "production")}
    assert len(senders[("com.heymatcha.schedule", "production")].sent) == 1

    senders.clear()
    await apns_service.send_to_user(user_id, "Message", kind="inbox_message", suppress_werk=True)
    assert set(senders) == {("com.heymatcha.schedule", "production")}

    senders.clear()
    await apns_service.send_to_user(user_id, "Message", kind="inbox_message")
    assert set(senders) == {
        ("com.matchawork.app", "sandbox"), ("com.heymatcha.schedule", "production"),
    }


@pytest.mark.asyncio
async def test_permanent_topic_mismatch_prunes_token(device_env, monkeypatch):
    conn, _senders = device_env
    user_id = uuid4()
    conn.rows = [{"user_id": user_id, "token": "a" * 64, "bundle_id": None,
                  "environment": "sandbox"}]

    class Rejected:
        async def send_notification(self, _request):
            return SimpleNamespace(is_successful=False, description="DeviceTokenNotForTopic")

    async def get_client(_bundle, _environment):
        return Rejected()

    monkeypatch.setattr(apns_service, "_get_client", get_client)
    await apns_service.send_to_user(user_id, "Alert", kind="mention")
    assert conn.deleted == ["a" * 64]


@pytest.mark.asyncio
async def test_worker_can_send_with_its_own_connection(device_env, monkeypatch):
    conn, senders = device_env
    user_id = uuid4()
    conn.rows = [{"user_id": user_id, "token": "b" * 64,
                  "bundle_id": "com.heymatcha.schedule", "environment": "sandbox"}]

    def no_pool():
        raise AssertionError("worker delivery must reuse its raw connection")

    monkeypatch.setattr(apns_service, "get_connection", no_pool)
    await apns_service.send_to_user(user_id, "Schedule published", kind="schedule_published", conn=conn)
    assert len(senders[("com.heymatcha.schedule", "sandbox")].sent) == 1


@pytest.mark.asyncio
async def test_register_rejects_unknown_bundle_before_database(monkeypatch):
    monkeypatch.setattr(apns_service, "get_settings", _settings)
    with pytest.raises(HTTPException) as error:
        await push_routes.register_device(
            push_routes.DeviceTokenBody(token="a" * 64, bundle_id="com.unknown.app"),
            current_user=SimpleNamespace(id=uuid4()),
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_register_persists_environment(monkeypatch):
    conn = _Connection()

    @asynccontextmanager
    async def get_connection():
        yield conn

    monkeypatch.setattr(apns_service, "get_settings", _settings)
    monkeypatch.setattr(push_routes, "get_connection", get_connection)
    user_id = uuid4()
    await push_routes.register_device(
        push_routes.DeviceTokenBody(
            token="b" * 64, bundle_id="com.heymatcha.schedule", environment="production"
        ),
        current_user=SimpleNamespace(id=user_id),
    )
    query, args = conn.queries[0]
    assert "environment" in query
    assert args == (user_id, "b" * 64, "ios", "com.heymatcha.schedule", "production", None)


@pytest.mark.asyncio
async def test_register_binds_token_to_mobile_device_session(monkeypatch):
    conn = _Connection()

    @asynccontextmanager
    async def get_connection():
        yield conn

    monkeypatch.setattr(apns_service, "get_settings", _settings)
    monkeypatch.setattr(push_routes, "get_connection", get_connection)
    user_id, sid = uuid4(), uuid4()
    await push_routes.register_device(
        push_routes.DeviceTokenBody(
            token="c" * 64, bundle_id="com.heymatcha.schedule", environment="sandbox"
        ),
        current_user=SimpleNamespace(id=user_id, device_session_id=sid),
    )
    query, args = conn.queries[0]
    assert "device_session_id = EXCLUDED.device_session_id" in query
    assert args[-1] == sid


@pytest.mark.asyncio
async def test_send_skips_tokens_whose_device_session_is_dead(device_env):
    """The SELECT itself must exclude revoked sessions and inactive employees;
    legacy (unbound) Werk rows are untouched."""
    conn, _senders = device_env
    await apns_service.send_to_user(uuid4(), "Open shift", kind="schedule_published")
    query, args = conn.queries[0]
    assert "LEFT JOIN auth_device_sessions" in query
    assert "dt.device_session_id IS NULL" in query
    assert "ds.revoked_at IS NULL" in query
    assert "employment_status" in query
    assert args[1] == ["terminated", "offboarded"]


def test_apns_client_is_rebuilt_for_a_new_event_loop(monkeypatch):
    """Each Celery task runs asyncio.run(); a client cached from the previous
    task's (now closed) loop must not be reused."""
    import asyncio

    import aioapns

    created = []

    def make_client(**kwargs):
        client = SimpleNamespace(**kwargs)
        created.append(client)
        return client

    monkeypatch.setattr(apns_service, "get_settings", _settings)
    monkeypatch.setattr(apns_service.Path, "read_text", lambda _path: "test-key")
    monkeypatch.setattr(aioapns, "APNs", make_client)
    apns_service._clients.clear()
    try:
        async def twice():
            a = await apns_service._get_client("com.heymatcha.schedule", "sandbox")
            b = await apns_service._get_client("com.heymatcha.schedule", "sandbox")
            return a, b

        first_a, first_b = asyncio.run(twice())
        second_a, _ = asyncio.run(twice())
        assert first_a is first_b
        assert second_a is not first_a
        assert len(created) == 2
        assert len(apns_service._clients) == 1
    finally:
        apns_service._clients.clear()


@pytest.mark.asyncio
async def test_inbox_push_does_not_depend_on_email_configuration(monkeypatch):
    from app import config
    from app.core.services import email as email_services

    recipient_id = uuid4()
    sent = []

    class Conn:
        async def fetch(self, *_args):
            return [{"user_id": recipient_id, "email": "recipient@example.com",
                     "name": "Recipient"}]

        async def fetchrow(self, *_args):
            raise AssertionError("Email cooldown should not run without email")

    @asynccontextmanager
    async def get_connection():
        yield Conn()

    async def is_online(_user_id):
        return True

    async def send_to_user(*args, **kwargs):
        sent.append((args, kwargs))

    monkeypatch.setattr(inbox_routes, "get_connection", get_connection)
    monkeypatch.setattr(email_services, "get_email_service", lambda: SimpleNamespace(is_configured=lambda: False))
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(app_base_url="https://example.com"))
    monkeypatch.setattr(apns_service, "is_user_online", is_online)
    monkeypatch.setattr(apns_service, "send_to_user", send_to_user)

    await inbox_routes._send_message_notification(uuid4(), uuid4(), "Sender", "Hello")
    assert len(sent) == 1
    assert sent[0][1]["kind"] == "inbox_message"
    assert sent[0][1]["suppress_werk"] is True
