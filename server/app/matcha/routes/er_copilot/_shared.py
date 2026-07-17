"""Shared helpers, constants, and imports for the ER Copilot routes package.

Split from the flat er_copilot.py into per-concern submodules; these utilities
are imported by crud / documents / export / analysis / guidance / search /
reports / notes / case_views via ``from ._shared import ...``.
"""
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

from ....config import get_settings

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


# ===========================================
# Helper Functions
# ===========================================

def generate_case_number() -> str:
    """Generate a unique case number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"ER-{now.year}-{now.month:02d}-{random_suffix}"


def _queue_risk_assessment_refresh(background_tasks: BackgroundTasks, company_id: UUID | None) -> None:
    if not company_id:
        return
    from ..employees import _refresh_risk_assessment

    background_tasks.add_task(_refresh_risk_assessment, company_id)


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


def _normalize_json_list(raw_value: Any) -> list:
    """Normalize JSONB list payloads (asyncpg may return a string)."""
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []


# Generous per-doc / total budgets for building document text fed to Gemini.
# Gemini context is ~1M tokens, so 600k chars (~150k tokens) is safe. Linear
# truncation preserves document order; the old head+tail slice silently dropped
# middle sections (e.g. the 2nd of 3 interviews concatenated in one PDF).
ER_DOC_PER_DOC_CHAR_CAP = 100_000
ER_DOC_TOTAL_CHAR_CAP = 600_000


def _build_document_excerpts(rows, *, text_key: str) -> str:
    """Concatenate document text for an AI prompt under a generous char budget.

    Uses linear truncation (text[:cap]) so document order is preserved and no
    middle section vanishes. When a cap is hit, a visible marker is appended so
    the model knows content was cut rather than it disappearing silently.
    """
    parts: list[str] = []
    total = 0
    for r in rows:
        text = (r[text_key] or "").strip()
        if not text:
            continue
        doc_type = r["document_type"] or "other"
        remaining = ER_DOC_TOTAL_CHAR_CAP - total
        if remaining <= 0:
            parts.append(
                f"--- {r['filename']} ({doc_type}) ---\n[omitted, prompt size cap reached]"
            )
            continue
        cap = min(ER_DOC_PER_DOC_CHAR_CAP, remaining)
        excerpt = text[:cap]
        if len(text) > cap:
            excerpt += f"\n[truncated after {cap} chars]"
        total += len(excerpt)
        parts.append(f"--- {r['filename']} ({doc_type}) ---\n{excerpt}")
    return "\n\n".join(parts)


async def _collect_raw_evidence_context(conn, case_id: UUID) -> str:
    """Pull uploaded document text + investigation notes + intake guidance
    rationale so the outcome analyzer has the raw source material even when
    prior analysis phases (timeline / discrepancies / policy_check) haven't
    been run.

    Without this, a case with 5 completed documents and detailed guidance
    notes shows up to the LLM as "no evidence" because the analysis
    summaries are empty. The LLM then refuses to recommend action.
    """
    parts: list[str] = []

    # Uploaded evidence documents (PII-scrubbed if available, else original)
    doc_rows = await conn.fetch(
        """
        SELECT filename, document_type,
               COALESCE(scrubbed_text, original_text) AS text
        FROM er_case_documents
        WHERE case_id = $1
          AND processing_status = 'completed'
          AND COALESCE(scrubbed_text, original_text) IS NOT NULL
        ORDER BY created_at
        """,
        case_id,
    )
    if doc_rows:
        parts.append("UPLOADED EVIDENCE DOCUMENTS (raw extracted text):")
        parts.append(_build_document_excerpts(doc_rows, text_key="text"))

    # Investigation guidance notes (auto_guidance + user-authored) — these
    # often contain the narrative of what happened when the description
    # field is empty.
    note_rows = await conn.fetch(
        """
        SELECT note_type, content
        FROM er_case_notes
        WHERE case_id = $1 AND content IS NOT NULL
        ORDER BY created_at
        LIMIT 20
        """,
        case_id,
    )
    if note_rows:
        parts.append("\nINVESTIGATION / GUIDANCE NOTES:")
        for n in note_rows:
            text = (n["content"] or "").strip()
            if not text:
                continue
            parts.append(f"- [{n['note_type']}] {text[:1500]}")

    return "\n".join(parts)


async def _fetch_company_policy_context(conn, company_id: UUID) -> str:
    """Fetch active policies + handbook sections as fallback policy context for outcome analysis."""
    parts: list[str] = []

    policies = await conn.fetch(
        "SELECT title, LEFT(content, 1000) as content FROM policies WHERE company_id = $1 AND status = 'active' LIMIT 15",
        company_id,
    )
    if policies:
        parts.append("COMPANY POLICIES:")
        for p in policies:
            title = p["title"] or "Untitled"
            content = (p["content"] or "").strip()
            parts.append(f"- {title}: {content[:500]}" if content else f"- {title}")

    handbook = await conn.fetchrow(
        "SELECT id, title, active_version FROM handbooks WHERE company_id = $1 AND status = 'active' ORDER BY published_at DESC NULLS LAST LIMIT 1",
        company_id,
    )
    if handbook:
        version_id = await conn.fetchval(
            "SELECT id FROM handbook_versions WHERE handbook_id = $1 AND version_number = $2",
            handbook["id"], handbook["active_version"],
        )
        if version_id is None:
            version_id = await conn.fetchval(
                "SELECT id FROM handbook_versions WHERE handbook_id = $1 ORDER BY version_number DESC LIMIT 1",
                handbook["id"],
            )
        if version_id:
            sections = await conn.fetch(
                "SELECT title, LEFT(content, 800) as content FROM handbook_sections WHERE handbook_version_id = $1 AND content IS NOT NULL ORDER BY section_order LIMIT 20",
                version_id,
            )
            if sections:
                hb_title = handbook["title"] or "Employee Handbook"
                parts.append(f"\nHANDBOOK ({hb_title}):")
                for s in sections:
                    title = s["title"] or "Section"
                    content = (s["content"] or "").strip()
                    parts.append(f"- {title}: {content[:400]}" if content else f"- {title}")

    return "\n".join(parts) if parts else ""


async def _resolve_involved_parties(conn, raw_employees: Any) -> list[dict]:
    """Resolve involved_employees JSONB into name+role dicts for Gemini context.

    Skips malformed entries (non-dict, missing/invalid employee_id) instead of
    raising — legacy rows predate Pydantic validation on this JSONB.
    """
    involved = _normalize_json_list(raw_employees)
    if not involved:
        return []
    parties: list[tuple[UUID, str]] = []
    for e in involved:
        if not isinstance(e, dict) or not e.get("employee_id"):
            continue
        try:
            emp_id = UUID(str(e["employee_id"]))
        except (ValueError, TypeError):
            continue
        parties.append((emp_id, e.get("role", "unknown")))
    if not parties:
        return []
    rows = await conn.fetch(
        "SELECT id, first_name, last_name FROM employees WHERE id = ANY($1::uuid[])",
        [p[0] for p in parties],
    )
    name_map = {
        str(r["id"]): (f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "Unknown")
        for r in rows
    }
    return [
        {"name": name_map.get(str(emp_id), "Unknown"), "role": role}
        for emp_id, role in parties
    ]


def _involved_employee_ids(raw_employees: Any) -> list[str]:
    """Validated employee ids from the involved_employees JSONB, for jurisdiction
    grounding. Kept separate from _resolve_involved_parties (which returns only
    name+role) so employee UUIDs never leak into the prompt-facing party dicts."""
    out: list[str] = []
    for e in _normalize_json_list(raw_employees):
        if isinstance(e, dict) and e.get("employee_id"):
            try:
                out.append(str(UUID(str(e["employee_id"]))))
            except (ValueError, TypeError):
                continue
    return out


async def _load_guidance_context(conn, case_id: UUID, case_row) -> dict[str, Any]:
    """Single-round-trip context load shared by the suggested-guidance endpoints.

    Replaces 3 sequential er_case_documents queries (evidence/transcript/all-text
    views only differ by filter) with one, and replaces an inline per-employee
    N+1 lookup with the batched _resolve_involved_parties.
    """
    enriched_employees = await _resolve_involved_parties(conn, case_row["involved_employees"])

    doc_rows = await conn.fetch(
        """
        SELECT id, filename, document_type, scrubbed_text
        FROM er_case_documents
        WHERE case_id = $1 AND processing_status = 'completed'
        ORDER BY created_at DESC
        """,
        case_id,
    )
    evidence_rows = [r for r in doc_rows if r["document_type"] != "policy"]
    transcript_rows = [r for r in doc_rows if r["document_type"] == "transcript"]
    all_doc_text_rows = [
        r for r in doc_rows
        if r["scrubbed_text"] is not None and r["scrubbed_text"] != ""
    ]

    linked_incident = await conn.fetchrow(
        "SELECT witnesses FROM ir_incidents WHERE er_case_id = $1 LIMIT 1",
        case_id,
    )
    completed_investigation_transcript_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM ir_investigation_interviews
        WHERE er_case_id = $1 AND status IN ('completed', 'analyzed')
        """,
        case_id,
    ) or 0

    return {
        "enriched_employees": enriched_employees,
        "evidence_rows": evidence_rows,
        "transcript_rows": transcript_rows,
        "all_doc_text_rows": all_doc_text_rows,
        "linked_incident": linked_incident,
        "completed_investigation_transcript_count": completed_investigation_transcript_count,
    }


def _build_er_analyzer(model_override: Optional[str] = None):
    """Create ERAnalyzer using shared Gemini credential cascade."""
    from ...services.er_analyzer import ERAnalyzer

    settings = get_settings()
    model = "gemini-3.1-pro-preview" if model_override == "pro" else settings.analysis_model
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        raise ValueError("ER analysis requires GEMINI_API_KEY or LIVE_API configuration")
    return ERAnalyzer(api_key=api_key, model=model)

