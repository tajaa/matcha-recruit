"""Workforce Compliance routes (`/workforce-compliance`, feature `workforce_compliance`).

Business-facing trackers — AI hiring-tool audit register, biometric/BIPA consent
inventory, and per-state pay-transparency status. Same data flips the broker EPL
factors attested → derived (see services/epl_readiness.py).
"""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import pay_equity_analysis
from ..services import workforce_suggest
from ..services import workforce_compliance as wf
from ..models.workforce_compliance import (
    HiringAiAuditCreate, HiringAiAuditUpdate, HiringAiAuditResponse,
    BiometricPointCreate, BiometricPointUpdate, BiometricPointResponse,
    PayTransparencyStateRow, PayTransparencyUpdate,
    PayEquityReviewCreate, PayEquityReviewUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# is_overdue computed at read-time (the stored column is only fresh at write-time;
# a tool crosses its due date later without a re-save).
_OVERDUE_EXPR = "(next_due_date IS NULL OR next_due_date < CURRENT_DATE)"
_AI_COLS = ("id, company_id, tool_name, vendor, purpose, last_audit_date, cadence_days, "
            f"next_due_date, {_OVERDUE_EXPR} AS is_overdue, notes, created_at")
_BIO_COLS = ("id, company_id, location_id, collection_type, purpose, consent_obtained, "
             "consent_obtained_date, consent_method, retention_policy, is_active, notes, created_at")
_PE_COLS = ("id, company_id, review_date, scope, methodology, gap_pct, remediation, cadence_days, "
            f"next_due_date, {_OVERDUE_EXPR} AS is_overdue, notes, created_at")


# --- AI hiring-tool audits --------------------------------------------------

@router.get("/ai-audits", response_model=list[HiringAiAuditResponse])
async def list_ai_audits(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {_AI_COLS} FROM hiring_ai_audits WHERE company_id = $1 "
            "ORDER BY is_overdue DESC, next_due_date ASC NULLS LAST, tool_name",
            company_id,
        )
    return [dict(r) for r in rows]


@router.post("/ai-audits/suggest")
async def suggest_ai_audits(current_user=Depends(require_admin_or_client)):
    """AI-propose the hiring-tool register from the company's profile (no auto-commit)."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await workforce_suggest.suggest(conn, company_id, "ai_audits")


@router.post("/ai-audits", response_model=HiringAiAuditResponse)
async def create_ai_audit(body: HiringAiAuditCreate, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    next_due, overdue = wf.audit_dates(body.last_audit_date, body.cadence_days)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO hiring_ai_audits
                (company_id, tool_name, vendor, purpose, last_audit_date, cadence_days,
                 next_due_date, is_overdue, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING {_AI_COLS}
            """,
            company_id, body.tool_name.strip(), body.vendor, body.purpose, body.last_audit_date,
            body.cadence_days, next_due, overdue, body.notes, current_user.id,
        )
    return dict(row)


