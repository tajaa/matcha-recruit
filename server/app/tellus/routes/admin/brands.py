"""Tell-Us internal admin — brand list/detail + plan overrides + owner
assignment (the first-ever writer of tellus_brands.claimed_at)."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ....database import get_connection
from .._shared import escape_like
from ...dependencies import require_tellus_admin
from ...models.tellus import TellusAccount
from ...services.admin_audit import record_admin_action
from ...models.admin import (
    TellusAdminAssignOwner,
    TellusAdminAuditEntry,
    TellusAdminBrandDetail,
    TellusAdminBrandList,
    TellusAdminBrandSummary,
    TellusAdminPlanAction,
)

router = APIRouter(dependencies=[Depends(require_tellus_admin)])

_BRAND_SELECT = """
    SELECT b.id, b.name, b.slug, b.plan_status, b.source, b.owner_account_id,
           a.email AS owner_email, b.location_count,
           (SELECT COUNT(*) FROM tellus_stores s WHERE s.brand_id = b.id) AS store_count,
           (b.stripe_subscription_id IS NOT NULL) AS has_stripe_subscription, b.created_at
    FROM tellus_brands b
    LEFT JOIN tellus_accounts a ON a.id = b.owner_account_id
"""


def _row_to_summary(row) -> TellusAdminBrandSummary:
    return TellusAdminBrandSummary(**dict(row))


@router.get("/admin/brands", response_model=TellusAdminBrandList)
async def list_brands(
    q: Optional[str] = None,
    plan_status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    clauses: list[str] = []
    params: list = []
    i = 1
    if q:
        clauses.append(f"(b.name ILIKE ${i} OR b.slug ILIKE ${i})")
        params.append(f"%{escape_like(q)}%")
        i += 1
    if plan_status:
        clauses.append(f"b.plan_status = ${i}")
        params.append(plan_status)
        i += 1
    if source:
        clauses.append(f"b.source = ${i}")
        params.append(source)
        i += 1
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{_BRAND_SELECT}{where} ORDER BY b.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tellus_brands b{where}", *params)
    return TellusAdminBrandList(
        items=[_row_to_summary(r) for r in rows], total=total, limit=limit, offset=offset,
    )


@router.get("/admin/brands/{brand_id}", response_model=TellusAdminBrandDetail)
async def get_brand_detail(brand_id: UUID):
    async with get_connection() as conn:
        row = await conn.fetchrow(f"{_BRAND_SELECT} WHERE b.id = $1", brand_id)
        if row is None:
            raise HTTPException(404, "Brand not found")

        extra = await conn.fetchrow(
            "SELECT activated_at, claimed_at, stripe_customer_id, stripe_subscription_id "
            "FROM tellus_brands WHERE id = $1", brand_id,
        )

        stores = await conn.fetch(
            "SELECT id, name, city, state FROM tellus_stores WHERE brand_id = $1 ORDER BY name", brand_id,
        )
        links = await conn.fetch(
            "SELECT id, is_active, revoked_at, created_at FROM tellus_links "
            "WHERE brand_id = $1 ORDER BY created_at DESC", brand_id,
        )
        prompts = await conn.fetch(
            "SELECT id, prompt, position FROM tellus_brand_prompts WHERE brand_id = $1 ORDER BY position",
            brand_id,
        )
        stats = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS last_30d,
                      ROUND(AVG(rating) FILTER (WHERE moderation_status <> 'removed')::numeric, 2) AS avg_rating
               FROM tellus_reports WHERE brand_id = $1""",
            brand_id,
        )
        audit_rows = await conn.fetch(
            "SELECT id, actor_email, action, target_type, target_id, detail, created_at "
            "FROM tellus_admin_audit WHERE target_type = 'brand' AND target_id = $1 "
            "ORDER BY created_at DESC LIMIT 10",
            str(brand_id),
        )

    return TellusAdminBrandDetail(
        brand=_row_to_summary(row),
        activated_at=extra["activated_at"],
        claimed_at=extra["claimed_at"],
        stripe_customer_id=extra["stripe_customer_id"],
        stripe_subscription_id=extra["stripe_subscription_id"],
        stores=[dict(r) for r in stores],
        links=[dict(r) for r in links],
        prompts=[dict(r) for r in prompts],
        report_stats=dict(stats) if stats else {},
        audit=[TellusAdminAuditEntry(**dict(r)) for r in audit_rows],
    )


@router.post("/admin/brands/{brand_id}/plan")
async def update_plan(
    brand_id: UUID, body: TellusAdminPlanAction,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT plan_status, stripe_subscription_id FROM tellus_brands WHERE id = $1", brand_id,
            )
            if row is None:
                raise HTTPException(404, "Brand not found")

            stripe_warning = None
            if body.action == "comp":
                await conn.execute(
                    "UPDATE tellus_brands SET plan_status = 'active', "
                    "activated_at = COALESCE(activated_at, NOW()), updated_at = NOW() WHERE id = $1",
                    brand_id,
                )
                new_status = "active"
                action_name = "brand.plan_comp"
            else:
                await conn.execute(
                    "UPDATE tellus_brands SET plan_status = 'canceled', updated_at = NOW() WHERE id = $1",
                    brand_id,
                )
                new_status = "canceled"
                action_name = "brand.plan_cancel"
                if row["stripe_subscription_id"]:
                    stripe_warning = (
                        f"Stripe subscription {row['stripe_subscription_id']} still exists — "
                        "cancel it in the Stripe dashboard."
                    )

            await record_admin_action(
                conn, admin, action_name, "brand", brand_id,
                {
                    "previous_status": row["plan_status"], "note": body.note,
                    "stripe_subscription_id": row["stripe_subscription_id"],
                },
            )
    return {"plan_status": new_status, "stripe_warning": stripe_warning}


@router.post("/admin/brands/{brand_id}/assign-owner")
async def assign_owner(
    brand_id: UUID, body: TellusAdminAssignOwner,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            brand = await conn.fetchrow(
                "SELECT owner_account_id FROM tellus_brands WHERE id = $1", brand_id,
            )
            if brand is None:
                raise HTTPException(404, "Brand not found")
            if brand["owner_account_id"] is not None:
                raise HTTPException(409, "Brand already has an owner — reassignment is not supported.")

            target = await conn.fetchrow(
                "SELECT id, email, account_type FROM tellus_accounts WHERE id = $1", body.account_id,
            )
            if target is None:
                raise HTTPException(404, "Account not found")

            already_owns = await conn.fetchval(
                "SELECT 1 FROM tellus_brands WHERE owner_account_id = $1", body.account_id,
            )
            if already_owns:
                raise HTTPException(409, "That account already owns a brand.")

            flipped_type = False
            if target["account_type"] == "consumer":
                await conn.execute(
                    "UPDATE tellus_accounts SET account_type = 'brand', updated_at = NOW() WHERE id = $1",
                    body.account_id,
                )
                flipped_type = True

            await conn.execute(
                "UPDATE tellus_brands SET owner_account_id = $1, claimed_at = NOW(), updated_at = NOW() "
                "WHERE id = $2",
                body.account_id, brand_id,
            )

            await record_admin_action(
                conn, admin, "brand.assign_owner", "brand", brand_id,
                {"account_id": str(body.account_id), "account_email": target["email"], "flipped_type": flipped_type},
            )

        row = await conn.fetchrow(f"{_BRAND_SELECT} WHERE b.id = $1", brand_id)
    return _row_to_summary(row)
