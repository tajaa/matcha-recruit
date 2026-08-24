"""The sole writer for forecast-derived inventory par levels."""

from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from app.matcha.services.inventory.waste.par import decide_par_line


async def _max_drift(conn, *, company_id: UUID, run_id: UUID) -> Decimal:
    settings = await conn.fetchrow(
        "SELECT par_max_drift_pct FROM inventory_forecast_settings WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM (SELECT location_id FROM inventory_forecast_runs WHERE id=$2)",
        company_id, run_id,
    )
    return Decimal(str(settings["par_max_drift_pct"])) if settings else Decimal("0.5")


async def _par_rows(conn, *, company_id: UUID, run_id: UUID, item_ids: Optional[list[UUID]], include_history: bool = False):
    history_join = "LEFT JOIN inventory_par_history ph ON ph.run_id=fl.run_id AND ph.item_id=fl.item_id" if include_history else ""
    history_column = ", ph.id AS already_applied" if include_history else ""
    return await conn.fetch(
        f"""
        SELECT fl.item_id, fl.status, fl.confidence, fl.recommended_par, fl.par_basis,
               fl.shelf_cap_quantity, i.low_stock_threshold AS current_par, i.par_source, i.name{history_column}
        FROM inventory_forecast_lines fl JOIN inventory_forecast_runs fr ON fr.id=fl.run_id
        JOIN inventory_items i ON i.id=fl.item_id
        {history_join}
        WHERE fl.run_id=$1 AND fr.company_id=$2
          AND ($3::uuid[] IS NULL OR fl.item_id=ANY($3::uuid[]))
        """, run_id, company_id, item_ids,
    )


async def apply_par_recommendations(conn, *, company_id: UUID, run_id: UUID, user_id: Optional[UUID], mode: Literal["auto", "manual", "huume"], item_ids: Optional[list[UUID]] = None) -> dict:
    max_drift = await _max_drift(conn, company_id=company_id, run_id=run_id)
    rows = await _par_rows(conn, company_id=company_id, run_id=run_id, item_ids=item_ids)
    out = {"considered": len(rows), "applied": 0, "skipped": [], "proposed": []}
    explicit = mode in {"manual", "huume"} and item_ids is not None
    for row in rows:
        current, recommendation = row["current_par"], row["recommended_par"]
        decision = decide_par_line(
            current_par=current, recommended_par=recommendation, par_source=row["par_source"],
            status=row["status"], confidence=row["confidence"], shelf_cap_quantity=row["shelf_cap_quantity"],
            max_drift_pct=max_drift, explicit=explicit,
        )
        allowed, reason, drift = decision["allowed"], decision["reason"], decision["drift_pct"]
        detail = {"item_id": row["item_id"], "current_par": current, "recommended_par": recommendation,
                  "par_basis": row["par_basis"], "drift_pct": drift, "reason": reason}
        if not allowed:
            out["skipped"].append({"item_id": row["item_id"], "reason": reason})
            out["proposed"].append(detail)
            continue
        try:
            async with conn.transaction():
                # Claim the (run, item) journal entry before changing the
                # mutable par.  The unique index is the idempotency boundary:
                # a retried *older* run must not overwrite a newer par just
                # because its history insert later conflicts.
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
                if inserted is None:
                    out["skipped"].append({"item_id": row["item_id"], "reason": "already_applied"})
                    continue
                updated = await conn.fetchrow(
                    "UPDATE inventory_items SET low_stock_threshold=$2, par_source=$3, updated_at=NOW() WHERE id=$1 AND company_id=$4 RETURNING id",
                    row["item_id"], recommendation, "auto" if mode == "auto" else row["par_source"], company_id,
                )
                if updated is None:
                    raise ValueError("item not found")
                out["applied"] += 1
        except Exception:
            out["skipped"].append({"item_id": row["item_id"], "reason": "write_failed"})
    return out


async def plan_par_recommendations(conn, *, company_id: UUID, run_id: UUID, mode: Literal["manual", "huume"], item_ids: Optional[list[UUID]] = None) -> dict:
    """Read-only preview of the exact gate used by the sole PAR writer."""
    max_drift = await _max_drift(conn, company_id=company_id, run_id=run_id)
    rows = await _par_rows(conn, company_id=company_id, run_id=run_id, item_ids=item_ids, include_history=True)
    explicit = mode in {"manual", "huume"} and item_ids is not None
    proposals, blocked = [], {}
    for row in rows:
        decision = decide_par_line(
            current_par=row["current_par"], recommended_par=row["recommended_par"], par_source=row["par_source"],
            status=row["status"], confidence=row["confidence"], shelf_cap_quantity=row["shelf_cap_quantity"],
            max_drift_pct=max_drift, explicit=explicit,
        )
        already_applied = row["already_applied"] is not None
        allowed = decision["allowed"] and not already_applied
        reason = "already_applied" if already_applied else decision["reason"]
        proposal = {"item_id": row["item_id"], "name": row["name"], "current_par": row["current_par"], "recommended_par": row["recommended_par"], "par_basis": row["par_basis"], "drift_pct": decision["drift_pct"], "allowed": allowed, "reason": reason, "overridable": decision["overridable"] if not already_applied else False, "already_applied": already_applied}
        proposals.append(proposal)
        if not allowed: blocked[reason] = blocked.get(reason, 0) + 1
    def ranking(line):
        delta = abs(line["recommended_par"] - line["current_par"]) if line["recommended_par"] is not None and line["current_par"] is not None else Decimal("-1")
        return (not line["allowed"], -delta, line["name"].lower())
    proposals.sort(key=ranking)
    return {"run_id": run_id, "mode": mode, "scope": "selected" if item_ids is not None else "all", "considered": len(proposals), "would_apply": sum(line["allowed"] for line in proposals), "would_skip": sum(not line["allowed"] for line in proposals), "max_drift_pct": max_drift, "blocked_by_reason": blocked, "proposals": proposals}


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
