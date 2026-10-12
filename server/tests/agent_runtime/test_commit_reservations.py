"""Shared commit allowances: fake DB connections and providers, never live I/O."""
import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import assistant, runner
from app.matcha.services.matcha_work.agent_runtime.abilities import domains
from app.matcha.services.matcha_work.agent_runtime.context import FrozenAction
from app.matcha.services.matcha_work.agent_runtime.policy import Grounding, PolicyContext
from app.matcha.services.matcha_work.agent_runtime.registry import Target
from app.matcha.services.matcha_work.project_agent import store

from .helpers import FakeClient, FakeConn, call, connection, context, contract, response


class Ledger:
    """Independent connections sharing transaction locks and committed rows."""

    def __init__(self):
        self.rows = []
        self.owners = {}
        self.locks = {}
        self.queries = []

    @asynccontextmanager
    async def connect(self):
        ledger = self

        class Conn:
            def __init__(self):
                self.lock = None
                self.pending = []
                self.in_transaction = False

            @asynccontextmanager
            async def transaction(self, *, isolation):
                assert isolation == "read_committed"
                self.in_transaction = True
                try:
                    yield
                except BaseException:
                    self.pending.clear()
                    raise
                else:
                    ledger.rows.extend(self.pending)
                finally:
                    self.in_transaction = False
                    if self.lock is not None:
                        self.lock.release()

            async def execute(self, query, *args):
                ledger.queries.append(query)
                if "pg_advisory_xact_lock" in query:
                    assert self.in_transaction and "hashtextextended" in query
                    self.lock = ledger.locks.setdefault(args[0], asyncio.Lock())
                    await self.lock.acquire()
                elif "UPDATE mw_project_agent_steps" in query:
                    for row in ledger.rows:
                        if row["id"] == args[0] and row["status"] == "claimed":
                            row["status"] = args[1]
                return "OK"

            async def fetchval(self, query, *args):
                ledger.queries.append(query)
                if "SUM(" in query:
                    assert "r.requested_by = $1" in query
                    assert "s.status IN ('ok', 'claimed', 'unknown')" in query
                    assert "s.kind IN ('commit', 'browse')" in query
                    assert "s.created_at > NOW() - make_interval(secs => $3)" in query
                    return sum(row["weight"] for row in ledger.rows
                               if row["user"] == args[0] and row["tool"] == args[1]
                               and row["status"] in {"ok", "claimed", "unknown"}
                               and row.get("age", 0) < args[2])
                assert "INSERT INTO mw_project_agent_steps" in query
                assert self.in_transaction
                row = {"id": uuid4(), "user": ledger.owners[args[0]], "tool": args[2],
                       "weight": json.loads(args[6])["weight"], "status": "claimed"}
                self.pending.append(row)
                await asyncio.sleep(0)  # contend on a separate connection before commit
                return row["id"]

        yield Conn()


@pytest.mark.asyncio
async def test_concurrent_approved_registrations_share_the_daily_ceiling(monkeypatch):
    from app.core.services import porkbun

    ledger = Ledger()
    user = uuid4()
    ledger.rows.append({"id": uuid4(), "user": user, "tool": "register_domain",
                        "weight": 1, "status": "unknown"})
    monkeypatch.setattr(store, "connection_or_direct", ledger.connect)
    registrations = FakeConn([("INSERT INTO mw_agent_domain_registrations",
                               {"id": uuid4(), "status": "registering", "inserted": True})])
    monkeypatch.setattr(domains, "connection_or_direct", connection(registrations))
    provider = AsyncMock()
    monkeypatch.setattr(porkbun, "get_porkbun", lambda: provider)
    barrier = asyncio.Barrier(3)
    abilities = [domains.build()]
    snapshots = []

    async def run_one(number):
        run_id = uuid4()
        ledger.owners[run_id] = user
        async with ledger.connect() as conn:
            counts = await assistant.load_counts(conn, user, abilities)
        snapshots.append(counts)
        await barrier.wait()  # every run starts with the same stale snapshot
        args = {"domain": f"espresso-{number}.test", "cost_cents": 1200}
        ctx = context(
            run_id=run_id, user_id=user, channel_id=uuid4(), commit_mode="live",
            resume_prompt_id=uuid4(),
            policy=PolicyContext(surface="assistant", private_conversation=True,
                                 grounding=Grounding(), counts=counts),
            resume=FrozenAction(tool="register_domain", args=args,
                                targets=(Target("domain", "porkbun.com"),),
                                preview=domains._preview(args, None)),
        )
        return await runner.run_agent(
            ctx, client=FakeClient([response(call("finish", {"answer": "Finished"}))]),
            abilities=abilities, contract=contract(), instructions="sys", first_input=[],
        )

    outcomes = await asyncio.gather(*(run_one(i) for i in range(3)))
    assert snapshots == [{("register_domain", 86400): 1}] * 3
    assert provider.register.await_count == 1
    assert len(ledger.rows) == 2
    assert sorted(out.receipts[0]["status"] for out in outcomes) == ["done", "failed", "failed"]
    assert sum("pg_advisory_xact_lock" in query for query in ledger.queries) == 3


@pytest.mark.asyncio
async def test_weighted_claims_check_every_window_and_isolate_owners_and_tools(monkeypatch):
    ledger = Ledger()
    owner, other = uuid4(), uuid4()
    run = uuid4()
    ledger.owners[run] = owner
    ledger.rows = [
        {"id": uuid4(), "user": owner, "tool": "archive_email", "weight": 3, "status": "claimed"},
        {"id": uuid4(), "user": owner, "tool": "archive_email", "weight": 4, "status": "ok", "age": 4000},
        {"id": uuid4(), "user": owner, "tool": "archive_email", "weight": 100, "status": "error"},
        {"id": uuid4(), "user": other, "tool": "archive_email", "weight": 100, "status": "ok"},
        {"id": uuid4(), "user": owner, "tool": "label_email", "weight": 100, "status": "ok"},
    ]
    monkeypatch.setattr(store, "connection_or_direct", ledger.connect)
    with pytest.raises(store.CommitCeilingExceeded, match="limit of 8"):
        await store.claim_step(run, 1, "archive_email", "commit", "Archive", {}, {"weight": 2},
                               ceiling_user_id=owner, ceilings=((5, 3600), (8, 86400)))
    assert len(ledger.rows) == 5
    step = await store.claim_step(run, 1, "archive_email", "commit", "Archive", {}, {"weight": 2},
                                  ceiling_user_id=owner, ceilings=((5, 3600), (9, 86400)))
    assert ledger.rows[-1]["id"] == step
    with pytest.raises(store.CommitCeilingExceeded, match="limit of 5"):
        await store.claim_step(run, 2, "archive_email", "commit", "Archive", {}, {"weight": 1},
                               ceiling_user_id=owner, ceilings=((5, 3600), (9, 86400)))


@pytest.mark.asyncio
async def test_ceiling_without_an_owner_fails_closed(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(store, "connection_or_direct", connection(conn))
    with pytest.raises(ValueError, match="requires its owner"):
        await store.claim_step(uuid4(), 1, "archive_email", "commit", "Archive", {}, {}, ceilings=((1, 3600),))
    assert not conn.ran("INSERT")
