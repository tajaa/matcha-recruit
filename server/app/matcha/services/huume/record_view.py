"""Normalized record views for Huume's `show_record` tool.

Two audiences, two builders per record type, kept structurally separate:

- `_model_*` — what the LLM sees (via `show_record_for_model`). Legal records
  (incident, er_case) stay name-free here — no involved_employee_ids,
  witnesses, or reporter identity — same rule as `onboarding_skill`'s
  `incidents`/`er_cases` lookup topics. This is a chat message; it must not
  become the legal record's narrative.
- `_build_*_view` — what the side panel renders (via `get_record_view`), one
  normalized `{title, chips, meta, sections, link}` shape a single generic
  React component (`RecordViewer.tsx`) can render for any type. This runs
  under the admin's own auth (the route re-derives company_id from the JWT,
  same as `/ir/incidents/{id}`) — it's the admin looking at their own
  record, not the model, so names are fine here.

Adding a record type: one `_model_<type>` + one `_build_<type>_view` +  one
`RECORD_REQUIRED_FEATURE` entry + one `SHOW_RECORD_TYPES` entry (tools.py).
No client change — RecordViewer.tsx renders whatever shape comes back.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# record_type -> feature flag gating it, for both the model tool and the
# panel route (route re-checks with the company's own merged features).
RECORD_REQUIRED_FEATURE: dict[str, str] = {
    "incident": "incidents",
    "er_case": "er_copilot",
    "employee": "employees",
    "credential": "credential_templates",
}


def _parse_uuid(value: Any) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _normalize_json_list(raw_value: Any) -> list:
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


# ---------------------------------------------------------------------------
# Model-facing summaries — minimal, name-free for legal records
# ---------------------------------------------------------------------------

async def _model_incident(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT id, incident_number, title, incident_type, severity, status,
               occurred_at, location, LEFT(description, 280) AS description
        FROM ir_incidents
        WHERE id = $1 AND company_id = $2
        """,
        rid, company_id,
    )
    if not row:
        return None
    data = dict(row)
    return {
        "record_id": str(data["id"]),
        "label": f"{data.get('incident_number')} — {data.get('title')}",
        "incident_number": data.get("incident_number"),
        "title": data.get("title"),
        "incident_type": data.get("incident_type"),
        "severity": data.get("severity"),
        "record_status": data.get("status"),
        "occurred_at": _iso(data.get("occurred_at")),
        "location": data.get("location"),
        "description": data.get("description"),
    }


async def _model_er_case(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT id, case_number, title, status, category, outcome, created_at, closed_at,
               LEFT(description, 280) AS description
        FROM er_cases
        WHERE id = $1 AND company_id = $2
        """,
        rid, company_id,
    )
    if not row:
        return None
    data = dict(row)
    return {
        "record_id": str(data["id"]),
        "label": f"{data.get('case_number')} — {data.get('title')}",
        "case_number": data.get("case_number"),
        "title": data.get("title"),
        "record_status": data.get("status"),
        "category": data.get("category"),
        "outcome": data.get("outcome"),
        "created_at": _iso(data.get("created_at")),
        "closed_at": _iso(data.get("closed_at")),
        "description": data.get("description"),
    }


async def _model_employee(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    # Names are fine here — the roster/employee lookup topics already return
    # them; this isn't a legal record.
    row = await conn.fetchrow(
        """
        SELECT id, first_name, last_name, email, job_title, employment_status, start_date, work_state
        FROM employees
        WHERE id = $1 AND org_id = $2
        """,
        rid, company_id,
    )
    if not row:
        return None
    data = dict(row)
    name = f"{data.get('first_name')} {data.get('last_name')}".strip()
    return {
        "record_id": str(data["id"]),
        "label": name,
        "first_name": data.get("first_name"),
        "last_name": data.get("last_name"),
        "email": data.get("email"),
        "job_title": data.get("job_title"),
        "employment_status": data.get("employment_status"),
        "start_date": _iso(data.get("start_date")),
        "work_state": data.get("work_state"),
    }


async def _model_credential(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT ecr.id, ecr.status, ecr.due_date, ecr.verified_at, ecr.waived_at,
               e.first_name, e.last_name, ct.label AS credential_label
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id AND e.org_id = $2
        JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE ecr.id = $1
        """,
        rid, company_id,
    )
    if not row:
        return None
    data = dict(row)
    name = f"{data.get('first_name')} {data.get('last_name')}".strip()
    return {
        "record_id": str(data["id"]),
        "label": f"{data.get('credential_label')} — {name}",
        "credential_label": data.get("credential_label"),
        "employee_name": name,
        "record_status": data.get("status"),
        "due_date": _iso(data.get("due_date")),
        "verified_at": _iso(data.get("verified_at")),
        "waived_at": _iso(data.get("waived_at")),
    }


_MODEL_BUILDERS = {
    "incident": _model_incident,
    "er_case": _model_er_case,
    "employee": _model_employee,
    "credential": _model_credential,
}


