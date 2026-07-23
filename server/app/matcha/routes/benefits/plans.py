"""Benefit plan + coverage-tier CRUD (admin/client-facing, under /benefits)."""
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.benefits import PlanCreate, PlanUpdate, TierInput
from app.matcha.services.benefits_enrollment import log_benefit_audit

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_tier(r) -> dict:
    return {
        "id": str(r["id"]),
        "plan_id": str(r["plan_id"]),
        "coverage_tier": r["coverage_tier"],
        "employee_cost": float(r["employee_cost"]),
        "employer_cost": float(r["employer_cost"]),
        "cost_period": r["cost_period"],
    }


def _serialize_plan(r, tiers: list[dict]) -> dict:
    return {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "plan_type": r["plan_type"],
        "name": r["name"],
        "carrier_name": r["carrier_name"],
        "description": r["description"],
        "status": r["status"],
        "waivable": r["waivable"],
        "tiers": tiers,
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


async def _require_company(current_user: CurrentUser) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    return company_id


@router.get("/plans")
async def list_plans(
    status: str | None = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        if status:
            plans = await conn.fetch(
                "SELECT * FROM benefit_plans WHERE company_id = $1 AND status = $2 ORDER BY plan_type, name",
                company_id, status,
            )
        else:
            plans = await conn.fetch(
                "SELECT * FROM benefit_plans WHERE company_id = $1 AND status != 'archived' ORDER BY plan_type, name",
                company_id,
            )
        plan_ids = [p["id"] for p in plans]
        tiers_by_plan: dict = {}
        if plan_ids:
            tier_rows = await conn.fetch(
                "SELECT * FROM benefit_plan_tiers WHERE plan_id = ANY($1::uuid[]) ORDER BY coverage_tier",
                plan_ids,
            )
            for t in tier_rows:
                tiers_by_plan.setdefault(t["plan_id"], []).append(_serialize_tier(t))
    return {
        "plans": [_serialize_plan(p, tiers_by_plan.get(p["id"], [])) for p in plans]
    }


@router.post("/plans")
async def create_plan(
    payload: PlanCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            try:
                plan = await conn.fetchrow(
                    """
                    INSERT INTO benefit_plans (company_id, plan_type, name, carrier_name, description, waivable)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING *
                    """,
                    company_id, payload.plan_type, payload.name, payload.carrier_name,
                    payload.description, payload.waivable,
                )
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail="a plan with this name already exists for this type")
            tiers = []
            for t in payload.tiers:
                tier = await conn.fetchrow(
                    """
                    INSERT INTO benefit_plan_tiers (plan_id, coverage_tier, employee_cost, employer_cost, cost_period)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING *
                    """,
                    plan["id"], t.coverage_tier, t.employee_cost, t.employer_cost, t.cost_period,
                )
                tiers.append(_serialize_tier(tier))
            await log_benefit_audit(
                conn, company_id, current_user.id, current_user.role,
                "plan", plan["id"], "created", {"name": payload.name, "plan_type": payload.plan_type},
            )
    return _serialize_plan(plan, tiers)


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        plan = await conn.fetchrow(
            "SELECT * FROM benefit_plans WHERE id = $1 AND company_id = $2", plan_id, company_id,
        )
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        tier_rows = await conn.fetch(
            "SELECT * FROM benefit_plan_tiers WHERE plan_id = $1 ORDER BY coverage_tier", plan_id,
        )
    return _serialize_plan(plan, [_serialize_tier(t) for t in tier_rows])


@router.patch("/plans/{plan_id}")
async def update_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM benefit_plans WHERE id = $1 AND company_id = $2", plan_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Plan not found")
        set_clauses = []
        values: list = []
        for i, (k, v) in enumerate(fields.items(), start=1):
            set_clauses.append(f"{k} = ${i}")
            values.append(v)
        values.append(plan_id)
        plan = await conn.fetchrow(
            f"UPDATE benefit_plans SET {', '.join(set_clauses)}, updated_at = NOW() "
            f"WHERE id = ${len(values)} RETURNING *",
            *values,
        )
        tier_rows = await conn.fetch(
            "SELECT * FROM benefit_plan_tiers WHERE plan_id = $1 ORDER BY coverage_tier", plan_id,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "plan", plan_id, "updated", fields,
        )
    return _serialize_plan(plan, [_serialize_tier(t) for t in tier_rows])


@router.put("/plans/{plan_id}/tiers")
async def replace_plan_tiers(
    plan_id: UUID,
    payload: list[TierInput],
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        plan = await conn.fetchrow(
            "SELECT id FROM benefit_plans WHERE id = $1 AND company_id = $2", plan_id, company_id,
        )
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        incoming_keys = {t.coverage_tier for t in payload}
        existing_tiers = await conn.fetch(
            "SELECT * FROM benefit_plan_tiers WHERE plan_id = $1", plan_id,
        )
        to_remove = [t for t in existing_tiers if t["coverage_tier"] not in incoming_keys]
        if to_remove:
            remove_ids = [t["id"] for t in to_remove]
            referenced = await conn.fetch(
                "SELECT DISTINCT tier_id FROM benefit_elections WHERE tier_id = ANY($1::uuid[])",
                remove_ids,
            )
            if referenced:
                referenced_tiers = [t["coverage_tier"] for t in to_remove if t["id"] in {r["tier_id"] for r in referenced}]
                raise HTTPException(
                    status_code=409,
                    detail=f"cannot remove tiers with existing elections: {', '.join(referenced_tiers)}",
                )
            await conn.execute(
                "DELETE FROM benefit_plan_tiers WHERE id = ANY($1::uuid[])", remove_ids,
            )

        async with conn.transaction():
            for t in payload:
                await conn.execute(
                    """
                    INSERT INTO benefit_plan_tiers (plan_id, coverage_tier, employee_cost, employer_cost, cost_period)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (plan_id, coverage_tier) DO UPDATE SET
                        employee_cost = EXCLUDED.employee_cost,
                        employer_cost = EXCLUDED.employer_cost,
                        cost_period = EXCLUDED.cost_period,
                        updated_at = NOW()
                    """,
                    plan_id, t.coverage_tier, t.employee_cost, t.employer_cost, t.cost_period,
                )
        tier_rows = await conn.fetch(
            "SELECT * FROM benefit_plan_tiers WHERE plan_id = $1 ORDER BY coverage_tier", plan_id,
        )
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role,
            "tier", plan_id, "updated", {"tier_count": len(payload)},
        )
    return {"tiers": [_serialize_tier(t) for t in tier_rows]}


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _require_company(current_user)
    async with get_connection() as conn:
        plan = await conn.fetchrow(
            "SELECT id FROM benefit_plans WHERE id = $1 AND company_id = $2", plan_id, company_id,
        )
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        election_count = await conn.fetchval(
            "SELECT COUNT(*) FROM benefit_elections WHERE plan_id = $1", plan_id,
        )
        if election_count:
            await conn.execute(
                "UPDATE benefit_plans SET status = 'archived', updated_at = NOW() WHERE id = $1", plan_id,
            )
            await log_benefit_audit(
                conn, company_id, current_user.id, current_user.role, "plan", plan_id, "archived",
            )
            return {"result": "archived"}
        await conn.execute("DELETE FROM benefit_plans WHERE id = $1", plan_id)
        await log_benefit_audit(
            conn, company_id, current_user.id, current_user.role, "plan", plan_id, "deleted",
        )
    return {"result": "deleted"}
