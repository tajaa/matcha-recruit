"""CBA document store + clause library routes.

Mounted (with prefix `/labor` + `require_feature("labor_relations")`) at the
package parent. All endpoints are tenant-isolated on the caller's company.
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.labor_relations import (
    CBACreateRequest,
    CBAUpdateRequest,
    ClauseCreateRequest,
    ClauseUpdateRequest,
)
from app.matcha.routes.labor_relations._shared import (
    _require_company,
    _serialize,
    _serialize_list,
    get_cba_or_404,
    write_audit,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Columns safe + cheap to return in list views (omit the large extracted_text).
_CBA_LIST_COLS = (
    "id, company_id, union_name, union_local, bargaining_unit_desc, effective_date, "
    "expiration_date, status, document_filename, extraction_status, renewal_alert_days, "
    "grievance_steps_confirmed, created_at, updated_at"
)


# ── CBAs ─────────────────────────────────────────────────────────────────────

@router.get("/cbas")
async def list_cbas(
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                f"SELECT {_CBA_LIST_COLS} FROM lr_cbas "
                "WHERE company_id = $1 AND status = $2 ORDER BY updated_at DESC",
                company_id, status,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {_CBA_LIST_COLS} FROM lr_cbas "
                "WHERE company_id = $1 ORDER BY updated_at DESC",
                company_id,
            )
    return {"cbas": _serialize_list(rows)}


@router.post("/cbas", status_code=201)
async def create_cba(
    body: CBACreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    step_config = (
        json.dumps([s.model_dump() for s in body.grievance_step_config])
        if body.grievance_step_config is not None else "[]"
    )
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO lr_cbas
                (company_id, union_name, union_local, bargaining_unit_desc, effective_date,
                 expiration_date, status, renewal_alert_days, grievance_step_config, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
            RETURNING *
            """,
            company_id, body.union_name, body.union_local, body.bargaining_unit_desc,
            body.effective_date, body.expiration_date, body.status, body.renewal_alert_days,
            step_config, current_user.id,
        )
        await write_audit(conn, company_id, "cba", row["id"], current_user.id, "created",
                          {"union_name": body.union_name})
    return _serialize(row)


