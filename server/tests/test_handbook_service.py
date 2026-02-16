import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from app.core.models.handbook import HandbookUpdateRequest
from app.core.services import handbook_service as handbook_service_module
from app.core.services.handbook_service import (
    HandbookService,
    _normalize_custom_sections,
    _translate_handbook_db_error,
)


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakeConnection:
    def __init__(self, current_row: dict, scope_count: int = 1):
        self.current_row = current_row
        self.scope_count = scope_count
        self.executed: list[tuple[str, tuple]] = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        if "FROM handbooks" in query:
            return self.current_row
        return None

    async def fetchval(self, query, *args):
        if "COUNT(*) FROM handbook_scopes" in query:
            return self.scope_count
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if query.lstrip().upper().startswith("UPDATE"):
            return "UPDATE 1"
        return "INSERT 0 1"


class _FakeConnContext:
    def __init__(self, conn: _FakeConnection):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _patch_connection(monkeypatch, conn: _FakeConnection):
    monkeypatch.setattr(handbook_service_module, "get_connection", lambda: _FakeConnContext(conn))


def test_update_handbook_rejects_mode_scope_mismatch(monkeypatch):
    conn = _FakeConnection(
        current_row={
            "id": "hb-1",
            "company_id": "co-1",
            "mode": "multi_state",
            "source_type": "template",
            "active_version": 1,
        },
        scope_count=2,
    )
    _patch_connection(monkeypatch, conn)

    with pytest.raises(ValueError, match="Single-state handbooks must have exactly one scope"):
        asyncio.run(
            HandbookService.update_handbook(
                "hb-1",
                "co-1",
                HandbookUpdateRequest(mode="single_state"),
                "user-1",
            )
        )


def test_update_handbook_invalidates_cached_pdf_for_template_changes(monkeypatch):
    conn = _FakeConnection(
        current_row={
            "id": "hb-1",
            "company_id": "co-1",
            "mode": "single_state",
            "source_type": "template",
            "active_version": 1,
        },
        scope_count=1,
    )
    _patch_connection(monkeypatch, conn)

    async def _fake_get(*args, **kwargs):
        return SimpleNamespace(id="hb-1")

    monkeypatch.setattr(HandbookService, "get_handbook_by_id", _fake_get)

    asyncio.run(
        HandbookService.update_handbook(
            "hb-1",
            "co-1",
            HandbookUpdateRequest(title="Updated Handbook"),
            "user-1",
        )
    )

    update_queries = [query for query, _ in conn.executed if query.lstrip().upper().startswith("UPDATE HANDBOOKS SET")]
    assert update_queries, "Expected handbook update query to be executed"
    assert "file_url = NULL" in update_queries[0]
    assert "file_name = NULL" in update_queries[0]


def test_generate_handbook_pdf_bytes_escapes_html(monkeypatch):
    captured: dict[str, str] = {}

    class DummyHTML:
        def __init__(self, string):
            captured["html"] = string

        def write_pdf(self):
            return b"%PDF-test"

    monkeypatch.setitem(sys.modules, "weasyprint", types.SimpleNamespace(HTML=DummyHTML))

    fake_handbook = SimpleNamespace(
        title="<script>alert(1)</script>",
        active_version=3,
        status="draft",
        scopes=[SimpleNamespace(state="CA")],
        profile=SimpleNamespace(
            legal_name="<b>Acme</b>",
            dba=None,
            ceo_or_president='Jane "CEO" <Leader>',
            headcount=42,
        ),
        sections=[
            SimpleNamespace(
                title="Welcome <img src=x>",
                content="Line 1\n<script>bad()</script>",
            )
        ],
    )

    async def _fake_get(*args, **kwargs):
        return fake_handbook

    monkeypatch.setattr(HandbookService, "get_handbook_by_id", _fake_get)

    pdf_bytes, filename = asyncio.run(
        HandbookService.generate_handbook_pdf_bytes("hb-1", "co-1")
    )
    assert pdf_bytes == b"%PDF-test"
    assert filename.endswith("-v3.pdf")

    rendered_html = captured["html"]
    assert "<script>" not in rendered_html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in rendered_html
    assert "&lt;b&gt;Acme&lt;/b&gt;" in rendered_html


def test_normalize_custom_sections_produces_unique_safe_keys():
    sections = [
        SimpleNamespace(
            section_key="",
            title="My Custom Policy!!!",
            content="A",
            section_order=300,
            jurisdiction_scope={},
        ),
        SimpleNamespace(
            section_key="my custom policy",
            title="My Custom Policy",
            content="B",
            section_order=301,
            jurisdiction_scope={},
        ),
    ]

    normalized = _normalize_custom_sections(sections)  # type: ignore[arg-type]
    keys = [item["section_key"] for item in normalized]
    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert all(len(key) <= 120 for key in keys)


def test_translate_handbook_db_error_handles_profile_schema_drift():
    err = Exception('column "tip_pooling" of relation "company_handbook_profiles" does not exist')
    translated = _translate_handbook_db_error(err)
    assert translated == "Handbook tables are out of date. Restart the API to apply schema updates."
