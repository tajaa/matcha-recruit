"""Broker WC portfolio rollup.

GET /broker/wc-portfolio
Returns one Workers-Comp summary row per linked client company for the
authenticated broker. Used by P&C brokers as a renewal-prep view —
sort clients by deterioration to know who needs loss-control attention.
"""

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_broker
from .ir_incidents import compute_wc_metrics
from ..services.wc_benchmarks import SEVERITY_BAND_RANK
from ..services import benefits_eligibility as be
from ..models.broker_action_center import MilestonesResponse, OutreachResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_BAND_RANK = {"critical": 0, "elevated": 1, "stable": 2}


class _ResolveBody(BaseModel):
    note: Optional[str] = None


async def _broker_clients(conn, user_id) -> tuple[UUID, dict]:
    """Resolve the broker_id + active client companies for the caller.

    Returns ``(broker_id, {company_id: {name, industry}})``. Raises 403 when the
    account has no active broker membership.
    """
    broker_id = await conn.fetchval(
        """
        SELECT broker_id FROM broker_members
        WHERE user_id = $1 AND is_active = true
        ORDER BY created_at ASC LIMIT 1
        """,
        user_id,
    )
    if not broker_id:
        raise HTTPException(status_code=403, detail="No active broker membership")
    rows = await conn.fetch(
        """
        SELECT bcl.company_id, comp.name AS company_name, comp.industry
        FROM broker_company_links bcl
        JOIN companies comp ON comp.id = bcl.company_id
        WHERE bcl.broker_id = $1 AND bcl.status IN ('active', 'grace')
        """,
        broker_id,
    )
    clients = {r["company_id"]: {"name": r["company_name"], "industry": r["industry"]} for r in rows}
    return broker_id, clients


async def _assert_broker_owns_company(conn, user_id, company_id: UUID) -> dict:
    """Verify the broker has an active link to ``company_id``; return its meta."""
    _, clients = await _broker_clients(conn, user_id)
    if company_id not in clients:
        raise HTTPException(status_code=403, detail="Broker does not have access to that company")
    return clients[company_id]


@router.get("/wc-portfolio")
async def get_wc_portfolio(current_user=Depends(require_broker)):
    """Per-client WC posture for the broker's active book."""
    async with get_connection() as conn:
        # Resolve broker_id from broker_members.
        broker_id = await conn.fetchval(
            """
            SELECT broker_id FROM broker_members
            WHERE user_id = $1 AND is_active = true
            ORDER BY created_at ASC
            LIMIT 1
            """,
            current_user.id,
        )
        if not broker_id:
            raise HTTPException(status_code=403, detail="No active broker membership")

        # Active client links + names.
        clients = await conn.fetch(
            """
            SELECT bcl.company_id, comp.name AS company_name, comp.industry
            FROM broker_company_links bcl
            JOIN companies comp ON comp.id = bcl.company_id
            WHERE bcl.broker_id = $1 AND bcl.status = 'active'
            ORDER BY comp.name
            """,
            broker_id,
        )

        results = []
        for client in clients:
            try:
                m = await compute_wc_metrics(conn, client["company_id"], period_days=365)
            except Exception as exc:
                logger.warning("wc-portfolio: compute failed for %s: %s", client["company_id"], exc)
                continue
            results.append({
                "company_id": str(client["company_id"]),
                "company_name": client["company_name"],
                "industry": client["industry"],
                "headcount": m["headcount"],
                "recordable_cases": m["recordable_cases"],
                "dart_cases": m["dart_cases"],
                "lost_days": m["lost_days"],
                "trir": m["trir"],
                "dart_rate": m["dart_rate"],
                "days_since_last_recordable": m["days_since_last_recordable"],
                "trir_delta_pct": m["prior"]["trir_delta_pct"],
                "benchmark": m["benchmark"],
                "premium_impact": m["premium_impact"],
                "severity_band": m["severity_band"],
                "data_quality": m["data_quality"],
            })

    # Sort: critical → at_risk → fair → good → unknown. Within band, worst TRIR first.
    results.sort(key=lambda r: (
        SEVERITY_BAND_RANK.get(r["severity_band"], 9),
        -(r["trir"] or 0),
    ))

    summary = {
        "client_count": len(results),
        "critical": sum(1 for r in results if r["severity_band"] == "critical"),
        "at_risk": sum(1 for r in results if r["severity_band"] == "at_risk"),
        "fair": sum(1 for r in results if r["severity_band"] == "fair"),
        "good": sum(1 for r in results if r["severity_band"] == "good"),
        "unknown": sum(1 for r in results if r["severity_band"] == "unknown"),
        "total_recordable_cases": sum(r["recordable_cases"] for r in results),
        "total_lost_days": sum(r["lost_days"] for r in results),
    }

    return {"summary": summary, "companies": results}