@router.get("/cbas/{cba_id}")
async def get_cba(
    cba_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        cba = await get_cba_or_404(conn, cba_id, company_id)
        clauses = await conn.fetch(
            "SELECT * FROM lr_cba_clauses WHERE cba_id = $1 ORDER BY sort_order, created_at",
            cba_id,
        )
    # Don't ship the full extracted contract text to the browser — the detail
    # view never renders it, and it can be very large.
    cba.pop("extracted_text", None)
    out = _serialize(cba)
    out["clauses"] = _serialize_list(clauses)
    return out


@router.patch("/cbas/{cba_id}")
async def update_cba(
    cba_id: UUID,
    body: CBAUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    sets: list[str] = []
    vals: list = []
    idx = 1
    for key, value in fields.items():
        if key == "grievance_step_config":
            sets.append(f"grievance_step_config = ${idx}::jsonb")
            vals.append(json.dumps([s if isinstance(s, dict) else s.model_dump() for s in (value or [])]))
        else:
            sets.append(f"{key} = ${idx}")
            vals.append(value)
        idx += 1
    sets.append("updated_at = NOW()")

    async with get_connection() as conn:
        await get_cba_or_404(conn, cba_id, company_id)
        vals.extend([cba_id, company_id])
        row = await conn.fetchrow(
            f"UPDATE lr_cbas SET {', '.join(sets)} "
            f"WHERE id = ${idx} AND company_id = ${idx + 1} RETURNING *",
            *vals,
        )
        await write_audit(conn, company_id, "cba", cba_id, current_user.id, "updated",
                          {"fields": list(fields.keys())})
    return _serialize(row)


@router.delete("/cbas/{cba_id}", status_code=204)
async def delete_cba(
    cba_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        await get_cba_or_404(conn, cba_id, company_id)
        await conn.execute("DELETE FROM lr_cbas WHERE id = $1 AND company_id = $2", cba_id, company_id)
        await write_audit(conn, company_id, "cba", cba_id, current_user.id, "deleted", {})
    return JSONResponse(status_code=204, content=None)


# ── CBA document (private PDF) ───────────────────────────────────────────────

@router.post("/cbas/{cba_id}/document")
async def upload_cba_document(
    cba_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    storage = get_storage()
    try:
        path = await storage.upload_private_file(
            file_bytes, file.filename or "cba.pdf",
            prefix="cba-documents", content_type=file.content_type,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("CBA document upload failed for %s: %s", cba_id, exc)
        raise HTTPException(status_code=502, detail="Document upload failed") from exc

    async with get_connection() as conn:
        await get_cba_or_404(conn, cba_id, company_id)
        row = await conn.fetchrow(
            """
            UPDATE lr_cbas
            SET document_storage_path = $1, document_filename = $2,
                extracted_text = NULL, extraction_status = 'processing', updated_at = NOW()
            WHERE id = $3 AND company_id = $4
            RETURNING *
            """,
            path, file.filename, cba_id, company_id,
        )
        await write_audit(conn, company_id, "cba", cba_id, current_user.id, "document_uploaded",
                          {"filename": file.filename})

    _queue_clause_extraction(cba_id)
    return _serialize(row)


@router.get("/cbas/{cba_id}/document")
async def get_cba_document_url(
    cba_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        cba = await get_cba_or_404(conn, cba_id, company_id)
    path = cba.get("document_storage_path")
    if not path:
        raise HTTPException(status_code=404, detail="No document on file")
    url = get_storage().get_presigned_download_url(path, expires_in=900)
    if not url:
        raise HTTPException(status_code=502, detail="Could not generate download link")
    return {"url": url, "filename": cba.get("document_filename")}


@router.post("/cbas/{cba_id}/extract-clauses", status_code=202)
async def extract_clauses(
    cba_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    """(Re)run AI clause extraction against the stored CBA document."""
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        cba = await get_cba_or_404(conn, cba_id, company_id)
        if not cba.get("document_storage_path"):
            raise HTTPException(status_code=400, detail="Upload a CBA document first")
        await conn.execute(
            "UPDATE lr_cbas SET extraction_status = 'processing', updated_at = NOW() WHERE id = $1",
            cba_id,
        )
    _queue_clause_extraction(cba_id)
    return {"status": "queued", "cba_id": str(cba_id)}


def _queue_clause_extraction(cba_id: UUID) -> None:
    """Enqueue the Celery extraction task; degrade to inline-skip on failure."""
    try:
        from app.workers.tasks.cba_clause_extraction import run_cba_clause_extraction
        run_cba_clause_extraction.delay(str(cba_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to queue CBA clause extraction for %s: %s", cba_id, exc)


# ── Clauses ─────────────────────────────────────────────────────────────────

@router.get("/cbas/{cba_id}/clauses")
async def list_clauses(
    cba_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        await get_cba_or_404(conn, cba_id, company_id)
        rows = await conn.fetch(
            "SELECT * FROM lr_cba_clauses WHERE cba_id = $1 ORDER BY sort_order, created_at",
            cba_id,
        )
    return {"clauses": _serialize_list(rows)}


@router.post("/cbas/{cba_id}/clauses", status_code=201)
async def create_clause(
    cba_id: UUID,
    body: ClauseCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        await get_cba_or_404(conn, cba_id, company_id)
        row = await conn.fetchrow(
            """
            INSERT INTO lr_cba_clauses
                (cba_id, company_id, article_number, title, clause_text, category, source, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, 'manual', $7)
            RETURNING *
            """,
            cba_id, company_id, body.article_number, body.title, body.clause_text,
            body.category, body.sort_order,
        )
        await write_audit(conn, company_id, "clause", row["id"], current_user.id, "created",
                          {"cba_id": str(cba_id)})
    return _serialize(row)


@router.patch("/cbas/{cba_id}/clauses/{clause_id}")
async def update_clause(
    cba_id: UUID,
    clause_id: UUID,
    body: ClauseUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    fields = body.model_dump(exclude_unset=True)
    confirm = fields.pop("confirm", False)

    sets: list[str] = []
    vals: list = []
    idx = 1
    for key, value in fields.items():
        sets.append(f"{key} = ${idx}")
        vals.append(value)
        idx += 1
    if confirm:
        # Confirming an AI-extracted clause makes it HR-owned.
        sets.append("source = 'manual'")
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets.append("updated_at = NOW()")

    async with get_connection() as conn:
        await get_cba_or_404(conn, cba_id, company_id)
        vals.extend([clause_id, cba_id])
        row = await conn.fetchrow(
            f"UPDATE lr_cba_clauses SET {', '.join(sets)} "
            f"WHERE id = ${idx} AND cba_id = ${idx + 1} RETURNING *",
            *vals,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Clause not found")
        await write_audit(conn, company_id, "clause", clause_id, current_user.id, "updated",
                          {"confirmed": bool(confirm)})
    return _serialize(row)


@router.delete("/cbas/{cba_id}/clauses/{clause_id}", status_code=204)
async def delete_clause(
    cba_id: UUID,
    clause_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        await get_cba_or_404(conn, cba_id, company_id)
        result = await conn.execute(
            "DELETE FROM lr_cba_clauses WHERE id = $1 AND cba_id = $2", clause_id, cba_id,
        )
        if result.split()[-1] == "0":
            raise HTTPException(status_code=404, detail="Clause not found")
        await write_audit(conn, company_id, "clause", clause_id, current_user.id, "deleted", {})
    return JSONResponse(status_code=204, content=None)
