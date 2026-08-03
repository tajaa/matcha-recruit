"""Shared helpers, constants, and imports for the ER Copilot routes package.

Split from the flat er_copilot.py into per-concern submodules; these utilities
are imported by crud / documents / export / analysis / guidance / search /
reports / notes / case_views via ``from ._shared import ...``.
"""
import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

_celery_probe: tuple[float, bool] | None = None
_CELERY_PROBE_TTL = 30.0


async def celery_available() -> bool:
    """Thread-wrapped, TTL-cached Celery liveness probe.

    The ping is a blocking broker round-trip; caching it keeps a burst of
    uploads from paying it repeatedly. A negative result is cached too, so a
    worker that just came up is ignored for up to TTL seconds — acceptable
    because every caller falls back to synchronous processing.
    """
    global _celery_probe
    now = time.monotonic()
    if _celery_probe is not None and now - _celery_probe[0] < _CELERY_PROBE_TTL:
        return _celery_probe[1]

    def _ping() -> bool:
        from app.workers.celery_app import celery_app
        return bool(celery_app.control.ping(timeout=1))

    try:
        ok = await asyncio.to_thread(_ping)
    except Exception as exc:
        logger.warning("Celery probe failed: %s", exc)
        ok = False
    _celery_probe = (now, ok)
    return ok


# Strong refs for fire-and-forget tasks — the event loop holds only a weak
# reference, so an unreferenced task can be collected mid-run.
_BG_TASKS: set[asyncio.Task] = set()


# ===========================================
# Helper Functions
# ===========================================

def generate_case_number() -> str:
    """Generate a unique case number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(4).upper()
    return f"ER-{now.year}-{now.month:02d}-{random_suffix}"


def _queue_risk_assessment_refresh(background_tasks: BackgroundTasks, company_id: UUID | None) -> None:
    if not company_id:
        return
    from ..employees import _refresh_risk_assessment

    background_tasks.add_task(_refresh_risk_assessment, company_id)


# Re-export (refactor round 2, stage 3) — the real implementation now lives
# in services/er/er_case_create.py; kept here so crud.py's
# `from ._shared import create_case_core` keeps working unchanged.
from app.matcha.services.er.er_case_create import create_case_core  # noqa: F401,E402


async def log_audit(
    conn,
    case_id: Optional[str],
    user_id: Optional[str],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Log an action to the audit trail."""
    from app.core.services.audit_log import insert_audit_log

    await insert_audit_log(
        conn,
        table="er_audit_log",
        id_column="case_id",
        id_value=case_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
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


# The real implementations now live in services/er/er_case_context.py (a
# services-layer caller — Huume's ER bridge — needs them without importing
# routes/). Re-imported under the old names so every existing call site in
# this package, plus tests/er_copilot/test_document_excerpts.py (which
# imports _build_document_excerpts via the package's __init__.py re-export),
# is unaffected.
from app.matcha.services.er.er_case_context import (  # noqa: F401,E402
    ER_DOC_PER_DOC_CHAR_CAP, ER_DOC_TOTAL_CHAR_CAP,
    build_document_excerpts as _build_document_excerpts,
    normalize_json_list as _normalize_json_list,
    resolve_involved_parties as _resolve_involved_parties,
    load_guidance_context as _load_guidance_context,
    build_er_analyzer as _build_er_analyzer,
)


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

