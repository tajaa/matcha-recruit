"""Company-facing employee-benefits router (gated by the ``benefits_admin``
feature flag).

This is the direct-client surface — a company on Matcha-lite/platform that
manages its own benefits roster (Finch-connected or CSV) and wants to see its
own eligibility exceptions and renewal-risk posture. The broker-portfolio
rollups across a whole book live separately under ``/broker/benefits/*``.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ...core.models.auth import CurrentUser
from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import benefits_eligibility as be

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_exception(r) -> dict:
    return {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "employee_name": r["employee_name"],
        "exception_type": r["exception_type"],
        "reference_date": r["reference_date"],
        "days_elapsed": r["days_elapsed"],
        "days_remaining": r["days_remaining"],
        "estimated_monthly_leak": float(r["estimated_monthly_leak"]) if r["estimated_monthly_leak"] is not None else None,
        "status": r["status"],
        "source": r["source"],
        "detected_at": r["detected_at"],
    }


@router.get("/roster/template")
async def roster_template(current_user: CurrentUser = Depends(require_admin_or_client)):
    """CSV template — RFC 2606 reserved-domain sample rows only."""
    header = ",".join(be.CSV_COLUMNS)
    samples = [
        "E1001,Jordan,Avery,jordan.avery@example.com,Warehouse,Warehouse B,2026-05-20,,active,false,0,2400",
        "E1002,Sam,Lee,sam.lee@example.com,Operations,Warehouse B,2024-02-01,2026-05-15,inactive,true,650,0",
    ]
    csv_text = header + "\n" + "\n".join(samples) + "\n"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="benefit_roster_template.csv"'},
    )


@router.post("/roster/upload")
async def roster_upload(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload this company's roster CSV, then re-run detection + risk."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    content = await file.read()
    async with get_connection() as conn:
        ingested = await be.ingest_roster_from_csv(conn, company_id, content)
        exc = await be.detect_eligibility_exceptions(conn, company_id)
        risk = await be.compute_renewal_risk(conn, company_id)
    return {"ingested": ingested, "exceptions_detected": exc["detected"], "risk": risk}


@router.post("/run")
async def run_detection(current_user: CurrentUser = Depends(require_admin_or_client)):
    """Manual full pass: Finch ingest (if connected) → detect → compute risk."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    async with get_connection() as conn:
        return await be.run_for_company(conn, company_id, use_finch=True)


@router.get("/eligibility-exceptions")
async def eligibility_exceptions(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"exceptions": []}
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM benefit_eligibility_exceptions
            WHERE company_id = $1 AND status = 'open'
            ORDER BY exception_type, days_remaining NULLS FIRST
            """,
            company_id,
        )
    return {"exceptions": [_serialize_exception(r) for r in rows]}


@router.get("/renewal-risk")
async def renewal_risk(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"dimensions": []}
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM benefit_renewal_risk WHERE company_id = $1 ORDER BY dimension_type, dimension_value",
            company_id,
        )
    dims = []
    for r in rows:
        triggers = r["triggers"] if isinstance(r["triggers"], list) else []
        dims.append({
            "dimension_type": r["dimension_type"],
            "dimension_value": r["dimension_value"],
            "risk_band": r["risk_band"],
            "turnover_pct": float(r["turnover_pct"] or 0),
            "turnover_delta_pct": float(r["turnover_delta_pct"] or 0),
            "lost_workdays": r["lost_workdays"],
            "near_misses": r["near_misses"],
            "behavioral_incidents": r["behavioral_incidents"],
            "headcount": r["headcount"],
            "triggers": triggers,
        })
    return {"dimensions": dims}