async def show_record_for_model(
    *, company_id: UUID, record_type: str, record_id: str, features: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Agent-facing tool wrapper for `show_record`. Never raises — degrades
    to a status the model can relay, same contract as `lookup_context`."""
    builder = _MODEL_BUILDERS.get(record_type)
    if builder is None:
        return {"status": "error", "message": f"Unknown record type '{record_type}'."}
    required = RECORD_REQUIRED_FEATURE[record_type]
    if not (features or {}).get(required):
        return {"status": "refused", "message": f"'{required}' isn't enabled for this company."}
    rid = _parse_uuid(record_id)
    if rid is None:
        return {"status": "not_found", "message": "That doesn't look like a valid record id."}
    from app.database import get_connection
    try:
        async with get_connection() as conn:
            summary = await builder(conn, company_id, rid)
    except Exception:
        logger.exception("huume show_record failed record_type=%s record_id=%s company=%s", record_type, record_id, company_id)
        return {"status": "error", "message": "Could not load that record."}
    if summary is None:
        return {"status": "not_found", "message": "No record with that id was found."}
    return {"status": "ok", "record_type": record_type, **summary}


# ---------------------------------------------------------------------------
# Panel views — full normalized shape, admin's own auth, names allowed
# ---------------------------------------------------------------------------

_SEVERITY_TONE = {"critical": "red", "high": "orange", "medium": "amber", "low": "zinc"}
_INCIDENT_STATUS_TONE = {"action_required": "red", "investigating": "amber", "resolved": "emerald"}
_ER_STATUS_TONE = {"open": "amber", "in_review": "amber", "pending_determination": "orange", "closed": "zinc"}


async def _build_incident_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow("SELECT * FROM ir_incidents WHERE id = $1 AND company_id = $2", rid, company_id)
    if not row:
        return None
    data = dict(row)
    chips = [{"label": (data.get("severity") or "").title(), "tone": _SEVERITY_TONE.get(data.get("severity"), "zinc")}]
    if data.get("status"):
        chips.append({"label": data["status"].replace("_", " ").title(), "tone": _INCIDENT_STATUS_TONE.get(data["status"], "zinc")})

    meta = [
        {"label": "Occurred", "value": _iso(data.get("occurred_at")) or "—"},
        {"label": "Type", "value": (data.get("incident_type") or "—").replace("_", " ").title()},
        {"label": "Location", "value": data.get("location") or "—"},
        {"label": "Reported by", "value": "Anonymous" if data.get("is_anonymous") else (data.get("reported_by_name") or "—")},
    ]

    sections = []
    if data.get("description"):
        sections.append({"label": "Description", "body": data["description"]})

    witnesses = _normalize_json_list(data.get("witnesses"))
    if witnesses:
        items = []
        for w in witnesses:
            if isinstance(w, dict):
                line = w.get("name") or "Witness"
                if w.get("statement"):
                    line = f"{line} — {w['statement']}"
                items.append(line)
            elif isinstance(w, str):
                items.append(w)
        if items:
            sections.append({"label": "Witnesses", "items": items})

    involved_ids = []
    for eid in (data.get("involved_employee_ids") or []):
        parsed = _parse_uuid(eid)
        if parsed:
            involved_ids.append(parsed)
    if involved_ids:
        emp_rows = await conn.fetch(
            "SELECT first_name, last_name FROM employees WHERE id = ANY($1::uuid[]) AND org_id = $2",
            involved_ids, company_id,
        )
        if emp_rows:
            sections.append({"label": "Involved employees", "items": [f"{r['first_name']} {r['last_name']}" for r in emp_rows]})

    if data.get("root_cause"):
        sections.append({"label": "Root cause", "body": data["root_cause"]})
    if data.get("corrective_actions"):
        sections.append({"label": "Corrective actions", "body": data["corrective_actions"]})

    return {
        "record_type": "incident",
        "record_id": str(data["id"]),
        "title": f"{data.get('incident_number')} — {data.get('title')}",
        "subtitle": None,
        "chips": chips,
        "meta": meta,
        "sections": sections,
        "link": f"/app/ir/{data['id']}",
    }


async def _build_er_case_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow("SELECT * FROM er_cases WHERE id = $1 AND company_id = $2", rid, company_id)
    if not row:
        return None
    data = dict(row)
    chips = [{"label": (data.get("status") or "").replace("_", " ").title(), "tone": _ER_STATUS_TONE.get(data.get("status"), "zinc")}]
    if data.get("category"):
        chips.append({"label": data["category"].replace("_", " ").title(), "tone": "zinc"})
    if data.get("outcome"):
        chips.append({"label": data["outcome"].replace("_", " ").title(), "tone": "emerald"})

    meta = [
        {"label": "Case #", "value": data.get("case_number") or "—"},
        {"label": "Opened", "value": _iso(data.get("created_at")) or "—"},
        {"label": "Closed", "value": _iso(data.get("closed_at")) or "—"},
    ]

    sections = []
    if data.get("description"):
        sections.append({"label": "Description", "body": data["description"]})

    involved = _normalize_json_list(data.get("involved_employees"))
    if involved:
        ids = []
        for e in involved:
            if isinstance(e, dict) and e.get("employee_id"):
                parsed = _parse_uuid(e["employee_id"])
                if parsed:
                    ids.append(parsed)
        names_by_id: dict[str, str] = {}
        if ids:
            emp_rows = await conn.fetch(
                "SELECT id, first_name, last_name FROM employees WHERE id = ANY($1::uuid[]) AND org_id = $2",
                ids, company_id,
            )
            names_by_id = {str(r["id"]): f"{r['first_name']} {r['last_name']}" for r in emp_rows}
        items = []
        for e in involved:
            if isinstance(e, dict):
                name = names_by_id.get(str(e.get("employee_id"))) or e.get("name") or "Employee"
                role = e.get("role")
                items.append(f"{name} ({role})" if role else name)
            elif isinstance(e, str):
                items.append(e)
        if items:
            sections.append({"label": "Involved employees", "items": items})

    return {
        "record_type": "er_case",
        "record_id": str(data["id"]),
        "title": f"{data.get('case_number')} — {data.get('title')}",
        "subtitle": None,
        "chips": chips,
        "meta": meta,
        "sections": sections,
        "link": f"/app/er-copilot/{data['id']}",
    }


async def _build_employee_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT e.*, m.first_name || ' ' || m.last_name AS manager_name
        FROM employees e
        LEFT JOIN employees m ON m.id = e.manager_id
        WHERE e.id = $1 AND e.org_id = $2
        """,
        rid, company_id,
    )
    if not row:
        return None
    data = dict(row)
    status = data.get("employment_status") or "unknown"
    chips = [{"label": status.replace("_", " ").title(), "tone": "emerald" if status == "active" else "amber"}]

    location = ", ".join(v for v in (data.get("work_city"), data.get("work_state")) if v) or None
    meta = [
        {"label": "Email", "value": data.get("email") or "—"},
        {"label": "Job title", "value": data.get("job_title") or "—"},
        {"label": "Department", "value": data.get("department") or "—"},
        {"label": "Location", "value": location or "—"},
        {"label": "Start date", "value": _iso(data.get("start_date")) or "—"},
        {"label": "Employment type", "value": data.get("employment_type") or "—"},
        {"label": "Manager", "value": data.get("manager_name") or "—"},
    ]

    return {
        "record_type": "employee",
        "record_id": str(data["id"]),
        "title": f"{data.get('first_name')} {data.get('last_name')}",
        "subtitle": data.get("job_title"),
        "chips": chips,
        "meta": meta,
        "sections": [],
        "link": f"/app/employees/{data['id']}",
    }


