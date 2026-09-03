"""Normalized record views for Huume's `show_record` tool.

Two audiences, two builders per record type, kept structurally separate:

- `_model_*` — what the LLM sees (via `show_records_for_model`). Legal records
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
    "discipline": "discipline",
    "ems_event": "ems",
    "inventory_item": "inventory",
}


async def _work_base_path(conn, company_id: UUID) -> str:
    """/werk-lite for werk-lite tenants, /work otherwise — same merge
    urgent_notify.py uses, so panel links land in the shell the admin
    actually has."""
    from app.core.feature_flags import merge_company_features

    row = await conn.fetchrow(
        "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id,
    )
    merged = merge_company_features(
        row["enabled_features"] if row else {}, row["signup_source"] if row else None,
    )
    return "/werk-lite" if merged.get("werk_lite") else "/work"

# Working-set cap on the side panel — also the per-call cap on show_record,
# so a single wildly over-broad request can't blow past it either.
MAX_OPEN_RECORDS = 8


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


def merge_open_records(current: list, new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure. Appends `new` entries onto the `current_state.huume_records`
    working set, deduped on `(record_type, record_id)` — a re-show of an
    already-open record MOVES it to the end (so it wins focus) rather than
    duplicating the tab. Caps at `MAX_OPEN_RECORDS`, dropping from the front
    (oldest first) so the most recently shown records always survive."""
    if not isinstance(current, list):
        current = []
    by_key = {(r.get("record_type"), r.get("record_id")): r for r in current if isinstance(r, dict)}
    order = [(r.get("record_type"), r.get("record_id")) for r in current if isinstance(r, dict)]

    for entry in new:
        key = (entry.get("record_type"), entry.get("record_id"))
        if key in by_key:
            order.remove(key)
        by_key[key] = entry
        order.append(key)

    order = order[-MAX_OPEN_RECORDS:]
    return [by_key[k] for k in order]


def remove_open_record(current: list, *, record_type: str, record_id: str) -> list[dict[str, Any]]:
    """Pure. Inverse of `merge_open_records` — drops one entry from the
    `current_state.huume_records` working set (the panel tab's `×`), keyed
    the same way (`record_type`, `record_id`)."""
    if not isinstance(current, list):
        return []
    return [r for r in current if not (isinstance(r, dict) and r.get("record_type") == record_type and r.get("record_id") == record_id)]


# ---------------------------------------------------------------------------
# Model-facing summaries — minimal, name-free for legal records
# ---------------------------------------------------------------------------

