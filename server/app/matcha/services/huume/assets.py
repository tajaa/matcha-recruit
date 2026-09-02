"""Cross-type asset registry — one row per durable artifact a Huume turn
created (offer letter, discipline record, incident report, schedule change,
inventory row, ...).

Written from a single choke point, `actions.execute_huume_action`'s tail,
after each staged action's executor returns `{status: "created", record_id,
...}` — see that module for the call site. `draft_offer_letter` (a WRITE
tool, not a staged action, so it never reaches that dispatch) gets its own
explicit call from `agent.py`'s draft arm via `record_offer_draft_asset`.

`record_asset` NEVER raises — a registry write failing must not fail the
real domain write it's annotating. Every caller can fire-and-forget it.

No stored status: the underlying row's status drifts independently of this
registry (an offer moves draft->sent->accepted from the public candidate
endpoint; a discipline record moves through the HR approval queue) —
`list_assets` hydrates status live per `ref_table` instead of trying to keep
a duplicate in sync.

Label strategy: prefer the executor's own `record_label` (already name-free
for discipline/ir/er — see huume_ops_skill.py / hr_pilot_actions.py, which
return incident/case NUMBERS, never employee names). Only `discipline_draft`
needs a synthesized fallback — its executor (`hr_pilot_actions.
_execute_discipline_draft`) doesn't return one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import UUID

from app.database import get_connection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssetSpec:
    asset_type: str
    ref_table: str
    label_fn: Callable[[dict, dict], str]  # (action, result) -> label; pure


def _label(result: dict, fallback: str) -> str:
    return str(result.get("record_label") or fallback)


ASSET_SPECS: dict[str, AssetSpec] = {
    "send_offer": AssetSpec(
        "offer_letter", "offer_letters",
        lambda a, r: f"Offer letter — {a.get('candidate_name') or 'candidate'}",
    ),
    "discipline_draft": AssetSpec(
        "discipline_record", "progressive_discipline",
        # Name-free: infraction_type only, never employee_name.
        lambda a, r: f"Discipline draft ({a.get('infraction_type') or 'draft'})",
    ),
    "discipline_from_incident": AssetSpec(
        "discipline_record", "progressive_discipline",
        lambda a, r: _label(r, "Disciplinary action"),
    ),
    "discipline_decision": AssetSpec(
        # Same ref_table/ref_id as the draft this decides — upsert refreshes
        # that row's label to reflect the decision rather than duplicating it.
        "discipline_record", "progressive_discipline",
        lambda a, r: _label(r, "Discipline decision"),
    ),
    "ir_report": AssetSpec(
        "ir_incident", "ir_incidents",
        lambda a, r: _label(r, "Incident report"),
    ),
    "er_case": AssetSpec(
        "er_case", "er_cases",
        lambda a, r: _label(r, "ER case"),
    ),
    "training_assign": AssetSpec(
        # record_id here is the training REQUIREMENT id, not a training_records
        # row — training_assign assigns one requirement to many employees.
        "training_requirement", "training_requirements",
        lambda a, r: _label(r, "Training assignment"),
    ),
    "pto_decision": AssetSpec(
        "pto_request", "pto_requests",
        lambda a, r: _label(r, "PTO decision"),
    ),
    "ems_promote": AssetSpec(
        "ir_incident", "ir_incidents",
        lambda a, r: _label(r, "Incident (promoted)"),
    ),
    "inventory_movement": AssetSpec(
        "inventory_movement", "inventory_movements",
        lambda a, r: _label(r, "Stock movement"),
    ),
    "inventory_receipt": AssetSpec(
        # record_id is a comma-joined list of movement ids, not one UUID —
        # list_assets/hydrate_statuses must tolerate that (skip cast failures).
        "inventory_receipt", "inventory_movements",
        lambda a, r: _label(r, "Receipt"),
    ),
    "inventory_order_decision": AssetSpec(
        "inventory_order", "inventory_orders",
        lambda a, r: _label(r, "Inventory order"),
    ),
    "inventory_item_create": AssetSpec(
        "inventory_item", "inventory_items",
        lambda a, r: _label(r, "Inventory item"),
    ),
    "inventory_item_archive": AssetSpec(
        # Same ref_table/ref_id as inventory_item_create — upsert just
        # refreshes the label; live status hydration reflects archived state.
        "inventory_item", "inventory_items",
        lambda a, r: _label(r, "Inventory item"),
    ),
    "schedule_change": AssetSpec(
        # record_id is the schedule_chat_proposals id (schedule_skill.execute
        # returns record_id=proposal_id), not a schedule_shifts row.
        "schedule_proposal", "schedule_chat_proposals",
        lambda a, r: f"Schedule change ({a.get('kind') or 'edit'})",
    ),
    "schedule_week_draft": AssetSpec(
        "schedule_generation", "schedule_generation_runs",
        lambda a, r: f"Generated week ({a.get('week_start') or 'schedule draft'})",
    ),
}

# amend_handbook: its executor (handbook_skill.promote) returns status="ok",
# never "created", and no record_id (different shape entirely: session_id/
# promoted/handbook/...) — record_asset's status guard already no-ops it.
# Listed here so the drift-guard test has a documented reason, not a gap.
_NO_ASSET_TYPES: frozenset[str] = frozenset({"amend_handbook"})


async def record_asset(
    *, company_id: UUID, thread_id: Optional[UUID], actor_user_id: Optional[UUID],
    action: dict[str, Any], result: dict[str, Any],
) -> None:
    try:
        if result.get("status") != "created":
            return
        record_id = result.get("record_id")
        spec = ASSET_SPECS.get(str(action.get("type") or ""))
        if not record_id or spec is None:
            return
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO huume_assets
                    (company_id, thread_id, asset_type, ref_table, ref_id, label, source, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, 'huume_action', $7)
                ON CONFLICT (company_id, ref_table, ref_id)
                DO UPDATE SET
                    label = EXCLUDED.label,
                    source = EXCLUDED.source,
                    thread_id = COALESCE(EXCLUDED.thread_id, huume_assets.thread_id),
                    created_by = COALESCE(EXCLUDED.created_by, huume_assets.created_by)
                """,
                company_id, thread_id, spec.asset_type, spec.ref_table,
                str(record_id), spec.label_fn(action, result), actor_user_id,
            )
    except Exception:
        logger.exception("[Huume] asset registry write failed (non-fatal)")


