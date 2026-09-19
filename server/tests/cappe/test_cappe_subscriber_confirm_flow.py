"""Double opt-in, executed — the staging side (clients add/import, the daily
confirmation budget, the worker hand-off) and the public confirm page/consent.

`test_cappe_subscriber_confirm.py` pins the SQL shapes; this module runs the
handlers through a scripted connection.

Test addresses use reserved domains (repo rule). Where a test needs one to be
treated as deliverable, the reserved-domain drop is switched off explicitly
instead of reaching for a real domain.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_subscriber_confirm_flow.py -q
"""
import asyncio
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.models.cappe import CappeClientCreate  # noqa: E402
from app.cappe.routes import clients as clients_mod  # noqa: E402
from app.cappe.routes.public import newsletter as public_mod  # noqa: E402

SITE_ID = "44444444-4444-4444-8444-444444444444"
TOKEN = "55555555-5555-4555-8555-555555555555"
ACCOUNT = SimpleNamespace(id="a-1", email="owner@example.com")


class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class ScriptedConn:
    def __init__(self, rows=(), vals=(), fetches=()):
        self.rows, self.vals, self.fetches = list(rows), list(vals), list(fetches)
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return self.rows.pop(0)

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        return self.vals.pop(0)

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.fetches.pop(0)

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return "INSERT 0 1"

    def transaction(self):
        return Tx()


class ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def staged(monkeypatch):
    """Owned site, deliverable addresses, and a recorded worker hand-off."""
    async def _owned(conn, site_id, account_id):
        return {"id": site_id}

    dispatched = []
    monkeypatch.setattr(clients_mod, "get_owned_site", _owned)
    monkeypatch.setattr(clients_mod, "_is_reserved_test_domain", lambda _e: False)
    monkeypatch.setattr(clients_mod, "_dispatch_confirmations", dispatched.append)
    return dispatched


def _use(monkeypatch, mod, conn):
    monkeypatch.setattr(mod, "get_connection", lambda: ConnCtx(conn))
    return conn


# ── the daily confirmation budget ────────────────────────────────────────────

@pytest.mark.parametrize("used,left", [(0, 500), (120, 380), (500, 0), (900, 0), (None, 500)])
def test_confirmation_budget_counts_down_and_floors_at_zero(used, left):
    conn = ScriptedConn(vals=[used])
    assert asyncio.run(clients_mod._confirmation_budget(conn, "a-1")) == left
    sql = conn.calls[0][1]
    assert "INTERVAL '24 hours'" in sql and "s.account_id = $1" in sql


# ── the worker hand-off ──────────────────────────────────────────────────────

def test_dispatch_queues_the_worker_task(monkeypatch):
    from app.workers.tasks import cappe_subscribe_confirm as task_mod

    queued = []
    monkeypatch.setattr(
        task_mod, "run_cappe_subscribe_confirm", SimpleNamespace(delay=queued.append)
    )
    clients_mod._dispatch_confirmations(SITE_ID)
    assert queued == [SITE_ID]


def test_dispatch_failure_is_logged_not_raised(monkeypatch, caplog):
    """A lost dispatch costs nothing — the rows wait unclaimed — so a broker
    outage must not fail the request that staged them."""
    def _boom(_site):
        raise RuntimeError("broker down")

    from app.workers.tasks import cappe_subscribe_confirm as task_mod

    monkeypatch.setattr(task_mod, "run_cappe_subscribe_confirm", SimpleNamespace(delay=_boom))
    clients_mod._dispatch_confirmations(SITE_ID)
    assert any("could not queue" in r.getMessage() for r in caplog.records)
    assert "app.workers.tasks.cappe_subscribe_confirm" in sys.modules


# ── single add ───────────────────────────────────────────────────────────────

def test_add_client_to_newsletter_stages_and_dispatches(monkeypatch, staged):
    conn = _use(monkeypatch, clients_mod, ScriptedConn(vals=[0, TOKEN], rows=[None]))
    out = asyncio.run(clients_mod.add_client(
        SITE_ID,
        CappeClientCreate(email="Pat@Example.com", name="Pat", add_to_newsletter=True),
        account=ACCOUNT,
    ))
    assert out.email == "pat@example.com"
    assert staged == [SITE_ID]
    insert = [c for c in conn.calls if "cappe_subscribers" in c[1] and "INSERT" in c[1]]
    assert insert and "'pending_confirmation'" in insert[0][1]


def test_add_client_over_budget_is_not_staged(monkeypatch, staged):
    conn = _use(monkeypatch, clients_mod, ScriptedConn(vals=[500], rows=[None]))
    asyncio.run(clients_mod.add_client(
        SITE_ID,
        CappeClientCreate(email="pat@example.com", add_to_newsletter=True),
        account=ACCOUNT,
    ))
    assert staged == []
    assert not any("INSERT INTO cappe_subscribers" in c[1] for c in conn.calls)


