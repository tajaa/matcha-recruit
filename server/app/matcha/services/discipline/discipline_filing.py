"""Post-signature filing of the signed disciplinary letter.

Called from both PDF-landing paths — physical upload and the e-sign webhook's
completed branch, in routes/employee_lifecycle/discipline.py — after
`signed_pdf_storage_path` has already been written. Never raises: filing must
not fail a signature write that already committed. Log-and-continue.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def signed_letter_doc_type(discipline_id: UUID) -> str:
    """`discipline:<uuid>` — 47 chars, fits employee_documents.doc_type
    VARCHAR(50). employee_documents has a partial UNIQUE index on
    (employee_id, doc_type) WHERE status IN ('pending_signature','signed') —
    a literal 'disciplinary_action' would collide on a SECOND signed letter
    for the same employee (or be silently dropped by ON CONFLICT DO NOTHING).
    Embedding the record id (the same convention handbook_service uses for
    `handbook:<id>:<version>`) makes each letter its own document AND makes
    webhook redelivery of the SAME record naturally idempotent.
    """
    return f"discipline:{discipline_id}"


async def file_signed_letter(conn, record: dict[str, Any]) -> None:
    """File the signed letter on `record` against the employee's document
    file and (when incident-triggered) the source incident's Documents tab.
    Never raises.
    """
    try:
        await _file_employee_document(conn, record)
    except Exception:
        logger.exception(
            "[discipline_filing] failed to file employee_documents row for record %s",
            record.get("id"),
        )

    if record.get("source_incident_id"):
        try:
            await _file_incident_document(conn, record)
        except Exception:
            logger.exception(
                "[discipline_filing] failed to file ir_incident_documents row for record %s",
                record.get("id"),
            )


async def _file_employee_document(conn, record: dict[str, Any]) -> None:
    storage_path = record.get("signed_pdf_storage_path")
    if not storage_path:
        return
    discipline_type = (record.get("discipline_type") or "").replace("_", " ").title()
    issued_date = record.get("issued_date")
    title = f"Disciplinary action — {discipline_type} ({issued_date})" if issued_date else f"Disciplinary action — {discipline_type}"

    # Tenant column on employee_documents is org_id, not company_id.
    #
    # signed_at is written with NOW(), NOT the record's signature_completed_at.
    # progressive_discipline.signature_completed_at is TIMESTAMPTZ (asyncpg hands
    # back a tz-AWARE datetime) while employee_documents.signed_at is a naive
    # TIMESTAMP — encoding one into the other raises inside asyncpg, and because
    # this whole module never raises, the failure would surface only as a log line
    # and no document row would ever be filed. Every other writer of this column
    # (employee_portal/documents.py, offer_letters.py) uses NOW() for the same
    # reason. The exact signature timestamp stays on the discipline record.
    await conn.execute(
        """
        INSERT INTO employee_documents (org_id, employee_id, doc_type, title, storage_path, status, signed_at)
        VALUES ($1, $2, $3, $4, $5, 'signed', NOW())
        ON CONFLICT (employee_id, doc_type) WHERE status IN ('pending_signature', 'signed') DO NOTHING
        """,
        record["company_id"],
        record["employee_id"],
        signed_letter_doc_type(record["id"]),
        title,
        storage_path,
    )


async def _file_incident_document(conn, record: dict[str, Any]) -> None:
    storage_path = record.get("signed_pdf_storage_path")
    if not storage_path:
        return
    incident_id = record["source_incident_id"]

    # ir_incident_documents has no unique constraint to ON CONFLICT against —
    # guard idempotency with an explicit existence check instead.
    exists = await conn.fetchval(
        "SELECT 1 FROM ir_incident_documents WHERE incident_id = $1 AND file_path = $2",
        incident_id, storage_path,
    )
    if exists:
        return

    discipline_type = (record.get("discipline_type") or "").replace("_", " ").title()
    filename = f"Disciplinary action - {discipline_type}.pdf"
    await conn.execute(
        """
        INSERT INTO ir_incident_documents (
            incident_id, document_type, filename, file_path, mime_type, uploaded_via
        )
        VALUES ($1, 'disciplinary', $2, $3, 'application/pdf', 'authed')
        """,
        incident_id, filename, storage_path,
    )
