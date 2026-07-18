"""Broker WC portfolio rollup.

GET /broker/wc-portfolio
Returns one Workers-Comp summary row per linked client company for the
authenticated broker. Used by P&C brokers as a renewal-prep view —
sort clients by deterioration to know who needs loss-control attention.
"""

import json
import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.database import get_connection
from app.matcha.dependencies import require_broker
from app.matcha.routes.ir_incidents import compute_wc_metrics
from app.matcha.services.wc_benchmarks import SEVERITY_BAND_RANK
from app.matcha.services import benefits_eligibility as be
from app.matcha.services import wc_depth
from app.matcha.services import wc_mod_parser
from app.matcha.services import epl_readiness
from app.matcha.services import risk_index
from app.matcha.services import external_clients as ext
from app.matcha.services import property_sov
from app.matcha.services import property_cat
from app.matcha.services import wc_classmap
from app.matcha.models.broker_action_center import MilestonesResponse, OutreachResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_BAND_RANK = {"critical": 0, "elevated": 1, "stable": 2}


class _ResolveBody(BaseModel):
    note: Optional[str] = None


class WcModCreate(BaseModel):
    """Broker-recorded experience-modification-rate (EMR) for a client policy period."""
    policy_period_start: date
    policy_period_end: Optional[date] = None
    experience_mod: float = Field(..., gt=0, le=10)
    carrier: Optional[str] = None
    annual_premium: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    # 'manual' = keyed; 'worksheet' = confirmed from a parsed bureau worksheet PDF.
    source: str = Field(default="manual", pattern="^(manual|worksheet)$")


class EplAttestationUpdate(BaseModel):
    """Broker-recorded status for an EPL underwriting ask Matcha can't derive."""
    status: str = Field(..., pattern="^(in_place|partial|gap|unknown)$")
    note: Optional[str] = None


class WcClassExposureCreate(BaseModel):
    """Broker-recorded WC class-code exposure for a client (payroll/headcount)."""
    class_code: str = Field(..., min_length=1, max_length=8)
    state: str = Field(default="US", min_length=2, max_length=2)
    payroll: Optional[float] = Field(default=None, ge=0)
    headcount: Optional[int] = Field(default=None, ge=0)
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
        all_states: set[str] = set()
        for client in clients:
            try:
                m = await compute_wc_metrics(conn, client["company_id"], period_days=365)
            except Exception as exc:
                logger.warning("wc-portfolio: compute failed for %s: %s", client["company_id"], exc)
                continue
            states = await wc_depth.resolve_company_states(conn, client["company_id"])
            all_states.update(states)
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
                # WC depth (wcdeep01): claim taxonomy, post-term, RTW, jurisdiction, mod.
                "claim_breakdown": m["claim_breakdown"],
                "post_termination_cases": m["post_termination_cases"],
                "rtw": m["rtw"],
                "primary_state": states[0] if states else None,
            })

        # Batch the jurisdiction + mod lookups across the whole book (1 query each).
        state_rates = await wc_depth.get_state_rates(conn, all_states)
        latest_mods = await wc_depth.latest_mods(conn, [c["company_id"] for c in clients])

    for r in results:
        r["state_rate"] = state_rates.get(r["primary_state"]) if r["primary_state"] else None
        r["latest_mod"] = latest_mods.get(r["company_id"])

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
        # WC depth aggregates.
        "total_ct_cases": sum(r["claim_breakdown"]["cumulative_trauma"] for r in results),
        "total_post_termination": sum(r["post_termination_cases"] for r in results),
        "total_open_lost_time": sum(r["rtw"]["open"] for r in results),
        "clients_in_rate_increase_states": sum(
            1 for r in results if r["state_rate"] and r["state_rate"]["trend"] == "increase"
        ),
    }

    return {"summary": summary, "companies": results}


# ---------------------------------------------------------------------------
# WC depth (wcdeep01): per-client detail + experience-mod entry + NCCI overlay
# ---------------------------------------------------------------------------