# ── CSV import ───────────────────────────────────────────────────────────────

def _import(monkeypatch, csv_text, conn, *, add_to_newsletter=True):
    async def _read(file, cap, msg):
        return csv_text.encode()

    monkeypatch.setattr(clients_mod, "read_capped", _read)
    _use(monkeypatch, clients_mod, conn)
    return asyncio.run(clients_mod.import_clients(
        SITE_ID, file=None, add_to_newsletter=add_to_newsletter, account=ACCOUNT,
    ))


def test_import_caps_confirmations_at_the_remaining_budget(monkeypatch, staged):
    conn = ScriptedConn(
        vals=[498],                                        # 2 confirmations left today
        fetches=[
            [],                                            # no locations
            [{"inserted": True}] * 3,                      # 3 clients written
            [{"id": "sub-1"}, {"id": "sub-2"}],            # 2 subscribers staged
        ],
    )
    csv_text = "email,name\na@example.com,A\nb@example.com,B\nc@example.com,C\n"
    result = _import(monkeypatch, csv_text, conn)

    assert result.created == 3
    assert result.newsletter_capped == 1
    assert result.newsletter_added == 2
    staged_emails = conn.calls[-1][2][1]
    assert staged_emails == ["a@example.com", "b@example.com"]
    assert staged == [SITE_ID]


def test_import_with_nothing_left_to_stage_does_not_dispatch(monkeypatch, staged):
    conn = ScriptedConn(vals=[500], fetches=[[], [{"inserted": False}]])
    result = _import(monkeypatch, "email\na@example.com\n", conn)
    assert result.updated == 1 and result.newsletter_capped == 1
    assert result.newsletter_added == 0
    assert staged == []


# ── public confirm: GET renders, POST consents ───────────────────────────────

@pytest.fixture
def public(monkeypatch):
    async def _no_limit(request):
        return None

    monkeypatch.setattr(public_mod, "_read_rate_limit", _no_limit)
    return SimpleNamespace(url=SimpleNamespace(path=f"/api/cappe/public/subscribe/confirm/{TOKEN}"))


def _body(resp):
    return resp.body.decode()


def test_get_renders_a_button_and_changes_nothing(monkeypatch, public):
    conn = _use(monkeypatch, public_mod, ScriptedConn(vals=["pending_confirmation"]))
    resp = asyncio.run(public_mod.public_confirm_subscription_page(TOKEN, public))
    assert resp.status_code == 200
    assert "<form method=\"post\"" in _body(resp) and "Confirm subscription" in _body(resp)
    assert [c[0] for c in conn.calls] == ["fetchval"]
    assert conn.calls[0][1].lstrip().startswith("SELECT")


def test_get_for_an_already_confirmed_address_says_so(monkeypatch, public):
    _use(monkeypatch, public_mod, ScriptedConn(vals=["subscribed"]))
    resp = asyncio.run(public_mod.public_confirm_subscription_page(TOKEN, public))
    assert "already confirmed" in _body(resp) and "<form" not in _body(resp)


def test_get_unknown_token_is_404(monkeypatch, public):
    _use(monkeypatch, public_mod, ScriptedConn(vals=[None]))
    resp = asyncio.run(public_mod.public_confirm_subscription_page(TOKEN, public))
    assert resp.status_code == 404


def test_malformed_token_is_404_before_any_query(monkeypatch, public):
    from fastapi import HTTPException

    conn = _use(monkeypatch, public_mod, ScriptedConn())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(public_mod.public_confirm_subscription("not-a-uuid", public))
    assert exc.value.status_code == 404
    assert conn.calls == []


def test_post_subscribes_a_pending_address(monkeypatch, public):
    conn = _use(monkeypatch, public_mod, ScriptedConn(vals=["sub-1"]))
    resp = asyncio.run(public_mod.public_confirm_subscription(TOKEN, public))
    assert resp.status_code == 200 and "unsubscribe link" in _body(resp)
    sql = conn.calls[0][1]
    assert "status = 'subscribed'" in sql and "status = 'pending_confirmation'" in sql


def test_post_twice_is_still_a_success(monkeypatch, public):
    _use(monkeypatch, public_mod, ScriptedConn(vals=[None, 1]))
    resp = asyncio.run(public_mod.public_confirm_subscription(TOKEN, public))
    assert resp.status_code == 200


def test_post_unknown_token_is_404(monkeypatch, public):
    _use(monkeypatch, public_mod, ScriptedConn(vals=[None, None]))
    resp = asyncio.run(public_mod.public_confirm_subscription(TOKEN, public))
    assert resp.status_code == 404