# ===========================================================================
# Employee-benefits broker surface  (/broker/benefits/*)
# Scope 1 — eligibility exceptions; Scope 2 — renewal risk radar.
# ===========================================================================

def _serialize_exception(r) -> dict:
    return {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "company_name": r["company_name"],
        "employee_name": r["employee_name"],
        "exception_type": r["exception_type"],
        "reference_date": r["reference_date"],
        "days_elapsed": r["days_elapsed"],
        "days_remaining": r["days_remaining"],
        "estimated_monthly_leak": float(r["estimated_monthly_leak"]) if r["estimated_monthly_leak"] is not None else None,
        "status": r["status"],
        "source": r["source"],
        "last_nudge_sent_at": r["last_nudge_sent_at"],
        "detected_at": r["detected_at"],
    }


def _serialize_dimension(r) -> dict:
    triggers = r["triggers"] if isinstance(r["triggers"], list) else []
    return {
        "dimension_type": r["dimension_type"],
        "dimension_value": r["dimension_value"],
        "risk_band": r["risk_band"],
        "turnover_pct": float(r["turnover_pct"] or 0),
        "turnover_baseline_pct": float(r["turnover_baseline_pct"] or 0),
        "turnover_delta_pct": float(r["turnover_delta_pct"] or 0),
        "lost_workdays": r["lost_workdays"],
        "lost_workdays_delta_pct": float(r["lost_workdays_delta_pct"] or 0),
        "near_misses": r["near_misses"],
        "behavioral_incidents": r["behavioral_incidents"],
        "headcount": r["headcount"],
        "gross_payroll": float(r["gross_payroll"]) if r["gross_payroll"] is not None else None,
        "triggers": triggers,
    }


@router.get("/benefits/eligibility-exceptions")
async def benefit_eligibility_exceptions(current_user=Depends(require_broker)):
    """Scope 1 task queue: open new-hire gaps + termination premium leaks across
    the broker's active book."""
    async with get_connection() as conn:
        _, clients = await _broker_clients(conn, current_user.id)
        if not clients:
            return {"summary": {"new_hire_count": 0, "termination_leak_count": 0,
                                "total_open": 0, "estimated_monthly_leak": 0.0},
                    "exceptions": []}
        rows = await conn.fetch(
            """
            SELECT e.*, comp.name AS company_name
            FROM benefit_eligibility_exceptions e
            JOIN companies comp ON comp.id = e.company_id
            WHERE e.company_id = ANY($1::uuid[]) AND e.status = 'open'
            """,
            list(clients.keys()),
        )

    exceptions = [_serialize_exception(r) for r in rows]
    # Terminations (leaks) first, then new hires by fewest days remaining.
    exceptions.sort(key=lambda e: (
        0 if e["exception_type"] == "termination_premium_leak" else 1,
        e["days_remaining"] if e["days_remaining"] is not None else 999,
    ))
    summary = {
        "new_hire_count": sum(1 for e in exceptions if e["exception_type"] == "new_hire_enrollment_gap"),
        "termination_leak_count": sum(1 for e in exceptions if e["exception_type"] == "termination_premium_leak"),
        "total_open": len(exceptions),
        "estimated_monthly_leak": round(sum(e["estimated_monthly_leak"] or 0 for e in exceptions), 2),
    }
    return {"summary": summary, "exceptions": exceptions}


