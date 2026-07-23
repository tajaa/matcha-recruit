"""Image asset library (migration zzzzcappe23, services/cappe_assets.py).

Pure store behavior against a fake asyncpg connection — no live database is
touched (repo rule: DB-mutating tests are never auto-run).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_assets.py -q
"""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services import cappe_assets  # noqa: E402

_NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


class FakeConn:
    """Same minimal asyncpg stand-in as test_merlin_conversations.py."""

    def __init__(self, *, fetch=None, execute_result="OK"):
        self._fetch = fetch or {}
        self._execute_result = execute_result
        self.statements: list[str] = []
        self.args: list[tuple] = []

    @staticmethod
    def _match(table, sql):
        for needle, value in table.items():
            if needle in sql:
                return value
        return None

    async def fetch(self, sql, *args):
        self.statements.append(sql)
        self.args.append(args)
        return self._match(self._fetch, sql) or []

    async def execute(self, sql, *args):
        self.statements.append(sql)
        self.args.append(args)
        return self._execute_result


@pytest.mark.asyncio
async def test_record_inserts_all_fields():
    conn = FakeConn()
    site_id, account_id = uuid4(), uuid4()
    await cappe_assets.record(
        conn, account_id=account_id, site_id=site_id, kind="generated",
        url="https://cdn.example.test/g.png", prompt="a lake", aspect="16:9", image_size="2K",
    )
    assert "INSERT INTO cappe_assets" in conn.statements[0]
    assert conn.args[0] == (account_id, site_id, "generated", "https://cdn.example.test/g.png", "a lake", "16:9", "2K")


@pytest.mark.asyncio
async def test_list_assets_filters_by_kind_when_given():
    conn = FakeConn(fetch={
        "FROM cappe_assets": [
            {"id": uuid4(), "kind": "upload", "url": "https://cdn.example.test/u.png",
             "prompt": None, "aspect": None, "image_size": None, "created_at": _NOW},
        ],
    })
    site_id = uuid4()
    rows = await cappe_assets.list_assets(conn, site_id, kind="upload")
    assert len(rows) == 1
    assert rows[0]["kind"] == "upload"
    # kind is bound as a parameter, not string-interpolated
    assert "kind = $2" in conn.statements[0]
    assert conn.args[0] == (site_id, "upload", 200)


@pytest.mark.asyncio
async def test_list_assets_without_kind_omits_the_filter():
    conn = FakeConn()
    site_id = uuid4()
    await cappe_assets.list_assets(conn, site_id)
    assert "kind = " not in conn.statements[0]
    assert conn.args[0] == (site_id, 200)


@pytest.mark.asyncio
async def test_delete_asset_is_site_scoped_and_reports_whether_a_row_existed():
    conn = FakeConn(execute_result="DELETE 1")
    site_id, asset_id = uuid4(), uuid4()
    deleted = await cappe_assets.delete_asset(conn, site_id, asset_id)
    assert deleted is True
    assert conn.args[0] == (asset_id, site_id)

    conn2 = FakeConn(execute_result="DELETE 0")
    assert await cappe_assets.delete_asset(conn2, uuid4(), uuid4()) is False