@router.put("/ai-audits/{audit_id}", response_model=HiringAiAuditResponse)
async def update_ai_audit(audit_id: UUID, body: HiringAiAuditUpdate,
                          current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        cur = await conn.fetchrow(
            "SELECT last_audit_date, cadence_days FROM hiring_ai_audits WHERE id=$1 AND company_id=$2",
            audit_id, company_id,
        )
        if not cur:
            raise HTTPException(status_code=404, detail="Audit not found")
        last = body.last_audit_date if body.last_audit_date is not None else cur["last_audit_date"]
        cadence = body.cadence_days if body.cadence_days is not None else cur["cadence_days"]
        next_due, overdue = wf.audit_dates(last, cadence)
        row = await conn.fetchrow(
            f"""
            UPDATE hiring_ai_audits SET
                tool_name = COALESCE($3, tool_name), vendor = COALESCE($4, vendor),
                purpose = COALESCE($5, purpose), last_audit_date = $6, cadence_days = $7,
                next_due_date = $8, is_overdue = $9, notes = COALESCE($10, notes), updated_at = NOW()
            WHERE id = $1 AND company_id = $2
            RETURNING {_AI_COLS}
            """,
            audit_id, company_id, body.tool_name, body.vendor, body.purpose, last, cadence,
            next_due, overdue, body.notes,
        )
    return dict(row)


@router.delete("/ai-audits/{audit_id}")
async def delete_ai_audit(audit_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        res = await conn.execute("DELETE FROM hiring_ai_audits WHERE id=$1 AND company_id=$2", audit_id, company_id)
    if res.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Audit not found")
    return {"status": "deleted"}


# --- Biometric consent points -----------------------------------------------

@router.get("/biometric-points", response_model=list[BiometricPointResponse])
async def list_biometric_points(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {_BIO_COLS} FROM biometric_consent_points WHERE company_id=$1 "
            "ORDER BY is_active DESC, consent_obtained ASC, created_at DESC",
            company_id,
        )
    return [dict(r) for r in rows]


@router.post("/biometric-points/suggest")
async def suggest_biometric_points(current_user=Depends(require_admin_or_client)):
    """AI-propose biometric collection points from the company's profile (no auto-commit)."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await workforce_suggest.suggest(conn, company_id, "biometric")


@router.post("/biometric-points", response_model=BiometricPointResponse)
async def create_biometric_point(body: BiometricPointCreate, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO biometric_consent_points
                (company_id, location_id, collection_type, purpose, consent_obtained,
                 consent_obtained_date, consent_method, retention_policy, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING {_BIO_COLS}
            """,
            company_id, body.location_id, body.collection_type, body.purpose, body.consent_obtained,
            body.consent_obtained_date, body.consent_method, body.retention_policy, body.notes, current_user.id,
        )
    return dict(row)


@router.put("/biometric-points/{point_id}", response_model=BiometricPointResponse)
async def update_biometric_point(point_id: UUID, body: BiometricPointUpdate,
                                 current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE biometric_consent_points SET
                collection_type = COALESCE($3, collection_type), location_id = COALESCE($4, location_id),
                purpose = COALESCE($5, purpose), consent_obtained = COALESCE($6, consent_obtained),
                consent_obtained_date = COALESCE($7, consent_obtained_date),
                consent_method = COALESCE($8, consent_method), retention_policy = COALESCE($9, retention_policy),
                is_active = COALESCE($10, is_active), notes = COALESCE($11, notes), updated_at = NOW()
            WHERE id = $1 AND company_id = $2
            RETURNING {_BIO_COLS}
            """,
            point_id, company_id, body.collection_type, body.location_id, body.purpose,
            body.consent_obtained, body.consent_obtained_date, body.consent_method,
            body.retention_policy, body.is_active, body.notes,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Point not found")
    return dict(row)


@router.delete("/biometric-points/{point_id}")
async def delete_biometric_point(point_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        res = await conn.execute("DELETE FROM biometric_consent_points WHERE id=$1 AND company_id=$2", point_id, company_id)
    if res.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Point not found")
    return {"status": "deleted"}


# --- Pay transparency -------------------------------------------------------

@router.get("/pay-transparency", response_model=list[PayTransparencyStateRow])
async def get_pay_transparency(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await wf.get_pay_transparency(conn, company_id)


@router.put("/pay-transparency/{state}", response_model=list[PayTransparencyStateRow])
async def set_pay_transparency(state: str, body: PayTransparencyUpdate,
                               current_user=Depends(require_admin_or_client)):
    if len(state) != 2 or not state.isalpha():
        raise HTTPException(status_code=400, detail="state must be a 2-letter code")
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await wf.set_pay_transparency(
            conn, company_id, state, status=body.status,
            postings_include_ranges=body.postings_include_ranges, note=body.note,
            updated_by=current_user.id,
        )
        return await wf.get_pay_transparency(conn, company_id)


# --- Pay-equity study register ----------------------------------------------

@router.get("/pay-equity")
async def list_pay_equity(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {_PE_COLS} FROM pay_equity_reviews WHERE company_id = $1 "
            "ORDER BY review_date DESC NULLS LAST, created_at DESC",
            company_id,
        )
    return [dict(r) for r in rows]


@router.post("/pay-equity")
async def create_pay_equity(body: PayEquityReviewCreate, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    next_due, _ = wf.audit_dates(body.review_date, body.cadence_days)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO pay_equity_reviews
                (company_id, review_date, scope, methodology, gap_pct, remediation,
                 cadence_days, next_due_date, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING {_PE_COLS}
            """,
            company_id, body.review_date, body.scope, body.methodology, body.gap_pct,
            body.remediation, body.cadence_days, next_due, body.notes, current_user.id,
        )
    return dict(row)


@router.put("/pay-equity/{review_id}")
async def update_pay_equity(review_id: UUID, body: PayEquityReviewUpdate,
                            current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        cur = await conn.fetchrow(
            "SELECT review_date, cadence_days FROM pay_equity_reviews WHERE id=$1 AND company_id=$2",
            review_id, company_id,
        )
        if not cur:
            raise HTTPException(status_code=404, detail="Review not found")
        review_date = body.review_date if body.review_date is not None else cur["review_date"]
        cadence = body.cadence_days if body.cadence_days is not None else cur["cadence_days"]
        next_due, _ = wf.audit_dates(review_date, cadence)
        row = await conn.fetchrow(
            f"""
            UPDATE pay_equity_reviews SET
                review_date = $3, scope = COALESCE($4, scope), methodology = COALESCE($5, methodology),
                gap_pct = COALESCE($6, gap_pct), remediation = COALESCE($7, remediation),
                cadence_days = $8, next_due_date = $9, notes = COALESCE($10, notes), updated_at = NOW()
            WHERE id = $1 AND company_id = $2 RETURNING {_PE_COLS}
            """,
            review_id, company_id, review_date, body.scope, body.methodology, body.gap_pct,
            body.remediation, cadence, next_due, body.notes,
        )
    return dict(row)


@router.post("/pay-equity/analyze")
async def analyze_pay_equity(current_user=Depends(require_admin_or_client)):
    """Compute within-role pay dispersion from employee comp data and log it as a
    pay-equity study (flips the EPL factor on real data). Returns analysis + the row."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        a = await pay_equity_analysis.analyze(conn, company_id)
        if a["analyzed_roles"] == 0:
            raise HTTPException(status_code=400, detail="Not enough comp data (need ≥2 employees sharing a role)")
        r = pay_equity_analysis.review_row(a)
        next_due, _ = wf.audit_dates(date.today(), 365)
        row = await conn.fetchrow(
            f"""
            INSERT INTO pay_equity_reviews
                (company_id, review_date, scope, methodology, gap_pct, remediation,
                 cadence_days, next_due_date, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,NULL,365,$6,$7,$8) RETURNING {_PE_COLS}
            """,
            company_id, date.today(), r["scope"], r["methodology"], r["gap_pct"],
            next_due, r["note"], current_user.id,
        )
    return {"analysis": a, "review": dict(row)}


@router.delete("/pay-equity/{review_id}")
async def delete_pay_equity(review_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        res = await conn.execute("DELETE FROM pay_equity_reviews WHERE id=$1 AND company_id=$2", review_id, company_id)
    if res.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": "deleted"}


# --- Summary (business dashboard) -------------------------------------------

@router.get("/summary")
async def summary(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        ai = await conn.fetchrow(
            f"SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE {_OVERDUE_EXPR}) AS overdue "
            "FROM hiring_ai_audits WHERE company_id=$1",
            company_id,
        )
        bio = await conn.fetchrow(
            "SELECT COUNT(*) FILTER (WHERE is_active) AS active, "
            "COUNT(*) FILTER (WHERE is_active AND NOT consent_obtained) AS missing_consent "
            "FROM biometric_consent_points WHERE company_id=$1",
            company_id,
        )
        pe = await conn.fetchrow(
            f"SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE {_OVERDUE_EXPR}) AS overdue "
            "FROM pay_equity_reviews WHERE company_id=$1",
            company_id,
        )
        pt = await wf.get_pay_transparency(conn, company_id)
    pt_required = [r for r in pt if r["required"]]
    return {
        "ai_audits": {"total": int(ai["total"] or 0), "overdue": int(ai["overdue"] or 0)},
        "biometric": {"active": int(bio["active"] or 0), "missing_consent": int(bio["missing_consent"] or 0)},
        "pay_equity": {"total": int(pe["total"] or 0), "overdue": int(pe["overdue"] or 0)},
        "pay_transparency": {
            "required_states": len(pt_required),
            "action_needed": sum(1 for r in pt_required if r["status"] != "compliant"),
        },
    }