async def _model_incidents_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    # No `description` — free-text narrative is exactly where a legal record
    # names people ("Maria slipped near bay 3"); the structural no-names rule
    # only holds if the narrative field is excluded too, not just the id
    # columns. Same reasoning as `onboarding_skill`'s incidents/er_cases topics.
    if not rids:
        return {}
    rows = await conn.fetch(
        """
        SELECT id, incident_number, title, incident_type, severity, status,
               occurred_at, location
        FROM ir_incidents
        WHERE id = ANY($1::uuid[]) AND company_id = $2
        """,
        rids, company_id,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        out[data["id"]] = {
            "record_id": str(data["id"]),
            "label": f"{data.get('incident_number')} — {data.get('title')}",
            "incident_number": data.get("incident_number"),
            "title": data.get("title"),
            "incident_type": data.get("incident_type"),
            "severity": data.get("severity"),
            "record_status": data.get("status"),
            "occurred_at": _iso(data.get("occurred_at")),
            "location": data.get("location"),
        }
    return out


async def _model_er_cases_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    # No `description` — same narrative-exclusion rule as the incident batch.
    if not rids:
        return {}
    rows = await conn.fetch(
        """
        SELECT id, case_number, title, status, category, outcome, created_at, closed_at
        FROM er_cases
        WHERE id = ANY($1::uuid[]) AND company_id = $2
        """,
        rids, company_id,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        out[data["id"]] = {
            "record_id": str(data["id"]),
            "label": f"{data.get('case_number')} — {data.get('title')}",
            "case_number": data.get("case_number"),
            "title": data.get("title"),
            "record_status": data.get("status"),
            "category": data.get("category"),
            "outcome": data.get("outcome"),
            "created_at": _iso(data.get("created_at")),
            "closed_at": _iso(data.get("closed_at")),
        }
    return out


async def _model_employees_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    # Names are fine here — the roster/employee lookup topics already return
    # them; this isn't a legal record.
    if not rids:
        return {}
    rows = await conn.fetch(
        """
        SELECT id, first_name, last_name, email, job_title, employment_status, start_date, work_state
        FROM employees
        WHERE id = ANY($1::uuid[]) AND org_id = $2
        """,
        rids, company_id,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        name = f"{data.get('first_name')} {data.get('last_name')}".strip()
        out[data["id"]] = {
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
    return out


async def _model_credentials_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    if not rids:
        return {}
    rows = await conn.fetch(
        """
        SELECT ecr.id, ecr.status, ecr.due_date, ecr.verified_at, ecr.waived_at,
               e.first_name, e.last_name, ct.label AS credential_label
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id AND e.org_id = $2
        JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
        WHERE ecr.id = ANY($1::uuid[])
        """,
        rids, company_id,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        name = f"{data.get('first_name')} {data.get('last_name')}".strip()
        out[data["id"]] = {
            "record_id": str(data["id"]),
            "label": f"{data.get('credential_label')} — {name}",
            "credential_label": data.get("credential_label"),
            "employee_name": name,
            "record_status": data.get("status"),
            "due_date": _iso(data.get("due_date")),
            "verified_at": _iso(data.get("verified_at")),
            "waived_at": _iso(data.get("waived_at")),
        }
    return out


async def _model_disciplines_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    # No `description`/`expected_improvement`/`denial_reason` — same
    # narrative-exclusion rule as the incident/er_case batches: a discipline
    # record's free-text fields are exactly where a legal record names
    # people and what they did. No employee name either.
    if not rids:
        return {}
    rows = await conn.fetch(
        """
        SELECT id, discipline_type, infraction_type, severity, status,
               approval_status, issued_date, review_date
        FROM progressive_discipline
        WHERE id = ANY($1::uuid[]) AND company_id = $2
        """,
        rids, company_id,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        level = (data.get("discipline_type") or "").replace("_", " ").title()
        out[data["id"]] = {
            "record_id": str(data["id"]),
            "label": f"{level} — {data.get('infraction_type')}",
            "discipline_type": data.get("discipline_type"),
            "infraction_type": data.get("infraction_type"),
            "severity": data.get("severity"),
            "record_status": data.get("status"),
            "approval_status": data.get("approval_status"),
            "issued_date": _iso(data.get("issued_date")),
            "review_date": _iso(data.get("review_date")),
        }
    return out


async def _model_ems_events_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    # Unlike every other batch builder above, this INCLUDES a truncated
    # narrative + doc. An EMS event is pre-promotion documentation the
    # reporter typed openly in a channel — not yet a legal record. The
    # strict no-narrative rule attaches the moment it IS promoted: it
    # becomes an ir_incidents row and _model_incidents_batch (which excludes
    # description) is what the model sees from then on. Deliberate product
    # call, 2026-07-31.
    if not rids:
        return {}
    rows = await conn.fetch(
        """
        SELECT id, title, category, severity_hint, status, incident_recommendation,
               suggested_incident_type, suggested_severity, urgency, protocol_qualifies,
               narrative, doc, created_at
        FROM ems_events
        WHERE id = ANY($1::uuid[]) AND company_id = $2
        """,
        rids, company_id,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        narrative = data.get("narrative") or ""
        doc = data.get("doc")
        if isinstance(doc, str):
            doc = json.loads(doc) if doc else {}
        out[data["id"]] = {
            "record_id": str(data["id"]),
            "label": data.get("title") or narrative[:60] or "Event",
            "category": data.get("category"),
            "record_status": data.get("status"),
            "severity_hint": data.get("severity_hint"),
            "incident_recommendation": bool(data.get("incident_recommendation")),
            "suggested_incident_type": data.get("suggested_incident_type"),
            "suggested_severity": data.get("suggested_severity"),
            # OSHA-reportable/severe — name-free, same as everything else here.
            "urgency": data.get("urgency"),
            "protocol_qualifies": data.get("protocol_qualifies"),
            "narrative": narrative[:500],
            "doc": doc or {},
            "created_at": _iso(data.get("created_at")),
        }
    return out


async def _model_inventory_items_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    if not rids:
        return {}
    rows = await conn.fetch(
        """
        SELECT it.id, it.name, it.current_quantity, it.unit, bl.name AS location_name,
               o.id AS order_id, o.status AS order_status
        FROM inventory_items it
        LEFT JOIN business_locations bl ON bl.id = it.location_id
        LEFT JOIN LATERAL (
            SELECT id, status FROM inventory_orders
            WHERE item_id = it.id AND status IN ('queued', 'ordered')
            ORDER BY created_at DESC, id DESC LIMIT 1
        ) o ON TRUE
        WHERE it.id = ANY($1::uuid[]) AND it.company_id = $2
        """,
        rids, company_id,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        out[data["id"]] = {
            "record_id": str(data["id"]),
            "label": data.get("name"),
            "current_quantity": float(data["current_quantity"]) if data.get("current_quantity") is not None else None,
            "unit": data.get("unit"),
            "location": data.get("location_name"),
            "order_id": str(data["order_id"]) if data.get("order_id") else None,
            "record_status": data.get("order_status") or "no open order",
        }
    return out


_MODEL_BATCH_BUILDERS = {
    "incident": _model_incidents_batch,
    "er_case": _model_er_cases_batch,
    "employee": _model_employees_batch,
    "credential": _model_credentials_batch,
    "discipline": _model_disciplines_batch,
    "ems_event": _model_ems_events_batch,
    "inventory_item": _model_inventory_items_batch,
}
# Kept for the record-type-parity test (SHOW_RECORD_TYPES == _MODEL_BUILDERS
# == ... == _VIEW_BUILDERS) — same key set as _MODEL_BATCH_BUILDERS.
_MODEL_BUILDERS = _MODEL_BATCH_BUILDERS


async def show_records_for_model(
    *, company_id: UUID, record_type: str, record_ids: list[str], features: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Agent-facing tool wrapper for `show_record`. Never raises — degrades
    to a status the model can relay, same contract as `lookup_context`.
    Resolves every id it can; a partial hit (some ids found, some not) is
    still `status: "ok"` with `not_found` listing what didn't resolve — only
    a request where NOTHING resolves is `not_found` as the top-level status."""
    batch_builder = _MODEL_BATCH_BUILDERS.get(record_type)
    if batch_builder is None:
        return {"status": "error", "message": f"Unknown record type '{record_type}'."}
    required = RECORD_REQUIRED_FEATURE[record_type]
    if not (features or {}).get(required):
        return {"status": "refused", "message": f"'{required}' isn't enabled for this company."}
    if not record_ids:
        return {"status": "error", "message": "No record ids were given."}

    note = None
    if len(record_ids) > MAX_OPEN_RECORDS:
        note = f"Only the first {MAX_OPEN_RECORDS} of {len(record_ids)} ids were opened — ask for the rest separately."
        record_ids = record_ids[:MAX_OPEN_RECORDS]

    records: list[dict[str, Any]] = []
    not_found: list[str] = []

    # Parse before opening a connection — a batch of entirely garbage ids
    # (the common case in a gate test, and a real possibility if the model
    # hallucinates) should short-circuit to not_found the same way the
    # single-id path does, never touching the DB.
    parsed = [(record_id, _parse_uuid(record_id)) for record_id in record_ids]
    not_found.extend(record_id for record_id, rid in parsed if rid is None)
    valid = [(record_id, rid) for record_id, rid in parsed if rid is not None]

    if valid:
        from app.database import get_connection
        try:
            async with get_connection() as conn:
                found_by_id = await batch_builder(conn, company_id, [rid for _, rid in valid])
            for record_id, rid in valid:
                summary = found_by_id.get(rid)
                if summary is None:
                    not_found.append(record_id)
                else:
                    records.append(summary)
        except Exception:
            logger.exception("huume show_records failed record_type=%s company=%s", record_type, company_id)
            return {"status": "error", "message": "Could not load those records."}

    if not records:
        result = {"status": "not_found", "message": "None of those record ids were found."}
        if not_found:
            result["not_found"] = not_found
        if note:
            result["note"] = note
        return result

    result: dict[str, Any] = {"status": "ok", "record_type": record_type, "records": records}
    if not_found:
        result["not_found"] = not_found
    if note:
        result["note"] = note
    return result


# ---------------------------------------------------------------------------
# Panel views — full normalized shape, admin's own auth, names allowed
# ---------------------------------------------------------------------------

_SEVERITY_TONE = {"critical": "red", "high": "orange", "medium": "amber", "low": "zinc"}
_INCIDENT_STATUS_TONE = {"action_required": "red", "investigating": "amber", "resolved": "emerald"}
_ER_STATUS_TONE = {"open": "amber", "in_review": "amber", "pending_determination": "orange", "closed": "zinc"}


async def _build_incident_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT id, incident_number, title, description, incident_type, severity, status,
               occurred_at, location, reported_by_name, witnesses, involved_employee_ids,
               root_cause, corrective_actions
        FROM ir_incidents
        WHERE id = $1 AND company_id = $2
        """,
        rid, company_id,
    )
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
        {"label": "Reported by", "value": data.get("reported_by_name") or "—"},
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
    row = await conn.fetchrow(
        """
        SELECT id, case_number, title, description, status, category, outcome,
               created_at, closed_at, involved_employees
        FROM er_cases
        WHERE id = $1 AND company_id = $2
        """,
        rid, company_id,
    )
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
        SELECT e.id, e.first_name, e.last_name, e.email, e.job_title, e.department,
               e.work_city, e.work_state, e.start_date, e.employment_type, e.employment_status,
               m.first_name || ' ' || m.last_name AS manager_name
        FROM employees e
        LEFT JOIN employees m ON m.id = e.manager_id AND m.org_id = e.org_id
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
        SELECT ecr.id, ecr.employee_id, ecr.status, ecr.due_date, ecr.verified_at,
               ecr.waived_at, ecr.waiver_reason, ecr.notes,
               ct.label AS credential_label, ct.category AS credential_category,
               e.first_name, e.last_name
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id AND e.org_id = $2
        JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
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


_DISCIPLINE_STATUS_TONE = {
    "draft": "zinc", "pending_meeting": "amber", "pending_signature": "amber",
    "active": "emerald", "completed": "emerald", "expired": "zinc",
    "escalated": "orange", "denied": "red",
}


async def _build_discipline_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT pd.id, pd.discipline_type, pd.infraction_type, pd.severity, pd.status,
               pd.approval_status, pd.issued_date, pd.review_date, pd.description,
               pd.expected_improvement, pd.denial_reason, pd.source_incident_id,
               e.first_name, e.last_name
        FROM progressive_discipline pd
        JOIN employees e ON e.id = pd.employee_id AND e.org_id = $2
        WHERE pd.id = $1 AND pd.company_id = $2
        """,
        rid, company_id,
    )
    if not row:
        return None
    data = dict(row)
    status = data.get("status") or "draft"
    level = (data.get("discipline_type") or "").replace("_", " ").title()
    employee_name = f"{data.get('first_name')} {data.get('last_name')}".strip()

    chips = [{"label": status.replace("_", " ").title(), "tone": _DISCIPLINE_STATUS_TONE.get(status, "zinc")}]
    approval_status = data.get("approval_status")
    if approval_status and approval_status != "not_required":
        chips.append({
            "label": f"Approval: {approval_status}",
            "tone": {"pending": "amber", "approved": "emerald", "denied": "red"}.get(approval_status, "zinc"),
        })

    meta = [
        {"label": "Employee", "value": employee_name or "—"},
        {"label": "Infraction", "value": (data.get("infraction_type") or "—").replace("_", " ").title()},
        {"label": "Severity", "value": (data.get("severity") or "—").title()},
        {"label": "Issued", "value": _iso(data.get("issued_date")) or "—"},
        {"label": "Review date", "value": _iso(data.get("review_date")) or "—"},
    ]
    sections = []
    if data.get("description"):
        sections.append({"label": "Description", "body": data["description"]})
    if data.get("expected_improvement"):
        sections.append({"label": "Expected improvement", "body": data["expected_improvement"]})
    if data.get("denial_reason"):
        sections.append({"label": "Denial reason", "body": data["denial_reason"]})

    return {
        "record_type": "discipline",
        "record_id": str(data["id"]),
        "title": f"{level} — {employee_name}",
        "subtitle": (data.get("infraction_type") or "").replace("_", " ").title(),
        "chips": chips,
        "meta": meta,
        "sections": sections,
        "link": f"/app/discipline/{data['id']}",
    }


_EMS_STATUS_TONE = {"logged": "amber", "promoted": "emerald", "dismissed": "zinc"}


async def _build_ems_event_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    from app.matcha.services.ems import categories
    from app.matcha.services.ems.queries import EVENT_SELECT

    row = await conn.fetchrow(f"{EVENT_SELECT} WHERE ev.id = $1 AND ev.company_id = $2", rid, company_id)
    if not row:
        return None
    data = dict(row)
    doc = data.get("doc")
    if isinstance(doc, str):
        doc = json.loads(doc) if doc else {}

    status = data.get("status") or "logged"
    chips = [
        {"label": categories.category_label(data.get("category")), "tone": "zinc"},
        {"label": status.title(), "tone": _EMS_STATUS_TONE.get(status, "zinc")},
    ]
    if data.get("severity_hint"):
        chips.append({"label": data["severity_hint"].title(), "tone": _SEVERITY_TONE.get(data["severity_hint"], "zinc")})
    if data.get("urgency") == "osha":
        chips.append({"label": "OSHA-reportable", "tone": "red"})
    elif data.get("urgency") == "severe":
        chips.append({"label": "Severe", "tone": "red"})
    if data.get("incident_recommendation"):
        chips.append({"label": "Flagged for incident review", "tone": "orange"})

    meta = [
        {"label": "Channel", "value": f"#{data.get('channel_name')}" if data.get("channel_name") else "—"},
        {"label": "Reported by", "value": data.get("reporter_name") or "—"},
        {"label": "Logged", "value": _iso(data.get("created_at")) or "—"},
    ]
    if data.get("incident_id"):
        # RecordViewer.tsx's Meta renders `value` as literal text (only
        # `view.link` becomes a clickable <Link>) — a raw "/app/ir/<uuid>"
        # path would show as an un-clickable string to copy by hand.
        # incident_number is the human label the admin actually recognizes.
        incident_number = await conn.fetchval(
            "SELECT incident_number FROM ir_incidents WHERE id = $1", data["incident_id"],
        )
        meta.append({"label": "Incident", "value": incident_number or str(data["incident_id"])})

    sections = []
    if data.get("narrative"):
        sections.append({"label": "Narrative", "body": data["narrative"]})
    for key, value in (doc or {}).items():
        label = key.replace("_", " ").title()
        if isinstance(value, str) and value.strip():
            sections.append({"label": label, "body": value})
        elif isinstance(value, list) and value:
            # doc list fields (people/items in the intake schema) were
            # silently dropped here while the model still sees them via
            # _model_ems_events_batch's full `doc` — the admin's panel and
            # the model's grounding must show the same thing.
            sections.append({"label": label, "items": [str(v) for v in value if v not in (None, "")]})
    if data.get("incident_reasoning"):
        sections.append({"label": "Incident reasoning", "body": data["incident_reasoning"]})
    if data.get("protocol_qualifies") is not None and data.get("protocol_reasoning"):
        label = (
            "Qualifies as an incident under company protocol"
            if data["protocol_qualifies"]
            else "Does not qualify as an incident under company protocol"
        )
        sections.append({"label": label, "body": data["protocol_reasoning"]})

    return {
        "record_type": "ems_event",
        "record_id": str(data["id"]),
        "title": data.get("title") or categories.category_label(data.get("category")),
        "subtitle": None,
        "chips": chips,
        "meta": meta,
        "sections": sections,
        "link": f"{await _work_base_path(conn, company_id)}/events/{data['id']}",
    }


async def _build_inventory_item_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    item = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1 AND company_id = $2", rid, company_id)
    if not item:
        return None
    data = dict(item)
    movement_rows = await conn.fetch(
        "SELECT * FROM inventory_movements WHERE item_id = $1 ORDER BY created_at DESC LIMIT 10", rid,
    )
    order = await conn.fetchrow(
        "SELECT * FROM inventory_orders WHERE item_id = $1 AND status = 'queued'", rid,
    )

    chips = [{"label": data.get("unit") or "unit", "tone": "zinc"}]
    if data.get("current_quantity") is not None:
        chips.append({"label": f"{data['current_quantity']} in stock", "tone": "zinc"})
    else:
        chips.append({"label": "count unknown", "tone": "amber"})
    if order:
        chips.append({"label": "Order queued", "tone": "orange"})
    if data.get("location_id"):
        location_name = await conn.fetchval(
            "SELECT name FROM business_locations WHERE id = $1", data["location_id"],
        )
        if location_name:
            chips.append({"label": location_name, "tone": "zinc"})

    meta = [{"label": "Created", "value": _iso(data.get("created_at")) or "—"}]

    sections = [{
        "label": "Recent movements",
        "items": [
            f"{m['kind']}: {m['quantity']} — {m['narrative']}" for m in movement_rows
        ] or ["No movements yet"],
    }]
    if order:
        sections.append({"label": "Open order", "body": f"{order['quantity']} queued"})

    return {
        "record_type": "inventory_item",
        "record_id": str(data["id"]),
        "title": data.get("name"),
        "subtitle": None,
        "chips": chips,
        "meta": meta,
        "sections": sections,
        "link": f"{await _work_base_path(conn, company_id)}/inventory/{data['id']}",
    }


_VIEW_BUILDERS = {
    "incident": _build_incident_view,
    "er_case": _build_er_case_view,
    "employee": _build_employee_view,
    "credential": _build_credential_view,
    "discipline": _build_discipline_view,
    "ems_event": _build_ems_event_view,
    "inventory_item": _build_inventory_item_view,
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
