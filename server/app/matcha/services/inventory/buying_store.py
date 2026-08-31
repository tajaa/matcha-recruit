"""Persistence and trusted-input assembly for buying guidance."""

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.matcha.services.inventory import buying, forecast_store, network
from app.matcha.services.inventory.matching import normalize_name


def _jsonable(value):
    if isinstance(value, (date, Decimal, UUID)):
        return value.isoformat() if isinstance(value, date) else str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


async def list_suppliers(conn, *, company_id: UUID) -> list[dict]:
    rows = await conn.fetch("SELECT * FROM inventory_suppliers WHERE company_id=$1 ORDER BY active DESC,name", company_id)
    return [dict(row) for row in rows]


async def upsert_supplier(conn, *, company_id: UUID, user_id: UUID, values: dict) -> dict:
    row = await conn.fetchrow(
        """INSERT INTO inventory_suppliers (company_id,name,normalized_name,contact_email,contact_phone,payment_terms,created_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7)
           ON CONFLICT(company_id,normalized_name) DO UPDATE SET name=EXCLUDED.name,
             contact_email=COALESCE(EXCLUDED.contact_email,inventory_suppliers.contact_email),
             contact_phone=COALESCE(EXCLUDED.contact_phone,inventory_suppliers.contact_phone),
             payment_terms=COALESCE(EXCLUDED.payment_terms,inventory_suppliers.payment_terms),updated_at=NOW()
           RETURNING *""",
        company_id, values["name"].strip(), normalize_name(values["name"]), values.get("contact_email"),
        values.get("contact_phone"), values.get("payment_terms"), user_id,
    )
    return dict(row)


async def upsert_supplier_item(conn, *, company_id: UUID, item_id: UUID, user_id: UUID, values: dict) -> dict:
    item = await conn.fetchrow("SELECT id,location_id FROM inventory_items WHERE id=$1 AND company_id=$2 AND archived_at IS NULL", item_id, company_id)
    supplier_owned = await conn.fetchval("SELECT 1 FROM inventory_suppliers WHERE id=$1 AND company_id=$2", values["supplier_id"], company_id)
    if not item or not supplier_owned:
        raise ValueError("item or supplier not found")
    location_id = values.get("location_id")
    if location_id and not await conn.fetchval("SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2", location_id, company_id):
        raise ValueError("location not found")
    if location_id and item["location_id"] and item["location_id"] != location_id:
        raise ValueError("item belongs to another location")
    row = await conn.fetchrow(
        """INSERT INTO inventory_supplier_items
             (company_id,supplier_id,item_id,location_id,vendor_sku,purchase_unit,pack_size_label,units_per_pack,
              minimum_order_quantity,unit_price,freight_flat,lead_time_days,price_observed_on,preferred,active)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
           ON CONFLICT(supplier_id,item_id,location_id) DO UPDATE SET vendor_sku=EXCLUDED.vendor_sku,
             purchase_unit=EXCLUDED.purchase_unit,pack_size_label=EXCLUDED.pack_size_label,units_per_pack=EXCLUDED.units_per_pack,
             minimum_order_quantity=EXCLUDED.minimum_order_quantity,unit_price=EXCLUDED.unit_price,freight_flat=EXCLUDED.freight_flat,
             lead_time_days=EXCLUDED.lead_time_days,price_observed_on=EXCLUDED.price_observed_on,
             preferred=EXCLUDED.preferred,active=EXCLUDED.active,updated_at=NOW() RETURNING *""",
        company_id, values["supplier_id"], item_id, location_id, values.get("vendor_sku"), values.get("purchase_unit"),
        values.get("pack_size_label"), values.get("units_per_pack", 1), values.get("minimum_order_quantity", 0),
        values.get("unit_price"), values.get("freight_flat"), values.get("lead_time_days"),
        values.get("price_observed_on"), values.get("preferred", False), values.get("active", True),
    )
    if values.get("unit_price") is not None:
        await conn.execute(
            """INSERT INTO inventory_supplier_price_history
                 (company_id,supplier_item_id,unit_price,observed_on,source,reviewed_by)
               VALUES ($1,$2,$3,COALESCE($4,CURRENT_DATE),'manual',$5)""",
            company_id, row["id"], values["unit_price"], values.get("price_observed_on"), user_id,
        )
    return dict(row)


async def record_reviewed_receipt_price(conn, *, company_id: UUID, user_id: UUID, item_id: UUID,
                                        location_id: Optional[UUID], vendor: Optional[str], vendor_sku: Optional[str],
                                        pack_size: Optional[str], unit_price, quantity, observed_on: date,
                                        invoice_number: Optional[str]) -> None:
    if not vendor or unit_price is None:
        return
    supplier = await upsert_supplier(conn, company_id=company_id, user_id=user_id, values={"name": vendor})
    row = await conn.fetchrow(
        """INSERT INTO inventory_supplier_items
             (company_id,supplier_id,item_id,location_id,vendor_sku,pack_size_label,unit_price,price_observed_on)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
           ON CONFLICT(supplier_id,item_id,location_id) DO UPDATE SET
             vendor_sku=COALESCE(EXCLUDED.vendor_sku,inventory_supplier_items.vendor_sku),
             pack_size_label=COALESCE(EXCLUDED.pack_size_label,inventory_supplier_items.pack_size_label),
             unit_price=EXCLUDED.unit_price,price_observed_on=EXCLUDED.price_observed_on,updated_at=NOW()
           RETURNING id""",
        company_id, supplier["id"], item_id, location_id, vendor_sku, pack_size, unit_price, observed_on,
    )
    await conn.execute(
        """INSERT INTO inventory_supplier_price_history
             (company_id,supplier_item_id,unit_price,quantity,observed_on,invoice_number,source,reviewed_by)
           VALUES ($1,$2,$3,$4,$5,$6,'receipt',$7)""",
        company_id, row["id"], unit_price, quantity, observed_on, invoice_number, user_id,
    )