async def _build_credential_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT ecr.*, ct.label AS credential_label, ct.category AS credential_category,
               e.first_name, e.last_name
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id AND e.org_id = $2
        JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE ecr.id = $1
        """,
        rid, company_id,
    )
    if not row:
        return None
    data = dict(row)
    status = data.get("status") or "pending"
    tone = "emerald" if status == "verified" else ("zinc" if data.get("waived_at") else "amber")
    chips = [{"label": status.replace("_", " ").title(), "tone": tone}]

    import datetime
    due = data.get("due_date")
    if due and status != "verified" and not data.get("waived_at") and due < datetime.date.today():
        chips.append({"label": "Overdue", "tone": "red"})

    employee_name = f"{data.get('first_name')} {data.get('last_name')}".strip()
    meta = [
        {"label": "Employee", "value": employee_name or "—"},
        {"label": "Category", "value": (data.get("credential_category") or "—").replace("_", " ").title()},
        {"label": "Due", "value": _iso(data.get("due_date")) or "—"},
        {"label": "Verified", "value": _iso(data.get("verified_at")) or "—"},
        {"label": "Waived", "value": _iso(data.get("waived_at")) or "—"},
    ]
    sections = []
    if data.get("waiver_reason"):
        sections.append({"label": "Waiver reason", "body": data["waiver_reason"]})
    if data.get("notes"):
        sections.append({"label": "Notes", "body": data["notes"]})

    return {
        "record_type": "credential",
        "record_id": str(data["id"]),
        "title": f"{data.get('credential_label')} — {employee_name}",
        "subtitle": None,
        "chips": chips,
        "meta": meta,
        "sections": sections,
        "link": f"/app/employees/{data['employee_id']}?tab=credentials",
    }


_VIEW_BUILDERS = {
    "incident": _build_incident_view,
    "er_case": _build_er_case_view,
    "employee": _build_employee_view,
    "credential": _build_credential_view,
}


async def get_record_view(*, company_id: UUID, record_type: str, record_id: str) -> Optional[dict[str, Any]]:
    """Panel-facing fetch — no feature gating here (the route re-checks with
    the caller's own merged features, since it has them already); None on
    unknown type, bad uuid, not found, or wrong tenant."""
    builder = _VIEW_BUILDERS.get(record_type)
    if builder is None:
        return None
    rid = _parse_uuid(record_id)
    if rid is None:
        return None
    from app.database import get_connection
    async with get_connection() as conn:
        return await builder(conn, company_id, rid)
