"""Real-Postgres run of the sales send queue, rolled back at the end.

The scripted tests in `test_sales_campaigns.py` pattern-match SQL text, so they
can't catch a prepare-time type error, a wrong constraint name, or a predicate
that never matches. This drives the real service and worker functions through
one connection inside a transaction that is always rolled back: claim, send,
an unconfirmed outcome that pauses, resolving it, opt-out and the worker-start
reconcile. Gmail is a fake; no email is sent. Test data uses reserved domains.

Needs `mwsales02` applied to the target database first. Run manually against
local dev only:
    cd server
    ./scripts/migrate-dev.sh   # from the repo root, once
    RUN_DB_TESTS=1 DATABASE_URL=postgresql://matcha:matcha_dev@localhost:5432/matcha \
        ./venv/bin/python -m pytest tests/matcha_work/test_sales_realdb.py -v
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest

from tests._helpers.db import real_database_url, requires_real_db

asyncpg = pytest.importorskip("asyncpg")

pytestmark = [requires_real_db(), pytest.mark.asyncio]

FOOTER = "Reply unsubscribe and I won't email you again.\nAcme Test, 1 Main St, Springfield"


class FakeGmail:
    def __init__(self, sender):
        self.sender = sender
        self.sent = []
        self.next_error = None

    async def get_status(self):
        return {"connected": True, "email": self.sender}

    async def send_email(self, *, to, subject, body):
        if self.next_error:
            error, self.next_error = self.next_error, None
            raise error
        self.sent.append((to, subject, body))
        return {"id": f"msg-{len(self.sent)}"}


async def test_queue_state_machine_against_postgres(monkeypatch):
    from app.matcha.models.matcha_work.sales import (
        CampaignCreate,
        ProspectImport,
        ProspectPatch,
        SendBatch,
    )
    from app.matcha.services.matcha_work import sales_service as sales
    from app.workers.tasks import sales_campaign as worker

    conn = await asyncpg.connect(real_database_url())
    outer = conn.transaction()
    await outer.start()
    try:
        if not await conn.fetchval("SELECT to_regclass('mw_sales_suppressions') IS NOT NULL"):
            pytest.skip("Apply mwsales02 to this database first (./scripts/migrate-dev.sh).")

        @asynccontextmanager
        async def same_connection(*_a, **_k):
            yield conn

        monkeypatch.setattr(sales, "connection_or_direct", same_connection)
        monkeypatch.setattr(worker, "connection_or_direct", same_connection)
        # The fake Gmail stands in for delivery; reserved test addresses are the data.
        monkeypatch.setattr(sales, "_is_reserved_test_domain", lambda _e: False)
        monkeypatch.setattr(worker, "_is_reserved_test_domain", lambda _e: False)
        monkeypatch.setattr(worker, "_campaign_wait", AsyncMock(return_value=0))
        dispatched = []

        async def dispatch(_campaign_id, token, *, countdown=0):
            dispatched.append(token)

        monkeypatch.setattr(sales, "dispatch", dispatch)

        tag = uuid4().hex[:8]
        sender = f"sales-{tag}@example.test"
        user_id = await conn.fetchval(
            "INSERT INTO users(email, password_hash, role) VALUES($1,'x','individual') RETURNING id",
            sender,
        )
        company_id = await conn.fetchval(
            "INSERT INTO companies(name) VALUES($1) RETURNING id", f"Sales test {tag}"
        )
        project_id = await conn.fetchval(
            "INSERT INTO mw_projects(company_id, created_by, title, project_type) VALUES($1,$2,'Sales','collab') RETURNING id",
            company_id,
            user_id,
        )
        await conn.execute(
            "INSERT INTO mw_project_collaborators(project_id,user_id,invited_by,role) VALUES($1,$2,$2,'owner')",
            project_id,
            user_id,
        )

        campaign = await sales.create_campaign(
            project_id, user_id, CampaignCreate(request_id=uuid4(), title="Clinics", footer=FOOTER)
        )
        campaign_id = UUID(campaign["id"])
        a, b = f"ana-{tag}@clinic.test", f"bea-{tag}@clinic.test"
        added = await sales.import_prospects(
            campaign_id, user_id, ProspectImport(prospects=[{"email": a, "name": "Ana"}, {"email": b, "name": "Bea"}])
        )
        assert added == {"added": 2, "duplicates": 0, "suppressed": 0}
        snapshot = await sales.read_campaign(campaign_id, user_id)
        for p in snapshot["prospects"]:
            await sales.patch_prospect(
                campaign_id, UUID(p["id"]), user_id,
                ProspectPatch(subject=f"Hi {p['name']}", body="A short offer.", review_token=p["review_token"]),
            )
        snapshot = await sales.read_campaign(campaign_id, user_id)
        assert {p["status"] for p in snapshot["prospects"]} == {"draft"}

        gmail = FakeGmail(sender)
        await sales.approve_batch(
            campaign_id, user_id,
            SendBatch(
                request_id=uuid4(), sender=sender,
                drafts=[{"id": p["id"], "review_token": p["review_token"]} for p in snapshot["prospects"]],
            ),
            gmail,
        )
        token = dispatched[-1]

        async def deliver():
            # NOW() is fixed inside this transaction, so clear the pacing gate by hand.
            await conn.execute("UPDATE mw_sales_campaigns SET next_attempt_at = NULL WHERE id = $1", campaign_id)
            await worker.deliver_one(campaign_id, token, gmail_factory=lambda _id: gmail)

        await deliver()
        assert gmail.sent == [(a, "Hi Ana", f"A short offer.\n\n{FOOTER}")]
        status = await sales.campaign_status(campaign_id, user_id)
        assert status["counts"] == {"sent": 1, "approved": 1}

        # A 5xx is uncertain: that recipient becomes unknown and the queue pauses.
        response = httpx.Response(503, request=httpx.Request("POST", "https://gmail.test"))
        gmail.next_error = httpx.HTTPStatusError("busy", request=response.request, response=response)
        await deliver()
        status = await sales.campaign_status(campaign_id, user_id)
        assert status["counts"] == {"sent": 1, "unknown": 1}
        assert status["campaign"]["status"] == "paused"

        bea = UUID(next(p["id"] for p in status["prospects"] if p["status"] == "unknown"))
        resolved = await sales.resolve_unknown(campaign_id, bea, user_id, "not_sent")
        assert resolved["status"] == "draft"

        opted = await sales.opt_out(campaign_id, bea, user_id)
        assert opted["status"] == "opted_out"
        # The opt-out holds in every campaign this sender runs.
        other = await sales.create_campaign(
            project_id, user_id, CampaignCreate(request_id=uuid4(), title="Follow-up", footer=FOOTER)
        )
        again = await sales.import_prospects(
            UUID(other["id"]), user_id, ProspectImport(prospects=[{"email": b}, {"email": a}])
        )
        assert again == {"added": 1, "duplicates": 0, "suppressed": 1}

        # Worker start restarts a sending queue under a new token.
        await conn.execute("UPDATE mw_sales_campaigns SET status = 'sending' WHERE id = $1", campaign_id)
        await worker.reconcile()
        new_token = await conn.fetchval("SELECT dispatch_token FROM mw_sales_campaigns WHERE id = $1", campaign_id)
        assert new_token != token and dispatched[-1] == new_token

        await sales.campaign_action(campaign_id, user_id, "pause")
        assert await sales.delete_campaign(campaign_id, user_id) == {"deleted": True}
        assert not await conn.fetchval("SELECT COUNT(*) FROM mw_sales_prospects WHERE campaign_id = $1", campaign_id)
    finally:
        await outer.rollback()
        await conn.close()
