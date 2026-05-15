"""Broker WC portfolio rollup.

GET /broker/wc-portfolio
Returns one Workers-Comp summary row per linked client company for the
authenticated broker. Used by P&C brokers as a renewal-prep view —
sort clients by deterioration to know who needs loss-control attention.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException

from ...database import get_connection
from ..dependencies import require_broker
from .ir_incidents import compute_wc_metrics
from ..services.wc_benchmarks import SEVERITY_BAND_RANK

logger = logging.getLogger(__name__)

router = APIRouter()


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
