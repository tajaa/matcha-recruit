"""Database persistence and input assembly for inventory forecasts."""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.matcha.services.inventory.forecast import build_reorder_plan, forecast_item
from app.matcha.services.inventory.waste.par import recommend_par


DEFAULT_SETTINGS = {
    "horizon_days": 56,
    "history_days": 90,
    "default_lead_time_days": 7,
    "default_safety_stock_days": 7,
    "timezone": "America/Los_Angeles",
    "par_auto_apply": False,
    "par_max_drift_pct": Decimal("0.5"),
}


def _jsonable(value):
    if isinstance(value, (date, Decimal)):
        return value.isoformat() if isinstance(value, date) else str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _json_object(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _settings_dict(row) -> dict:
    values = dict(DEFAULT_SETTINGS)
    if row is not None:
        values.update({key: row[key] for key in DEFAULT_SETTINGS if row[key] is not None})
        values["id"] = row["id"]
        values["company_id"] = row["company_id"]
        values["location_id"] = row["location_id"]
        values["created_at"] = row["created_at"]
        values["updated_at"] = row["updated_at"]
        values["configured"] = True
    else:
        values.update({"location_id": None, "configured": False})
    return values


async def validate_location(conn, company_id: UUID, location_id: Optional[UUID]) -> None:
    if location_id is None:
        return
    exists = await conn.fetchval(
        """SELECT 1 FROM business_locations
           WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE
             AND is_company_wide=FALSE""",
        location_id,
        company_id,
    )
    if not exists:
        raise ValueError("location not found")


async def get_settings(conn, company_id: UUID, location_id: Optional[UUID]) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM inventory_forecast_settings "
        "WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM $2",
        company_id,
        location_id,
    )
    return _settings_dict(row)


async def upsert_settings(conn, *, company_id: UUID, user_id: UUID, values: dict) -> dict:
    location_id = values.get("location_id")
    await validate_location(conn, company_id, location_id)
    row = await conn.fetchrow(
        """
        INSERT INTO inventory_forecast_settings
            (company_id, location_id, horizon_days, history_days,
             default_lead_time_days, default_safety_stock_days, timezone, par_auto_apply, par_max_drift_pct, updated_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (company_id, location_id) DO UPDATE SET
            horizon_days=EXCLUDED.horizon_days,
            history_days=EXCLUDED.history_days,
            default_lead_time_days=EXCLUDED.default_lead_time_days,
            default_safety_stock_days=EXCLUDED.default_safety_stock_days,
            timezone=EXCLUDED.timezone,
            par_auto_apply=EXCLUDED.par_auto_apply,
            par_max_drift_pct=EXCLUDED.par_max_drift_pct,
            updated_by=EXCLUDED.updated_by,
            updated_at=NOW()
        RETURNING *
        """,
        company_id,
        location_id,
        values["horizon_days"],
        values["history_days"],
        values["default_lead_time_days"],
        values["default_safety_stock_days"],
        values["timezone"],
        values.get("par_auto_apply", False),
        values.get("par_max_drift_pct", Decimal("0.5")),
        user_id,
    )
    return _settings_dict(row)


async def list_par_auto_apply_scopes(conn, *, company_id: UUID) -> list[Optional[UUID]]:
    """Every location_id (including NULL for company-wide) with its own
    par_auto_apply=TRUE settings row. A location never inherits the
    company-wide row's par_auto_apply — it must configure its own."""
    rows = await conn.fetch(
        "SELECT location_id FROM inventory_forecast_settings "
        "WHERE company_id=$1 AND par_auto_apply=TRUE",
        company_id,
    )
    return [row["location_id"] for row in rows]


