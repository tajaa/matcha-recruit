"""Image asset library (migrations zzzzcappe23 + cappemag01, services/cappe_assets.py).

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
async def test_a_generated_image_is_always_recorded_as_ai():
    conn = FakeConn()
    site_id, account_id = uuid4(), uuid4()
    await cappe_assets.record(
        conn, account_id=account_id, site_id=site_id, kind="generated",
        url="https://cdn.example.test/g.png", prompt="a lake", aspect="16:9", image_size="2K",
    )
    assert "INSERT INTO cappe_assets" in conn.statements[0]
    assert conn.args[0] == (
        account_id, site_id, "generated", "https://cdn.example.test/g.png", "a lake", "16:9", "2K",
        "generated", True, "ai", "AI illustration", None, None, None, None,
    )


@pytest.mark.asyncio
async def test_an_editor_upload_is_recorded_with_its_size_and_no_credit():
    conn = FakeConn()
    await cappe_assets.record(
        conn, account_id=uuid4(), site_id=uuid4(), kind="upload", url="https://cdn.example.test/u.jpg",
        width=640, height=480, size_bytes=1234, mime="image/jpeg",
    )
    assert conn.args[0][7:] == ("upload", False, None, None, 640, 480, 1234, "image/jpeg")


@pytest.mark.asyncio
async def test_list_assets_filters_by_kind_when_given():
    conn = FakeConn(fetch={
        "FROM cappe_assets": [
            {"id": uuid4(), "kind": "upload", "url": "https://cdn.example.test/u.png",
             "prompt": None, "aspect": None, "image_size": None, "created_at": _NOW,
             "variants": '{"webp": [{"w": 480, "url": "https://cdn.example.test/w.webp"}]}'},
        ],
    })
    site_id = uuid4()
    rows = await cappe_assets.list_assets(conn, site_id, kind="upload")
    assert len(rows) == 1
    assert rows[0]["kind"] == "upload"
    assert rows[0]["variants"]["webp"][0]["w"] == 480  # jsonb text is parsed
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
async def test_list_assets_searches_the_words_around_a_picture():
    conn = FakeConn()
    site_id = uuid4()
    await cappe_assets.list_assets(conn, site_id, kind="stock", q=" harbour ")
    sql = conn.statements[0]
    assert "alt ILIKE $3" in sql and "creator ILIKE $3" in sql and "prompt ILIKE $3" in sql
    assert "credit_line ILIKE $3" in sql  # an upload's credit is all it has of its photographer
    assert conn.args[0] == (site_id, "stock", "%harbour%", 200)


@pytest.mark.asyncio
async def test_list_assets_searches_for_percent_and_underscore_literally():
    conn = FakeConn()
    site_id = uuid4()
    await cappe_assets.list_assets(conn, site_id, q="100%_off\\")
    assert conn.args[0][1] == "%100\\%\\_off\\\\%"


def test_row_tolerates_missing_or_broken_variants():
    assert cappe_assets.row({"variants": None})["variants"] == {}
    assert cappe_assets.row({"variants": "{not json"})["variants"] == {}
    assert cappe_assets.row({"variants": {"share": {"w": 1}}})["variants"] == {"share": {"w": 1}}


class RowConn(FakeConn):
    def __init__(self, returned=None):
        super().__init__()
        self.returned = returned

    async def fetchrow(self, sql, *args):
        self.statements.append(sql)
        self.args.append(args)
        return self.returned


@pytest.mark.asyncio
async def test_a_library_upload_records_the_attestation_and_its_credit():
    conn = RowConn({"id": uuid4(), "variants": "{}"})
    await cappe_assets.insert_upload(
        conn, account_id=uuid4(), site_id=uuid4(), url="https://cdn.example.test/a.jpg", width=10,
        height=20, size_bytes=99, mime="image/jpeg", variants={"webp": []}, alt="A harbour",
        caption=None, credit_line="Photo: Ana Ruiz", ai_made=False,
    )
    sql, args = conn.statements[0], conn.args[0]
    assert "rights_attested_at" in sql and "NOW()" in sql
    assert args[3:6] == ("own", False, "Photo: Ana Ruiz")
    assert args[-1] == '{"webp": []}'


@pytest.mark.asyncio
async def test_an_ai_made_upload_is_credited_as_ai_whatever_was_typed():
    conn = RowConn({"id": uuid4(), "variants": {}})
    await cappe_assets.insert_upload(
        conn, account_id=uuid4(), site_id=uuid4(), url="https://cdn.example.test/a.jpg", width=10,
        height=20, size_bytes=99, mime="image/jpeg", variants={}, alt=None, caption=None,
        credit_line="Photo: me", ai_made=True,
    )
    assert conn.args[0][3:6] == ("ai", True, "AI illustration")


def test_alt_text_and_captions_are_always_the_owners():
    stock = {"kind": "stock", "ai_generated": False}
    assert cappe_assets.editable_fields(stock, {"alt": " Boats ", "caption": ""}) == {"alt": "Boats", "caption": None}


@pytest.mark.parametrize("asset", [
    {"kind": "stock", "ai_generated": False},
    {"kind": "generated", "ai_generated": True},
    {"kind": "upload", "ai_generated": True},
])
def test_the_credit_of_an_archive_or_ai_picture_is_not_the_owners(asset):
    with pytest.raises(cappe_assets.NotEditable, match="credit_line"):
        cappe_assets.editable_fields(asset, {"credit_line": "Photo: me"})


def test_the_owner_writes_the_credit_of_their_own_upload():
    upload = {"kind": "upload", "ai_generated": False}
    assert cappe_assets.editable_fields(upload, {"credit_line": "Photo: Ana", "creator": "Ana"}) == {
        "credit_line": "Photo: Ana", "creator": "Ana",
    }


@pytest.mark.asyncio
async def test_update_asset_writes_only_known_columns():
    with pytest.raises(cappe_assets.NotEditable):
        await cappe_assets.update_asset(RowConn(), uuid4(), uuid4(), {"url; DROP TABLE x": "y"})

    conn = RowConn({"id": uuid4(), "variants": "{}", "alt": "Boats"})
    site_id, asset_id = uuid4(), uuid4()
    updated = await cappe_assets.update_asset(conn, site_id, asset_id, {"alt": "Boats"})
    assert updated["alt"] == "Boats"
    assert "SET alt = $3, updated_at = NOW() WHERE id = $1 AND site_id = $2" in conn.statements[0]
    assert conn.args[0] == (asset_id, site_id, "Boats")


@pytest.mark.asyncio
async def test_update_asset_with_nothing_to_change_just_reads_it():
    conn = RowConn(None)
    assert await cappe_assets.update_asset(conn, uuid4(), uuid4(), {}) is None
    assert conn.statements[0].startswith("SELECT")


@pytest.mark.asyncio
async def test_delete_asset_is_site_scoped_and_reports_whether_a_row_existed():
    conn = FakeConn(execute_result="DELETE 1")
    site_id, asset_id = uuid4(), uuid4()
    deleted = await cappe_assets.delete_asset(conn, site_id, asset_id)
    assert deleted is True
    assert conn.args[0] == (asset_id, site_id)

    conn2 = FakeConn(execute_result="DELETE 0")
    assert await cappe_assets.delete_asset(conn2, uuid4(), uuid4()) is False
