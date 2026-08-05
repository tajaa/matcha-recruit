"""`_bg_receipt_reply` re-checks the `approve_order` authz bar on the
REPLIER before committing — the same bar `_bg_inventory_reply` already
re-checks on its own replier. Before this fix, ANY channel member could
reply "confirm" to an admin-staged receipt draft and commit `kind='in'`
inventory movements, and a company that turned `inventory` off between
stage and confirm would still commit. Fake asyncpg connection, no real DB,
no Redis broadcast.

    cd server && ./venv/bin/python -m pytest tests/ems/test_receipt_reply_authz.py -q
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.werk.routes import channels_ws


def _run(coro):
    return asyncio.run(coro)


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, *, claimed_row):
        self.claimed_row = claimed_row
        self.role = None
        self.executed = []

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if q.startswith("UPDATE inventory_receipt_drafts SET confirm_message_id = NULL"):
            return self.claimed_row
        if q.startswith("INSERT INTO channel_messages"):
            return {
                "id": uuid4(), "channel_id": args[0], "content": args[1],
                "message_type": "system", "created_at": datetime.now(timezone.utc),
            }
        raise AssertionError(f"unexpected fetchrow: {q[:80]}")

    async def fetchval(self, query, *args):
        q = " ".join(query.split())
        if q.startswith("SELECT role FROM users"):
            return self.role
        raise AssertionError(f"unexpected fetchval: {q[:80]}")

    async def execute(self, query, *args):
        q = " ".join(query.split())
        self.executed.append((q, args))
        return "UPDATE 1"


def _claimed_row(**over):
    base = {
        "id": uuid4(), "company_id": uuid4(), "location_id": None,
        "vendor": "Acme Foods", "invoice_number": "INV-1", "lines": "[]",
    }
    base.update(over)
    return base


def _install(monkeypatch, conn, *, features, role):
    monkeypatch.setattr(channels_ws, "get_connection", lambda: _FakeConnCtx(conn))

    async def fake_features(_conn, _company_id):
        return features

    monkeypatch.setattr(channels_ws, "_schedule_company_features", fake_features)
    conn.role = role
    broadcasts = []

    async def fake_broadcast(_channel_id_str, payload):
        broadcasts.append(payload)

    monkeypatch.setattr(channels_ws, "broadcast_system_message", fake_broadcast)
    return broadcasts


async def _call(conn, *, content="confirm"):
    reply_id = str(uuid4())
    channel_id = str(uuid4())
    sender_id = str(uuid4())
    return await channels_ws._bg_receipt_reply(channel_id, reply_id, sender_id, content)


class TestReplierAuthzReCheck:
    def test_non_admin_reply_is_refused_and_pill_rearmed(self, monkeypatch):
        # An admin staged the draft; a plain employee replies "confirm" —
        # must be refused, not committed.
        conn = FakeConn(claimed_row=_claimed_row())
        broadcasts = _install(monkeypatch, conn, features={"inventory": True}, role="employee")

        claimed = _run(_call(conn))

        assert claimed is True  # the reply WAS aimed at this pill — claim contract holds
        assert len(broadcasts) == 1
        assert "manager" in broadcasts[0]["content"].lower() or "admin" in broadcasts[0]["content"].lower()
        # Re-armed: the SAME confirm_message_id restored, not cleared.
        rearm_calls = [c for c in conn.executed if c[0].startswith(
            "UPDATE inventory_receipt_drafts SET confirm_message_id = $1")]
        assert len(rearm_calls) == 1
        # Nothing else was written — no status flip, no commit.
        assert not any("status = 'committed'" in c[0] for c in conn.executed)
        assert not any("status = 'cancelled'" in c[0] for c in conn.executed)

    def test_inventory_disabled_between_stage_and_confirm_is_refused(self, monkeypatch):
        # An admin replies, but `inventory` was turned off in the meantime.
        conn = FakeConn(claimed_row=_claimed_row())
        broadcasts = _install(monkeypatch, conn, features={"inventory": False}, role="admin")

        claimed = _run(_call(conn))

        assert claimed is True
        assert len(broadcasts) == 1
        assert "inventory" in broadcasts[0]["content"].lower()
        assert not any("status = 'committed'" in c[0] for c in conn.executed)

    def test_admin_reply_with_inventory_on_still_commits(self, monkeypatch):
        # Regression guard: the authz re-check must not block the
        # legitimate path.
        conn = FakeConn(claimed_row=_claimed_row())
        broadcasts = _install(monkeypatch, conn, features={"inventory": True}, role="admin")

        received_calls = []

        async def fake_receive(_conn, **kwargs):
            received_calls.append(kwargs)
            return {"received": [], "unmatched": []}

        monkeypatch.setattr(
            "app.matcha.services.inventory.receipts.receive_channel_lines", fake_receive)

        claimed = _run(_call(conn, content="confirm"))

        assert claimed is True
        assert len(received_calls) == 1
        assert any("status = 'committed'" in c[0] for c in conn.executed)
        assert len(broadcasts) == 1
