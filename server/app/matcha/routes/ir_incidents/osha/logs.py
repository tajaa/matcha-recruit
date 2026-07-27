"""OSHA 300 log (recordable injury/illness log) + CSV, the privacy-case list,
and the per-incident 301 form. Read-only reporting over `ir_incidents` +
`ir_osha_cases`; every description passes the privacy/redaction gate.
"""
import csv
import io
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    Osha300LogEntry,
    OshaPrivacyCaseEntry,
)
from app.matcha.routes.ir_incidents._shared import (
    log_audit,
    _hydrate_involved_employees,
    fetch_osha_case_rows,
    fetch_osha_case_rows_for,
)
from app.core.services.osha_redaction import redact_osha_text
from app.core.services.osha_privacy import (
    determine_privacy_case,
    compose_clinical_description,
    PRIVACY_NAME,
    PRIVACY_DESCRIPTION_PLACEHOLDER,
)
from ._shared import _attest_export, _safe_json_loads

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_STRUCTURED_DESCRIPTION = "See incident record for details"


def _mask_from_reason(privacy_case_reason, category_data: dict, osha_injury_type):
    """Hybrid Column-B mask decision for one case, from its privacy answer.

    The per-employee answer (``ir_osha_case_details.privacy_case_reason``, or the
    legacy ``category_data.privacy_cases`` value for un-captured rows) is the
    source of truth:
      * a reason string  → mask (human confirmed this category),
      * ``"none"``        → don't mask (human reviewed and cleared it),
      * NULL/unanswered   → fall back to ``determine_privacy_case`` as a
        fail-closed safety net (incident-level signals + this case's M-column
        injury type; may over-mask, the safe direction).
    Returns ``(is_privacy_case, reason)``.
    """
    if isinstance(privacy_case_reason, str):
        h = privacy_case_reason.strip().lower()
        if h == "none":
            return False, None
        if h:
            return True, h
    cd = category_data or {}
    return determine_privacy_case(
        cd, osha_injury_type, bool(cd.get("employee_privacy_requested")),
    )


def _resolve_osha_description(category_data: dict, is_privacy_case: bool) -> str:
    """OSHA 300/301 Description (Column F) — NEVER the raw reporter narrative.

    Precedence (all name-free by construction):
      1. ``osha_clean_description`` — the AI-cleansed narrative (names stripped).
      2. ``compose_clinical_description`` — structured injury phrase.
      3. a neutral placeholder.
    """
    cd = category_data or {}
    clean = (cd.get("osha_clean_description") or "").strip()
    if clean:
        return clean
    return compose_clinical_description(cd) or (
        PRIVACY_DESCRIPTION_PLACEHOLDER if is_privacy_case else _NO_STRUCTURED_DESCRIPTION
    )


def _reporter_name_title(row):
    """``(name, job_title)`` for the reporter-fallback case — the reporter's
    roster match if any, else the typed ``reported_by_name``."""
    name = row["reported_by_name"]
    if row.get("emp_first_name"):
        name = f"{row['emp_first_name']} {row.get('emp_last_name') or ''}".strip()
    return name, row.get("emp_job_title")


def _injured_persons(row, emp_map: dict) -> list:
    """One injured person per row: ``[(case_key, name, job_title)]`` — the
    incident-level fallback when an incident has no ir_osha_case_details rows.

    Roster employees from ``involved_employee_ids`` (name + Finch-synced
    ``job_title``), in stored order; else a single ``"reporter"`` row.
    """
    ids = [str(x) for x in (row.get("involved_employee_ids") or []) if x]
    if ids:
        out = []
        for eid in ids:
            emp = emp_map.get(eid)
            if emp:
                name = f"{emp.get('first_name') or ''} {emp.get('last_name') or ''}".strip() or "Unknown"
                out.append((eid, name, emp.get("job_title")))
            else:
                # id no longer on the roster — keep a row (mask-safe), no name leak.
                out.append((eid, "Unknown", None))
        return out
    name, title = _reporter_name_title(row)
    return [("reporter", name, title)]


