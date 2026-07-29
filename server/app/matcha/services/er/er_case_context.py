"""ER case context builders — the read-only material fed to Gemini for AI
guidance / outcome analysis / evidence search.

Lifted out of `routes/er_copilot/_shared.py` so a services-layer caller
(Huume's ER bridge, `services/huume/er_skill.py`) can build the same context
without importing from `routes/` — services must not depend on routes (root
CLAUDE.md's Code Modification Rules). `routes/er_copilot/_shared.py` re-
imports these under their old underscore names as thin aliases, so existing
route callers and `tests/er_copilot/test_document_excerpts.py` (which
imports `_build_document_excerpts` through the package's `__init__.py`
re-export) are unaffected — one implementation, not a fork.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional
from uuid import UUID

from app.config import get_settings

# Generous per-doc / total budgets for building document text fed to Gemini.
# Gemini context is ~1M tokens, so 600k chars (~150k tokens) is safe. Linear
# truncation preserves document order; a head+tail slice would silently drop
# middle sections (e.g. the 2nd of 3 interviews concatenated in one PDF).
ER_DOC_PER_DOC_CHAR_CAP = 100_000
ER_DOC_TOTAL_CHAR_CAP = 600_000


def normalize_json_list(raw_value: Any) -> list:
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


def build_document_excerpts(rows, *, text_key: str) -> str:
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


async def resolve_involved_parties(conn, raw_employees: Any, company_id) -> list[dict]:
    """Resolve involved_employees JSONB into name+role dicts for Gemini context.

    Skips malformed entries (non-dict, missing/invalid employee_id) instead of
    raising — legacy rows predate Pydantic validation on this JSONB. Scoped to
    `company_id` (employees.org_id) the same way `er_compliance_grounding.
    _resolve_states` scopes its identical lookup — otherwise an
    `involved_employees` entry carrying another tenant's employee id resolves
    that tenant's real name into this case's UI and Gemini prompt.
    """
    involved = normalize_json_list(raw_employees)
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
        "SELECT id, first_name, last_name FROM employees WHERE id = ANY($1::uuid[]) AND org_id::text = $2::text",
        [p[0] for p in parties],
        str(company_id),
    )
    name_map = {
        str(r["id"]): (f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "Unknown")
        for r in rows
    }
    return [
        {"name": name_map.get(str(emp_id), "Unknown"), "role": role}
        for emp_id, role in parties
    ]


async def load_guidance_context(conn, case_id: UUID, case_row, company_id) -> dict[str, Any]:
    """Single-round-trip context load shared by the suggested-guidance endpoints
    (and, via the Huume ER bridge, `ask_er_copilot`).

    Replaces 3 sequential er_case_documents queries (evidence/transcript/all-text
    views only differ by filter) with one, and replaces an inline per-employee
    N+1 lookup with the batched `resolve_involved_parties`.
    """
    enriched_employees = await resolve_involved_parties(conn, case_row["involved_employees"], company_id)

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


def build_er_analyzer(model_override: Optional[str] = None):
    """Create ERAnalyzer using shared Gemini credential cascade."""
    from .er_analyzer import ERAnalyzer

    settings = get_settings()
    model = "gemini-3.1-pro-preview" if model_override == "pro" else settings.analysis_model
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        raise ValueError("ER analysis requires GEMINI_API_KEY or LIVE_API configuration")
    return ERAnalyzer(api_key=api_key, model=model)