@router.get("/wc-portfolio/{company_id}")
async def get_wc_client_detail(company_id: UUID, current_user=Depends(require_broker)):
    """Deep WC view for one client: full metrics (incl. quarterly + claim depth),
    experience-mod trajectory, and the NCCI rate trend for each operating state."""
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        metrics = await compute_wc_metrics(conn, company_id, period_days=365)
        states = await wc_depth.resolve_company_states(conn, company_id)
        state_rates = await wc_depth.get_state_rates(conn, states)
        mods = await wc_depth.mod_trajectory(conn, company_id)
        mod_proxy = await wc_depth.mod_proxy_trajectory(conn, company_id)

    return {
        "company_id": str(company_id),
        "company_name": meta["name"],
        "metrics": metrics,
        "states": [
            {"state": s, "rate": state_rates.get(s)} for s in states
        ],
        "primary_state": states[0] if states else None,
        "mods": mods,
        "mod_proxy": mod_proxy,
    }


@router.get("/wc-portfolio/{company_id}/mods")
async def list_wc_mods(company_id: UUID, current_user=Depends(require_broker)):
    """Experience-mod (EMR) trajectory for a client, oldest period first — recorded
    real mods (manual + parsed worksheet) plus the auto directional proxy series."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        mods = await wc_depth.mod_trajectory(conn, company_id)
        mod_proxy = await wc_depth.mod_proxy_trajectory(conn, company_id)
    return {"company_id": str(company_id), "mods": mods, "mod_proxy": mod_proxy}


@router.post("/wc-portfolio/{company_id}/mods/parse")
async def parse_wc_mod_worksheet(company_id: UUID, file: UploadFile = File(...),
                                 current_user=Depends(require_broker)):
    """Auto-extract the real experience mod from an uploaded bureau experience-rating
    worksheet PDF (no manual keying). Returns a draft the broker confirms via POST
    /mods (source='worksheet'); never auto-commits. The PDF is parsed and discarded."""
    is_pdf = (file.content_type == "application/pdf") or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Upload a PDF experience-rating worksheet")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 15_000_000:
        raise HTTPException(status_code=413, detail="PDF too large (max 15 MB)")
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
    return await wc_mod_parser.parse_mod_worksheet(data)


@router.post("/wc-portfolio/{company_id}/mods")
async def record_wc_mod(company_id: UUID, body: WcModCreate,
                        current_user=Depends(require_broker)):
    """Record (or update) a client's experience mod for a policy period.

    Upserts on (company_id, policy_period_start) so re-entering a period corrects
    rather than duplicates."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id, _ = await _broker_clients(conn, current_user.id)
        row = await conn.fetchrow(
            """
            INSERT INTO company_wc_mods
                (company_id, broker_id, policy_period_start, policy_period_end,
                 experience_mod, carrier, annual_premium, note, source, recorded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT ON CONSTRAINT uq_company_wc_mod DO UPDATE SET
                policy_period_end = EXCLUDED.policy_period_end,
                experience_mod    = EXCLUDED.experience_mod,
                carrier           = EXCLUDED.carrier,
                annual_premium    = EXCLUDED.annual_premium,
                note              = EXCLUDED.note,
                source            = EXCLUDED.source,
                recorded_by       = EXCLUDED.recorded_by
            RETURNING id, company_id, policy_period_start, policy_period_end,
                      experience_mod, carrier, annual_premium, note, source, created_at
            """,
            company_id, broker_id, body.policy_period_start, body.policy_period_end,
            body.experience_mod, body.carrier, body.annual_premium, body.note, body.source,
            current_user.id,
        )
    return wc_depth._serialize_mod(row)