async def record_offer_draft_asset(
    *, company_id: UUID, thread_id: Optional[UUID], actor_user_id: Optional[UUID],
    offer_id: str, candidate_name: str, position_title: str,
) -> None:
    try:
        label = f"Offer letter — {candidate_name or 'candidate'}"
        if position_title:
            label += f" ({position_title})"
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO huume_assets
                    (company_id, thread_id, asset_type, ref_table, ref_id, label, source, created_by)
                VALUES ($1, $2, 'offer_letter', 'offer_letters', $3, $4, 'draft', $5)
                ON CONFLICT (company_id, ref_table, ref_id)
                DO UPDATE SET
                    label = EXCLUDED.label,
                    thread_id = COALESCE(EXCLUDED.thread_id, huume_assets.thread_id),
                    created_by = COALESCE(EXCLUDED.created_by, huume_assets.created_by)
                """,
                company_id, thread_id, offer_id, label, actor_user_id,
            )
    except Exception:
        logger.exception("[Huume] asset registry draft write failed (non-fatal)")


# One status query per ref_table actually present in a listing — bounded by
# len(ASSET_SPECS) (currently 14 distinct ref_tables), never per-row.
_STATUS_SQL: dict[str, str] = {
    "offer_letters": "SELECT id::text AS ref_id, status FROM offer_letters WHERE company_id = $1 AND id = ANY($2::uuid[])",
    "progressive_discipline": "SELECT id::text AS ref_id, approval_status AS status FROM progressive_discipline WHERE company_id = $1 AND id = ANY($2::uuid[])",
    "ir_incidents": "SELECT id::text AS ref_id, status FROM ir_incidents WHERE company_id = $1 AND id = ANY($2::uuid[])",
    "er_cases": "SELECT id::text AS ref_id, status FROM er_cases WHERE company_id = $1 AND id = ANY($2::uuid[])",
    "training_requirements": "SELECT id::text AS ref_id, (CASE WHEN is_active THEN 'active' ELSE 'inactive' END) AS status FROM training_requirements WHERE company_id = $1 AND id = ANY($2::uuid[])",
    # pto_requests has no company_id of its own (employee-scoped) — join
    # through employees.org_id, the company-scoping column that table uses.
    "pto_requests": (
        "SELECT pr.id::text AS ref_id, pr.status FROM pto_requests pr "
        "JOIN employees e ON e.id = pr.employee_id "
        "WHERE e.org_id = $1 AND pr.id = ANY($2::uuid[])"
    ),
    "inventory_orders": "SELECT id::text AS ref_id, status FROM inventory_orders WHERE company_id = $1 AND id = ANY($2::uuid[])",
    # inventory_items has archived_at (nullable timestamp), not is_archived.
    "inventory_items": (
        "SELECT id::text AS ref_id, (CASE WHEN archived_at IS NOT NULL THEN 'archived' ELSE 'active' END) AS status "
        "FROM inventory_items WHERE company_id = $1 AND id = ANY($2::uuid[])"
    ),
    "schedule_chat_proposals": "SELECT id::text AS ref_id, status FROM schedule_chat_proposals WHERE company_id = $1 AND id = ANY($2::uuid[])",
    "schedule_generation_runs": "SELECT id::text AS ref_id, status FROM schedule_generation_runs WHERE company_id = $1 AND id = ANY($2::uuid[])",
}


def _as_uuid(ref_id: str) -> Optional[UUID]:
    try:
        return UUID(ref_id)
    except (ValueError, AttributeError, TypeError):
        # inventory_receipt's ref_id is a comma-joined list of movement ids,
        # never a single UUID — status hydration skips it, doesn't crash it.
        return None


async def hydrate_statuses(conn, assets: list[dict]) -> list[dict]:
    by_table: dict[str, list[UUID]] = {}
    for a in assets:
        u = _as_uuid(a["ref_id"])
        if u is not None and a["ref_table"] in _STATUS_SQL:
            by_table.setdefault(a["ref_table"], []).append(u)

    statuses: dict[tuple[str, str], str] = {}
    for ref_table, ids in by_table.items():
        company_ids = {a["company_id"] for a in assets if a["ref_table"] == ref_table}
        for company_id in company_ids:
            rows = await conn.fetch(_STATUS_SQL[ref_table], company_id, ids)
            for row in rows:
                statuses[(ref_table, row["ref_id"])] = row["status"]

    for a in assets:
        a["status"] = statuses.get((a["ref_table"], a["ref_id"]))
    return assets


async def list_assets(
    *, company_id: UUID, thread_id: Optional[UUID] = None,
    asset_type: Optional[str] = None, query: Optional[str] = None, limit: int = 25,
) -> list[dict]:
    conditions = ["ha.company_id = $1"]
    params: list[Any] = [company_id]
    if thread_id is not None:
        params.append(thread_id)
        conditions.append(f"ha.thread_id = ${len(params)}")
    if asset_type:
        params.append(asset_type)
        conditions.append(f"ha.asset_type = ${len(params)}")
    if query:
        # Escape ILIKE wildcards in user input so a literal '%' or '_' in a
        # search term is matched literally, not as a pattern.
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
        conditions.append(f"ha.label ILIKE ${len(params)} ESCAPE '\\'")
    params.append(min(max(limit, 1), 200))

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT ha.id AS asset_id, ha.asset_type, ha.ref_table, ha.ref_id, ha.label,
                   ha.source, ha.created_at, ha.company_id,
                   ha.thread_id, COALESCE(t.title, 'Untitled Chat') AS thread_title
            FROM huume_assets ha
            LEFT JOIN mw_threads t ON t.id = ha.thread_id
            WHERE {' AND '.join(conditions)}
            ORDER BY ha.created_at DESC
            LIMIT ${len(params)}
            """,
            *params,
        )
        assets = [dict(r) for r in rows]
        assets = await hydrate_statuses(conn, assets)

    for a in assets:
        a.pop("company_id", None)
        a["asset_id"] = str(a["asset_id"])
        a["thread_id"] = str(a["thread_id"]) if a.get("thread_id") else None
        a["created_at"] = a["created_at"].isoformat() if a["created_at"] else None
    return assets
