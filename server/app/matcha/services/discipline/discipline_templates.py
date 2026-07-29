"""Company letter templates for disciplinary actions.

Resolution is deterministic, never model-chosen: exact
(infraction_type, discipline_type) match, then infraction_type-only, then the
company default, then None (draft from scratch). Rendering is server-side over
a CLOSED placeholder vocabulary — unknown placeholders survive verbatim in the
rendered text, because a silently emptied clause in a legal document is worse
than a visible `{{token}}`.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from uuid import UUID

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

DISCIPLINE_TEMPLATE_PLACEHOLDERS: frozenset[str] = frozenset({
    "employee_name", "employee_title", "manager_name", "company_name", "issued_date",
    "infraction_type", "discipline_type", "occurrence_dates", "incident_number",
    "policy_citations", "description", "expected_improvement", "review_date",
})


# ── Resolution (pure) ────────────────────────────────────────────────────

def resolve_template(
    templates: list[dict[str, Any]], *, infraction_type: str, discipline_type: Optional[str],
) -> Optional[dict[str, Any]]:
    """Pick the best-matching active template for this infraction/level.

    Priority: exact (infraction_type, discipline_type) match > infraction_type-only
    match (template.discipline_type is NULL) > the company default (is_default=True)
    > None. Ties within a tier broken by the most recently updated. Caller is
    expected to have already filtered `templates` to active rows for the company.
    """
    candidates = [t for t in templates if t.get("is_active", True)]
    if not candidates:
        return None

    def _sort_key(t: dict[str, Any]) -> tuple[int, Any]:
        # (has_timestamp, timestamp) — rows with no timestamp at all sort last
        # rather than seeding a `datetime > str` TypeError into max().
        stamp = t.get("updated_at") or t.get("created_at")
        return (1, stamp) if stamp is not None else (0, None)

    def _newest(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not rows:
            return None
        stamped = [t for t in rows if _sort_key(t)[0]]
        return max(stamped, key=_sort_key) if stamped else rows[0]

    exact = [
        t for t in candidates
        if t.get("infraction_type") == infraction_type
        and discipline_type is not None
        and t.get("discipline_type") == discipline_type
    ]
    if exact:
        return _newest(exact)

    infraction_only = [
        t for t in candidates
        if t.get("infraction_type") == infraction_type and not t.get("discipline_type")
    ]
    if infraction_only:
        return _newest(infraction_only)

    defaults = [t for t in candidates if t.get("is_default")]
    if defaults:
        return _newest(defaults)

    return None


def render_template(body: str, values: dict[str, Optional[str]]) -> tuple[str, list[str]]:
    """Render `body` over `values`. Pure.

    Returns (rendered, missing_fields). A KNOWN placeholder (member of
    DISCIPLINE_TEMPLATE_PLACEHOLDERS) whose value is None/empty renders as ''
    AND is reported in missing_fields, so a caller can surface "no manager on
    file" instead of silently shipping a blank clause. An UNKNOWN placeholder
    (a typo, or a token the vocabulary doesn't define) is left verbatim as
    `{{token}}` — never blanked, never reported as missing.
    """
    missing: list[str] = []

    def _sub(match: "re.Match[str]") -> str:
        token = match.group(1)
        if token not in DISCIPLINE_TEMPLATE_PLACEHOLDERS:
            return match.group(0)
        value = values.get(token)
        if value is None or value == "":
            if token not in missing:      # a token repeated in the body is ONE missing field
                missing.append(token)
            return ""
        return str(value)

    rendered = _PLACEHOLDER_RE.sub(_sub, body)
    return rendered, missing


# ── CRUD ─────────────────────────────────────────────────────────────────

async def list_templates(
    conn, company_id: UUID, *, include_inactive: bool = False,
) -> list[dict[str, Any]]:
    if include_inactive:
        rows = await conn.fetch(
            """
            SELECT id, company_id, name, infraction_type, discipline_type, body,
                   is_default, is_active, created_by, created_at, updated_at
            FROM company_discipline_templates
            WHERE company_id = $1
            ORDER BY is_default DESC, name ASC
            """,
            company_id,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, company_id, name, infraction_type, discipline_type, body,
                   is_default, is_active, created_by, created_at, updated_at
            FROM company_discipline_templates
            WHERE company_id = $1 AND is_active = TRUE
            ORDER BY is_default DESC, name ASC
            """,
            company_id,
        )
    return [dict(r) for r in rows]


