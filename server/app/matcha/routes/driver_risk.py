"""Driver-risk / MVR routes (`/driver-risk`, feature `driver_risk`).

Gap-analysis #15 — a standalone driver-risk surface for any employer with
drivers (commercial-auto entry), scoring each driver from employer-recorded MVR
data (license status, violations, accidents, major violations) → clean / marginal
/ high-risk + a fleet grade + insurer PDF. Reuses the mvr_reviews table shared
with resident_care. Business-facing, tenant-isolated.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import driver_risk as dr
from ..models.driver_risk import DriverReviewCreate, DriverReviewUpdate

router = APIRouter()

_COLS = ("id, driver_name, employee_id, review_type, review_date, status, next_due_date, notes, "
         "violation_count, accident_count, major_violation, license_status")


async def _require_company_id(current_user) -> UUID:
    """Resolve the caller's company, 403 if they have none (mirrors flight_risk)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


@router.get("/fleet")
async def get_fleet(current_user=Depends(require_admin_or_client)):
    """Scored driver list + fleet summary (grade, tier counts, overdue MVRs)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return {"company_id": None, "company_name": "", "drivers": [], "summary": dr.summarize([])}
    async with get_connection() as conn:
        return await dr.build_fleet(conn, company_id)


@router.post("/drivers")
async def create_driver(body: DriverReviewCreate, current_user=Depends(require_admin_or_client)):
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO mvr_reviews
                (company_id, driver_name, employee_id, review_type, review_date, status, next_due_date,
                 notes, violation_count, accident_count, major_violation, license_status, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            """,
            company_id, body.driver_name.strip(), body.employee_id, body.review_type, body.review_date,
            body.status, body.next_due_date, body.notes, body.violation_count, body.accident_count,
            body.major_violation, body.license_status, current_user.id,
        )
        return await dr.build_fleet(conn, company_id)


@router.put("/drivers/{review_id}")
async def update_driver(review_id: UUID, body: DriverReviewUpdate,
                        current_user=Depends(require_admin_or_client)):
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mvr_reviews SET
                driver_name = COALESCE($3, driver_name), review_type = COALESCE($4, review_type),
                review_date = COALESCE($5, review_date), status = COALESCE($6, status),
                next_due_date = COALESCE($7, next_due_date), notes = COALESCE($8, notes),
                violation_count = COALESCE($9, violation_count), accident_count = COALESCE($10, accident_count),
                major_violation = COALESCE($11, major_violation), license_status = COALESCE($12, license_status),
                updated_at = NOW()
            WHERE id = $1 AND company_id = $2 RETURNING id
            """,
            review_id, company_id, body.driver_name, body.review_type, body.review_date, body.status,
            body.next_due_date, body.notes, body.violation_count, body.accident_count,
            body.major_violation, body.license_status,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Driver record not found")
        return await dr.build_fleet(conn, company_id)


@router.delete("/drivers/{review_id}")
async def delete_driver(review_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mvr_reviews WHERE id = $1 AND company_id = $2", review_id, company_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Driver record not found")
        return await dr.build_fleet(conn, company_id)


@router.get("/fleet.pdf")
async def fleet_pdf(current_user=Depends(require_admin_or_client)):
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        fleet = await dr.build_fleet(conn, company_id)
    pdf = await dr.render_fleet_pdf(fleet["company_name"], fleet)
    safe = fleet["company_name"].replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="driver-risk-{safe}.pdf"'},
    )
