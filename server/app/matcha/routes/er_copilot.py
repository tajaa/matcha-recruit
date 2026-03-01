"""ER Copilot API Routes.

Employee Relations Investigation management:
- Cases CRUD
- Document upload and processing
- AI analysis (timeline, discrepancies, policy check)
- Report generation
- Evidence search (RAG)
"""

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timezone

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Request

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser
from ...config import get_settings
from ...core.services.storage import get_storage
from ..services.er_guidance import (
    _build_fallback_guidance_payload,
    _determination_confidence_floor,
    _normalize_analysis_payload,
    _normalize_suggested_guidance_payload,
)
from ..models.er_case import (
    ERCaseCreate,
    ERCaseUpdate,
    ERCaseResponse,
    ERCaseListResponse,
    ERCaseStatus,
    ERCaseNoteCreate,
    ERCaseNoteResponse,
    ERDocumentResponse,
    ERDocumentUploadResponse,
    TimelineAnalysis,
    DiscrepancyAnalysis,
    PolicyCheckAnalysis,
    SuggestedGuidanceResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
    ReportGenerateRequest,
    ReportResponse,
    TaskStatusResponse,
    AuditLogEntry,
    AuditLogResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


# ===========================================
# Helper Functions
# ===========================================

def generate_case_number() -> str:
    """Generate a unique case number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"ER-{now.year}-{now.month:02d}-{random_suffix}"


async def log_audit(
    conn,
    case_id: Optional[str],
    user_id: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Log an action to the audit trail."""
    await conn.execute(
        """
        INSERT INTO er_audit_log (case_id, user_id, action, entity_type, entity_id, details, ip_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        case_id,
        user_id,
        action,
        entity_type,
        entity_id,
        json.dumps(details) if details else None,
        ip_address,
    )


async def _verify_case_company(conn, case_id: UUID, company_id: UUID, is_admin: bool = False):
    """Verify a case exists and belongs to the company. Raises 404 if not.
    Admins can also access legacy rows with NULL company_id."""
    if is_admin:
        exists = await conn.fetchval(
            "SELECT 1 FROM er_cases WHERE id = $1 AND (company_id = $2 OR company_id IS NULL)",
            case_id,
            company_id,
        )
    else:
        exists = await conn.fetchval(
            "SELECT 1 FROM er_cases WHERE id = $1 AND company_id = $2",
            case_id,
            company_id,
        )
    if not exists:
        raise HTTPException(status_code=404, detail="Case not found")


def _normalize_search_metadata(raw_value: Any) -> Optional[dict]:
    """Normalize metadata payloads to dict for API response compatibility."""
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _normalize_json_dict(raw_value: Any) -> Optional[dict]:
    """Normalize JSON/JSONB payloads to dict for API response compatibility."""
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _normalize_document_type(raw_value: Any) -> str:
    """Normalize legacy/invalid document types to a supported value."""
    if isinstance(raw_value, str):
        value = raw_value.strip().lower()
        if value in {"transcript", "policy", "email", "other"}:
            return value
    return "other"


def _normalize_intake_context(raw_value: Any) -> Optional[dict]:
    """Normalize intake_context payloads to a dict for API response compatibility."""
    return _normalize_json_dict(raw_value)


def _build_er_analyzer():
    """Create ERAnalyzer using shared Gemini credential cascade."""
    from ..services.er_analyzer import ERAnalyzer

    settings = get_settings()
    explicit_api_key = os.getenv("GEMINI_API_KEY")

    if explicit_api_key:
        return ERAnalyzer(api_key=explicit_api_key, model=settings.analysis_model)
    if settings.use_vertex:
        return ERAnalyzer(
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
            model=settings.analysis_model,
        )
    if settings.gemini_api_key:
        return ERAnalyzer(api_key=settings.gemini_api_key, model=settings.analysis_model)
    raise ValueError("ER analysis requires GEMINI_API_KEY, LIVE_API, or VERTEX_PROJECT configuration")


# ===========================================
# Cases CRUD
# ===========================================

@router.post("", response_model=ERCaseResponse)
async def create_case(
    case: ERCaseCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new ER investigation case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    case_number = generate_case_number()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO er_cases (case_number, title, description, intake_context, created_by, company_id, category)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
            RETURNING id, case_number, title, description, intake_context, status, company_id, created_by, assigned_to, created_at, updated_at, closed_at, category, outcome
            """,
            case_number,
            case.title,
            case.description,
            json.dumps(case.intake_context) if case.intake_context is not None else None,
            str(current_user.id),
            company_id,
            case.category,
        )

        # Log audit
        await log_audit(
            conn,
            str(row["id"]),
            str(current_user.id),
            "case_created",
            "case",
            str(row["id"]),
            {"title": case.title},
            request.client.host if request.client else None,
        )

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            intake_context=_normalize_intake_context(row["intake_context"]),
            status=row["status"],
            category=row["category"],
            outcome=row["outcome"],
            company_id=row["company_id"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.get("", response_model=ERCaseListResponse)
async def list_cases(
    status: Optional[ERCaseStatus] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List ER cases scoped to the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return ERCaseListResponse(cases=[], total=0)

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        company_filter = "(c.company_id = $1 OR c.company_id IS NULL)" if is_admin else "c.company_id = $1"
        base_query = f"""
            SELECT c.*, COUNT(d.id) as document_count
            FROM er_cases c
            LEFT JOIN er_case_documents d ON c.id = d.case_id
            WHERE {company_filter}
        """

        if status:
            query = base_query + " AND c.status = $2 GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query, company_id, status)
        else:
            query = base_query + " GROUP BY c.id ORDER BY c.updated_at DESC"
            rows = await conn.fetch(query, company_id)

        cases = [
            ERCaseResponse(
                id=row["id"],
                case_number=row["case_number"],
                title=row["title"],
                description=row["description"],
                intake_context=_normalize_intake_context(row["intake_context"]),
                status=row["status"],
                category=row.get("category"),
                outcome=row.get("outcome"),
                company_id=row["company_id"],
                created_by=row["created_by"],
                assigned_to=row["assigned_to"],
                document_count=row["document_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"],
            )
            for row in rows
        ]

        return ERCaseListResponse(cases=cases, total=len(cases))


@router.get("/metrics")
async def get_case_metrics(
    days: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get ER case metrics for the specified period."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"period_days": days, "total_cases": 0, "by_status": {}, "by_category": {}, "by_outcome": {}, "trend": []}

    async with get_connection() as conn:
        is_admin = current_user.role == "admin"
        company_filter = "(company_id = $1 OR company_id IS NULL)" if is_admin else "company_id = $1"
        date_filter = f"created_at >= NOW() - interval '{int(days)} days'"

        # Total cases
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM er_cases WHERE {company_filter} AND {date_filter}",
            company_id,
        )

        # By status
        status_rows = await conn.fetch(
            f"SELECT status, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} GROUP BY status",
            company_id,
        )
        by_status = {r["status"]: r["cnt"] for r in status_rows}

        # By category
        cat_rows = await conn.fetch(
            f"SELECT category, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} AND category IS NOT NULL GROUP BY category",
            company_id,
        )
        by_category = {r["category"]: r["cnt"] for r in cat_rows}

        # By outcome
        out_rows = await conn.fetch(
            f"SELECT outcome, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} AND outcome IS NOT NULL GROUP BY outcome",
            company_id,
        )
        by_outcome = {r["outcome"]: r["cnt"] for r in out_rows}

        # Daily trend
        trend_rows = await conn.fetch(
            f"SELECT created_at::date as d, COUNT(*) as cnt FROM er_cases WHERE {company_filter} AND {date_filter} GROUP BY d ORDER BY d",
            company_id,
        )
        trend = [{"date": str(r["d"]), "count": r["cnt"]} for r in trend_rows]

        return {
            "period_days": days,
            "total_cases": total or 0,
            "by_status": by_status,
            "by_category": by_category,
            "by_outcome": by_outcome,
            "trend": trend,
        }


@router.get("/{case_id}", response_model=ERCaseResponse)
async def get_case(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get a case by ID."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        company_filter = "(c.company_id = $2 OR c.company_id IS NULL)" if is_admin else "c.company_id = $2"
        row = await conn.fetchrow(
            f"""
            SELECT c.*, COUNT(d.id) as document_count
            FROM er_cases c
            LEFT JOIN er_case_documents d ON c.id = d.case_id
            WHERE c.id = $1 AND {company_filter}
            GROUP BY c.id
            """,
            case_id,
            company_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            intake_context=_normalize_intake_context(row["intake_context"]),
            status=row["status"],
            category=row.get("category"),
            outcome=row.get("outcome"),
            company_id=row["company_id"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=row["document_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.put("/{case_id}", response_model=ERCaseResponse)
async def update_case(
    case_id: UUID,
    case: ERCaseUpdate,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, is_admin)

        # Build dynamic update
        updates = []
        params = []
        param_count = 1

        if case.title is not None:
            updates.append(f"title = ${param_count}")
            params.append(case.title)
            param_count += 1

        if case.description is not None:
            updates.append(f"description = ${param_count}")
            params.append(case.description)
            param_count += 1

        if case.status is not None:
            updates.append(f"status = ${param_count}")
            params.append(case.status)
            param_count += 1

            if case.status == "closed":
                updates.append("closed_at = NOW()")

        if case.assigned_to is not None:
            updates.append(f"assigned_to = ${param_count}")
            params.append(case.assigned_to)
            param_count += 1

        if case.intake_context is not None:
            updates.append(f"intake_context = ${param_count}::jsonb")
            params.append(json.dumps(case.intake_context))
            param_count += 1

        if case.category is not None:
            updates.append(f"category = ${param_count}")
            params.append(case.category)
            param_count += 1

        if case.outcome is not None:
            updates.append(f"outcome = ${param_count}")
            params.append(case.outcome)
            param_count += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(case_id)
        param_count += 1
        params.append(company_id)

        company_filter = f"(company_id = ${param_count} OR company_id IS NULL)" if is_admin else f"company_id = ${param_count}"
        query = f"""
            UPDATE er_cases
            SET {', '.join(updates)}
            WHERE id = ${param_count - 1} AND {company_filter}
            RETURNING id, case_number, title, description, intake_context, status, company_id, created_by, assigned_to, created_at, updated_at, closed_at, category, outcome
        """

        row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        # Get document count
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_documents WHERE case_id = $1",
            case_id,
        )

        # Log audit
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "case_updated",
            "case",
            str(case_id),
            case.model_dump(exclude_none=True),
            request.client.host if request.client else None,
        )

        return ERCaseResponse(
            id=row["id"],
            case_number=row["case_number"],
            title=row["title"],
            description=row["description"],
            intake_context=_normalize_intake_context(row["intake_context"]),
            status=row["status"],
            category=row["category"],
            outcome=row["outcome"],
            company_id=row["company_id"],
            created_by=row["created_by"],
            assigned_to=row["assigned_to"],
            document_count=doc_count or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )


@router.delete("/{case_id}")
async def delete_case(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a case and all associated data."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    company_filter = "(company_id = $2 OR company_id IS NULL)" if is_admin else "company_id = $2"

    async with get_connection() as conn:
        # Get case info for audit log before deletion
        case = await conn.fetchrow(
            f"SELECT case_number, title FROM er_cases WHERE id = $1 AND {company_filter}",
            case_id,
            company_id,
        )

        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        # Delete case (cascades to documents, chunks, analysis)
        await conn.execute(
            f"DELETE FROM er_cases WHERE id = $1 AND {company_filter}",
            case_id,
            company_id,
        )

        # Log audit (case_id is null since case is deleted)
        await log_audit(
            conn,
            None,
            str(current_user.id),
            "case_deleted",
            "case",
            str(case_id),
            {"case_number": case["case_number"], "title": case["title"]},
            request.client.host if request.client else None,
        )

        return {"status": "deleted", "case_id": str(case_id)}


# ===========================================
# Case Export
# ===========================================

@router.post("/{case_id}/export")
async def export_case_file(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Export a case as a password-protected PDF."""
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, Field

    # Parse password from body
    body = await request.json()
    password = body.get("password", "")
    if not password or len(password) < 4 or len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be 4-128 characters")

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, is_admin)

        # Fetch case
        case_row = await conn.fetchrow(
            "SELECT * FROM er_cases WHERE id = $1", case_id
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        # Fetch documents
        doc_rows = await conn.fetch(
            "SELECT filename, document_type, file_size, created_at FROM er_case_documents WHERE case_id = $1 ORDER BY created_at",
            case_id,
        )

        # Fetch analyses
        analysis_rows = await conn.fetch(
            "SELECT analysis_type, result, created_at FROM er_case_analysis WHERE case_id = $1 ORDER BY created_at",
            case_id,
        )

        # Fetch notes
        note_rows = await conn.fetch(
            "SELECT note_type, content, created_at FROM er_case_notes WHERE case_id = $1 ORDER BY created_at",
            case_id,
        )

    # Build HTML report
    case_title = case_row["title"] or "Untitled Case"
    case_number = case_row["case_number"]
    status = case_row["status"]
    category = case_row.get("category") or "—"
    outcome = case_row.get("outcome") or "—"
    description = case_row["description"] or "No description provided."
    created_at = case_row["created_at"].strftime("%Y-%m-%d %H:%M") if case_row["created_at"] else "—"
    closed_at = case_row["closed_at"].strftime("%Y-%m-%d %H:%M") if case_row.get("closed_at") else "—"

    docs_html = ""
    if doc_rows:
        rows_html = "".join(
            f"<tr><td>{r['filename']}</td><td>{r['document_type']}</td><td>{(r['file_size'] or 0) // 1024} KB</td><td>{r['created_at'].strftime('%Y-%m-%d')}</td></tr>"
            for r in doc_rows
        )
        docs_html = f"<h2>Documents ({len(doc_rows)})</h2><table><tr><th>Filename</th><th>Type</th><th>Size</th><th>Uploaded</th></tr>{rows_html}</table>"

    analyses_html = ""
    for a in analysis_rows:
        atype = (a["analysis_type"] or "unknown").replace("_", " ").title()
        result = a["result"]
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                pass
        summary = ""
        if isinstance(result, dict):
            summary = result.get("summary") or result.get("timeline_summary") or json.dumps(result, indent=2)[:500]
        else:
            summary = str(result)[:500] if result else "No results."
        analyses_html += f"<h3>{atype}</h3><p>{summary}</p>"
    if analyses_html:
        analyses_html = f"<h2>Analyses</h2>{analyses_html}"

    notes_html = ""
    if note_rows:
        items = "".join(
            f"<div class='note'><span class='note-type'>{r['note_type']}</span> <span class='note-date'>{r['created_at'].strftime('%Y-%m-%d %H:%M')}</span><p>{r['content']}</p></div>"
            for r in note_rows
        )
        notes_html = f"<h2>Case Notes ({len(note_rows)})</h2>{items}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; color: #1a1a1a; font-size: 12px; line-height: 1.6; }}
h1 {{ font-size: 20px; margin-bottom: 4px; }}
h2 {{ font-size: 14px; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 28px; text-transform: uppercase; letter-spacing: 1px; color: #555; }}
h3 {{ font-size: 12px; margin-top: 16px; color: #333; }}
.meta {{ color: #666; font-size: 11px; margin-bottom: 20px; }}
.meta span {{ display: inline-block; margin-right: 20px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin: 12px 0; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
th {{ background: #f5f5f5; font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px; }}
.note {{ border-left: 3px solid #ddd; padding: 8px 12px; margin: 8px 0; background: #fafafa; }}
.note-type {{ font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px; }}
.note-date {{ color: #999; font-size: 10px; margin-left: 8px; }}
.footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 12px; color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
<h1>{case_title}</h1>
<div class="meta">
  <span><strong>Case:</strong> {case_number}</span>
  <span><strong>Status:</strong> {status}</span>
  <span><strong>Category:</strong> {category}</span>
  <span><strong>Outcome:</strong> {outcome}</span>
  <span><strong>Created:</strong> {created_at}</span>
  <span><strong>Closed:</strong> {closed_at}</span>
</div>
<h2>Description</h2>
<p>{description}</p>
{docs_html}
{analyses_html}
{notes_html}
<div class="footer">Confidential — ER Case Export — Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
</body></html>"""

    # Convert to PDF
    try:
        from weasyprint import HTML as WeasyHTML
        pdf_bytes = WeasyHTML(string=html).write_pdf()
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF generation not available (WeasyPrint not installed)")

    # Encrypt PDF with password
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password)

        output = BytesIO()
        writer.write(output)
        output.seek(0)
        encrypted_bytes = output.read()
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF encryption not available (pypdf not installed)")

    filename = f"ER-Case-{case_number}.pdf"

    return StreamingResponse(
        BytesIO(encrypted_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===========================================
# Case Notes
# ===========================================

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

@router.post("/{case_id}/documents", response_model=ERDocumentUploadResponse)
async def upload_document(
    case_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("transcript"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a document to a case. Triggers async processing."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    # Validate case exists and belongs to company
    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        if is_admin:
            case = await conn.fetchval(
                "SELECT id FROM er_cases WHERE id = $1 AND (company_id = $2 OR company_id IS NULL)",
                case_id,
                company_id,
            )
        else:
            case = await conn.fetchval(
                "SELECT id FROM er_cases WHERE id = $1 AND company_id = $2",
                case_id,
                company_id,
            )
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

    # Validate document type
    valid_types = ["transcript", "policy", "email", "other"]
    if document_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type. Must be one of: {valid_types}",
        )

    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".csv", ".json"}
    filename = file.filename or "document"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {allowed_extensions}",
        )

    # Read file content
    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
        )

    # Upload to storage
    storage = get_storage()
    file_path = await storage.upload_file(
        file_bytes,
        filename,
        prefix=f"er-documents/{case_id}",
        content_type=file.content_type,
    )

    # Create document record
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO er_case_documents
            (case_id, document_type, filename, file_path, mime_type, file_size, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, case_id, document_type, filename, file_path, mime_type, file_size,
                      pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
            """,
            case_id,
            document_type,
            filename,
            file_path,
            file.content_type,
            file_size,
            str(current_user.id),
        )

        # Log audit
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "document_uploaded",
            "document",
            str(row["id"]),
            {"filename": filename, "document_type": document_type, "file_size": file_size},
            request.client.host if request.client else None,
        )

        # Queue Celery task for processing (with sync fallback)
        task_id = None
        celery_available = False
        try:
            from app.workers.tasks.er_document_processing import process_er_document
            # Check if Celery broker AND workers are available
            from app.workers.celery_app import celery_app
            ping_responses = celery_app.control.ping(timeout=1)
            if not ping_responses:
                raise RuntimeError("No Celery workers responded to ping")
            task = process_er_document.delay(str(row["id"]), str(case_id))
            task_id = task.id
            celery_available = True
            logger.info(f"Queued document {row['id']} for Celery processing, task_id={task_id}")
        except Exception as e:
            logger.warning(f"Celery unavailable ({e}), will process document synchronously")

        # Fallback: process synchronously if Celery not available
        if not celery_available:
            try:
                from app.workers.tasks.er_document_processing import _process_document
                logger.info(f"Starting synchronous processing for document {row['id']}")
                result = await _process_document(str(row["id"]), str(case_id))
                logger.info(f"Document {row['id']} processed successfully: {result}")
                # Refresh document data after processing
                row = await conn.fetchrow(
                    """
                    SELECT id, case_id, document_type, filename, file_path, mime_type, file_size,
                           pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
                    FROM er_case_documents WHERE id = $1
                    """,
                    row["id"],
                )
            except Exception as sync_error:
                logger.error(f"Document {row['id']} processing failed: {sync_error}", exc_info=True)
                error_detail = str(sync_error).strip() or "Document processing failed"
                if len(error_detail) > 1000:
                    error_detail = error_detail[:997] + "..."
                await conn.execute(
                    """UPDATE er_case_documents
                       SET processing_status = 'failed', processing_error = $1
                       WHERE id = $2""",
                    error_detail,
                    row["id"],
                )
                # Refresh document data after failure
                row = await conn.fetchrow(
                    """
                    SELECT id, case_id, document_type, filename, file_path, mime_type, file_size,
                           pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
                    FROM er_case_documents WHERE id = $1
                    """,
                    row["id"],
                )

        document = ERDocumentResponse(
            id=row["id"],
            case_id=row["case_id"],
            document_type=row["document_type"],
            filename=row["filename"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            pii_scrubbed=row["pii_scrubbed"],
            processing_status=row["processing_status"],
            processing_error=row["processing_error"],
            parsed_at=row["parsed_at"],
            uploaded_by=row["uploaded_by"],
            created_at=row["created_at"],
        )

        return ERDocumentUploadResponse(
            document=document,
            task_id=task_id,
            message="Document uploaded and queued for processing",
        )


@router.get("/{case_id}/documents", response_model=list[ERDocumentResponse])
async def list_documents(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all documents in a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        rows = await conn.fetch(
            """
            SELECT id, case_id, document_type, filename, mime_type, file_size,
                   pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
            FROM er_case_documents
            WHERE case_id = $1
            ORDER BY created_at DESC
            """,
            case_id,
        )

        return [
            ERDocumentResponse(
                id=row["id"],
                case_id=row["case_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                pii_scrubbed=row["pii_scrubbed"],
                processing_status=row["processing_status"],
                processing_error=row["processing_error"],
                parsed_at=row["parsed_at"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.get("/{case_id}/documents/{doc_id}", response_model=ERDocumentResponse)
async def get_document(
    case_id: UUID,
    doc_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get document details."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT id, case_id, document_type, filename, mime_type, file_size,
                   pii_scrubbed, processing_status, processing_error, parsed_at, uploaded_by, created_at
            FROM er_case_documents
            WHERE id = $1 AND case_id = $2
            """,
            doc_id,
            case_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        return ERDocumentResponse(
            id=row["id"],
            case_id=row["case_id"],
            document_type=row["document_type"],
            filename=row["filename"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            pii_scrubbed=row["pii_scrubbed"],
            processing_status=row["processing_status"],
            processing_error=row["processing_error"],
            parsed_at=row["parsed_at"],
            uploaded_by=row["uploaded_by"],
            created_at=row["created_at"],
        )


@router.post("/{case_id}/documents/{doc_id}/reprocess", response_model=TaskStatusResponse)
async def reprocess_document(
    case_id: UUID,
    doc_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Manually reprocess a document that is stuck or failed."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        doc = await conn.fetchrow(
            "SELECT id, processing_status FROM er_case_documents WHERE id = $1 AND case_id = $2",
            doc_id,
            case_id,
        )

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc["processing_status"] == "processing":
            raise HTTPException(status_code=400, detail="Document is already being processed")

        # Reset status to pending
        await conn.execute(
            "UPDATE er_case_documents SET processing_status = 'pending', processing_error = NULL WHERE id = $1",
            doc_id,
        )

        # Delete existing chunks (will be regenerated)
        await conn.execute(
            "DELETE FROM er_evidence_chunks WHERE document_id = $1",
            doc_id,
        )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "document_reprocessed",
            "document",
            str(doc_id),
            {},
            request.client.host if request.client else None,
        )

    # Queue for processing
    try:
        from app.workers.tasks.er_document_processing import process_er_document
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = process_er_document.delay(str(doc_id), str(case_id))
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Document queued for reprocessing",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), processing synchronously")
        # Fallback to synchronous processing
        try:
            from app.workers.tasks.er_document_processing import _process_document
            await _process_document(str(doc_id), str(case_id))
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Document reprocessed successfully",
            )
        except Exception as sync_error:
            logger.error(f"Reprocess failed: {sync_error}", exc_info=True)
            error_detail = str(sync_error).strip() or "Document reprocessing failed"
            if len(error_detail) > 1000:
                error_detail = error_detail[:997] + "..."
            async with get_connection() as err_conn:
                await err_conn.execute(
                    """UPDATE er_case_documents
                       SET processing_status = 'failed', processing_error = $1
                       WHERE id = $2""",
                    error_detail,
                    doc_id,
                )
            return TaskStatusResponse(
                task_id=None,
                status="failed",
                message="Reprocessing failed",
            )


@router.post("/{case_id}/documents/reprocess-all")
async def reprocess_all_documents(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reprocess all pending or failed documents in a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        # Find all documents that need processing
        docs = await conn.fetch(
            """
            SELECT id, filename, processing_status
            FROM er_case_documents
            WHERE case_id = $1 AND processing_status IN ('pending', 'failed')
            """,
            case_id,
        )

        if not docs:
            return {
                "status": "no_action",
                "message": "No pending or failed documents to reprocess",
                "processed": 0,
            }

        results = []
        for doc in docs:
            doc_id = doc["id"]
            try:
                # Reset status
                await conn.execute(
                    "UPDATE er_case_documents SET processing_status = 'pending', processing_error = NULL WHERE id = $1",
                    doc_id,
                )
                # Delete existing chunks
                await conn.execute("DELETE FROM er_evidence_chunks WHERE document_id = $1", doc_id)

                # Process synchronously (most reliable)
                from app.workers.tasks.er_document_processing import _process_document
                await _process_document(str(doc_id), str(case_id))
                results.append({"id": str(doc_id), "filename": doc["filename"], "status": "completed"})
            except Exception as e:
                logger.error(f"Failed to reprocess document {doc_id}: {e}", exc_info=True)
                error_detail = str(e).strip() or "Document processing failed"
                if len(error_detail) > 1000:
                    error_detail = error_detail[:997] + "..."
                await conn.execute(
                    "UPDATE er_case_documents SET processing_status = 'failed', processing_error = $1 WHERE id = $2",
                    error_detail,
                    doc_id,
                )
                results.append({"id": str(doc_id), "filename": doc["filename"], "status": "failed"})

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "documents_batch_reprocessed",
            "case",
            str(case_id),
            {"count": len(docs), "results": results},
            request.client.host if request.client else None,
        )

        completed = sum(1 for r in results if r["status"] == "completed")
        return {
            "status": "completed",
            "message": f"Reprocessed {completed}/{len(docs)} documents",
            "processed": completed,
            "total": len(docs),
            "results": results,
        }


@router.delete("/{case_id}/documents/{doc_id}")
async def delete_document(
    case_id: UUID,
    doc_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a document and its chunks."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        doc = await conn.fetchrow(
            "SELECT filename FROM er_case_documents WHERE id = $1 AND case_id = $2",
            doc_id,
            case_id,
        )

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        await conn.execute("DELETE FROM er_case_documents WHERE id = $1", doc_id)

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "document_deleted",
            "document",
            str(doc_id),
            {"filename": doc["filename"]},
            request.client.host if request.client else None,
        )

        return {"status": "deleted", "document_id": str(doc_id)}


# ===========================================
# Analysis
# ===========================================

@router.post("/{case_id}/analysis/timeline", response_model=TaskStatusResponse)
async def generate_timeline(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate timeline analysis. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        # Verify case exists and has documents
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_case_documents WHERE case_id = $1 AND processing_status = 'completed'",
            case_id,
        )

        if not doc_count:
            raise HTTPException(
                status_code=400,
                detail="No processed documents found. Upload and process documents first.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "timeline",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import run_timeline_analysis
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_timeline_analysis.delay(str(case_id))
        celery_available = True
        logger.info(f"Queued timeline analysis for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Timeline analysis queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running timeline analysis synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _run_timeline_analysis
            logger.info(f"Starting synchronous timeline analysis for case {case_id}")
            result = await _run_timeline_analysis(str(case_id))
            logger.info(f"Timeline analysis completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Timeline analysis completed: {result.get('events_found', 0)} events found",
            )
        except Exception as sync_error:
            logger.error(f"Timeline analysis failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Timeline analysis failed: {sync_error}")


@router.get("/{case_id}/analysis/timeline")
async def get_timeline(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached timeline analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'timeline'
            """,
            case_id,
        )

        if not row:
            return {
                "analysis": {
                    "events": [],
                    "gaps_identified": [],
                    "timeline_summary": "",
                },
                "source_documents": [],
                "generated_at": None,
            }

        # Handle case where JSONB might be returned as string
        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/discrepancies", response_model=TaskStatusResponse)
async def generate_discrepancies(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate discrepancy analysis. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        doc_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM er_case_documents
            WHERE case_id = $1
              AND processing_status = 'completed'
              AND document_type != 'policy'
            """,
            case_id,
        )

        if doc_count < 2:
            raise HTTPException(
                status_code=400,
                detail="Upload at least 2 completed non-policy documents for discrepancy analysis.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "discrepancies",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import run_discrepancy_analysis
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_discrepancy_analysis.delay(str(case_id))
        celery_available = True
        logger.info(f"Queued discrepancy analysis for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Discrepancy analysis queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running discrepancy analysis synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _run_discrepancy_analysis
            logger.info(f"Starting synchronous discrepancy analysis for case {case_id}")
            result = await _run_discrepancy_analysis(str(case_id))
            logger.info(f"Discrepancy analysis completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Discrepancy analysis completed: {result.get('discrepancies_found', 0)} discrepancies found",
            )
        except Exception as sync_error:
            logger.error(f"Discrepancy analysis failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Discrepancy analysis failed: {sync_error}")


@router.get("/{case_id}/analysis/discrepancies")
async def get_discrepancies(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached discrepancy analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'discrepancies'
            """,
            case_id,
        )

        if not row:
            return {
                "analysis": {
                    "discrepancies": [],
                    "credibility_notes": [],
                    "summary": "",
                },
                "source_documents": [],
                "generated_at": None,
            }

        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/analysis/policy-check", response_model=TaskStatusResponse)
async def run_policy_check(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Run policy violation check against all company policies. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        # Verify we have evidence documents
        evidence_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM er_case_documents
            WHERE case_id = $1 AND document_type != 'policy' AND processing_status = 'completed'
            """,
            case_id,
        )

        if not evidence_count:
            raise HTTPException(
                status_code=400,
                detail="No evidence documents found.",
            )

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_requested",
            "policy_check",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue analysis task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import run_policy_check as run_policy_check_task
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = run_policy_check_task.delay(str(case_id))
        celery_available = True
        logger.info(f"Queued policy check for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Policy check queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running policy check synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _run_policy_check
            logger.info(f"Starting synchronous policy check for case {case_id}")
            result = await _run_policy_check(str(case_id))
            logger.info(f"Policy check completed for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message=f"Policy check completed: {result.get('violations_found', 0)} violations found",
            )
        except Exception as sync_error:
            logger.error(f"Policy check failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Policy check failed: {sync_error}")


@router.get("/{case_id}/analysis/policy-check")
async def get_policy_check(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached policy check analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = 'policy_check'
            """,
            case_id,
        )

        if not row:
            return {
                "analysis": {
                    "violations": [],
                    "policies_potentially_applicable": [],
                    "summary": "",
                },
                "source_documents": [],
                "generated_at": None,
            }

        analysis = row["analysis_data"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "analysis": analysis,
            "source_documents": source_docs,
            "generated_at": row["generated_at"],
        }


@router.post("/{case_id}/guidance/suggested", response_model=SuggestedGuidanceResponse)
async def generate_suggested_guidance(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate Gemini-backed interactive suggested guidance from current case analyses."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        case_row = await conn.fetchrow(
            """
            SELECT case_number, title, description, status, intake_context, created_at, updated_at
            FROM er_cases
            WHERE id = $1
            """,
            case_id,
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        evidence_rows = await conn.fetch(
            """
            SELECT id, filename
            FROM er_case_documents
            WHERE case_id = $1
              AND processing_status = 'completed'
              AND document_type != 'policy'
            ORDER BY created_at DESC
            """,
            case_id,
        )

        analysis_rows = await conn.fetch(
            """
            SELECT analysis_type, analysis_data
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = ANY($2::text[])
            """,
            case_id,
            ["timeline", "discrepancies", "policy_check"],
        )

        transcript_rows = await conn.fetch(
            """
            SELECT id, filename, scrubbed_text
            FROM er_case_documents
            WHERE case_id = $1 AND processing_status = 'completed' AND document_type = 'transcript'
            ORDER BY created_at DESC
            """,
            case_id,
        )

    analysis_map: dict[str, dict[str, Any]] = {}
    for row in analysis_rows:
        analysis_type = str(row["analysis_type"])
        analysis_map[analysis_type] = _normalize_analysis_payload(row["analysis_data"], {})

    timeline_data = _normalize_analysis_payload(
        analysis_map.get("timeline"),
        {"events": [], "gaps_identified": [], "timeline_summary": ""},
    )
    discrepancies_data = _normalize_analysis_payload(
        analysis_map.get("discrepancies"),
        {"discrepancies": [], "credibility_notes": [], "summary": ""},
    )
    policy_data = _normalize_analysis_payload(
        analysis_map.get("policy_check"),
        {"violations": [], "policies_potentially_applicable": [], "summary": ""},
    )

    intake_context = _normalize_intake_context(case_row["intake_context"]) or {}
    assistance_answers = intake_context.get("answers", {}) if isinstance(intake_context, dict) else {}
    objective = assistance_answers.get("objective") if isinstance(assistance_answers, dict) else None
    immediate_risk = assistance_answers.get("immediate_risk") if isinstance(assistance_answers, dict) else None

    completed_non_policy_docs = [
        {
            "id": str(row["id"]),
            "filename": row["filename"] or f"Document {idx + 1}",
        }
        for idx, row in enumerate(evidence_rows)
    ]
    can_run_discrepancies = len(completed_non_policy_docs) >= 2

    fallback_payload = _build_fallback_guidance_payload(
        timeline_data=timeline_data,
        discrepancies_data=discrepancies_data,
        policy_data=policy_data,
        completed_non_policy_docs=completed_non_policy_docs,
        objective=objective if isinstance(objective, str) else None,
        immediate_risk=immediate_risk if isinstance(immediate_risk, str) else None,
    )

    case_info = {
        "case_number": case_row["case_number"],
        "title": case_row["title"],
        "description": case_row["description"],
        "status": case_row["status"],
        "created_at": case_row["created_at"].isoformat() if case_row["created_at"] else None,
        "updated_at": case_row["updated_at"].isoformat() if case_row["updated_at"] else None,
    }
    analyses_completed = {
        "timeline": "timeline" in analysis_map and bool(
            timeline_data.get("events") or timeline_data.get("timeline_summary")
        ),
        "discrepancies": "discrepancies" in analysis_map and bool(
            discrepancies_data.get("discrepancies") or discrepancies_data.get("summary")
        ),
        "policy_check": "policy_check" in analysis_map and bool(
            policy_data.get("violations") or policy_data.get("summary")
        ),
    }
    evidence_overview = {
        "completed_non_policy_doc_count": len(completed_non_policy_docs),
        "completed_non_policy_doc_names": [doc["filename"] for doc in completed_non_policy_docs[:12]],
        "can_run_discrepancies": can_run_discrepancies,
        "analyses_completed": analyses_completed,
    }
    analysis_results = {
        "timeline": timeline_data,
        "discrepancies": discrepancies_data,
        "policy_check": policy_data,
    }

    # Build transcript excerpts for confidence eval (truncate each to ~2000 chars)
    transcript_parts: list[str] = []
    for tr in transcript_rows:
        text = tr["scrubbed_text"] or ""
        if len(text) > 2000:
            text = text[:1000] + "\n...\n" + text[-1000:]
        transcript_parts.append(f"--- {tr['filename']} ---\n{text}")
    transcript_excerpts = "\n\n".join(transcript_parts) if transcript_parts else ""

    has_policy_violations = bool(policy_data.get("violations"))
    has_analyses = any(analyses_completed.values())
    floor_confidence = _determination_confidence_floor(
        completed_doc_count=len(completed_non_policy_docs),
        transcript_count=len(transcript_rows),
        has_analyses=has_analyses,
        has_policy_violations=has_policy_violations,
    )

    try:
        analyzer = _build_er_analyzer()
        guidance_task = analyzer.generate_suggested_guidance(
            case_info=case_info,
            intake_context=intake_context if isinstance(intake_context, dict) else {},
            evidence_overview=evidence_overview,
            analysis_results=analysis_results,
        )
        confidence_task = analyzer.evaluate_determination_confidence(
            case_info=case_info,
            evidence_overview={"doc_count": len(completed_non_policy_docs), "transcript_count": len(transcript_rows)},
            transcript_excerpts=transcript_excerpts,
            timeline_summary=timeline_data.get("timeline_summary", ""),
            discrepancies_summary=discrepancies_data.get("summary", ""),
            policy_summary=policy_data.get("summary", ""),
        )
        raw_payload, confidence_result = await asyncio.gather(
            guidance_task, confidence_task, return_exceptions=True,
        )

        # Handle guidance result
        if isinstance(raw_payload, BaseException):
            logger.warning("Suggested guidance generation failed for case %s: %s", case_id, raw_payload)
            payload = fallback_payload
        else:
            payload = _normalize_suggested_guidance_payload(
                raw_payload,
                fallback_payload=fallback_payload,
                can_run_discrepancies=can_run_discrepancies,
                model_name=analyzer.model,
            )

        # Handle confidence result
        if isinstance(confidence_result, BaseException):
            logger.warning("Confidence eval failed for case %s: %s", case_id, confidence_result)
            confidence_result = {"confidence": floor_confidence, "signals": [], "summary": ""}

        confidence = confidence_result.get("confidence", floor_confidence)
        if not isinstance(confidence, (int, float)):
            confidence = floor_confidence
        confidence = max(floor_confidence, float(confidence))
        signals = [s for s in confidence_result.get("signals", []) if isinstance(s, dict) and s.get("present")]
        determination_signals = [s["reasoning"] for s in signals if isinstance(s.get("reasoning"), str)]

        payload["determination_suggested"] = confidence >= 0.50
        payload["determination_confidence"] = round(confidence, 2)
        payload["determination_signals"] = determination_signals

        return SuggestedGuidanceResponse(**payload)
    except Exception as exc:
        logger.warning("Suggested guidance generation failed for case %s: %s", case_id, exc)
        fallback_payload["determination_confidence"] = floor_confidence
        return SuggestedGuidanceResponse(**fallback_payload)


# ===========================================
# Evidence Search (RAG)
# ===========================================

@router.post("/{case_id}/search", response_model=EvidenceSearchResponse)
async def search_evidence(
    case_id: UUID,
    search: EvidenceSearchRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Search case evidence using semantic similarity."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    # Verify case belongs to company before searching
    async with get_connection() as verify_conn:
        await _verify_case_company(verify_conn, case_id, company_id, current_user.role == "admin")

    async with get_connection() as conn:
        try:
            total_chunks = await conn.fetchval(
                "SELECT COUNT(*) FROM er_evidence_chunks WHERE case_id = $1",
                case_id,
            )
        except Exception as chunk_count_error:
            logger.warning(
                "Failed to count evidence chunks for case %s: %s",
                case_id,
                chunk_count_error,
            )
            total_chunks = 0
        results: list[dict] = []
        semantic_error: Exception | None = None

        try:
            settings = get_settings()
            from ...core.services.embedding_service import EmbeddingService
            from ...core.services.rag_service import RAGService

            embedding_service = EmbeddingService(
                api_key=settings.gemini_api_key,
                vertex_project=settings.vertex_project,
                vertex_location=settings.vertex_location,
            )
            rag_service = RAGService(embedding_service)
            results = await rag_service.search_evidence(
                case_id=str(case_id),
                query=search.query,
                conn=conn,
                top_k=search.top_k,
            )
        except Exception as exc:
            semantic_error = exc

        # Fallback to keyword matching when semantic search is unavailable or returns no matches.
        if semantic_error is not None or not results:
            if semantic_error is not None:
                logger.warning(
                    "Semantic evidence search failed for case %s; using keyword fallback: %s",
                    case_id,
                    semantic_error,
                )
            else:
                logger.info(
                    "Semantic evidence search returned no matches for case %s; using keyword fallback",
                    case_id,
                )
            like_query = f"%{search.query.strip()}%"
            chunk_rows = []
            try:
                chunk_rows = await conn.fetch(
                    """
                    SELECT
                        ec.id,
                        ec.content,
                        ec.speaker,
                        ec.page_number,
                        ec.line_start,
                        ec.line_end,
                        ec.metadata,
                        ed.filename,
                        ed.document_type
                    FROM er_evidence_chunks ec
                    JOIN er_case_documents ed ON ec.document_id = ed.id
                    WHERE ec.case_id = $1
                      AND ec.content ILIKE $2
                    ORDER BY ec.created_at DESC
                    LIMIT $3
                    """,
                    case_id,
                    like_query,
                    search.top_k,
                )
            except Exception as chunk_query_error:
                logger.warning(
                    "Chunk-level keyword search failed for case %s: %s",
                    case_id,
                    chunk_query_error,
                )

            results = []
            for row in chunk_rows:
                line_range = None
                if row["line_start"] is not None:
                    line_range = f"{row['line_start']}"
                    if row["line_end"] is not None and row["line_end"] != row["line_start"]:
                        line_range += f"-{row['line_end']}"

                results.append(
                    {
                        "chunk_id": str(row["id"]),
                        "content": row["content"],
                        "speaker": row["speaker"],
                        "source_file": row["filename"],
                        "document_type": row["document_type"],
                        "page_number": row["page_number"],
                        "line_range": line_range,
                        "similarity": 0.35,
                        "metadata": row["metadata"] or {"search_mode": "keyword_chunk"},
                    }
                )

            if not results:
                doc_rows = []
                try:
                    doc_rows = await conn.fetch(
                        """
                        SELECT id, filename, document_type, scrubbed_text
                        FROM er_case_documents
                        WHERE case_id = $1
                          AND processing_status = 'completed'
                          AND scrubbed_text ILIKE $2
                        ORDER BY created_at DESC
                        LIMIT $3
                        """,
                        case_id,
                        like_query,
                        search.top_k,
                    )
                except Exception as doc_query_error:
                    logger.warning(
                        "Document-level keyword search failed for case %s: %s",
                        case_id,
                        doc_query_error,
                    )

                query_lower = search.query.strip().lower()
                for row in doc_rows:
                    text = (row["scrubbed_text"] or "").strip()
                    if not text:
                        continue
                    match_idx = text.lower().find(query_lower)
                    if match_idx < 0:
                        continue
                    start = max(0, match_idx - 140)
                    end = min(len(text), match_idx + len(query_lower) + 180)
                    snippet = text[start:end].strip()
                    if start > 0:
                        snippet = f"...{snippet}"
                    if end < len(text):
                        snippet = f"{snippet}..."

                    results.append(
                        {
                            "chunk_id": f"doc-{row['id']}",
                            "content": snippet,
                            "speaker": None,
                            "source_file": row["filename"],
                            "document_type": row["document_type"],
                            "page_number": None,
                            "line_range": None,
                            "similarity": 0.2,
                            "metadata": {"search_mode": "keyword_document_excerpt"},
                        }
                    )

        normalized_results: list[EvidenceSearchResult] = []
        for r in results:
            similarity_raw = r.get("similarity") if isinstance(r, dict) else None
            try:
                similarity = float(similarity_raw) if similarity_raw is not None else 0.0
            except Exception:
                similarity = 0.0

            normalized_results.append(
                EvidenceSearchResult(
                    chunk_id=str(r.get("chunk_id") or ""),
                    content=str(r.get("content") or ""),
                    speaker=r.get("speaker") if isinstance(r.get("speaker"), str) else None,
                    source_file=str(r.get("source_file") or "Unknown source"),
                    document_type=_normalize_document_type(r.get("document_type")),
                    page_number=r.get("page_number") if isinstance(r.get("page_number"), int) else None,
                    line_range=r.get("line_range") if isinstance(r.get("line_range"), str) else None,
                    similarity=similarity,
                    metadata=_normalize_search_metadata(r.get("metadata")),
                )
            )

        return EvidenceSearchResponse(
            results=normalized_results,
            query=search.query,
            total_chunks=total_chunks or 0,
        )


# ===========================================
# Reports
# ===========================================

@router.post("/{case_id}/reports/summary", response_model=TaskStatusResponse)
async def generate_summary_report(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate investigation summary report. Queues async task or runs synchronously."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "report_requested",
            "summary",
            None,
            {},
            request.client.host if request.client else None,
        )

    # Try to queue task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import generate_summary_report as generate_summary_task
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = generate_summary_task.delay(str(case_id), str(current_user.id))
        celery_available = True
        logger.info(f"Queued summary report for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Summary report generation queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), generating summary report synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _generate_summary_report
            logger.info(f"Starting synchronous summary report generation for case {case_id}")
            result = await _generate_summary_report(str(case_id), str(current_user.id))
            logger.info(f"Summary report generated for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Summary report generated successfully",
            )
        except Exception as sync_error:
            logger.error(f"Summary report generation failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail="Summary report generation failed")


@router.post("/{case_id}/reports/determination", response_model=TaskStatusResponse)
async def generate_determination_letter(
    case_id: UUID,
    report_request: ReportGenerateRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate determination letter. Queues async task or runs synchronously."""
    if not report_request.determination:
        raise HTTPException(
            status_code=400,
            detail="Determination is required (substantiated, unsubstantiated, inconclusive)",
        )

    valid_determinations = ["substantiated", "unsubstantiated", "inconclusive"]
    if report_request.determination not in valid_determinations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid determination. Must be one of: {valid_determinations}",
        )

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "report_requested",
            "determination",
            None,
            {"determination": report_request.determination},
            request.client.host if request.client else None,
        )

    # Try to queue task via Celery, fall back to sync
    celery_available = False
    try:
        from app.workers.tasks.er_analysis import generate_determination_letter as generate_determination_task
        from app.workers.celery_app import celery_app
        ping_responses = celery_app.control.ping(timeout=1)
        if not ping_responses:
            raise RuntimeError("No Celery workers responded to ping")
        task = generate_determination_task.delay(
            str(case_id),
            report_request.determination,
            str(current_user.id),
        )
        celery_available = True
        logger.info(f"Queued determination letter for case {case_id}, task_id={task.id}")
        return TaskStatusResponse(
            task_id=task.id,
            status="queued",
            message="Determination letter generation queued",
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), generating determination letter synchronously")

    # Fallback: run synchronously
    if not celery_available:
        try:
            from app.workers.tasks.er_analysis import _generate_determination_letter
            logger.info(f"Starting synchronous determination letter generation for case {case_id}")
            result = await _generate_determination_letter(
                str(case_id),
                report_request.determination,
                str(current_user.id),
            )
            logger.info(f"Determination letter generated for case {case_id}: {result}")
            return TaskStatusResponse(
                task_id=None,
                status="completed",
                message="Determination letter generated successfully",
            )
        except Exception as sync_error:
            logger.error(f"Determination letter generation failed for case {case_id}: {sync_error}", exc_info=True)
            raise HTTPException(status_code=500, detail="Determination letter generation failed")


@router.get("/{case_id}/reports/{report_type}")
async def get_report(
    case_id: UUID,
    report_type: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get generated report."""
    valid_types = ["summary", "determination"]
    if report_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report type. Must be one of: {valid_types}",
        )

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            """
            SELECT analysis_data, source_documents, generated_at
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = $2
            """,
            case_id,
            report_type,
        )

        if not row:
            raise HTTPException(status_code=404, detail=f"{report_type.title()} report not found.")

        analysis_data = row["analysis_data"]
        if isinstance(analysis_data, str):
            analysis_data = json.loads(analysis_data)

        source_docs = row["source_documents"]
        if isinstance(source_docs, str):
            source_docs = json.loads(source_docs)

        return {
            "report_type": report_type,
            "content": analysis_data.get("content", ""),
            "generated_at": row["generated_at"],
            "source_documents": source_docs,
        }


# ===========================================
# Audit Log
# ===========================================

@router.get("/{case_id}/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    case_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get audit log for a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        rows = await conn.fetch(
            """
            SELECT id, case_id, user_id, action, entity_type, entity_id, details, ip_address, created_at
            FROM er_audit_log
            WHERE case_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            case_id,
            limit,
            offset,
        )

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM er_audit_log WHERE case_id = $1",
            case_id,
        )

        entries = [
            AuditLogEntry(
                id=row["id"],
                case_id=row["case_id"],
                user_id=row["user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=row["details"],
                ip_address=row["ip_address"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return AuditLogResponse(entries=entries, total=total or 0)
