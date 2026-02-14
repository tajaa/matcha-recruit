"""ADA Accommodation Case Management API Routes.

Accommodation interactive process management:
- Cases CRUD
- Document upload
- AI analysis (suggestions, hardship, job functions)
- Audit log
"""

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Request, BackgroundTasks

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser
from ...config import get_settings
from ...core.services.storage import get_storage
from ..models.accommodation import (
    AccommodationCaseCreate,
    AccommodationCaseUpdate,
    AccommodationCaseResponse,
    AccommodationCaseListResponse,
    AccommodationEmployeeOption,
    AccommodationCaseStatus,
    AccommodationDocumentResponse,
    AccommodationAnalysisResponse,
    AuditLogEntry,
    AuditLogResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
TEXT_EXTRACTABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json"}
MAX_ANALYSIS_DOC_CHARS = 12_000
_schema_ready = False
_schema_lock = asyncio.Lock()


async def _ensure_accommodations_schema(conn) -> None:
    """Best-effort schema guard for environments that missed accommodation migrations."""
    global _schema_ready
    if _schema_ready:
        return

    async with _schema_lock:
        if _schema_ready:
            return

        has_cases_table = await conn.fetchval(
            "SELECT to_regclass('accommodation_cases') IS NOT NULL"
        )
        if not has_cases_table:
            await conn.execute(
                """
                CREATE TABLE accommodation_cases (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    case_number VARCHAR(50) NOT NULL UNIQUE,
                    org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    linked_leave_id UUID,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    disability_category VARCHAR(50),
                    status VARCHAR(50) NOT NULL DEFAULT 'requested',
                    requested_accommodation TEXT,
                    approved_accommodation TEXT,
                    denial_reason TEXT,
                    undue_hardship_analysis TEXT,
                    assigned_to UUID REFERENCES users(id),
                    created_by UUID REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    closed_at TIMESTAMP
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accommodation_cases_status ON accommodation_cases(status)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accommodation_cases_employee ON accommodation_cases(employee_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accommodation_cases_org ON accommodation_cases(org_id)"
            )
        else:
            has_linked_leave_column = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'accommodation_cases'
                      AND column_name = 'linked_leave_id'
                )
                """
            )
            if not has_linked_leave_column:
                await conn.execute(
                    "ALTER TABLE accommodation_cases ADD COLUMN linked_leave_id UUID"
                )

        has_documents_table = await conn.fetchval(
            "SELECT to_regclass('accommodation_documents') IS NOT NULL"
        )
        if not has_documents_table:
            await conn.execute(
                """
                CREATE TABLE accommodation_documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    case_id UUID NOT NULL REFERENCES accommodation_cases(id) ON DELETE CASCADE,
                    document_type VARCHAR(50) NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    mime_type VARCHAR(100),
                    file_size INTEGER,
                    uploaded_by UUID REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accommodation_documents_case ON accommodation_documents(case_id)"
            )

        has_analysis_table = await conn.fetchval(
            "SELECT to_regclass('accommodation_analysis') IS NOT NULL"
        )
        if not has_analysis_table:
            await conn.execute(
                """
                CREATE TABLE accommodation_analysis (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    case_id UUID NOT NULL REFERENCES accommodation_cases(id) ON DELETE CASCADE,
                    analysis_type VARCHAR(50) NOT NULL,
                    analysis_data JSONB NOT NULL,
                    generated_by UUID REFERENCES users(id),
                    generated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(case_id, analysis_type)
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accommodation_analysis_case ON accommodation_analysis(case_id)"
            )

        has_audit_table = await conn.fetchval(
            "SELECT to_regclass('accommodation_audit_log') IS NOT NULL"
        )
        if not has_audit_table:
            await conn.execute(
                """
                CREATE TABLE accommodation_audit_log (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    case_id UUID REFERENCES accommodation_cases(id) ON DELETE SET NULL,
                    user_id UUID REFERENCES users(id),
                    action VARCHAR(100) NOT NULL,
                    entity_type VARCHAR(50),
                    entity_id UUID,
                    details JSONB,
                    ip_address VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accommodation_audit_case ON accommodation_audit_log(case_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accommodation_audit_user ON accommodation_audit_log(user_id)"
            )

        _schema_ready = True


# ===========================================
# Helper Functions
# ===========================================

def generate_case_number() -> str:
    """Generate a unique case number."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    random_suffix = secrets.token_hex(4).upper()
    return f"AC-{timestamp}-{random_suffix}"


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
    """Log an action to the accommodation audit trail."""
    await conn.execute(
        """
        INSERT INTO accommodation_audit_log (case_id, user_id, action, entity_type, entity_id, details, ip_address)
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
    """Verify a case exists and belongs to the company. Raises 404 if not."""
    await _ensure_accommodations_schema(conn)
    if is_admin:
        exists = await conn.fetchval(
            "SELECT 1 FROM accommodation_cases WHERE id = $1 AND (org_id = $2 OR org_id IS NULL)",
            case_id,
            company_id,
        )
    else:
        exists = await conn.fetchval(
            "SELECT 1 FROM accommodation_cases WHERE id = $1 AND org_id = $2",
            case_id,
            company_id,
        )
    if not exists:
        raise HTTPException(status_code=404, detail="Case not found")


def _case_response(row, document_count: int = 0) -> AccommodationCaseResponse:
    """Build an AccommodationCaseResponse from a DB row."""
    return AccommodationCaseResponse(
        id=row["id"],
        case_number=row["case_number"],
        org_id=row["org_id"],
        employee_id=row["employee_id"],
        linked_leave_id=row["linked_leave_id"],
        title=row["title"],
        description=row["description"],
        disability_category=row["disability_category"],
        status=row["status"],
        requested_accommodation=row["requested_accommodation"],
        approved_accommodation=row["approved_accommodation"],
        denial_reason=row["denial_reason"],
        undue_hardship_analysis=row["undue_hardship_analysis"],
        assigned_to=row["assigned_to"],
        created_by=row["created_by"],
        document_count=document_count,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        closed_at=row["closed_at"],
    )


async def _extract_document_text_from_storage(file_path: Optional[str], filename: str) -> str:
    """Extract plain text for text-like files used in analysis prompts."""
    if not file_path:
        return ""

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in TEXT_EXTRACTABLE_EXTENSIONS:
        return ""

    try:
        content = await get_storage().download_file(file_path)
    except Exception:
        logger.warning("Failed to download accommodation document for analysis: %s", filename)
        return ""

    text = content.decode("utf-8", errors="ignore").strip()
    if len(text) > MAX_ANALYSIS_DOC_CHARS:
        text = text[:MAX_ANALYSIS_DOC_CHARS] + "\n...[truncated]..."
    return text


# ===========================================
# Cases CRUD
# ===========================================

CASE_COLUMNS = """
    id, case_number, org_id, employee_id, linked_leave_id, title, description,
    disability_category, status, requested_accommodation, approved_accommodation,
    denial_reason, undue_hardship_analysis, assigned_to, created_by,
    created_at, updated_at, closed_at
"""


@router.post("", response_model=AccommodationCaseResponse)
async def create_case(
    case: AccommodationCaseCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new accommodation case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    case_number = generate_case_number()

    async with get_connection() as conn:
        await _ensure_accommodations_schema(conn)
        # Verify employee belongs to company
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            case.employee_id,
            company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found in your organization")

        if case.linked_leave_id:
            linked_leave = await conn.fetchval(
                """SELECT id FROM leave_requests
                   WHERE id = $1 AND org_id = $2 AND employee_id = $3""",
                case.linked_leave_id,
                company_id,
                case.employee_id,
            )
            if not linked_leave:
                raise HTTPException(
                    status_code=400,
                    detail="linked_leave_id must reference this employee's leave request in your organization",
                )

        row = await conn.fetchrow(
            f"""
            INSERT INTO accommodation_cases
            (case_number, org_id, employee_id, linked_leave_id, title, description,
             disability_category, requested_accommodation, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING {CASE_COLUMNS}
            """,
            case_number,
            company_id,
            case.employee_id,
            case.linked_leave_id,
            case.title,
            case.description,
            case.disability_category,
            case.requested_accommodation,
            str(current_user.id),
        )

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

        from ..services.leave_agent import get_leave_agent

        background_tasks.add_task(get_leave_agent().on_accommodation_request_created, row["id"])
        return _case_response(row, document_count=0)


@router.get("", response_model=AccommodationCaseListResponse)
async def list_cases(
    status: Optional[AccommodationCaseStatus] = None,
    employee_id: Optional[UUID] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List accommodation cases scoped to the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return AccommodationCaseListResponse(cases=[], total=0)

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        await _ensure_accommodations_schema(conn)
        company_filter = "(c.org_id = $1 OR c.org_id IS NULL)" if is_admin else "c.org_id = $1"
        base_query = f"""
            SELECT c.*, COUNT(d.id) as document_count
            FROM accommodation_cases c
            LEFT JOIN accommodation_documents d ON c.id = d.case_id
            WHERE {company_filter}
        """

        params: list = [company_id]
        param_idx = 2

        if status:
            base_query += f" AND c.status = ${param_idx}"
            params.append(status)
            param_idx += 1

        if employee_id:
            base_query += f" AND c.employee_id = ${param_idx}"
            params.append(employee_id)
            param_idx += 1

        query = base_query + " GROUP BY c.id ORDER BY c.updated_at DESC"
        rows = await conn.fetch(query, *params)

        cases = [_case_response(row, document_count=row["document_count"]) for row in rows]
        return AccommodationCaseListResponse(cases=cases, total=len(cases))


@router.get("/employees", response_model=list[AccommodationEmployeeOption])
async def list_employees_for_accommodations(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List company employees for accommodation case creation/edit workflows."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    async with get_connection() as conn:
        await _ensure_accommodations_schema(conn)
        rows = await conn.fetch(
            """
            SELECT id, first_name, last_name, email
            FROM employees
            WHERE org_id = $1
            ORDER BY first_name, last_name, email
            """,
            company_id,
        )
        return [
            AccommodationEmployeeOption(
                id=row["id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                email=row["email"],
            )
            for row in rows
        ]


@router.get("/{case_id}", response_model=AccommodationCaseResponse)
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
        await _ensure_accommodations_schema(conn)
        company_filter = "(c.org_id = $2 OR c.org_id IS NULL)" if is_admin else "c.org_id = $2"
        row = await conn.fetchrow(
            f"""
            SELECT c.*, COUNT(d.id) as document_count
            FROM accommodation_cases c
            LEFT JOIN accommodation_documents d ON c.id = d.case_id
            WHERE c.id = $1 AND {company_filter}
            GROUP BY c.id
            """,
            case_id,
            company_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        return _case_response(row, document_count=row["document_count"])


@router.put("/{case_id}", response_model=AccommodationCaseResponse)
async def update_case(
    case_id: UUID,
    case: AccommodationCaseUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, is_admin)

        updates = []
        params = []
        param_count = 1

        for field_name, col_name in [
            ("title", "title"),
            ("description", "description"),
            ("status", "status"),
            ("disability_category", "disability_category"),
            ("requested_accommodation", "requested_accommodation"),
            ("approved_accommodation", "approved_accommodation"),
            ("denial_reason", "denial_reason"),
        ]:
            value = getattr(case, field_name)
            if value is not None:
                updates.append(f"{col_name} = ${param_count}")
                params.append(value)
                param_count += 1

        if case.status == "closed":
            updates.append("closed_at = NOW()")

        if case.assigned_to is not None:
            updates.append(f"assigned_to = ${param_count}")
            params.append(case.assigned_to)
            param_count += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        updates.append("updated_at = NOW()")
        params.append(case_id)
        param_count += 1
        params.append(company_id)

        company_filter = f"(org_id = ${param_count} OR org_id IS NULL)" if is_admin else f"org_id = ${param_count}"
        query = f"""
            UPDATE accommodation_cases
            SET {', '.join(updates)}
            WHERE id = ${param_count - 1} AND {company_filter}
            RETURNING {CASE_COLUMNS}
        """

        row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM accommodation_documents WHERE case_id = $1",
            case_id,
        )

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

        if case.status is not None:
            from ..services.leave_agent import get_leave_agent

            background_tasks.add_task(
                get_leave_agent().on_accommodation_status_changed,
                case_id,
                case.status,
            )

        return _case_response(row, document_count=doc_count or 0)


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
    company_filter = "(org_id = $2 OR org_id IS NULL)" if is_admin else "org_id = $2"

    async with get_connection() as conn:
        case = await conn.fetchrow(
            f"SELECT case_number, title FROM accommodation_cases WHERE id = $1 AND {company_filter}",
            case_id,
            company_id,
        )

        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        await conn.execute(
            f"DELETE FROM accommodation_cases WHERE id = $1 AND {company_filter}",
            case_id,
            company_id,
        )

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
# Documents
# ===========================================

@router.post("/{case_id}/documents", response_model=AccommodationDocumentResponse)
async def upload_document(
    case_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a document to an accommodation case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    is_admin = current_user.role == "admin"
    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, is_admin)

    valid_types = [
        "medical_certification", "accommodation_request_form",
        "interactive_process_notes", "job_description",
        "hardship_analysis", "approval_letter", "other",
    ]
    if document_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type. Must be one of: {valid_types}",
        )

    allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".csv", ".json", ".png", ".jpg", ".jpeg"}
    filename = file.filename or "document"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {allowed_extensions}",
        )

    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
        )

    storage = get_storage()
    file_path = await storage.upload_file(
        file_bytes,
        filename,
        prefix=f"accommodation-documents/{case_id}",
        content_type=file.content_type,
    )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO accommodation_documents
            (case_id, document_type, filename, file_path, mime_type, file_size, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, case_id, document_type, filename, file_path, mime_type, file_size, uploaded_by, created_at
            """,
            case_id,
            document_type,
            filename,
            file_path,
            file.content_type,
            file_size,
            str(current_user.id),
        )

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

        return AccommodationDocumentResponse(
            id=row["id"],
            case_id=row["case_id"],
            document_type=row["document_type"],
            filename=row["filename"],
            file_path=row["file_path"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            uploaded_by=row["uploaded_by"],
            created_at=row["created_at"],
        )


@router.get("/{case_id}/documents", response_model=list[AccommodationDocumentResponse])
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
            SELECT id, case_id, document_type, filename, file_path, mime_type, file_size, uploaded_by, created_at
            FROM accommodation_documents
            WHERE case_id = $1
            ORDER BY created_at DESC
            """,
            case_id,
        )

        return [
            AccommodationDocumentResponse(
                id=row["id"],
                case_id=row["case_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                file_path=row["file_path"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.delete("/{case_id}/documents/{doc_id}")
async def delete_document(
    case_id: UUID,
    doc_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a document."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        doc = await conn.fetchrow(
            "SELECT filename, file_path FROM accommodation_documents WHERE id = $1 AND case_id = $2",
            doc_id,
            case_id,
        )

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        try:
            await get_storage().delete_file(doc["file_path"])
        except Exception:
            logger.warning("Failed to delete accommodation document from storage: %s", doc_id)

        await conn.execute("DELETE FROM accommodation_documents WHERE id = $1", doc_id)

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
# AI Analysis
# ===========================================

def _get_analyzer():
    """Create an AccommodationAnalyzer instance from settings."""
    from ..services.accommodation_service import AccommodationAnalyzer
    settings = get_settings()
    return AccommodationAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
    )


async def _get_case_info(conn, case_id: UUID) -> dict:
    """Fetch case info as a dict for analysis prompts."""
    row = await conn.fetchrow(
        f"SELECT {CASE_COLUMNS} FROM accommodation_cases WHERE id = $1",
        case_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return dict(row)


async def _get_case_documents_text(conn, case_id: UUID) -> list[dict]:
    """Fetch document metadata and extract text when possible."""
    rows = await conn.fetch(
        "SELECT id, filename, document_type, file_path FROM accommodation_documents WHERE case_id = $1",
        case_id,
    )
    documents = []
    for r in rows:
        text = await _extract_document_text_from_storage(r["file_path"], r["filename"])
        documents.append({
            "filename": r["filename"],
            "document_type": r["document_type"],
            "text": text,
        })
    return documents


async def _upsert_analysis(conn, case_id: UUID, analysis_type: str, data: dict, user_id: str):
    """Insert or update an analysis record."""
    await conn.execute(
        """
        INSERT INTO accommodation_analysis (case_id, analysis_type, analysis_data, generated_by)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (case_id, analysis_type) DO UPDATE
        SET analysis_data = $3, generated_by = $4, generated_at = NOW()
        """,
        case_id,
        analysis_type,
        json.dumps(data),
        user_id,
    )


async def _get_analysis(conn, case_id: UUID, analysis_type: str):
    """Fetch a cached analysis record."""
    return await conn.fetchrow(
        "SELECT analysis_type, analysis_data, generated_by, generated_at FROM accommodation_analysis WHERE case_id = $1 AND analysis_type = $2",
        case_id,
        analysis_type,
    )


# -- Suggestions --

@router.post("/{case_id}/analysis/suggestions", response_model=AccommodationAnalysisResponse)
async def generate_suggestions(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate AI-powered accommodation suggestions."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        case_info = await _get_case_info(conn, case_id)
        documents = await _get_case_documents_text(conn, case_id)

    analyzer = _get_analyzer()
    result = await analyzer.suggest_accommodations(case_info, documents)

    async with get_connection() as conn:
        await _upsert_analysis(conn, case_id, "accommodation_suggestions", result, str(current_user.id))

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_generated",
            "accommodation_suggestions",
            None,
            {},
            request.client.host if request.client else None,
        )

        row = await _get_analysis(conn, case_id, "accommodation_suggestions")

    analysis_data = row["analysis_data"]
    if isinstance(analysis_data, str):
        analysis_data = json.loads(analysis_data)

    return AccommodationAnalysisResponse(
        analysis_type=row["analysis_type"],
        analysis_data=analysis_data,
        generated_by=row["generated_by"],
        generated_at=row["generated_at"],
    )


@router.get("/{case_id}/analysis/suggestions", response_model=AccommodationAnalysisResponse)
async def get_suggestions(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached accommodation suggestions."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await _get_analysis(conn, case_id, "accommodation_suggestions")

    if not row:
        raise HTTPException(status_code=404, detail="Suggestions analysis not found. Generate it first.")

    analysis_data = row["analysis_data"]
    if isinstance(analysis_data, str):
        analysis_data = json.loads(analysis_data)

    return AccommodationAnalysisResponse(
        analysis_type=row["analysis_type"],
        analysis_data=analysis_data,
        generated_by=row["generated_by"],
        generated_at=row["generated_at"],
    )


# -- Hardship --

@router.post("/{case_id}/analysis/hardship", response_model=AccommodationAnalysisResponse)
async def generate_hardship(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate AI-powered undue hardship assessment."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        case_info = await _get_case_info(conn, case_id)
        documents = await _get_case_documents_text(conn, case_id)

    analyzer = _get_analyzer()
    result = await analyzer.assess_undue_hardship(case_info, documents)

    async with get_connection() as conn:
        await _upsert_analysis(conn, case_id, "hardship_assessment", result, str(current_user.id))

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_generated",
            "hardship_assessment",
            None,
            {},
            request.client.host if request.client else None,
        )

        row = await _get_analysis(conn, case_id, "hardship_assessment")

    analysis_data = row["analysis_data"]
    if isinstance(analysis_data, str):
        analysis_data = json.loads(analysis_data)

    return AccommodationAnalysisResponse(
        analysis_type=row["analysis_type"],
        analysis_data=analysis_data,
        generated_by=row["generated_by"],
        generated_at=row["generated_at"],
    )


@router.get("/{case_id}/analysis/hardship", response_model=AccommodationAnalysisResponse)
async def get_hardship(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached hardship assessment."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await _get_analysis(conn, case_id, "hardship_assessment")

    if not row:
        raise HTTPException(status_code=404, detail="Hardship assessment not found. Generate it first.")

    analysis_data = row["analysis_data"]
    if isinstance(analysis_data, str):
        analysis_data = json.loads(analysis_data)

    return AccommodationAnalysisResponse(
        analysis_type=row["analysis_type"],
        analysis_data=analysis_data,
        generated_by=row["generated_by"],
        generated_at=row["generated_at"],
    )


# -- Job Functions --

@router.post("/{case_id}/analysis/job-functions", response_model=AccommodationAnalysisResponse)
async def generate_job_functions(
    case_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate AI-powered job function analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        case_info = await _get_case_info(conn, case_id)

        # Try to find a job description document
        jd_row = await conn.fetchrow(
            """SELECT filename, file_path FROM accommodation_documents
               WHERE case_id = $1 AND document_type = 'job_description'
               LIMIT 1""",
            case_id,
        )
        if jd_row:
            extracted = await _extract_document_text_from_storage(jd_row["file_path"], jd_row["filename"])
            job_description = extracted or f"Job description file: {jd_row['filename']}"
        else:
            job_description = ""

    analyzer = _get_analyzer()
    result = await analyzer.analyze_job_functions(case_info, job_description)

    async with get_connection() as conn:
        await _upsert_analysis(conn, case_id, "job_function_analysis", result, str(current_user.id))

        await log_audit(
            conn,
            str(case_id),
            str(current_user.id),
            "analysis_generated",
            "job_function_analysis",
            None,
            {},
            request.client.host if request.client else None,
        )

        row = await _get_analysis(conn, case_id, "job_function_analysis")

    analysis_data = row["analysis_data"]
    if isinstance(analysis_data, str):
        analysis_data = json.loads(analysis_data)

    return AccommodationAnalysisResponse(
        analysis_type=row["analysis_type"],
        analysis_data=analysis_data,
        generated_by=row["generated_by"],
        generated_at=row["generated_at"],
    )


@router.get("/{case_id}/analysis/job-functions", response_model=AccommodationAnalysisResponse)
async def get_job_functions(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get cached job function analysis."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await _get_analysis(conn, case_id, "job_function_analysis")

    if not row:
        raise HTTPException(status_code=404, detail="Job function analysis not found. Generate it first.")

    analysis_data = row["analysis_data"]
    if isinstance(analysis_data, str):
        analysis_data = json.loads(analysis_data)

    return AccommodationAnalysisResponse(
        analysis_type=row["analysis_type"],
        analysis_data=analysis_data,
        generated_by=row["generated_by"],
        generated_at=row["generated_at"],
    )


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
    """Get audit log for an accommodation case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        rows = await conn.fetch(
            """
            SELECT id, case_id, user_id, action, entity_type, entity_id, details, ip_address, created_at
            FROM accommodation_audit_log
            WHERE case_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            case_id,
            limit,
            offset,
        )

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM accommodation_audit_log WHERE case_id = $1",
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
