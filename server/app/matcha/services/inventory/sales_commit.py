"""Transactional writer for reviewed POS sales imports."""

import json
import logging
from datetime import date
from typing import Optional
from uuid import UUID

from asyncpg.exceptions import UniqueViolationError

from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory import sales_mappings
from app.matcha.services.inventory.matching import normalize_name

logger = logging.getLogger(__name__)
MAX_LINES = 500


class DuplicateSalesPeriodError(Exception):
    pass


def _duplicate_result(import_id) -> dict:
    return {"import_id": import_id, "total": 0, "mapped": 0, "unmapped": 0,
            "items_affected": 0, "errors": [], "duplicate": True}


async def _is_idempotent_terminal_import(conn, import_row) -> bool:
    if import_row["status"] == "committed":
        return True
    if import_row["status"] != "discarded":
        return False
    return bool(await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM inventory_sales_lines WHERE import_id=$1
        ) AND NOT EXISTS (
            SELECT 1 FROM inventory_sales_lines
            WHERE import_id=$1 AND status <> 'ignored'
        )
        """,
        import_row["id"],
    ))


def _date_value(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


async def _components_for_line(conn, company_id: UUID, line: dict) -> list[dict]:
    mapping_id = line.get("mapping_id")
    if mapping_id:
        owned = await conn.fetchval(
            "SELECT 1 FROM inventory_sales_mappings WHERE id=$1 AND company_id=$2",
            mapping_id, company_id,
        )
        if not owned:
            raise ValueError("sales mapping not found")
        rows = await conn.fetch(
            """
            SELECT l.item_id, l.quantity_per_sale, l.unit
            FROM inventory_sales_mapping_lines l
            JOIN inventory_sales_mappings m ON m.id=l.mapping_id
            WHERE l.mapping_id=$1 AND m.company_id=$2
            """, mapping_id, company_id,
        )
        return [dict(row) for row in rows]
    components = line.get("components") or []
    if components:
        return components
    item_id = line.get("item_id")
    quantity_per_sale = line.get("quantity_per_sale")
    if item_id and quantity_per_sale:
        return [{"item_id": item_id, "quantity_per_sale": quantity_per_sale}]
    return []


async def commit_sales_import(
    conn, *, company_id: UUID, user_id: Optional[UUID], location_id: Optional[UUID],
    business_date, source: str, filename: Optional[str], gmail_message_id: Optional[str],
    lines: list[dict], note: Optional[str] = None, raw: Optional[dict] = None,
    import_id: Optional[UUID] = None,
    connection_id: Optional[UUID] = None, external_batch_id: Optional[str] = None,
) -> dict:
    business_date = _date_value(business_date)
    existing_import = None
    if import_id:
        existing_import = await conn.fetchrow(
            "SELECT id, status, location_id, business_date, source, connection_id, external_batch_id "
            "FROM inventory_sales_imports WHERE id=$1 AND company_id=$2",
            import_id, company_id,
        )
        if existing_import is None:
            raise ValueError("sales import not found")
        if await _is_idempotent_terminal_import(conn, existing_import):
            return _duplicate_result(existing_import["id"])
        if existing_import["status"] != "draft":
            raise ValueError("Sales import was already discarded.")
        source = existing_import["source"]
        location_id = existing_import["location_id"]
        if business_date is None:
            business_date = existing_import["business_date"]
        connection_id = connection_id or existing_import["connection_id"]
        external_batch_id = external_batch_id or existing_import["external_batch_id"]
    if gmail_message_id:
        gmail_import = await conn.fetchrow(
            "SELECT id, status, location_id, business_date, connection_id, external_batch_id "
            "FROM inventory_sales_imports WHERE company_id=$1 AND gmail_message_id=$2",
            company_id, gmail_message_id,
        )
        if existing_import and gmail_import and existing_import["id"] != gmail_import["id"]:
            raise ValueError("Sales import identity does not match the email draft.")
        if gmail_import and await _is_idempotent_terminal_import(conn, gmail_import):
            return _duplicate_result(gmail_import["id"])
        if gmail_import and gmail_import["status"] != "draft":
            raise ValueError("Sales import was already discarded.")
        if gmail_import:
            existing_import = gmail_import
            # Mailbox drafts retain the source's store even when reviewed from
            # the unfiltered Inventory page.
            location_id = existing_import["location_id"]
            if business_date is None:
                business_date = existing_import["business_date"]

    if connection_id and external_batch_id:
        batch_import = await conn.fetchrow(
            "SELECT id, status, location_id, business_date FROM inventory_sales_imports "
            "WHERE company_id=$1 AND connection_id=$2 AND external_batch_id=$3",
            company_id, connection_id, external_batch_id,
        )
        if batch_import and await _is_idempotent_terminal_import(conn, batch_import):
            return _duplicate_result(batch_import["id"])
        if batch_import and batch_import["status"] != "draft":
            raise ValueError("Sales import was already discarded.")
        if batch_import:
            if existing_import and existing_import["id"] != batch_import["id"]:
                raise ValueError("Sales import identity does not match the POS batch.")
            existing_import = batch_import
            location_id = batch_import["location_id"]
            if business_date is None:
                business_date = batch_import["business_date"]

    if location_id is not None:
        owned = await conn.fetchval(
            "SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2 "
            "AND is_active IS NOT FALSE AND is_company_wide=FALSE",
            location_id, company_id,
        )
        if not owned:
            raise ValueError("location not found")
    # An all-ignored review is discarded below, so it must not contend with a
    # prior committed import for the same period.
    all_ignored_submission = bool(lines) and all(
        (line["new_mapping"].get("kind") == "ignore"
         if line.get("new_mapping") else line.get("status") == "ignored")
        for line in lines
    )
    if business_date and not all_ignored_submission:
        duplicate = await conn.fetchval(
            """
            SELECT id FROM inventory_sales_imports
            WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM $2
              AND business_date=$3 AND status='committed'
            ORDER BY created_at DESC, id DESC LIMIT 1
            """, company_id, location_id, business_date,
        )
        if duplicate:
            raise DuplicateSalesPeriodError(
                f"Sales for {business_date.isoformat()} have already been committed."
            )

    raw_json = json.dumps(raw, default=str) if raw is not None else None
    created_import = False
    if existing_import:
        import_id = existing_import["id"]
        await conn.execute(
            """
            UPDATE inventory_sales_imports
            SET source=$2, business_date=$3, filename=$4, raw=COALESCE($5, raw),
                uploaded_by=COALESCE($6, uploaded_by), line_count=$7,
                note=COALESCE($8, note), connection_id=COALESCE($9, connection_id),
                external_batch_id=COALESCE($10, external_batch_id)
            WHERE id=$1
            """,
            import_id, source, business_date, filename, raw_json, user_id, len(lines), note,
            connection_id, external_batch_id,
        )
        # A mailbox draft already has its first-pass lines; replace them with
        # the manager's reviewed submission before committing.
        await conn.execute("DELETE FROM inventory_sales_lines WHERE import_id=$1", import_id)
    else:
        import_row = await conn.fetchrow(
            """
            INSERT INTO inventory_sales_imports
                (company_id, location_id, source, status, business_date, filename,
                 gmail_message_id, connection_id, external_batch_id, raw, uploaded_by, line_count, note)
            VALUES ($1, $2, $3, 'draft', $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            company_id, location_id, source, business_date, filename, gmail_message_id,
            connection_id, external_batch_id, raw_json, user_id, len(lines), note,
        )
        import_id = import_row["id"]
        created_import = True

    normalized_lines = []
    mapped = 0
    unmapped = 0
    errors = []
    for number, line in enumerate(lines, start=1):
        sold_name = (line.get("sold_name") or line.get("item_name") or "").strip()
        quantity = line.get("quantity")
        status = line.get("status", "unmapped")
        try:
            if not sold_name:
                raise ValueError("sold name is required")
            if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or quantity == 0:
                raise ValueError("quantity must be a non-zero number")
            mapping_id = line.get("mapping_id")
            new_mapping = line.get("new_mapping")
            if new_mapping:
                components = new_mapping.get("components", [])
                await sales_mappings.validate_mapping(
                    conn, company_id=company_id, location_id=location_id,
                    kind=new_mapping["kind"], components=components,
                )
                mapping_id = None
                status = "ignored" if new_mapping["kind"] == "ignore" else "mapped"
            else:
                components = await _components_for_line(conn, company_id, line)
                if status == "ignored":
                    components = []
                elif not components:
                    status = "unmapped"
                else:
                    status = "mapped"
            if status == "mapped":
                mapped += 1
            elif status == "unmapped":
                unmapped += 1
            normalized_lines.append({
                **line, "sold_name": sold_name, "normalized_name": normalize_name(sold_name),
                "quantity": quantity, "mapping_id": mapping_id, "status": status,
                "components": components,
            })
        except Exception as exc:
            errors.append({"row": number, "item": sold_name, "error": str(exc)})
            unmapped += 1
            normalized_lines.append({
                **line, "sold_name": sold_name or "(blank)",
                "normalized_name": normalize_name(sold_name), "quantity": quantity or 0,
                # Never persist an unvalidated caller-provided mapping id.
                "mapping_id": None, "status": "unmapped", "components": [],
            })

    if unmapped or errors:
        for line in normalized_lines:
            await conn.execute(
                """
                INSERT INTO inventory_sales_lines
                    (import_id, company_id, sold_name, normalized_name, quantity,
                     gross_sales, mapping_id, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                import_id, company_id, line["sold_name"], line["normalized_name"],
                line["quantity"], line.get("gross_sales"), line.get("mapping_id"), line["status"],
            )
        await conn.execute(
            "UPDATE inventory_sales_imports SET mapped_count=$2 WHERE id=$1",
            import_id, mapped,
        )
        return {"import_id": import_id, "total": len(lines), "mapped": mapped,
                "unmapped": unmapped, "items_affected": 0, "errors": errors}

    depletion: dict[UUID, float] = {}
    for line in normalized_lines:
        if line["status"] != "mapped":
            continue
        for component in line["components"]:
            item_id = component["item_id"]
            owned = await conn.fetchval(
                "SELECT 1 FROM inventory_items "
                "WHERE id=$1 AND company_id=$2 AND archived_at IS NULL "
                "AND (location_id IS NULL OR location_id IS NOT DISTINCT FROM $3)",
                item_id, company_id, location_id,
            )
            if not owned:
                errors.append({"item": line["sold_name"], "error": "mapped item not found"})
                continue
            depletion[item_id] = depletion.get(item_id, 0) + float(line["quantity"]) * float(component["quantity_per_sale"])
    if errors:
        for line in normalized_lines:
            await conn.execute(
                """
                INSERT INTO inventory_sales_lines
                    (import_id, company_id, sold_name, normalized_name, quantity,
                     gross_sales, mapping_id, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                import_id, company_id, line["sold_name"], line["normalized_name"],
                line["quantity"], line.get("gross_sales"), line.get("mapping_id"), line["status"],
            )
        await conn.execute(
            "UPDATE inventory_sales_imports SET mapped_count=$2 WHERE id=$1", import_id, mapped,
        )
        return {"import_id": import_id, "total": len(lines), "mapped": mapped,
                "unmapped": len(errors), "items_affected": 0, "errors": errors}

    all_ignored = bool(normalized_lines) and all(
        line["status"] == "ignored" for line in normalized_lines
    )
    try:
        async with conn.transaction():
            for line in normalized_lines:
                new_mapping = line.get("new_mapping")
                if not new_mapping:
                    continue
                saved = await sales_mappings.upsert_mapping(
                    conn, company_id=company_id, location_id=location_id,
                    sold_name=line["sold_name"], kind=new_mapping["kind"],
                    components=new_mapping.get("components", []), created_by=user_id,
                )
                line["mapping_id"] = saved["id"]
                line["components"] = saved.get("components", [])
            for line in normalized_lines:
                sales_line = await conn.fetchrow(
                    """
                    INSERT INTO inventory_sales_lines
                        (import_id, company_id, sold_name, normalized_name, quantity,
                         gross_sales, mapping_id, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    import_id, company_id, line["sold_name"], line["normalized_name"],
                    line["quantity"], line.get("gross_sales"), line.get("mapping_id"), line["status"],
                )
                if line["status"] == "mapped":
                    for component in line["components"]:
                        await conn.execute(
                            """
                            INSERT INTO inventory_sales_line_components
                                (sales_line_id, item_id, quantity_per_sale, unit)
                            VALUES ($1, $2, $3, $4)
                            """,
                            sales_line["id"], component["item_id"],
                            component["quantity_per_sale"], component.get("unit"),
                        )
            if not all_ignored:
                await movements_service.record_movements(
                    conn, company_id=company_id, channel_id=None, source_message_id=None,
                    recorded_by=user_id, kind="sale",
                    lines=[{"item_id": item_id, "quantity": quantity, "estimated": False}
                           for item_id, quantity in depletion.items()],
                    narrative=f"Sales depletion — {business_date.isoformat()}" if business_date else "Sales depletion",
                    note=filename, sales_import_id=import_id,
                )
            await conn.execute(
                """
                UPDATE inventory_sales_imports
                SET status=$2, mapped_count=$3,
                    committed_by=CASE WHEN $2='committed' THEN $4 ELSE NULL END,
                    committed_at=CASE WHEN $2='committed' THEN NOW() ELSE NULL END
                WHERE id=$1
                """, import_id,
                "discarded" if all_ignored else "committed",
                mapped, user_id,
            )
    except UniqueViolationError as exc:
        if exc.constraint_name != "uniq_inventory_sales_imports_period":
            raise
        if created_import:
            await conn.execute(
                "DELETE FROM inventory_sales_imports WHERE id=$1 AND company_id=$2 AND status='draft'",
                import_id, company_id,
            )
        label = business_date.isoformat() if business_date else "this period"
        raise DuplicateSalesPeriodError(
            f"Sales for {label} have already been committed."
        ) from exc
    return {"import_id": import_id, "total": len(lines), "mapped": mapped,
            "unmapped": 0, "items_affected": len(depletion), "errors": []}