async def list_rules(conn, *, company_id: UUID, location_id: Optional[UUID]) -> list[dict]:
    settings = await get_settings(conn, company_id, location_id)
    rows = await conn.fetch(
        """
        SELECT i.id AS item_id, i.name, i.unit, i.location_id, bl.name AS location_name,
               COALESCE(r.lead_time_days, $3) AS lead_time_days,
               COALESCE(r.safety_stock_days, $4) AS safety_stock_days,
               COALESCE(r.case_pack_quantity, 1) AS case_pack_quantity,
               COALESCE(r.minimum_order_quantity, 0) AS minimum_order_quantity,
               (r.id IS NOT NULL) AS customized
        FROM inventory_items i
        LEFT JOIN business_locations bl ON bl.id=i.location_id
        LEFT JOIN inventory_forecast_replenishment_rules r
          ON r.item_id=i.id AND r.company_id=$1
        WHERE i.company_id=$1 AND i.archived_at IS NULL
          AND ($2::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$2)
        ORDER BY i.name
        """,
        company_id,
        location_id,
        settings["default_lead_time_days"],
        settings["default_safety_stock_days"],
    )
    return [dict(row) for row in rows]


async def upsert_rule(conn, *, company_id: UUID, item_id: UUID, values: dict) -> dict:
    owned = await conn.fetchval(
        "SELECT 1 FROM inventory_items WHERE id=$1 AND company_id=$2 AND archived_at IS NULL",
        item_id,
        company_id,
    )
    if not owned:
        raise ValueError("item not found")
    row = await conn.fetchrow(
        """
        INSERT INTO inventory_forecast_replenishment_rules
            (company_id, item_id, lead_time_days, safety_stock_days,
             case_pack_quantity, minimum_order_quantity, updated_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (company_id, item_id) DO UPDATE SET
            lead_time_days=EXCLUDED.lead_time_days,
            safety_stock_days=EXCLUDED.safety_stock_days,
            case_pack_quantity=EXCLUDED.case_pack_quantity,
            minimum_order_quantity=EXCLUDED.minimum_order_quantity,
            updated_by=EXCLUDED.updated_by,
            updated_at=NOW()
        RETURNING *
        """,
        company_id,
        item_id,
        values["lead_time_days"],
        values["safety_stock_days"],
        values["case_pack_quantity"],
        values["minimum_order_quantity"],
        values.get("updated_by"),
    )
    return dict(row)


