"""OSHA log + form endpoints for IR Incidents.

Covers:
- OSHA 300 log (recordable injury/illness log) + CSV
- OSHA 301 form (per-incident detail)
- OSHA 300A annual summary + CSV
- Recordability update (manual)
- Recordability AI determination (Gemini-backed)
"""
import asyncio
import csv
import io
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    Osha300LogEntry,
    Osha300ASummary,
    OshaRecordabilityUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


VALID_OSHA_CLASSIFICATIONS = {
    "death", "days_away", "restricted_duty",
    "medical_treatment", "loss_of_consciousness", "significant_injury",
}


def _safe_json_loads(val, default=None):
    """Parse a JSON string or return a dict/list as-is."""
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default


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

    entries = []
    for row in rows:
        emp_name = row["reported_by_name"]
        if row["emp_first_name"]:
            emp_name = f"{row['emp_first_name']} {row['emp_last_name'] or ''}".strip()

        category_data = _safe_json_loads(row.get("category_data"), {})
        injury_type = category_data.get("injury_type")

        entries.append(Osha300LogEntry(
            case_number=row["osha_case_number"] or str(row["id"])[:8],
            employee_name=emp_name,
            job_title=row["emp_job_title"],
            date_of_injury=row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else "",
            location=row["location"],
            description=row["description"],
            classification=row["osha_classification"],
            days_away=row["days_away_from_work"],
            days_restricted=row["days_restricted_duty"],
            injury_type=injury_type,
            incident_id=str(row["id"]),
        ))
    return entries


