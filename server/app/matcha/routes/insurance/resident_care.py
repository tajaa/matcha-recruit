"""Resident-care risk routes (`/resident-care`, feature `resident_care`).

Healthcare / senior-living risk-management asset (WTW p.175–176): safety-program
register, MVR-review tracking (hire + annual), credentialing-currency readout,
and an insurer-facing asset PDF. Business-facing; tenant-isolated by company.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ...services import resident_care as rc
from ...services import workforce_suggest
from ...models.resident_care import (
    SafetyProgramCreate, SafetyProgramUpdate, MvrReviewCreate, MvrReviewUpdate,
)

router = APIRouter()

_PROG_COLS = ("id, company_id, program_type, name, status, last_reviewed_date, owner, notes, created_at")
_MVR_COLS = ("id, company_id, driver_name, employee_id, review_type, review_date, status, "
             "next_due_date, notes, created_at")


@router.get("/summary")
async def get_summary(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await rc.summary(conn, company_id)


# --- safety programs --------------------------------------------------------

@router.get("/programs")
async def list_programs(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {_PROG_COLS} FROM safety_programs WHERE company_id = $1 "
            "ORDER BY status, program_type, name",
            company_id,
        )
    return [dict(r) for r in rows]


@router.post("/programs/suggest")
async def suggest_programs(current_user=Depends(require_admin_or_client)):
    """AI-propose safety programs from the company's industry + incident history (no auto-commit)."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await workforce_suggest.suggest(conn, company_id, "safety_programs")


@router.post("/programs")
async def create_program(body: SafetyProgramCreate, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO safety_programs
                (company_id, program_type, name, status, last_reviewed_date, owner, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING {_PROG_COLS}
            """,
            company_id, body.program_type, body.name.strip(), body.status,
            body.last_reviewed_date, body.owner, body.notes, current_user.id,
        )
    return dict(row)


@router.put("/programs/{program_id}")
async def update_program(program_id: UUID, body: SafetyProgramUpdate,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE safety_programs SET
                program_type = COALESCE($3, program_type), name = COALESCE($4, name),
                status = COALESCE($5, status), last_reviewed_date = COALESCE($6, last_reviewed_date),
                owner = COALESCE($7, owner), notes = COALESCE($8, notes), updated_at = NOW()
            WHERE id = $1 AND company_id = $2 RETURNING {_PROG_COLS}
            """,
            program_id, company_id, body.program_type, body.name, body.status,
            body.last_reviewed_date, body.owner, body.notes,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Program not found")
    return dict(row)


@router.delete("/programs/{program_id}")
async def delete_program(program_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        res = await conn.execute("DELETE FROM safety_programs WHERE id=$1 AND company_id=$2", program_id, company_id)
    if res.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Program not found")
    return {"status": "deleted"}


# --- MVR reviews ------------------------------------------------------------

@router.get("/mvr")
async def list_mvr(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {_MVR_COLS} FROM mvr_reviews WHERE company_id = $1 "
            "ORDER BY (next_due_date IS NOT NULL AND next_due_date < CURRENT_DATE) DESC, "
            "next_due_date ASC NULLS LAST, driver_name",
            company_id,
        )
    return [dict(r) for r in rows]


@router.post("/mvr")
async def create_mvr(body: MvrReviewCreate, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO mvr_reviews
                (company_id, driver_name, employee_id, review_type, review_date, status, next_due_date, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING {_MVR_COLS}
            """,
            company_id, body.driver_name.strip(), body.employee_id, body.review_type,
            body.review_date, body.status, body.next_due_date, body.notes, current_user.id,
        )
    return dict(row)


@router.put("/mvr/{review_id}")
async def update_mvr(review_id: UUID, body: MvrReviewUpdate,
                     current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE mvr_reviews SET
                driver_name = COALESCE($3, driver_name), review_type = COALESCE($4, review_type),
                review_date = COALESCE($5, review_date), status = COALESCE($6, status),
                next_due_date = COALESCE($7, next_due_date), notes = COALESCE($8, notes), updated_at = NOW()
            WHERE id = $1 AND company_id = $2 RETURNING {_MVR_COLS}
            """,
            review_id, company_id, body.driver_name, body.review_type, body.review_date,
            body.status, body.next_due_date, body.notes,
        )
        if not row:
            raise HTTPException(status_code=404, detail="MVR review not found")
    return dict(row)


@router.delete("/mvr/{review_id}")
async def delete_mvr(review_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        res = await conn.execute("DELETE FROM mvr_reviews WHERE id=$1 AND company_id=$2", review_id, company_id)
    if res.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="MVR review not found")
    return {"status": "deleted"}


# --- insurer-facing asset PDF -----------------------------------------------

@router.get("/asset.pdf")
async def asset_pdf(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        s = await rc.summary(conn, company_id)
        programs = [dict(r) for r in await conn.fetch(
            f"SELECT {_PROG_COLS} FROM safety_programs WHERE company_id=$1 ORDER BY status, program_type", company_id)]
        mvr = [dict(r) for r in await conn.fetch(
            f"SELECT {_MVR_COLS} FROM mvr_reviews WHERE company_id=$1 ORDER BY driver_name", company_id)]
    name = company["name"] if company else "Client"
    pdf = await rc.render_asset_pdf(name, s, programs, mvr)
    safe = name.replace("/", "-").replace('"', "")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="resident-care-{safe}.pdf"'})