async def upsert_template(
    conn, company_id: UUID, *,
    template_id: Optional[UUID],
    name: str,
    infraction_type: Optional[str],
    discipline_type: Optional[str],
    body: str,
    is_default: bool,
    is_active: bool,
    created_by: Optional[UUID],
) -> dict[str, Any]:
    """Insert or update a template. When `is_default=True`, the previous
    default is cleared FIRST in the same transaction as the caller's — the
    partial unique index (company_id) WHERE is_default AND is_active rejects
    a second concurrent default otherwise.
    """
    if is_default:
        await conn.execute(
            """
            UPDATE company_discipline_templates
            SET is_default = FALSE, updated_at = NOW()
            WHERE company_id = $1 AND is_default = TRUE AND id != COALESCE($2, '00000000-0000-0000-0000-000000000000'::uuid)
            """,
            company_id, template_id,
        )

    if template_id is not None:
        row = await conn.fetchrow(
            """
            UPDATE company_discipline_templates
            SET name = $3, infraction_type = $4, discipline_type = $5, body = $6,
                is_default = $7, is_active = $8, updated_at = NOW()
            WHERE id = $1 AND company_id = $2
            RETURNING id, company_id, name, infraction_type, discipline_type, body,
                      is_default, is_active, created_by, created_at, updated_at
            """,
            template_id, company_id, name, infraction_type, discipline_type, body,
            is_default, is_active,
        )
        if row is None:
            raise ValueError("Template not found")
        return dict(row)

    row = await conn.fetchrow(
        """
        INSERT INTO company_discipline_templates
          (company_id, name, infraction_type, discipline_type, body,
           is_default, is_active, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, company_id, name, infraction_type, discipline_type, body,
                  is_default, is_active, created_by, created_at, updated_at
        """,
        company_id, name, infraction_type, discipline_type, body,
        is_default, is_active, created_by,
    )
    return dict(row)


async def deactivate_template(conn, company_id: UUID, template_id: UUID) -> bool:
    """Soft delete. Returns False if the template doesn't belong to this
    company (caller 404s)."""
    row = await conn.fetchrow(
        """
        UPDATE company_discipline_templates
        SET is_active = FALSE, is_default = FALSE, updated_at = NOW()
        WHERE id = $1 AND company_id = $2
        RETURNING id
        """,
        template_id, company_id,
    )
    return row is not None


# ── Placeholder values ──────────────────────────────────────────────────

async def build_placeholder_values(
    conn, *,
    company_id: UUID,
    employee: dict[str, Any],
    record_fields: dict[str, Any],
    incident: Optional[dict[str, Any]],
    policy_citations: list[str],
) -> dict[str, Optional[str]]:
    """Assemble the value map for `render_template`.

    `employee` must carry at least id/first_name/last_name/job_title/manager_id
    (the shape `_load_employee` in routes/employee_lifecycle/discipline.py
    already selects). `record_fields` carries the discipline fields being
    drafted: infraction_type, discipline_type, occurrence_dates, description,
    expected_improvement, review_date, issued_date.
    """
    manager_name: Optional[str] = None
    manager_id = employee.get("manager_id")
    if manager_id:
        mgr = await conn.fetchrow(
            "SELECT first_name, last_name FROM employees WHERE id = $1 AND org_id = $2",
            manager_id, company_id,
        )
        if mgr:
            manager_name = " ".join(
                p for p in (mgr["first_name"], mgr["last_name"]) if p
            ).strip() or None

    company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)

    employee_name = " ".join(
        p for p in (employee.get("first_name"), employee.get("last_name")) if p
    ).strip() or employee.get("name")

    occurrence_dates = record_fields.get("occurrence_dates") or []
    occurrence_dates_str = ", ".join(str(d) for d in occurrence_dates) if occurrence_dates else None

    return {
        "employee_name": employee_name,
        "employee_title": employee.get("job_title"),
        "manager_name": manager_name,
        "company_name": company["name"] if company else None,
        "issued_date": str(record_fields.get("issued_date")) if record_fields.get("issued_date") else None,
        "infraction_type": record_fields.get("infraction_type"),
        "discipline_type": record_fields.get("discipline_type"),
        "occurrence_dates": occurrence_dates_str,
        "incident_number": incident.get("incident_number") if incident else None,
        "policy_citations": "; ".join(policy_citations) if policy_citations else None,
        "description": record_fields.get("description"),
        "expected_improvement": record_fields.get("expected_improvement"),
        "review_date": str(record_fields.get("review_date")) if record_fields.get("review_date") else None,
    }
