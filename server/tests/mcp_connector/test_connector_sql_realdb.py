"""Schema contract for the MCP connector's SQL, against a real database.

The unit suites drive these queries through `QueryConn`, which returns whatever
row a test fabricates — so `t.autopr_run_requested_at`, a column that never
existed on `mw_tasks`, passed 69 tests and failed every real connector call
(docs/plans/ESPRESSO_CODEX_APP_SERVER_SPIKE.md). Here each query is captured
from the production code path and PREPAREd, which makes Postgres resolve every
table and column without running anything.

Read-only: PREPARE plans a statement, it never executes it. Run manually:

    cd server
    RUN_DB_TESTS=1 DATABASE_URL=postgresql://matcha:matcha_dev@localhost:5432/matcha \
        ./venv/bin/python -m pytest tests/mcp_connector/test_connector_sql_realdb.py -v
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.core.services import mcp_local_tokens, mcp_oauth
from app.matcha.routes.matcha_work import _shared
from app.matcha.routes.mcp_connector import research
from tests._helpers.db import real_database_url, requires_real_db
from tests._helpers.routes import QueryConn

asyncpg = pytest.importorskip("asyncpg")

pytestmark = [requires_real_db(), pytest.mark.asyncio(loop_scope="module")]

USER = SimpleNamespace(id=uuid.uuid4(), role="admin")
TASK, PROJECT = uuid.uuid4(), uuid.uuid4()
CARD = {"id": TASK, "project_id": PROJECT, "category": "research", "board_column": "in_progress"}


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def conn():
    c = await asyncpg.connect(real_database_url())
    try:
        yield c
    finally:
        await c.close()


def _capture(monkeypatch, module, **tables):
    fake = QueryConn(**tables)
    monkeypatch.setattr(module, "get_connection", lambda *a, **k: fake)
    return fake


async def _prepare_all(conn, fake):
    assert fake.calls, "the code path issued no SQL"
    for _kind, sql, _args in fake.calls:
        await conn.prepare(sql)


async def test_card_lookup_prepares(conn, monkeypatch):
    fake = _capture(monkeypatch, research, fetchrow={"FROM mw_tasks t": None})
    await research._load_card(TASK)
    await _prepare_all(conn, fake)


async def test_research_card_list_prepares(conn, monkeypatch):
    fake = _capture(monkeypatch, research, fetch={"FROM mw_tasks t": []})
    await research.list_research_cards(USER)
    await _prepare_all(conn, fake)


async def test_release_queries_prepare(conn, monkeypatch):
    async def authorized(_user, _task):
        return CARD, {"title": "p"}, "owner"

    monkeypatch.setattr(research, "_authorized_card", authorized)
    monkeypatch.setattr(_shared, "_can_edit_project", lambda role: True)
    fake = _capture(
        monkeypatch, research,
        fetchrow={"event_type = 'column_change'": {
            "created_at": datetime.now(timezone.utc), "from_value": "todo",
            "to_value": "in_progress", "actor_user_id": USER.id}},
        fetchval={"mw_project_files": True},  # stop before any write
    )
    out = await research.release_unfinished_claim(
        USER, project_id=PROJECT, task_id=TASK, since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert out == {"released": False, "reason": "changed_since_claim"}
    await _prepare_all(conn, fake)


async def test_local_grant_queries_prepare(conn, monkeypatch):
    fake = _capture(monkeypatch, mcp_local_tokens, fetchval={"FROM oauth_tokens": None})
    await mcp_local_tokens.grant_issued_at(USER.id, uuid.uuid4())
    await mcp_local_tokens.revoke_token(USER.id, uuid.uuid4())
    await _prepare_all(conn, fake)
    listing = _capture(monkeypatch, mcp_oauth, fetch={"GROUP BY c.client_id": []})
    await mcp_oauth.list_user_grants(USER.id)
    await _prepare_all(conn, listing)