@router.get("/osha/300-log/csv")
async def get_osha_300_log_csv(
    year: int = Query(..., description="Calendar year for the 300 log CSV"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300 log as CSV for a given year."""
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


@router.get("/osha/301/{incident_id}")
async def get_osha_301_form(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 301 form data for a specific recordable incident."""
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

    category_data = _safe_json_loads(row.get("category_data"), {})
    form_301_data = _safe_json_loads(row.get("osha_form_301_data"), {})

    emp_name = row["reported_by_name"]
    if row["emp_first_name"]:
        emp_name = f"{row['emp_first_name']} {row['emp_last_name'] or ''}".strip()

    return {
        "incident_id": str(row["id"]),
        "case_number": row["osha_case_number"] or str(row["id"])[:8],
        "employee_name": emp_name,
        "employee_email": row.get("emp_email"),
        "employee_job_title": row.get("emp_job_title"),
        "employee_start_date": row["emp_start_date"].isoformat() if row.get("emp_start_date") else None,
        "employer_name": row.get("company_name"),
        "employer_address": row.get("company_address"),
        "establishment_name": row.get("location_name"),
        "establishment_city": row.get("location_city"),
        "establishment_state": row.get("location_state"),
        "date_of_injury": row["occurred_at"].strftime("%Y-%m-%d") if row["occurred_at"] else None,
        "time_of_event": row["occurred_at"].strftime("%H:%M") if row["occurred_at"] else None,
        "location_of_event": row.get("location"),
        "description_of_injury": row.get("description"),
        "object_or_substance": category_data.get("equipment_involved"),
        "injury_type": category_data.get("injury_type"),
        "body_parts_affected": category_data.get("body_parts", []),
        "treatment": category_data.get("treatment"),
        "osha_classification": row.get("osha_classification"),
        "days_away_from_work": row.get("days_away_from_work") or 0,
        "days_restricted_duty": row.get("days_restricted_duty") or 0,
        "date_of_death": row["date_of_death"].isoformat() if row.get("date_of_death") else None,
        "additional_data": form_301_data,
    }


@router.get("/osha/300a", response_model=Osha300ASummary)
async def get_osha_300a_summary(
    year: int = Query(..., description="Calendar year for the 300A summary"),
    current_user=Depends(require_admin_or_client),
):
    """Generate OSHA 300A annual summary for a given year."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        cached = await conn.fetchrow(
            "SELECT * FROM osha_annual_summaries WHERE company_id = $1 AND year = $2",
            company_id, year,
        )
        if cached:
            return Osha300ASummary(
                year=cached["year"],
                establishment_name=cached["establishment_name"],
                total_cases=cached["total_cases"],
                total_deaths=cached["total_deaths"],
                total_days_away_cases=cached["total_days_away_cases"],
                total_restricted_cases=cached["total_restricted_cases"],
                total_other_recordable=cached["total_other_recordable"],
                total_days_away=cached["total_days_away"],
                total_days_restricted=cached["total_days_restricted"],
                total_injuries=cached["total_injuries"],
                total_skin_disorders=cached["total_skin_disorders"],
                total_respiratory=cached["total_respiratory"],
                total_poisonings=cached["total_poisonings"],
                total_hearing_loss=cached["total_hearing_loss"],
                total_other_illnesses=cached["total_other_illnesses"],
                average_employees=cached["average_employees"],
                total_hours_worked=cached["total_hours_worked"],
            )

        # M-column injury/illness type is stashed in osha_form_301_data->>'injury_type'
        # (set by the IR Copilot OSHA recordable chain — see _shared.OSHA_INJURY_TYPES).
        # When the value is NULL we fall back to "injury" so legacy rows still get counted
        # under the Standard Injury column rather than vanishing from totals.
        agg = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_cases,
                COALESCE(SUM(CASE WHEN osha_classification = 'death' THEN 1 ELSE 0 END), 0) AS total_deaths,
                COALESCE(SUM(CASE WHEN osha_classification = 'days_away' THEN 1 ELSE 0 END), 0) AS total_days_away_cases,
                COALESCE(SUM(CASE WHEN osha_classification = 'restricted_duty' THEN 1 ELSE 0 END), 0) AS total_restricted_cases,
                COALESCE(SUM(CASE WHEN osha_classification NOT IN ('death','days_away','restricted_duty') THEN 1 ELSE 0 END), 0) AS total_other_recordable,
                COALESCE(SUM(days_away_from_work), 0) AS total_days_away,
                COALESCE(SUM(days_restricted_duty), 0) AS total_days_restricted,
                COALESCE(SUM(CASE WHEN COALESCE(osha_form_301_data->>'injury_type','injury') = 'injury' THEN 1 ELSE 0 END), 0) AS total_injuries,
                COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'skin_disorder' THEN 1 ELSE 0 END), 0) AS total_skin_disorders,
                COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'respiratory' THEN 1 ELSE 0 END), 0) AS total_respiratory,
                COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'poisoning' THEN 1 ELSE 0 END), 0) AS total_poisonings,
                COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'hearing_loss' THEN 1 ELSE 0 END), 0) AS total_hearing_loss,
                COALESCE(SUM(CASE WHEN osha_form_301_data->>'injury_type' = 'other_illness' THEN 1 ELSE 0 END), 0) AS total_other_illnesses
            FROM ir_incidents
            WHERE company_id = $1
              AND osha_recordable = true
              AND EXTRACT(YEAR FROM occurred_at) = $2
            """,
            company_id, year,
        )

        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", company_id,
        )

        return Osha300ASummary(
            year=year,
            establishment_name=company["name"] if company else None,
            total_cases=agg["total_cases"],
            total_deaths=agg["total_deaths"],
            total_days_away_cases=agg["total_days_away_cases"],
            total_restricted_cases=agg["total_restricted_cases"],
            total_other_recordable=agg["total_other_recordable"],
            total_days_away=agg["total_days_away"],
            total_days_restricted=agg["total_days_restricted"],
            total_injuries=agg["total_injuries"],
            total_skin_disorders=agg["total_skin_disorders"],
            total_respiratory=agg["total_respiratory"],
            total_poisonings=agg["total_poisonings"],
            total_hearing_loss=agg["total_hearing_loss"],
            total_other_illnesses=agg["total_other_illnesses"],
            average_employees=None,
            total_hours_worked=None,
        )


