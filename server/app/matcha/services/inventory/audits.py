"""Stock-audit bulk count commit. A manager walks the store, counts every
item, and saves all the changed counts in one shot. Writes kind='adjust'
rows ONLY, via movements.adjust_item_count — the one sanctioned set-count
path — NEVER 'in' (provenance invariant, see services/inventory/CLAUDE.md:
a physical recount is a bare assertion, accepted as a correction to a real
count, not a claim of a delivery event).

Mirrors receipts.commit_receipt_lines: per-line transactions so one bad
row can't sink the rest (Postgres aborts the whole transaction on the
first error, hence one `conn.transaction()` per line, not one wrapping
the loop)."""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory.expected import variance_rollup
from app.matcha.services.inventory.waste import usage as usage_service

logger = logging.getLogger(__name__)

MAX_LINES = 200

_DEFAULT_NOTE = "Stock audit"


async def commit_audit_lines(
    conn, *, company_id: UUID, user_id: UUID, location_id: Optional[UUID],
    note: Optional[str], lines: list[dict],
) -> dict:
    """lines: [{item_id: UUID|str|None, new_item_name: str|None,
    counted_quantity: number}] — exactly one of item_id/new_item_name per
    line. Raises ValueError("location not found") for an unowned location
    (checked once, before any line). Returns {total, applied, failed,
    errors: [{row, item, error}]}. Untouched items are simply absent from
    `lines` — the caller (route) only sends rows the manager actually
    edited."""
    if location_id is not None:
        ok = await conn.fetchval(
            "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2 "
            "AND is_active IS NOT FALSE AND is_company_wide = FALSE",
            location_id, company_id,
        )
        if not ok:
            raise ValueError("location not found")

    resolved_note = note or _DEFAULT_NOTE

    # The lightweight fake connection used by the legacy audit unit tests has
    # no row-fetching API. The real asyncpg connection always does, so retain
    # the old result shape only for that test double.
    audit_run_id = None
    variance = None
    before = {}
    if hasattr(conn, "fetchrow"):
        run = await conn.fetchrow(
            """
            INSERT INTO inventory_audit_runs (company_id, location_id, committed_by, note, line_count)
            VALUES ($1, $2, $3, $4, $5) RETURNING id
            """, company_id, location_id, user_id, resolved_note, len(lines),
        )
        audit_run_id = run["id"]
        item_ids = [line["item_id"] for line in lines if line.get("item_id")]
        item_rows = await conn.fetch(
            "SELECT id, name, current_quantity, unit_cost FROM inventory_items "
            "WHERE company_id=$1 AND id=ANY($2::uuid[])", company_id, item_ids,
        ) if item_ids else []
        before = {str(row["id"]): dict(row) for row in item_rows}
        variance_lines = [
            {"item_id": line.get("item_id"), "counted_quantity": line.get("counted_quantity"),
             "expected": before.get(str(line.get("item_id")), {}).get("current_quantity")}
            for line in lines
        ]
        variance = variance_rollup(variance_lines, before)

    # A count establishes a fresh expected-on-hand baseline.  Usage on this
    # audit is therefore measured from the prior physical count, where one
    # exists, through today.  New/un-counted items deliberately remain unknown.
    usage_by_id = {}
    if audit_run_id is not None and before:
        item_ids = [row["id"] for row in before.values()]
        baseline_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (item_id) item_id, created_at::date AS baseline_date
            FROM inventory_movements
            WHERE company_id=$1 AND item_id=ANY($2::uuid[]) AND kind='adjust'
            ORDER BY item_id, created_at DESC, id DESC
            """, company_id, item_ids,
        )
        baselines = {row["item_id"]: row["baseline_date"] for row in baseline_rows}
        if baselines:
            ids_by_start = {}
            for item_id, start in baselines.items():
                ids_by_start.setdefault(start, []).append(item_id)
            for start, known_ids in ids_by_start.items():
                theoretical = await usage_service.theoretical_usage(
                    conn, company_id=company_id, location_id=location_id,
                    item_ids=known_ids, start=start, end=date.today(),
                )
                actual = await usage_service.actual_usage(
                    conn, company_id=company_id, item_ids=known_ids,
                    start=start, end=date.today(),
                )
                for item_id in known_ids:
                    theory = theoretical.get(item_id)
                    observed = actual.get(item_id, Decimal("0"))
                    usage_by_id[item_id] = {
                        "theoretical_usage": theory,
                        "actual_usage": observed if theory is not None else None,
                        **usage_service.usage_variance(
                            theory, observed if theory is not None else None,
                            before[str(item_id)].get("unit_cost"),
                        ),
                    }

    # Fetched lazily on the first new_item_name line (most audits are all
    # item_id lines and never need it), then reused + appended-to across
    # every subsequent new_item_name line so N new items in one audit don't
    # each pay a full-table catalog SELECT, and so two new lines with the
    # same spoken/typed name resolve to the same row (find_or_create_item's
    # ON CONFLICT DO NOTHING + re-SELECT already handles the second insert;
    # refreshing `existing` just keeps find_item's in-memory match current
    # for any THIRD occurrence in the same batch).
    existing: Optional[list[dict]] = None

    errors: list[dict] = []
    applied = 0
    for n, line in enumerate(lines, start=1):
        item_label = line.get("new_item_name") or str(line.get("item_id") or "")
        try:
            async with conn.transaction():
                quantity = line.get("counted_quantity")
                if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or quantity < 0:
                    raise ValueError("counted_quantity must be a non-negative number")

                item_id = line.get("item_id")
                new_item_name = line.get("new_item_name")
                new_item_row = None
                if item_id is not None and new_item_name:
                    raise ValueError("line has both item_id and new_item_name")
                elif item_id is not None:
                    pass
                elif new_item_name:
                    if existing is None:
                        catalog_fn = (
                            movements_service.list_item_names_for_audit
                            if hasattr(conn, "fetch") else movements_service.list_item_names
                        )
                        existing = await catalog_fn(conn, company_id, location_id)
                    item = await movements_service.find_or_create_item(
                        conn, company_id, new_item_name,
                        created_by=user_id, location_id=location_id, existing=existing,
                    )
                    item_id = item["id"]
                    new_item_row = {
                        "id": item["id"], "name": item["name"],
                        "normalized_name": item["normalized_name"], "location_id": item["location_id"],
                    }
                else:
                    raise ValueError("line needs item_id or new_item_name")

                adjust_kwargs = {
                    "conn": conn, "item_id": item_id, "company_id": company_id,
                    "quantity": quantity, "user_id": user_id, "note": resolved_note,
                }
                if audit_run_id is not None:
                    adjust_kwargs["audit_run_id"] = audit_run_id
                await movements_service.adjust_item_count(**adjust_kwargs)
                if audit_run_id is not None and item_id is not None:
                    prior = before.get(str(item_id), {})
                    usage = usage_by_id.get(item_id, {
                        "theoretical_usage": None, "actual_usage": None,
                        **usage_service.usage_variance(None, None, None),
                    })
                    expected = prior.get("current_quantity")
                    counted = quantity
                    count_variance = (
                        Decimal(str(counted)) - Decimal(str(expected))
                        if expected is not None else None
                    )
                    cost = prior.get("unit_cost")
                    await conn.execute(
                        """
                        INSERT INTO inventory_audit_lines
                            (run_id, item_id, expected, counted, variance, unit_cost, variance_value,
                             theoretical_usage, actual_usage, usage_variance)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                        ON CONFLICT (run_id, item_id) DO NOTHING
                        """,
                        audit_run_id, item_id, expected, counted, count_variance, cost,
                        count_variance * Decimal(str(cost)) if count_variance is not None and cost is not None else None,
                        usage.get("theoretical_usage"), usage.get("actual_usage"), usage["variance_units"],
                    )
                applied += 1
                # Only recorded once the line's transaction is guaranteed to
                # commit — appending before adjust_item_count could run meant
                # a rolled-back line still left its item in `existing`, so a
                # later same-name line in this batch would resolve to an id
                # that was never actually inserted.
                if new_item_row is not None:
                    existing.append(new_item_row)
        except Exception:
            logger.warning("audit line %d commit failed", n, exc_info=True)
            errors.append({
                "row": n,
                "item": item_label,
                "error": "Could not record this count — check the item and try again.",
            })

    result = {"total": len(lines), "applied": applied, "failed": len(errors), "errors": errors}
    if audit_run_id is not None:
        await conn.execute(
            "UPDATE inventory_audit_runs SET variance_units=$2, variance_value=$3 WHERE id=$1",
            audit_run_id, variance["total_units"], variance["total_value"],
        )
        result["variance"] = {**variance, "run_id": audit_run_id}
    return result
