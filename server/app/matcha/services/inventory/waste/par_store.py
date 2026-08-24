"""The sole writer for forecast-derived inventory par levels."""

from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from app.matcha.services.inventory.waste.par import (
    par_drift_pct, par_exceeds_shelf_capacity, should_auto_apply,
)


async def apply_par_recommendations(conn, *, company_id: UUID, run_id: UUID, user_id: Optional[UUID], mode: Literal["auto", "manual", "huume"], item_ids: Optional[list[UUID]] = None) -> dict:
    settings = await conn.fetchrow(
        "SELECT par_max_drift_pct FROM inventory_forecast_settings WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM (SELECT location_id FROM inventory_forecast_runs WHERE id=$2)",
        company_id, run_id,
    )
    max_drift = Decimal(str(settings["par_max_drift_pct"])) if settings else Decimal("0.5")
    rows = await conn.fetch(
        """
        SELECT fl.item_id, fl.status, fl.confidence, fl.recommended_par, fl.par_basis,
               fl.shelf_cap_quantity, i.low_stock_threshold AS current_par, i.par_source
        FROM inventory_forecast_lines fl JOIN inventory_forecast_runs fr ON fr.id=fl.run_id
        JOIN inventory_items i ON i.id=fl.item_id
        WHERE fl.run_id=$1 AND fr.company_id=$2
          AND ($3::uuid[] IS NULL OR fl.item_id=ANY($3::uuid[]))
        """, run_id, company_id, item_ids,
    )
    out = {"considered": len(rows), "applied": 0, "skipped": [], "proposed": []}
    explicit = mode in {"manual", "huume"} and item_ids is not None
    for row in rows:
        current, recommendation = row["current_par"], row["recommended_par"]
        if explicit:
            allowed, reason = should_auto_apply(
                current_par=current, recommended_par=recommendation, par_source="auto",
                status=row["status"], confidence=row["confidence"], max_drift_pct=max_drift,
            )
            if not allowed and reason in {"manual_par_pinned", "drift_exceeds_bound"}:
                allowed, reason = True, "manager_override"
        else:
            allowed, reason = should_auto_apply(
                current_par=current, recommended_par=recommendation, par_source=row["par_source"],
                status=row["status"], confidence=row["confidence"], max_drift_pct=max_drift,
            )
        drift = par_drift_pct(current, recommendation)
        detail = {"item_id": row["item_id"], "current_par": current, "recommended_par": recommendation,
                  "par_basis": row["par_basis"], "drift_pct": drift, "reason": reason}
        if not allowed:
            out["skipped"].append({"item_id": row["item_id"], "reason": reason})
            out["proposed"].append(detail)
            continue
        if par_exceeds_shelf_capacity(recommendation, row["shelf_cap_quantity"]):
            out["skipped"].append({"item_id": row["item_id"], "reason": "par_exceeds_shelf_capacity"})
            out["proposed"].append({**detail, "reason": "par_exceeds_shelf_capacity"})
            continue
        try:
            async with conn.transaction():
                updated = await conn.fetchrow(
                    "UPDATE inventory_items SET low_stock_threshold=$2, par_source=$3, updated_at=NOW() WHERE id=$1 AND company_id=$4 RETURNING id",
                    row["item_id"], recommendation, "auto" if mode == "auto" else row["par_source"], company_id,
                )
                if updated is None:
                    raise ValueError("item not found")
                inserted = await conn.fetchrow(
                    """
                    INSERT INTO inventory_par_history
                        (company_id,item_id,run_id,previous_par,new_par,par_basis,drift_pct,source,reason,changed_by)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    ON CONFLICT (run_id,item_id) WHERE run_id IS NOT NULL DO NOTHING
                    RETURNING id
                    """, company_id, row["item_id"], run_id, current, recommendation, row["par_basis"], drift,
                    mode, reason, user_id,
                )
                if inserted is not None:
                    out["applied"] += 1
        except Exception:
            out["skipped"].append({"item_id": row["item_id"], "reason": "write_failed"})
    return out


async def enroll_items_in_auto_par(conn, *, company_id: UUID, item_ids: list[UUID], enrolled: bool) -> int:
    result = await conn.execute(
        "UPDATE inventory_items SET par_source=$3, updated_at=NOW() WHERE company_id=$1 AND id=ANY($2::uuid[])",
        company_id, item_ids, "auto" if enrolled else "manual",
    )
    return int(result.rsplit(" ", 1)[-1])


async def par_history(conn, *, company_id: UUID, item_id: UUID, limit: int = 50) -> list[dict]:
    rows = await conn.fetch(
        "SELECT * FROM inventory_par_history WHERE company_id=$1 AND item_id=$2 ORDER BY changed_at DESC, id DESC LIMIT $3",
        company_id, item_id, limit,
    )
    return [dict(row) for row in rows]