@router.get("/osha/300a/csv")
async def get_osha_300a_csv(
    year: int = Query(..., description="Calendar year for the 300A summary CSV"),
    current_user=Depends(require_admin_or_client),
):
    """Export OSHA 300A annual summary as CSV."""
    summary = await get_osha_300a_summary(year=year, current_user=current_user)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Field", "Value"])
    writer.writerow(["Year", summary.year])
    writer.writerow(["Establishment Name", summary.establishment_name or ""])
    writer.writerow(["Total Cases", summary.total_cases])
    writer.writerow(["Total Deaths", summary.total_deaths])
    writer.writerow(["Total Days Away From Work Cases", summary.total_days_away_cases])
    writer.writerow(["Total Restricted Duty / Transfer Cases", summary.total_restricted_cases])
    writer.writerow(["Total Other Recordable Cases", summary.total_other_recordable])
    writer.writerow(["Total Days Away From Work", summary.total_days_away])
    writer.writerow(["Total Days Restricted Duty", summary.total_days_restricted])
    writer.writerow(["Total Injuries", summary.total_injuries])
    writer.writerow(["Total Skin Disorders", summary.total_skin_disorders])
    writer.writerow(["Total Respiratory Conditions", summary.total_respiratory])
    writer.writerow(["Total Poisonings", summary.total_poisonings])
    writer.writerow(["Total Hearing Loss", summary.total_hearing_loss])
    writer.writerow(["Total Other Illnesses", summary.total_other_illnesses])
    writer.writerow(["Average Number of Employees", summary.average_employees or ""])
    writer.writerow(["Total Hours Worked", summary.total_hours_worked or ""])

    output.seek(0)
    filename = f"osha_300a_summary_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.put("/{incident_id}/osha")
async def update_osha_recordability(
    incident_id: UUID,
    update: OshaRecordabilityUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Set OSHA recordability determination for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    if update.osha_classification and update.osha_classification not in VALID_OSHA_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OSHA classification. Must be one of: {', '.join(sorted(VALID_OSHA_CLASSIFICATIONS))}",
        )

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        sets = ["osha_recordable = $3"]
        params = [str(incident_id), company_id, update.osha_recordable]
        idx = 4

        if update.osha_classification is not None:
            sets.append(f"osha_classification = ${idx}")
            params.append(update.osha_classification)
            idx += 1
        if update.osha_case_number is not None:
            sets.append(f"osha_case_number = ${idx}")
            params.append(update.osha_case_number)
            idx += 1
        if update.days_away_from_work is not None:
            sets.append(f"days_away_from_work = ${idx}")
            params.append(update.days_away_from_work)
            idx += 1
        if update.days_restricted_duty is not None:
            sets.append(f"days_restricted_duty = ${idx}")
            params.append(update.days_restricted_duty)
            idx += 1

        updated = await conn.fetchrow(
            f"UPDATE ir_incidents SET {', '.join(sets)} WHERE id = $1 AND company_id = $2 RETURNING *",
            *params,
        )
        return {"message": "OSHA recordability updated", "id": str(updated["id"])}


@router.post("/{incident_id}/osha/determine")
async def osha_ai_determination(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """AI-assisted OSHA recordability determination using Gemini."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1 AND company_id = $2",
            str(incident_id), company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        category_data = _safe_json_loads(row.get("category_data"), {})

        prompt = f"""Analyze this workplace incident for OSHA recordability.

Incident: {row['title']}
Description: {row['description']}
Type: {row['incident_type']}
Severity: {row['severity']}
Injury type: {category_data.get('injury_type', 'unknown')}
Body parts: {category_data.get('body_parts', [])}
Treatment: {category_data.get('treatment', 'unknown')}
Lost days: {category_data.get('lost_days', 0)}

OSHA recordability criteria (29 CFR 1904):
- Death
- Days away from work
- Restricted work or transfer to another job
- Medical treatment beyond first aid
- Loss of consciousness
- Significant injury or illness diagnosed by a physician

Respond in JSON:
{{"recordable": true/false, "classification": "death|days_away|restricted_duty|medical_treatment|loss_of_consciousness|significant_injury|not_recordable", "reasoning": "brief explanation"}}
"""

        settings = get_settings()
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-3-flash-preview")
            response = await asyncio.to_thread(
                model.generate_content, prompt
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
        except Exception as e:
            logger.error("OSHA AI determination failed: %s", e)
            raise HTTPException(status_code=500, detail="AI determination failed")

        return {
            "incident_id": str(incident_id),
            "recordable": result.get("recordable", False),
            "classification": result.get("classification", "not_recordable"),
            "reasoning": result.get("reasoning", ""),
        }
