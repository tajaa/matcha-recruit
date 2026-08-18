"""Read/write and resolution helpers for POS sold-name mappings."""

from typing import Optional
from uuid import UUID

from app.matcha.services.inventory.matching import best_match, normalize_name
from app.matcha.services.inventory import movements as movements_service


async def list_mappings(conn, company_id: UUID, location_id: Optional[UUID] = None) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT m.*, COALESCE(jsonb_agg(jsonb_build_object(
            'id', l.id, 'item_id', l.item_id,
            'quantity_per_sale', l.quantity_per_sale, 'unit', l.unit
        ) ORDER BY l.created_at) FILTER (WHERE l.id IS NOT NULL), '[]'::jsonb) AS components
        FROM inventory_sales_mappings m
        LEFT JOIN inventory_sales_mapping_lines l ON l.mapping_id = m.id
        WHERE m.company_id = $1 AND (m.location_id IS NULL OR m.location_id = $2)
        GROUP BY m.id ORDER BY (m.location_id IS NULL), m.sold_name
        """,
        company_id, location_id,
    )
    return [dict(row) for row in rows]


async def upsert_mapping(
    conn, *, company_id: UUID, location_id: Optional[UUID], sold_name: str,
    kind: str, components: list[dict], created_by: Optional[UUID],
) -> dict:
    if location_id is not None:
        owned = await conn.fetchval(
            "SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2 "
            "AND is_active IS NOT FALSE AND is_company_wide=FALSE",
            location_id, company_id,
        )
        if not owned:
            raise ValueError("location not found")
    if kind == "direct" and len(components) != 1:
        raise ValueError("direct mappings need exactly one component")
    if kind == "recipe" and not components:
        raise ValueError("recipe mappings need at least one component")
    if kind == "ignore" and components:
        raise ValueError("ignore mappings cannot have components")

    for component in components:
        item_id = component.get("item_id")
        owned = await conn.fetchval(
            "SELECT 1 FROM inventory_items "
            "WHERE id=$1 AND company_id=$2 AND archived_at IS NULL "
            "AND (location_id IS NULL OR location_id IS NOT DISTINCT FROM $3)",
            item_id, company_id, location_id,
        )
        if not owned:
            raise ValueError("mapping item not found or outside location")

    normalized = normalize_name(sold_name)
    async with conn.transaction():
        mapping = await conn.fetchrow(
            """
            SELECT * FROM inventory_sales_mappings
            WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM $2
              AND normalized_name=$3 FOR UPDATE
            """, company_id, location_id, normalized,
        )
        if mapping is not None:
            mapping = await conn.fetchrow(
                """
                UPDATE inventory_sales_mappings
                SET sold_name=$2, kind=$3, updated_at=NOW()
                WHERE id=$1 RETURNING *
                """, mapping["id"], sold_name.strip(), kind,
            )
        else:
            await conn.execute(
                """
                INSERT INTO inventory_sales_mappings
                    (company_id, location_id, sold_name, normalized_name, kind, created_by)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT DO NOTHING
                """,
                company_id, location_id, sold_name.strip(), normalized, kind, created_by,
            )
            mapping = await conn.fetchrow(
                """
                SELECT * FROM inventory_sales_mappings
                WHERE company_id=$1 AND location_id IS NOT DISTINCT FROM $2
                  AND normalized_name=$3
                """, company_id, location_id, normalized,
            )
        await conn.execute("DELETE FROM inventory_sales_mapping_lines WHERE mapping_id=$1", mapping["id"])
        for component in components:
            await conn.execute(
                """
                INSERT INTO inventory_sales_mapping_lines
                    (mapping_id, item_id, quantity_per_sale, unit)
                SELECT $1, id, $3, $4 FROM inventory_items
                WHERE id=$2 AND company_id=$5 AND archived_at IS NULL
                  AND (location_id IS NULL OR location_id IS NOT DISTINCT FROM $6)
                """,
                mapping["id"], component["item_id"], component["quantity_per_sale"],
                component.get("unit"), company_id, location_id,
            )
        rows = await conn.fetch(
            "SELECT * FROM inventory_sales_mapping_lines WHERE mapping_id=$1 ORDER BY created_at",
            mapping["id"],
        )
    result = dict(mapping)
    result["components"] = [dict(row) for row in rows]
    return result


async def resolve_sold_lines(conn, *, company_id: UUID, location_id: Optional[UUID], lines: list[dict]) -> list[dict]:
    mappings = await list_mappings(conn, company_id, location_id)
    # Sales without a location must resolve only company-wide items; the audit
    # catalog intentionally widens None to every store, which is unsafe here.
    catalog = await movements_service.list_item_names(conn, company_id, location_id)
    resolved = []
    for line in lines:
        sold_name = line.get("item_name") or line.get("sold_name") or ""
        normalized = normalize_name(sold_name)
        mapping = next((m for m in mappings if m["normalized_name"] == normalized), None)
        if mapping is None:
            mapping = best_match(sold_name, mappings)
        status = "unmapped"
        components = []
        auto_match = None
        if mapping is not None:
            status = "ignored" if mapping["kind"] == "ignore" else "mapped"
            components = mapping.get("components") or []
        else:
            auto_match = best_match(sold_name, catalog)
            if auto_match:
                components = [{"item_id": auto_match["id"], "quantity_per_sale": 1, "unit": None}]
        resolved.append({
            **line,
            "sold_name": sold_name,
            "normalized_name": normalized,
            "mapping_id": mapping["id"] if mapping else None,
            "mapping_kind": mapping["kind"] if mapping else None,
            "status": status,
            "components": components,
            "auto_match": auto_match,
        })
    return resolved