@router.post("/benefits/eligibility-exceptions/{exc_id}/nudge")
async def nudge_client_hr(exc_id: UUID, current_user=Depends(require_broker)):
    """'Ping Client HR' — email the client's HR contact about this exception."""
    async with get_connection() as conn:
        broker_id, clients = await _broker_clients(conn, current_user.id)
        row = await conn.fetchrow(
            """
            SELECT e.*, comp.name AS company_name
            FROM benefit_eligibility_exceptions e
            JOIN companies comp ON comp.id = e.company_id
            WHERE e.id = $1
            """,
            exc_id,
        )
        if not row or row["company_id"] not in clients:
            raise HTTPException(status_code=404, detail="Exception not found")
        contact = await conn.fetchrow(
            """
            SELECT contact_email, contact_name FROM broker_client_setups
            WHERE broker_id = $1 AND company_id = $2 AND contact_email IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            broker_id, row["company_id"],
        )
        to_email = contact["contact_email"] if contact else None
        to_name = contact["contact_name"] if contact else None
        if not to_email:
            to_email = await conn.fetchval(
                "SELECT u.email FROM companies c JOIN users u ON u.id = c.owner_id WHERE c.id = $1",
                row["company_id"],
            )
        broker_name = await conn.fetchval("SELECT name FROM brokers WHERE id = $1", broker_id)

    if not to_email:
        raise HTTPException(status_code=400, detail="No client HR contact on file to notify")

    from ...core.services.email import get_email_service
    svc = get_email_service()
    sent = await svc.send_benefit_eligibility_nudge_email(
        to_email=to_email,
        to_name=to_name,
        broker_name=broker_name or "Your broker",
        company_name=row["company_name"],
        employee_name=row["employee_name"],
        exception_type=row["exception_type"],
        days_remaining=row["days_remaining"],
    )

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE benefit_eligibility_exceptions SET last_nudge_sent_at = NOW() WHERE id = $1",
            exc_id,
        )
    return {"status": "sent" if sent else "skipped"}


async def _set_exception_status(exc_id: UUID, status: str, note, current_user) -> dict:
    async with get_connection() as conn:
        _, clients = await _broker_clients(conn, current_user.id)
        row = await conn.fetchrow(
            """
            SELECT e.*, comp.name AS company_name
            FROM benefit_eligibility_exceptions e
            JOIN companies comp ON comp.id = e.company_id
            WHERE e.id = $1
            """,
            exc_id,
        )
        if not row or row["company_id"] not in clients:
            raise HTTPException(status_code=404, detail="Exception not found")
        updated = await conn.fetchrow(
            """
            UPDATE benefit_eligibility_exceptions
            SET status = $2, resolution_note = $3, resolved_at = NOW()
            WHERE id = $1
            RETURNING *, (SELECT name FROM companies WHERE id = company_id) AS company_name
            """,
            exc_id, status, note,
        )
    return _serialize_exception(updated)


@router.post("/benefits/eligibility-exceptions/{exc_id}/resolve")
async def resolve_exception(exc_id: UUID, body: Optional[_ResolveBody] = None,
                            current_user=Depends(require_broker)):
    return await _set_exception_status(exc_id, "resolved", body.note if body else None, current_user)


@router.post("/benefits/eligibility-exceptions/{exc_id}/dismiss")
async def dismiss_exception(exc_id: UUID, body: Optional[_ResolveBody] = None,
                           current_user=Depends(require_broker)):
    return await _set_exception_status(exc_id, "dismissed", body.note if body else None, current_user)


@router.get("/benefits/renewal-radar")
async def renewal_radar(current_user=Depends(require_broker)):
    """Scope 2 portfolio radar: one company-level risk row per active client."""
    async with get_connection() as conn:
        _, clients = await _broker_clients(conn, current_user.id)
        if not clients:
            return {"summary": {"client_count": 0, "stable": 0, "elevated": 0, "critical": 0},
                    "companies": []}
        rows = await conn.fetch(
            """
            SELECT * FROM benefit_renewal_risk
            WHERE company_id = ANY($1::uuid[]) AND dimension_type = 'company'
            """,
            list(clients.keys()),
        )

    companies = []
    for r in rows:
        meta = clients.get(r["company_id"], {})
        triggers = r["triggers"] if isinstance(r["triggers"], list) else []
        companies.append({
            "company_id": str(r["company_id"]),
            "company_name": meta.get("name"),
            "industry": meta.get("industry"),
            "risk_band": r["risk_band"],
            "policy_month": r["policy_month"],
            "turnover_pct": float(r["turnover_pct"] or 0),
            "turnover_delta_pct": float(r["turnover_delta_pct"] or 0),
            "lost_workdays": r["lost_workdays"],
            "near_misses": r["near_misses"],
            "behavioral_incidents": r["behavioral_incidents"],
            "headcount": r["headcount"],
            "top_trigger": triggers[0] if triggers else None,
            "computed_at": r["computed_at"],
        })
    companies.sort(key=lambda c: _BAND_RANK.get(c["risk_band"], 9))
    summary = {
        "client_count": len(companies),
        "stable": sum(1 for c in companies if c["risk_band"] == "stable"),
        "elevated": sum(1 for c in companies if c["risk_band"] == "elevated"),
        "critical": sum(1 for c in companies if c["risk_band"] == "critical"),
    }
    return {"summary": summary, "companies": companies}


async def _renewal_detail(conn, company_id: UUID, company_name: str) -> dict:
    rows = await conn.fetch(
        "SELECT * FROM benefit_renewal_risk WHERE company_id = $1 ORDER BY dimension_type, dimension_value",
        company_id,
    )
    dims = [_serialize_dimension(r) for r in rows]
    worst = min((d["risk_band"] for d in dims), key=lambda b: _BAND_RANK.get(b, 9), default="stable")
    return {
        "company_id": str(company_id),
        "company_name": company_name,
        "risk_band": worst,
        "policy_month": next((r["policy_month"] for r in rows if r["policy_month"] is not None), None),
        "recommendation": be.build_recommendation(dims),
        "dimensions": dims,
    }


@router.get("/benefits/renewal-radar/{company_id}")
async def renewal_radar_detail(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        return await _renewal_detail(conn, company_id, meta["name"])


@router.get("/benefits/renewal-radar/{company_id}/stabilization-kit.pdf")
async def stabilization_kit(company_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        detail = await _renewal_detail(conn, company_id, meta["name"])
    pdf = await be.render_stabilization_kit_pdf(meta["name"], detail)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="stabilization-kit.pdf"'},
    )


@router.get("/benefits/roster/template")
async def benefit_roster_template(current_user=Depends(require_broker)):
    """CSV template for the source-agnostic roster upload. Reserved-domain
    sample rows only (RFC 2606) — never real-looking domains."""
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


@router.post("/benefits/roster/upload")
async def benefit_roster_upload(
    company_id: UUID = Query(...),
    file: UploadFile = File(...),
    current_user=Depends(require_broker),
):
    """Broker uploads a client's roster CSV (for clients without an HRIS feed),
    then immediately re-runs detection + risk for that client."""
    content = await file.read()
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        ingested = await be.ingest_roster_from_csv(conn, company_id, content)
        exc = await be.detect_eligibility_exceptions(conn, company_id)
        risk = await be.compute_renewal_risk(conn, company_id)
    return {"ingested": ingested, "exceptions_detected": exc["detected"], "risk": risk}


# ===========================================================================
# Action Center  (/broker/action-center/*)
# Milestones feed (written by the broker_milestones Celery task) + on-demand
# AI consultative outreach. The Alerts / Renewals / Eligibility tabs reuse the
# existing feeds; only these two surfaces are net-new.
# ===========================================================================

def _serialize_milestone(r) -> dict:
    return {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "company_name": r["company_name"],
        "milestone_key": r["milestone_key"],
        "milestone_family": r["milestone_family"],
        "tier": r["tier"],
        "title": r["title"],
        "detail": r["detail"],
        "current_value": float(r["current_value"]) if r["current_value"] is not None else None,
        "benchmark_value": float(r["benchmark_value"]) if r["benchmark_value"] is not None else None,
        "is_read": r["is_read"],
        "achieved_at": r["achieved_at"].isoformat() if r["achieved_at"] else None,
        "superseded_at": r["superseded_at"].isoformat() if r["superseded_at"] else None,
    }


@router.get("/action-center/milestones", response_model=MilestonesResponse)
async def action_center_milestones(
    include_superseded: bool = Query(False),
    current_user=Depends(require_broker),
):
    """Positive client milestones across the broker's active book."""
    import asyncpg

    async with get_connection() as conn:
        broker_id, clients = await _broker_clients(conn, current_user.id)
        if not clients:
            return {"summary": {"total": 0, "unread": 0}, "milestones": []}
        try:
            rows = await conn.fetch(
                """
                SELECT m.id, m.company_id, c.name AS company_name, m.milestone_key,
                       m.milestone_family, m.tier, m.title, m.detail, m.current_value,
                       m.benchmark_value, m.is_read, m.achieved_at, m.superseded_at
                FROM broker_milestones m
                JOIN companies c ON c.id = m.company_id
                WHERE m.broker_id = $1
                  AND m.company_id = ANY($2::uuid[])
                  AND ($3::bool OR m.superseded_at IS NULL)
                ORDER BY (m.superseded_at IS NOT NULL), m.achieved_at DESC
                """,
                broker_id, list(clients.keys()), include_superseded,
            )
        except asyncpg.exceptions.UndefinedTableError:
            # Migration brokermile01 not applied yet — the sidebar polls this on
            # every broker page load, so degrade to empty instead of 500-spamming
            # the error reporter until the table exists.
            return {"summary": {"total": 0, "unread": 0}, "milestones": []}
    milestones = [_serialize_milestone(r) for r in rows]
    summary = {
        "total": len(milestones),
        "unread": sum(1 for m in milestones if not m["is_read"] and m["superseded_at"] is None),
    }
    return {"summary": summary, "milestones": milestones}


@router.post("/action-center/milestones/{milestone_id}/read")
async def mark_milestone_read(milestone_id: UUID, current_user=Depends(require_broker)):
    async with get_connection() as conn:
        broker_id, _ = await _broker_clients(conn, current_user.id)
        result = await conn.execute(
            "UPDATE broker_milestones SET is_read = true WHERE id = $1 AND broker_id = $2",
            milestone_id, broker_id,
        )
    if result.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"status": "ok"}


