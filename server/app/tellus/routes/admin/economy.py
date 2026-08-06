"""Tell-Us internal admin — config editors for the points economy: earning
rules (tellus_earning_rules had no UI before this), badge definitions, and
marketplace listing oversight."""
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ....database import get_connection
from ...dependencies import require_tellus_admin
from ...models.tellus import TellusAccount
from ...services.admin_audit import record_admin_action
from ...models.admin import (
    TellusAdminBadge,
    TellusAdminBadgeUpdate,
    TellusAdminEarningRule,
    TellusAdminEarningRuleUpdate,
    TellusAdminListingUpdate,
)

router = APIRouter(dependencies=[Depends(require_tellus_admin)])


@router.get("/admin/earning-rules")
async def list_earning_rules():
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT event_key, points, daily_cap, cooldown_seconds, is_active "
            "FROM tellus_earning_rules ORDER BY event_key",
        )
    return [TellusAdminEarningRule(**dict(r)) for r in rows]


@router.patch("/admin/earning-rules/{event_key}")
async def update_earning_rule(
    event_key: str, body: TellusAdminEarningRuleUpdate,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(422, "No fields to update.")

    async with get_connection() as conn:
        async with conn.transaction():
            before = await conn.fetchrow(
                "SELECT event_key, points, daily_cap, cooldown_seconds, is_active "
                "FROM tellus_earning_rules WHERE event_key = $1", event_key,
            )
            if before is None:
                raise HTTPException(404, "Unknown earning rule.")

            set_clauses = []
            params: list = []
            i = 1
            for key, value in updates.items():
                set_clauses.append(f"{key} = ${i}")
                params.append(value)
                i += 1
            params.append(event_key)
            await conn.execute(
                f"UPDATE tellus_earning_rules SET {', '.join(set_clauses)} WHERE event_key = ${i}",
                *params,
            )
            after = await conn.fetchrow(
                "SELECT event_key, points, daily_cap, cooldown_seconds, is_active "
                "FROM tellus_earning_rules WHERE event_key = $1", event_key,
            )
            await record_admin_action(
                conn, admin, "earning_rule.update", "earning_rule", event_key,
                {"before": dict(before), "after": dict(after)},
            )
    return TellusAdminEarningRule(**dict(after))


@router.get("/admin/badges")
async def list_badges():
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT d.key, d.name, d.description, d.icon, d.criteria, d.sort_order,
                      (SELECT COUNT(*) FROM tellus_user_badges ub WHERE ub.badge_key = d.key) AS award_count
               FROM tellus_badge_definitions d ORDER BY d.sort_order, d.key""",
        )
    badges = []
    for r in rows:
        d = dict(r)
        if isinstance(d["criteria"], str):
            try:
                d["criteria"] = json.loads(d["criteria"])
            except ValueError:
                d["criteria"] = {}
        badges.append(TellusAdminBadge(**d))
    return badges


@router.patch("/admin/badges/{key}")
async def update_badge(
    key: str, body: TellusAdminBadgeUpdate,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow("SELECT key FROM tellus_badge_definitions WHERE key = $1", key)
            if existing is None:
                raise HTTPException(404, "Unknown badge.")

            if body.name is not None:
                await conn.execute(
                    "UPDATE tellus_badge_definitions SET name = $2 WHERE key = $1", key, body.name,
                )
            if body.description is not None:
                await conn.execute(
                    "UPDATE tellus_badge_definitions SET description = $2 WHERE key = $1", key, body.description,
                )
            if body.threshold is not None:
                await conn.execute(
                    "UPDATE tellus_badge_definitions SET criteria = jsonb_set(criteria, '{threshold}', to_jsonb($2::int)) "
                    "WHERE key = $1",
                    key, body.threshold,
                )
            await record_admin_action(
                conn, admin, "badge.update", "badge", key,
                {"name": body.name, "description": body.description, "threshold": body.threshold},
            )
            row = await conn.fetchrow(
                """SELECT d.key, d.name, d.description, d.icon, d.criteria, d.sort_order,
                          (SELECT COUNT(*) FROM tellus_user_badges ub WHERE ub.badge_key = d.key) AS award_count
                   FROM tellus_badge_definitions d WHERE d.key = $1""",
                key,
            )
    d = dict(row)
    if isinstance(d["criteria"], str):
        d["criteria"] = json.loads(d["criteria"])
    return TellusAdminBadge(**d)


@router.get("/admin/listings")
async def list_listings(
    brand_id: Optional[UUID] = None,
    active: Optional[bool] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    clauses: list[str] = []
    params: list = []
    i = 1
    if brand_id:
        clauses.append(f"l.brand_id = ${i}")
        params.append(brand_id)
        i += 1
    if active is not None:
        clauses.append(f"l.is_active = ${i}")
        params.append(active)
        i += 1
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT l.id, l.title, l.brand_id, b.name AS brand_name, l.points_cost,
                       l.quantity_total, l.quantity_claimed, l.redemption_type, l.is_active, l.created_at
                FROM tellus_reward_listings l
                LEFT JOIN tellus_brands b ON b.id = l.brand_id
                {where}
                ORDER BY l.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tellus_reward_listings l{where}", *params)
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.patch("/admin/listings/{listing_id}")
async def update_listing(
    listing_id: UUID, body: TellusAdminListingUpdate,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE tellus_reward_listings SET is_active = $2, updated_at = NOW() WHERE id = $1",
                listing_id, body.is_active,
            )
            if result == "UPDATE 0":
                raise HTTPException(404, "Listing not found")
            await record_admin_action(
                conn, admin, "listing.update", "listing", listing_id, {"is_active": body.is_active},
            )
    return {"is_active": body.is_active}