def _osha_case_views(row, case_rows, emp_map) -> list:
    """Per-incident case views for the 300/301 reads — one per injured employee.

    Each view: ``{case_key, case_seq, name, job_title, classification,
    days_away, days_restricted, injury_type, privacy_case_reason}``. Prefers the
    ``ir_osha_case_details`` rows (per-employee classification/days/injury +
    privacy); falls back to synthesizing from the incident-level columns +
    ``involved_employee_ids`` + ``category_data.privacy_cases`` when an incident
    has no case rows yet (legacy / not-yet-captured).
    """
    if case_rows:
        views = []
        for cr in case_rows:  # ordered by case_seq
            ek = cr.get("case_key")
            if ek == "reporter":
                name, title = _reporter_name_title(row)
            else:
                emp = emp_map.get(ek)
                if emp:
                    name = f"{emp.get('first_name') or ''} {emp.get('last_name') or ''}".strip() or "Unknown"
                    title = emp.get("job_title")
                else:
                    name, title = "Unknown", None
            views.append({
                "case_key": ek,
                "case_seq": cr.get("case_seq") or 1,
                "name": name,
                "job_title": title,
                "classification": cr.get("classification"),
                "days_away": cr.get("days_away") or 0,
                "days_restricted": cr.get("days_restricted") or 0,
                "injury_type": cr.get("injury_type"),
                "privacy_case_reason": cr.get("privacy_case_reason"),
            })
        return views
    # Fallback: no case rows yet — synthesize from incident-level values.
    cd = _safe_json_loads(row.get("category_data"), {})
    form_301 = _safe_json_loads(row.get("osha_form_301_data"), {})
    privacy_map = cd.get("privacy_cases") or {}
    out = []
    for idx, (key, name, title) in enumerate(_injured_persons(row, emp_map)):
        out.append({
            "case_key": key,
            "case_seq": idx + 1,
            "name": name,
            "job_title": title,
            "classification": row.get("osha_classification"),
            "days_away": row.get("days_away_from_work") or 0,
            "days_restricted": row.get("days_restricted_duty") or 0,
            "injury_type": form_301.get("injury_type"),
            "privacy_case_reason": privacy_map.get(key),
        })
    return out


async def _hydrate_case_emp_map(conn, company_id, rows, cases_by_incident) -> dict:
    """Batch-resolve employee ids → roster detail for the 300-log read. Gathers
    ids from case rows' ``employee_id`` (captured incidents) and from
    ``involved_employee_ids`` (fallback incidents). One query."""
    emp_ids = set()
    for row in rows:
        crs = cases_by_incident.get(str(row["id"]))
        if crs:
            for cr in crs:
                if cr.get("employee_id"):
                    emp_ids.add(str(cr["employee_id"]))
        else:
            for x in (row.get("involved_employee_ids") or []):
                if x:
                    emp_ids.add(str(x))
    if not emp_ids:
        return {}
    hydrated = await _hydrate_involved_employees(conn, company_id, list(emp_ids))
    return {str(e["id"]): e for e in hydrated}