@router.get("/action-center/outreach/{company_id}", response_model=OutreachResponse)
async def action_center_outreach(
    company_id: UUID,
    refresh: bool = Query(False),
    current_user=Depends(require_broker),
):
    """AI consultative outreach prompts for ONE client, grounded in anonymized
    aggregate trends. Cached 24h per (broker, company)."""
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id, _ = await _broker_clients(conn, current_user.id)

        if not refresh:
            cached = await conn.fetchrow(
                "SELECT payload, generated_at FROM broker_outreach_cache "
                "WHERE broker_id = $1 AND company_id = $2 AND expires_at > NOW()",
                broker_id, company_id,
            )
            if cached:
                payload = cached["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return {
                    "company_id": str(company_id), "company_name": meta["name"], "cached": True,
                    "prompts": payload.get("prompts", []), "model": payload.get("model"),
                    "generated_at": cached["generated_at"].isoformat() if cached["generated_at"] else None,
                }

        # Gather aggregate inputs while we hold the connection.
        wc = await compute_wc_metrics(conn, company_id)
        from .ir_incidents import compute_behavioral_friction
        behavioral = await compute_behavioral_friction(conn, company_id)
        renewal = await conn.fetchrow(
            "SELECT * FROM benefit_renewal_risk WHERE company_id = $1 AND dimension_type = 'company'",
            company_id,
        )
        milestone_rows = await conn.fetch(
            "SELECT milestone_family, tier, title FROM broker_milestones "
            "WHERE broker_id = $1 AND company_id = $2 AND superseded_at IS NULL",
            broker_id, company_id,
        )

    # Gemini call happens OUTSIDE any pooled connection so a slow model call
    # doesn't hold a connection.
    from ..services.broker_outreach import generate_outreach_prompts
    result = await generate_outreach_prompts(
        company_name=meta["name"],
        wc_metrics=wc,
        behavioral=behavioral,
        renewal_risk=dict(renewal) if renewal else None,
        milestones=[dict(m) for m in milestone_rows],
    )

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO broker_outreach_cache (broker_id, company_id, payload, expires_at)
            VALUES ($1, $2, $3::jsonb, NOW() + interval '24 hours')
            ON CONFLICT (broker_id, company_id) DO UPDATE SET
                payload = EXCLUDED.payload, generated_at = NOW(), expires_at = EXCLUDED.expires_at
            """,
            broker_id, company_id, json.dumps(result),
        )

    return {
        "company_id": str(company_id), "company_name": meta["name"], "cached": False,
        "prompts": result["prompts"], "model": result.get("model"), "generated_at": None,
    }
