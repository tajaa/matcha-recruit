"""discipline_filing: doc_type embeds the record id (GAP-3 fix — the
employee_documents partial-unique index collides on a literal doc_type for a
second signed letter), and filing never raises.

    cd server && ./venv/bin/python -m pytest tests/discipline/test_discipline_filing.py -q
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.discipline import discipline_filing as filing

RECORD_ID = uuid4()
COMPANY_ID = uuid4()
EMPLOYEE_ID = uuid4()
INCIDENT_ID = uuid4()


def _record(**overrides):
    base = {
        "id": RECORD_ID, "company_id": COMPANY_ID, "employee_id": EMPLOYEE_ID,
        "discipline_type": "written_warning", "issued_date": "2026-07-28",
        "signed_pdf_storage_path": "s3://bucket/discipline-signed.pdf",
        # tz-AWARE, exactly as asyncpg hands back a TIMESTAMPTZ column
        "signature_completed_at": datetime(2026, 7, 29, tzinfo=timezone.utc),
        "source_incident_id": None,
    }
    base.update(overrides)
    return base


class TestSignedLetterDocType:
    def test_embeds_record_id_and_fits_varchar50(self):
        doc_type = filing.signed_letter_doc_type(RECORD_ID)
        assert doc_type == f"discipline:{RECORD_ID}"
        assert len(doc_type) <= 50

    def test_two_different_records_get_different_doc_types(self):
        assert filing.signed_letter_doc_type(uuid4()) != filing.signed_letter_doc_type(uuid4())


class TestFileSignedLetter:
    @pytest.mark.asyncio
    async def test_writes_employee_document_with_org_id_tenant_column(self):
        conn = MagicMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)

        await filing.file_signed_letter(conn, _record())

        assert conn.execute.await_count == 1
        query, *args = conn.execute.await_args.args
        assert "INSERT INTO employee_documents" in query
        assert "org_id" in query
        assert args[0] == COMPANY_ID  # org_id positional
        assert args[1] == EMPLOYEE_ID
        assert args[2] == filing.signed_letter_doc_type(RECORD_ID)

    @pytest.mark.asyncio
    async def test_signed_at_uses_now_not_a_tz_aware_param(self):
        """employee_documents.signed_at is a naive TIMESTAMP; the discipline
        record's signature_completed_at is TIMESTAMPTZ. Binding the latter to the
        former raises inside asyncpg, and file_signed_letter swallows everything —
        so the row would silently never be written. NOW() is the only safe form."""
        conn = MagicMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)

        await filing.file_signed_letter(conn, _record())

        query, *args = conn.execute.await_args.args
        assert "NOW()" in query
        assert not any(
            isinstance(a, datetime) and a.tzinfo is not None for a in args
        ), "no tz-aware datetime may be bound into the naive signed_at column"

    @pytest.mark.asyncio
    async def test_incident_row_only_when_source_incident_set(self):
        conn = MagicMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)  # NOT EXISTS check -> no prior row

        await filing.file_signed_letter(conn, _record(source_incident_id=None))
        assert conn.execute.await_count == 1  # only the employee_documents insert

        conn.execute.reset_mock()
        await filing.file_signed_letter(conn, _record(source_incident_id=INCIDENT_ID))
        assert conn.execute.await_count == 2  # + ir_incident_documents insert
        second_call_query = conn.execute.await_args_list[1].args[0]
        assert "ir_incident_documents" in second_call_query
        assert "disciplinary" in second_call_query

    @pytest.mark.asyncio
    async def test_incident_row_skipped_when_already_filed(self):
        conn = MagicMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=1)  # NOT EXISTS check finds an existing row

        await filing.file_signed_letter(conn, _record(source_incident_id=INCIDENT_ID))

        # Only the employee_documents insert — the incident-doc insert was skipped.
        assert conn.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_never_raises_on_employee_document_failure(self):
        conn = MagicMock()
        conn.execute = AsyncMock(side_effect=RuntimeError("db down"))
        conn.fetchval = AsyncMock(return_value=None)

        await filing.file_signed_letter(conn, _record(source_incident_id=INCIDENT_ID))  # must not raise

    @pytest.mark.asyncio
    async def test_never_raises_on_incident_document_failure(self):
        conn = MagicMock()
        calls = {"n": 0}

        async def execute(query, *args):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("db down")

        conn.execute = AsyncMock(side_effect=execute)
        conn.fetchval = AsyncMock(return_value=None)

        await filing.file_signed_letter(conn, _record(source_incident_id=INCIDENT_ID))  # must not raise
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_skips_when_no_signed_pdf_path(self):
        conn = MagicMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)

        await filing.file_signed_letter(conn, _record(signed_pdf_storage_path=None, source_incident_id=INCIDENT_ID))

        conn.execute.assert_not_called()