@router.get("/osha/300-log", response_model=list[Osha300LogEntry])
async def get_osha_300_log(
    year: int = Query(..., description="Calendar year for the 300 log"),
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 300 log for a given year."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.id,
                i.osha_case_number,
                i.title,
                i.description,
                i.location,
                i.occurred_at,
                i.osha_classification,
                COALESCE(i.days_away_from_work, 0) AS days_away_from_work,
                COALESCE(i.days_restricted_duty, 0) AS days_restricted_duty,
                i.category_data,
                i.osha_form_301_data,
                i.involved_employee_ids,
                i.reported_by_name,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title
            FROM ir_incidents i
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id = i.company_id
            WHERE i.company_id = $1
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $2
            ORDER BY i.occurred_at
            """,
            company_id,
            year,
        )
        cases_by_incident = await fetch_osha_case_rows_for(conn, [r["id"] for r in rows])
        emp_map = await _hydrate_case_emp_map(conn, company_id, rows, cases_by_incident)

    entries = []
    for row in rows:
        category_data = _safe_json_loads(row.get("category_data"), {})
        injury_type_display = category_data.get("injury_type")  # clinical nature, incident-level
        base_case = row["osha_case_number"] or str(row["id"])[:8]
        date_str = row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else ""
        location = redact_osha_text(row["location"])

        # One row per injured employee — each its OWN classification/days/injury
        # (from its ir_osha_case_details row, incident-level fallback otherwise)
        # and its OWN Column-B mask. Description (Column F) is name-free regardless.
        views = _osha_case_views(row, cases_by_incident.get(str(row["id"]), []), emp_map)
        multi = len(views) > 1
        for v in views:
            is_priv, reason = _mask_from_reason(v["privacy_case_reason"], category_data, v["injury_type"])
            entries.append(Osha300LogEntry(
                case_number=f"{base_case}-{v['case_seq']}" if multi else base_case,
                employee_name=PRIVACY_NAME if is_priv else v["name"],
                job_title=v["job_title"],
                date_of_injury=date_str,
                location=location,
                description=_resolve_osha_description(category_data, is_priv),
                classification=v["classification"],
                days_away=v["days_away"],
                days_restricted=v["days_restricted"],
                injury_type=injury_type_display,
                incident_id=str(row["id"]),
                is_privacy_case=is_priv,
                privacy_case_reason=reason,
            ))
    return entries


@router.get("/osha/300-log/csv")
async def get_osha_300_log_csv(
    year: int = Query(..., description="Calendar year for the 300 log CSV"),
    attested: bool = Query(False, description="Reviewer confirmed they reviewed the data before export"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300 log as CSV for a given year."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        await _attest_export(conn, current_user, form="300_log", year=year, attested=attested)

    entries = await get_osha_300_log(year=year, current_user=current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Case Number", "Employee Name", "Job Title", "Date of Injury/Illness",
        "Where Event Occurred", "Description", "Classification",
        "Days Away From Work", "Days on Restricted Duty", "Injury/Illness Type",
        "Incident ID",
    ])
    for entry in entries:
        writer.writerow([
            entry.case_number,
            entry.employee_name,
            entry.job_title or "",
            entry.date_of_injury,
            entry.location or "",
            entry.description or "",
            entry.classification or "",
            entry.days_away,
            entry.days_restricted,
            entry.injury_type or "",
            entry.incident_id,
        ])

    output.seek(0)
    filename = f"osha_300_log_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/osha/privacy-cases", response_model=list[OshaPrivacyCaseEntry])
async def get_osha_privacy_cases(
    year: int = Query(..., description="Calendar year for the privacy-case reference list"),
    current_user=Depends(require_admin_or_client),
):
    """Confidential OSHA Privacy Case reference list (29 CFR 1904.29(b)(9)).

    Resolves each masked 300-log row's case number back to the REAL employee
    name. Company-scoped, admin/client-gated, and every access is written to the
    IR audit log. Never exposed on the public 300 log / CSV / 301 form.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.id,
                i.osha_case_number,
                i.occurred_at,
                i.osha_classification,
                i.category_data,
                i.osha_form_301_data,
                i.involved_employee_ids,
                i.reported_by_name,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title
            FROM ir_incidents i
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id = i.company_id
            WHERE i.company_id = $1
              AND i.osha_recordable = true
              AND EXTRACT(YEAR FROM i.occurred_at) = $2
            ORDER BY i.occurred_at
            """,
            company_id,
            year,
        )
        cases_by_incident = await fetch_osha_case_rows_for(conn, [r["id"] for r in rows])
        emp_map = await _hydrate_case_emp_map(conn, company_id, rows, cases_by_incident)

        entries: list[OshaPrivacyCaseEntry] = []
        for row in rows:
            category_data = _safe_json_loads(row.get("category_data"), {})
            base_case = row["osha_case_number"] or str(row["id"])[:8]
            views = _osha_case_views(row, cases_by_incident.get(str(row["id"]), []), emp_map)
            multi = len(views) > 1
            for v in views:
                is_priv, reason = _mask_from_reason(v["privacy_case_reason"], category_data, v["injury_type"])
                if not is_priv:
                    continue
                entries.append(OshaPrivacyCaseEntry(
                    case_number=f"{base_case}-{v['case_seq']}" if multi else base_case,
                    real_employee_name=v["name"] or "Unknown",
                    privacy_case_reason=reason,
                    classification=v["classification"],
                    date_of_injury=row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else "",
                    incident_id=str(row["id"]),
                ))

        # Confidential access is audited (list view → no single-incident scope).
        await log_audit(
            conn, None, str(current_user.id), "privacy_case_names_viewed",
            entity_type="osha_privacy_case",
            details={"year": year, "count": len(entries)},
        )

    return entries


@router.get("/osha/301/{incident_id}")
async def get_osha_301_form(
    incident_id: UUID,
    employee_id: Optional[UUID] = Query(None, description="Which injured employee's 301 (defaults to the first injured person)"),
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 301 form data for a recordable incident + injured employee."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                i.*,
                c.name AS company_name,
                c.address AS company_address,
                bl.name AS location_name,
                bl.city AS location_city,
                bl.state AS location_state,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.job_title AS emp_job_title,
                e.personal_email AS emp_email,
                e.start_date AS emp_start_date
            FROM ir_incidents i
            LEFT JOIN companies c ON c.id = i.company_id
            LEFT JOIN business_locations bl ON bl.id = i.location_id
            LEFT JOIN employees e
                ON e.email = i.reported_by_email
                AND e.org_id = i.company_id
            WHERE i.id = $1
              AND i.company_id = $2
              AND i.osha_recordable = true
            """,
            incident_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Recordable incident not found")
        case_rows = await fetch_osha_case_rows(conn, row["id"])
        emp_map = await _hydrate_case_emp_map(
            conn, company_id, [row], {str(row["id"]): case_rows}
        )

    category_data = _safe_json_loads(row.get("category_data"), {})
    form_301_data = _safe_json_loads(row.get("osha_form_301_data"), {})

    # One 301 per injured employee. Pick the requested employee (else the first
    # injured person) and key the mask + facts to that person's case so the 301
    # matches its 300-log row. Description is name-free (never the raw narrative).
    # The real name stays resolvable via /osha/privacy-cases.
    views = _osha_case_views(row, case_rows, emp_map)
    target = None
    if employee_id is not None:
        target = next((v for v in views if v["case_key"] == str(employee_id)), None)
    if target is None:
        target = views[0]
    is_reporter = target["case_key"] == "reporter"
    base_case = row["osha_case_number"] or str(row["id"])[:8]
    case_number = f"{base_case}-{target['case_seq']}" if len(views) > 1 else base_case

    is_priv, reason = _mask_from_reason(target["privacy_case_reason"], category_data, target["injury_type"])
    clinical_description = _resolve_osha_description(category_data, is_priv)
    return {
        "incident_id": str(row["id"]),
        "case_number": case_number,
        "employee_name": PRIVACY_NAME if is_priv else target["name"],
        "is_privacy_case": is_priv,
        "privacy_case_reason": reason,
        # email/start_date come from the reporter join — valid only when this 301
        # is the reporter's own; otherwise it would show another person's PII.
        "employee_email": row.get("emp_email") if is_reporter else None,
        "employee_job_title": target["job_title"],
        "employee_start_date": row["emp_start_date"].isoformat() if (is_reporter and row.get("emp_start_date")) else None,
        "employer_name": row.get("company_name"),
        "employer_address": row.get("company_address"),
        "establishment_name": row.get("location_name"),
        "establishment_city": row.get("location_city"),
        "establishment_state": row.get("location_state"),
        "date_of_injury": row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else None,
        "time_of_event": row["occurred_at"].strftime("%H:%M") if row["occurred_at"] else None,
        "location_of_event": redact_osha_text(row.get("location")),
        "description_of_injury": clinical_description,
        "object_or_substance": category_data.get("equipment_involved"),
        "injury_type": category_data.get("injury_type"),
        "body_parts_affected": category_data.get("body_parts", []),
        "treatment": redact_osha_text(category_data.get("treatment")),
        "osha_classification": target["classification"],
        "days_away_from_work": target["days_away"],
        "days_restricted_duty": target["days_restricted"],
        "date_of_death": row["date_of_death"].isoformat() if row.get("date_of_death") else None,
        "additional_data": form_301_data,
    }