async def _forecast_inputs(conn, *, company_id: UUID, location_id: Optional[UUID], history_start: date, forecast_start: date):
    settings = await get_settings(conn, company_id, location_id)
    rows = await conn.fetch(
        """
        SELECT i.id, i.name, i.unit, i.location_id, i.current_quantity, i.unit_cost,
               i.category, i.shelf_life_days, i.low_stock_threshold, i.par_source,
               COALESCE(r.lead_time_days, $3) AS lead_time_days,
               COALESCE(r.safety_stock_days, $4) AS safety_stock_days,
               COALESCE(r.case_pack_quantity, 1) AS case_pack_quantity,
               COALESCE(r.minimum_order_quantity, 0) AS minimum_order_quantity,
               COALESCE(SUM(CASE WHEN o.status='ordered'
                                THEN COALESCE(o.quantity, o.suggested_quantity, 0)
                                ELSE 0 END), 0) AS on_order_quantity
        FROM inventory_items i
        LEFT JOIN inventory_forecast_replenishment_rules r
          ON r.item_id=i.id AND r.company_id=$1
        LEFT JOIN inventory_orders o ON o.item_id=i.id AND o.company_id=$1
        WHERE i.company_id=$1 AND i.archived_at IS NULL
          AND ($2::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$2)
        GROUP BY i.id, r.id
        ORDER BY i.name
        """,
        company_id,
        location_id,
        settings["default_lead_time_days"],
        settings["default_safety_stock_days"],
    )
    sales_rows = await conn.fetch(
        """
        SELECT ml.item_id, si.business_date, SUM(sl.quantity * ml.quantity_per_sale) AS quantity
        FROM inventory_sales_lines sl
        JOIN inventory_sales_imports si ON si.id=sl.import_id
        JOIN inventory_sales_mappings sm ON sm.id=sl.mapping_id
        JOIN inventory_sales_mapping_lines ml ON ml.mapping_id=sm.id
        JOIN inventory_items i ON i.id=ml.item_id
        WHERE si.company_id=$1 AND si.status='committed' AND sl.status='mapped'
          AND si.business_date >= $3 AND si.business_date < $4
          AND ($2::uuid IS NULL OR si.location_id IS NULL OR si.location_id=$2)
          AND ($2::uuid IS NULL OR sm.location_id IS NULL OR sm.location_id=$2)
          AND ($2::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$2)
        GROUP BY ml.item_id, si.business_date
        """,
        company_id,
        location_id,
        history_start,
        forecast_start,
    )
    sales_by_item: dict[UUID, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for row in sales_rows:
        if row["business_date"] is not None:
            sales_by_item[row["item_id"]][row["business_date"]] += Decimal(str(row["quantity"] or 0))
    return settings, [dict(row) for row in rows], sales_by_item


async def build_preview(
    conn,
    *,
    company_id: UUID,
    location_id: Optional[UUID],
    forecast_start: date,
    overrides: list[dict],
) -> dict:
    settings = await get_settings(conn, company_id, location_id)
    history_start = forecast_start - timedelta(days=settings["history_days"])
    settings, items, sales_by_item = await _forecast_inputs(
        conn,
        company_id=company_id,
        location_id=location_id,
        history_start=history_start,
        forecast_start=forecast_start,
    )
    lines = []
    for item in items:
        result = forecast_item(
            sales_by_day=sales_by_item.get(item["id"], {}),
            forecast_start=forecast_start,
            horizon_days=settings["horizon_days"],
            history_days=settings["history_days"],
            current_quantity=item["current_quantity"],
            lead_time_days=item["lead_time_days"],
            safety_stock_days=item["safety_stock_days"],
            case_pack_quantity=item["case_pack_quantity"],
            minimum_order_quantity=item["minimum_order_quantity"],
            on_order_quantity=item["on_order_quantity"],
            shelf_life_days=item["shelf_life_days"],
            overrides=overrides,
        )
        par = recommend_par(
            lead_demand=result["lead_demand"], safety_demand=result["safety_demand"],
            daily_demand=result["daily_demand"], lead_time_days=item["lead_time_days"],
            shelf_life_days=item["shelf_life_days"], status=result["status"],
        )
        lines.append({
            "item_id": item["id"],
            "name": item["name"],
            "unit": item["unit"],
            "location_id": item["location_id"],
            "current_quantity": item["current_quantity"],
            "unit_cost": item["unit_cost"],
            "category": item["category"],
            "shelf_life_days": item["shelf_life_days"],
            "low_stock_threshold": item["low_stock_threshold"],
            "current_par": item["low_stock_threshold"],
            "par_source": item["par_source"],
            "recommended_par": par["recommended_par"],
            "par_basis": par["par_basis"],
            "shelf_cap_quantity": par["shelf_cap"],
            "structural_deficit": par["structural_deficit"],
            "lead_time_days": item["lead_time_days"],
            "safety_stock_days": item["safety_stock_days"],
            "case_pack_quantity": item["case_pack_quantity"],
            "minimum_order_quantity": item["minimum_order_quantity"],
            **result,
        })
    return {
        "forecast_start": forecast_start,
        "forecast_end": forecast_start + timedelta(days=settings["horizon_days"] - 1),
        "history_start": history_start,
        "settings": settings,
        "overrides": overrides,
        "lines": lines,
    }


async def create_run(
    conn,
    *,
    company_id: UUID,
    user_id: UUID,
    location_id: Optional[UUID],
    forecast_start: date,
    overrides: list[dict],
) -> dict:
    preview = await build_preview(
        conn,
        company_id=company_id,
        location_id=location_id,
        forecast_start=forecast_start,
        overrides=overrides,
    )
    settings = preview["settings"]
    async with conn.transaction():
        run = await conn.fetchrow(
            """
            INSERT INTO inventory_forecast_runs
                (company_id, location_id, forecast_start, forecast_end, history_start,
                 settings_snapshot, override_count, created_by)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            RETURNING *
            """,
            company_id,
            location_id,
            preview["forecast_start"],
            preview["forecast_end"],
            preview["history_start"],
            json.dumps(_jsonable({"settings": settings, "overrides": overrides})),
            len(overrides),
            user_id,
        )
        for override in overrides:
            await conn.execute(
                """
                INSERT INTO inventory_forecast_overrides
                    (company_id, location_id, week_start, demand_multiplier, reason,
                     source, confidence, created_by, run_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                company_id,
                location_id,
                override["week_start"],
                override["demand_multiplier"],
                override["reason"],
                override.get("source", "manual"),
                override.get("confidence"),
                user_id,
                run["id"],
            )
        for line in preview["lines"]:
            calculation = _jsonable({
                key: value for key, value in line.items()
                if key not in {"item_id", "name", "unit", "location_id", "unit_cost"}
            })
            await conn.execute(
                """
                INSERT INTO inventory_forecast_lines
                    (run_id, item_id, status, confidence, history_nonzero_days,
                     current_quantity, on_order_quantity, projected_demand,
                     average_daily_demand, lead_demand, safety_demand, target_quantity,
                     suggested_quantity, runout_date, order_by_date, daily_demand,
                     recommended_par, par_basis, current_par, shelf_cap_quantity, shelf_life_capped, calculation)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16::jsonb, $17, $18, $19, $20, $21, $22::jsonb)
                """,
                run["id"], line["item_id"], line["status"], line["confidence"],
                line["history_nonzero_days"], line["current_quantity"],
                line["on_order_quantity"], line["projected_demand"],
                line["average_daily_demand"], line["lead_demand"],
                line["safety_demand"], line["target_quantity"],
                line["suggested_quantity"], line["runout_date"], line["order_by_date"],
                json.dumps(_jsonable(line["daily_demand"])), line["recommended_par"], line["par_basis"],
                line["current_par"], line["shelf_cap_quantity"], line["shelf_life_capped"], json.dumps(calculation),
            )
    return await get_run(conn, company_id=company_id, run_id=run["id"])


async def get_run(conn, *, company_id: UUID, run_id: UUID) -> Optional[dict]:
    run = await conn.fetchrow(
        "SELECT * FROM inventory_forecast_runs WHERE id=$1 AND company_id=$2",
        run_id,
        company_id,
    )
    if run is None:
        return None
    lines = await conn.fetch(
        """
        SELECT l.*, i.name, i.unit, i.location_id, i.unit_cost
        FROM inventory_forecast_lines l
        JOIN inventory_items i ON i.id=l.item_id
        WHERE l.run_id=$1
        ORDER BY i.name
        """,
        run_id,
    )
    materialized = []
    for line in lines:
        row = dict(line)
        calculation = _json_object(row.get("calculation"))
        materialized.append({**row, **calculation, "calculation": calculation})
    snapshot = _json_object(run.get("settings_snapshot"))
    settings = _json_object(snapshot.get("settings"))
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo(settings.get("timezone", "UTC"))).date()
    except Exception:
        today = datetime.utcnow().date()
    return {**dict(run), "lines": materialized, "plan": build_reorder_plan(materialized, today=today)}


async def get_latest_run(conn, *, company_id: UUID, location_id: Optional[UUID]) -> Optional[dict]:
    run_id = await conn.fetchval(
        """
        SELECT id FROM inventory_forecast_runs
        WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM $2
        ORDER BY created_at DESC, id DESC LIMIT 1
        """,
        company_id,
        location_id,
    )
    if run_id is None:
        return None
    return await get_run(conn, company_id=company_id, run_id=run_id)