async def _offers(conn, *, company_id: UUID, location_id: Optional[UUID]) -> list[dict]:
    rows = await conn.fetch(
        """SELECT si.id AS supplier_item_id,si.item_id,si.supplier_id,s.name AS supplier_name,
                  si.location_id,si.units_per_pack,si.minimum_order_quantity,si.unit_price,
                  si.freight_flat,si.lead_time_days,si.price_observed_on,si.preferred,si.active
           FROM inventory_supplier_items si JOIN inventory_suppliers s ON s.id=si.supplier_id
           WHERE si.company_id=$1 AND s.company_id=$1 AND s.active=TRUE AND si.active=TRUE
             AND ($2::uuid IS NULL OR si.location_id IS NULL OR si.location_id=$2)
           ORDER BY si.item_id, (si.location_id IS NOT NULL) DESC, si.preferred DESC, s.name""",
        company_id, location_id,
    )
    return [dict(row) for row in rows]


async def build_plan(conn, *, company_id: UUID, forecast_run_id: UUID,
                     location_id: Optional[UUID], today: date) -> Optional[dict]:
    run = await forecast_store.get_run(conn, company_id=company_id, run_id=forecast_run_id)
    if run is None:
        return None
    if location_id and run["location_id"] not in (None, location_id):
        return None
    if run["location_id"] is None:
        network_plan = await network.build_network_preview(conn, company_id=company_id, run_id=forecast_run_id)
        if network_plan is None:
            return None
        shortages = network_plan["remaining_shortages"]
        attention = network_plan["attention"]
        transfers = network_plan["transfers"]
    else:
        location_name = await conn.fetchval("SELECT COALESCE(name,city,'Unnamed') FROM business_locations WHERE id=$1 AND company_id=$2", run["location_id"], company_id)
        shortages = [{"item_id": line["item_id"], "item_name": line["name"], "unit": line.get("unit"),
                       "location_id": line.get("location_id"), "location_name": location_name,
                       "shortage_quantity": line["suggested_quantity"], "suggested_order_quantity": line["suggested_quantity"],
                       "runout_date": line.get("runout_date"), "order_by_date": line.get("order_by_date"),
                       "confidence": line.get("confidence", "low")}
                      for line in run["lines"] if line["status"] == "ready" and (line.get("suggested_quantity") or 0) > 0]
        attention = [{"item_id": line["item_id"], "item_name": line["name"], "unit": line.get("unit"),
                      "location_id": line.get("location_id"), "location_name": location_name, "status": line["status"]}
                     for line in run["lines"] if line["status"] in ("count_required", "insufficient_history")]
        transfers = []
    if location_id:
        shortages = [line for line in shortages if line.get("location_id") == location_id]
        attention = [line for line in attention if line.get("location_id") == location_id]
        transfers = [line for line in transfers if line.get("to_location_id") == location_id]
    offers = await _offers(conn, company_id=company_id, location_id=location_id or run["location_id"])
    raw = buying.build_buying_plan(forecast_run_id=forecast_run_id, forecast_start=run["forecast_start"],
                                   shortages=shortages, attention=attention, offers=offers, transfers=transfers, today=today)
    fingerprint_payload = _jsonable({"forecast": forecast_run_id, "shortages": shortages, "attention": attention,
                                    "transfers": transfers, "offers": offers})
    raw["location_id"] = location_id or run["location_id"]
    raw["input_fingerprint"] = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode()).hexdigest()
    return raw


async def create_run(conn, *, company_id: UUID, user_id: UUID, forecast_run_id: UUID,
                     location_id: Optional[UUID], today: date) -> Optional[dict]:
    plan = await build_plan(conn, company_id=company_id, forecast_run_id=forecast_run_id, location_id=location_id, today=today)
    if plan is None:
        return None
    async with conn.transaction():
        run = await conn.fetchrow(
            """INSERT INTO inventory_buying_runs(company_id,forecast_run_id,location_id,input_fingerprint,summary,created_by)
               VALUES($1,$2,$3,$4,$5::jsonb,$6) RETURNING id,created_at""",
            company_id, forecast_run_id, plan["location_id"], plan["input_fingerprint"],
            json.dumps(_jsonable(plan["summary"])), user_id,
        )
        for line in plan["lines"]:
            saved = await conn.fetchrow(
                """INSERT INTO inventory_buying_lines
                     (run_id,company_id,item_id,location_id,action,needed_quantity,purchase_quantity,supplier_id,supplier_item_id,
                      order_by_date,expected_arrival,landed_cost,confidence,price_confirmation_required,rationale,alternatives,calculation)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::jsonb,$17::jsonb) RETURNING id""",
                run["id"], company_id, line["item_id"], line.get("location_id"), line["action"], line.get("needed_quantity"),
                line.get("purchase_quantity"), line.get("supplier_id"), line.get("supplier_item_id"), line.get("order_by_date"),
                line.get("expected_arrival"), line.get("landed_cost"), line["confidence"], line["price_confirmation_required"],
                line["rationale"], json.dumps(_jsonable(line["alternatives"])), json.dumps(_jsonable(line["calculation"])),
            )
            line["id"] = saved["id"]
    plan["id"] = run["id"]
    plan["created_at"] = run["created_at"]
    return plan
