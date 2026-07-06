"""ER case notes: list + create."""
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Request

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ...models.er_case import (
    ERCaseNoteCreate,
    ERCaseNoteResponse,
)

from ._shared import (
    log_audit,
    _verify_case_company,
    _normalize_json_dict,
)

router = APIRouter()


@router.get("/{case_id}/notes", response_model=list[ERCaseNoteResponse])
async def list_case_notes(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List notes for a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        rows = await conn.fetch(
            """
            SELECT id, case_id, note_type, content, metadata, created_by, created_at
            FROM er_case_notes
            WHERE case_id = $1
            ORDER BY created_at ASC
            """,
            case_id,
        )

        return [
            ERCaseNoteResponse(
                id=row["id"],
                case_id=row["case_id"],
                note_type=row["note_type"],
                content=row["content"],
                metadata=_normalize_json_dict(row["metadata"]),
                created_by=row["created_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.post("/{case_id}/notes", response_model=ERCaseNoteResponse)
async def create_case_note(
    case_id: UUID,
    note: ERCaseNoteCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a note for a case."""
    content = note.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Note content cannot be empty")

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            INSERT INTO er_case_notes (case_id, note_type, content, metadata, created_by)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING id, case_id, note_type, content, metadata, created_by, created_at
            """,
            case_id,
            note.note_type,
            content,
            json.dumps(note.metadata) if note.metadata is not None else None,
            str(current_user.id),
        )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "case_note_created",
            "note",
            str(row["id"]),
            {"note_type": note.note_type},
            request.client.host if request.client else None,
        )

        return ERCaseNoteResponse(
            id=row["id"],
            case_id=row["case_id"],
            note_type=row["note_type"],
            content=row["content"],
            metadata=_normalize_json_dict(row["metadata"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
        )


# ===========================================
# Documents
# ===========================================