@router.delete("/wc-portfolio/{company_id}/mods/{mod_id}")
async def delete_wc_mod(company_id: UUID, mod_id: UUID,
                        current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        result = await conn.execute(
            "DELETE FROM company_wc_mods WHERE id = $1 AND company_id = $2",
            mod_id, company_id,
        )
    if result.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Mod entry not found")
    return {"status": "deleted"}


@router.get("/wc-state-rates")
async def get_wc_state_rates(current_user=Depends(require_broker)):
    """NCCI loss-cost rate trend by state — reference panel + jurisdiction lens."""
    async with get_connection() as conn:
        rates = await wc_depth.list_state_rates(conn)
    return {"rates": rates}


@router.get("/wc-class-codes")
async def get_wc_class_codes(current_user=Depends(require_broker)):
    """Reference NCCI class codes (illustrative seed pending a licensed feed)."""
    async with get_connection() as conn:
        return {"class_codes": await wc_depth.list_class_codes(conn)}


@router.get("/wc-portfolio/{company_id}/class-exposures")
async def list_class_exposures(company_id: UUID, current_user=Depends(require_broker)):
    """A client's WC class-code exposures + estimated manual premium per class."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        return {"exposures": await wc_depth.class_exposures(conn, company_id)}


@router.post("/wc-portfolio/{company_id}/class-exposures")
async def record_class_exposure(company_id: UUID, body: WcClassExposureCreate,
                                current_user=Depends(require_broker)):
    """Record a client's payroll/headcount for one WC class code."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id, _ = await _broker_clients(conn, current_user.id)
        await conn.execute(
            """
            INSERT INTO company_wc_class_exposures
                (company_id, broker_id, class_code, state, payroll, headcount, note, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            company_id, broker_id, body.class_code.strip(), body.state.upper(),
            body.payroll, body.headcount, body.note, current_user.id,
        )
        return {"exposures": await wc_depth.class_exposures(conn, company_id)}


@router.post("/wc-portfolio/{company_id}/class-exposures/auto")
async def auto_map_class_exposures(company_id: UUID, current_user=Depends(require_broker)):
    """Derive proposed class exposures from the client's employees (AI title→class map).
    Returns proposals only — the broker reviews and saves via the normal create route."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        return await wc_classmap.auto_map(conn, company_id)


@router.delete("/wc-portfolio/{company_id}/class-exposures/{exposure_id}")
async def delete_class_exposure(company_id: UUID, exposure_id: UUID,
                                current_user=Depends(require_broker)):
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        result = await conn.execute(
            "DELETE FROM company_wc_class_exposures WHERE id = $1 AND company_id = $2",
            exposure_id, company_id,
        )
    if result.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Class exposure not found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# EPL readiness (epldeep01): turn HR hygiene into an EPL underwriting-readiness
# score + a "what underwriters will ask" checklist the broker takes to market.
# ---------------------------------------------------------------------------

_EPL_BAND_RANK = {"exposed": 0, "developing": 1, "adequate": 2, "strong": 3}


@router.get("/epl-portfolio")
async def get_epl_portfolio(current_user=Depends(require_broker)):
    """EPL-readiness rollup across the broker's active book — one row per client."""
    async with get_connection() as conn:
        _, clients = await _broker_clients(conn, current_user.id)
        results = []
        for company_id, meta in clients.items():
            try:
                a = await epl_readiness.compute_epl_readiness(conn, company_id)
            except Exception as exc:
                logger.warning("epl-portfolio: compute failed for %s: %s", company_id, exc)
                continue
            results.append({
                "company_id": str(company_id),
                "company_name": meta["name"],
                "industry": meta["industry"],
                "score": a["score"],
                "band": a["band"],
                "derived_score": a["derived_score"],
                "attested_score": a["attested_score"],
                "top_gap": epl_readiness.top_gap(a),
            })

    # Worst readiness first.
    results.sort(key=lambda r: (_EPL_BAND_RANK.get(r["band"], 9), r["score"]))
    summary = {
        "client_count": len(results),
        "strong": sum(1 for r in results if r["band"] == "strong"),
        "adequate": sum(1 for r in results if r["band"] == "adequate"),
        "developing": sum(1 for r in results if r["band"] == "developing"),
        "exposed": sum(1 for r in results if r["band"] == "exposed"),
        "avg_score": round(sum(r["score"] for r in results) / len(results)) if results else 0,
    }
    return {"summary": summary, "companies": results}


@router.get("/epl-portfolio/{company_id}")
async def get_epl_client_detail(company_id: UUID, current_user=Depends(require_broker)):
    """Full EPL-readiness breakdown for one client: score + per-factor checklist."""
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        assessment = await epl_readiness.compute_epl_readiness(conn, company_id)
    return {"company_name": meta["name"], **assessment}


@router.get("/risk-index")
async def get_risk_index_portfolio(current_user=Depends(require_broker)):
    """Composite risk-index rollup across the book — one benchmarkable number per client."""
    async with get_connection() as conn:
        _, clients = await _broker_clients(conn, current_user.id)
        results = []
        for company_id, meta in clients.items():
            try:
                r = await risk_index.compute_risk_index(conn, company_id)
            except Exception as exc:
                logger.warning("risk-index: compute failed for %s: %s", company_id, exc)
                continue
            if r["index"] is None:
                continue
            results.append({
                "company_id": str(company_id), "company_name": meta["name"],
                "industry": meta["industry"], "index": r["index"], "band": r["band"],
                "components": r["components"], "index_confidence": r.get("index_confidence"),
            })
    results.sort(key=lambda r: (_EPL_BAND_RANK.get(r["band"], 9), r["index"]))
    scored = [r for r in results if r["index"] is not None]
    summary = {
        "client_count": len(results),
        "strong": sum(1 for r in results if r["band"] == "strong"),
        "adequate": sum(1 for r in results if r["band"] == "adequate"),
        "developing": sum(1 for r in results if r["band"] == "developing"),
        "exposed": sum(1 for r in results if r["band"] == "exposed"),
        "avg_index": round(sum(r["index"] for r in scored) / len(scored)) if scored else 0,
    }
    return {"summary": summary, "companies": results}


@router.get("/property-portfolio")
async def get_property_portfolio(current_user=Depends(require_broker)):
    """Per-client commercial-property posture across the book — TIV, COPE grade,
    insurance-to-value, and worst catastrophe tier. Batched (no per-client build_sov)."""
    async with get_connection() as conn:
        _, clients = await _broker_clients(conn, current_user.id)
        ids = list(clients.keys())
        rollups = await property_sov.book_sov_rollups(conn, ids)
        cats = await property_cat.book_cat_exposure(conn, ids)
    results = []
    for cid, meta in clients.items():
        r = rollups.get(str(cid))
        if not r or not r["building_count"]:
            continue
        cat = cats.get(str(cid)) or {}
        results.append({
            "company_id": str(cid), "company_name": meta["name"], "industry": meta["industry"],
            "building_count": r["building_count"], "tiv": r["tiv"],
            "avg_cope_score": r["avg_cope_score"], "worst_cope_grade": r["worst_cope_grade"],
            "itv_ratio": r["itv"]["portfolio_ratio"], "under_insured": r["itv"]["under_count"],
            "worst_cat_tier": cat.get("worst_tier"),
            "worst_peril": cat.get("worst_peril"),
            "by_peril_detail": cat.get("by_peril_detail", {}),
        })
    # worst COPE + biggest TIV first (most underwriting attention)
    _grade = {"D": 0, "C": 1, "B": 2, "A": 3, None: 4}
    results.sort(key=lambda x: (_grade.get(x["worst_cope_grade"], 4), -(x["tiv"] or 0)))
    summary = {
        "client_count": len(results),
        "total_tiv": round(sum(x["tiv"] or 0 for x in results)),
        "under_insured_clients": sum(1 for x in results if x["under_insured"]),
        "severe_cat_clients": sum(1 for x in results if x["worst_cat_tier"] in ("severe", "high")),
    }
    return {"summary": summary, "companies": results}


@router.get("/property-portfolio/{company_id}")
async def get_property_client_detail(company_id: UUID, current_user=Depends(require_broker)):
    """Full SOV + catastrophe exposure for one owned client."""
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        sov = await property_sov.build_sov(conn, company_id)
        cat = await property_cat.company_cat_exposure(conn, company_id)
    return {**sov, "cat": cat}


@router.get("/risk-curve")
async def get_book_risk_curve(current_user=Depends(require_broker)):
    """Whole-book data for the interactive exposure-weighted risk curve.

    One row per client — on-platform tenants plus, for Broker Pro, off-platform
    external clients — carrying the composite risk index + exposure (headcount,
    annual premium). The curve and the weighted aggregate are recomputed client-side
    as the broker selects/deselects clients; ``default_aggregate`` is the
    all-selected headcount-weighted roll-up (also what a future packet PDF embeds)."""
    async with get_connection() as conn:
        broker_id, clients = await _broker_clients(conn, current_user.id)
        company_ids = list(clients.keys())

        # Batch the exposure signals to avoid N+1: headcount + latest WC premium.
        headcount_by_id: dict = {}
        if company_ids:
            hc_rows = await conn.fetch(
                "SELECT company_id, headcount FROM company_handbook_profiles "
                "WHERE company_id = ANY($1::uuid[])",
                company_ids,
            )
            headcount_by_id = {r["company_id"]: r["headcount"] for r in hc_rows}
        mods = await wc_depth.latest_mods(conn, company_ids) if company_ids else {}

        out: list[dict] = []
        for company_id, meta in clients.items():
            try:
                r = await risk_index.compute_risk_index(conn, company_id)
            except Exception as exc:
                logger.warning("risk-curve: compute failed for %s: %s", company_id, exc)
                continue
            if r["index"] is None:
                continue
            out.append({
                "id": str(company_id), "source": "platform",
                "name": meta["name"], "industry": meta["industry"],
                "index": r["index"], "band": r["band"], "confidence": r.get("index_confidence"),
                "headcount": headcount_by_id.get(company_id),
                "annual_premium": (mods.get(str(company_id)) or {}).get("annual_premium"),
            })
        platform_count = len(out)

        # Off-platform external book — Broker Pro only. Inline the plan check (not the
        # require_broker_pro dep, which raises 403) so non-Pro brokers degrade to their
        # on-platform book instead of erroring.
        plan = await conn.fetchval(
            """
            SELECT b.plan FROM brokers b
            JOIN broker_members bm ON bm.broker_id = b.id
            WHERE bm.user_id = $1 AND bm.is_active = true
            ORDER BY bm.created_at ASC LIMIT 1
            """,
            current_user.id,
        )
        is_pro = plan == "pro"
        if is_pro:
            for c in await ext.list_with_scores(conn, broker_id):
                if c.get("risk_index") is None:
                    continue
                out.append({
                    "id": c["id"], "source": "external",
                    "name": c["name"], "industry": c["industry"],
                    "index": c["risk_index"], "band": c["risk_band"],
                    "confidence": c.get("risk_confidence"),
                    "headcount": c["headcount"],
                    "annual_premium": c.get("annual_premium"),
                })

    counts = {
        "platform": platform_count,
        "external": len(out) - platform_count,
        "missing_headcount": sum(1 for c in out if not c["headcount"]),
        "missing_premium": sum(1 for c in out if not c["annual_premium"]),
    }
    return {
        "is_pro": is_pro,
        "clients": out,
        "default_aggregate": risk_index.weighted_book_risk(out, "headcount"),
        "counts": counts,
    }


@router.get("/risk-index/{company_id}")
async def get_risk_index_client(company_id: UUID, current_user=Depends(require_broker)):
    """Composite risk index + component breakdown + top fixes for one client."""
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        result = await risk_index.compute_risk_index(conn, company_id)
    return {"company_name": meta["name"], **result}


@router.post("/risk-index/{company_id}/narrative")
async def get_risk_index_narrative(company_id: UUID, current_user=Depends(require_broker)):
    """AI explanation + prioritized moves for one client, written for the broker."""
    from app.matcha.services import risk_narrative
    async with get_connection() as conn:
        meta = await _assert_broker_owns_company(conn, current_user.id, company_id)
        result = await risk_index.compute_risk_index(conn, company_id)
    return await risk_narrative.narrative(result, company_name=meta["name"], audience="broker")


@router.put("/epl-portfolio/{company_id}/attestations/{item_key}")
async def upsert_epl_attestation(company_id: UUID, item_key: str,
                                 body: EplAttestationUpdate,
                                 current_user=Depends(require_broker)):
    """Record the broker's status for one non-derivable EPL underwriting ask."""
    if item_key not in epl_readiness.ATTESTED_KEYS:
        raise HTTPException(status_code=400, detail="Unknown EPL attestation item")
    async with get_connection() as conn:
        await _assert_broker_owns_company(conn, current_user.id, company_id)
        broker_id, _ = await _broker_clients(conn, current_user.id)
        await conn.execute(
            """
            INSERT INTO company_epl_attestations
                (company_id, broker_id, item_key, status, note, updated_by, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT ON CONSTRAINT uq_company_epl_attestation DO UPDATE SET
                status = EXCLUDED.status, note = EXCLUDED.note,
                broker_id = EXCLUDED.broker_id, updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            company_id, broker_id, item_key, body.status, body.note, current_user.id,
        )
        assessment = await epl_readiness.compute_epl_readiness(conn, company_id)
    return assessment


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

    from app.core.services.email import get_email_service
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
    from app.matcha.services.broker_outreach import generate_outreach_prompts
    result = await generate_outreach_prompts(
        company_name=meta["name"],
        wc_metrics=wc,
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
