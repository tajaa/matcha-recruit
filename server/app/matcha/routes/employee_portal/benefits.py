"""Employee self-service benefits enrollment (feature: benefits_admin)."""
import json
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from app.matcha.models.benefits.benefits import ElectionUpsert, LifeEventCreate
from app.matcha.dependencies import require_employee_record
from app.matcha.services.benefits.benefits_enrollment import log_benefit_audit, resolve_active_window

from ._shared import _benefits_dep

router = APIRouter()


def _serialize_my_election(r) -> dict:
    return {
        "id": str(r["id"]),
        "plan_type": r["plan_type"],
        "plan_id": str(r["plan_id"]) if r["plan_id"] else None,
        "tier_id": str(r["tier_id"]) if r["tier_id"] else None,
        "waived": r["waived"],
        "dependents": json.loads(r["dependents"]) if isinstance(r["dependents"], str) else r["dependents"],
        "status": r["status"],
        "submitted_at": r["submitted_at"],
        "decided_at": r["decided_at"],
        "decision_note": r["decision_note"],
        "effective_date": r["effective_date"],
    }


async def _my_active_window(conn, org_id: UUID, employee_id: UUID) -> Optional[dict]:
    open_period = await conn.fetchrow(
        "SELECT * FROM open_enrollment_periods WHERE company_id = $1 AND status = 'open'",
        org_id,
    )
    life_events = await conn.fetch(
        """
        SELECT * FROM life_event_changes
        WHERE employee_id = $1 AND status = 'approved' AND window_ends_on IS NOT NULL
        """,
        employee_id,
    )
    return resolve_active_window(date.today(), dict(open_period) if open_period else None, [dict(r) for r in life_events])


@router.get("/me/benefits", dependencies=_benefits_dep)
async def get_my_benefits(employee: dict = Depends(require_employee_record)):
    org_id = employee["org_id"]
    async with get_connection() as conn:
        window = await _my_active_window(conn, org_id, employee["id"])

        plans = await conn.fetch(
            "SELECT * FROM benefit_plans WHERE company_id = $1 AND status = 'active' ORDER BY plan_type, name",
            org_id,
        )
        plan_ids = [p["id"] for p in plans]
        tiers_by_plan: dict = {}
        if plan_ids:
            tier_rows = await conn.fetch(
                "SELECT * FROM benefit_plan_tiers WHERE plan_id = ANY($1::uuid[]) ORDER BY coverage_tier",
                plan_ids,
            )
            for t in tier_rows:
                tiers_by_plan.setdefault(t["plan_id"], []).append({
                    "id": str(t["id"]), "coverage_tier": t["coverage_tier"],
                    "employee_cost": float(t["employee_cost"]), "employer_cost": float(t["employer_cost"]),
                    "cost_period": t["cost_period"],
                })

        window_elections = []
        if window:
            col = "open_enrollment_period_id" if window["kind"] == "oe" else "life_event_id"
            rows = await conn.fetch(
                f"SELECT * FROM benefit_elections WHERE employee_id = $1 AND {col} = $2",
                employee["id"], window["id"],
            )
            window_elections = [_serialize_my_election(r) for r in rows]

        current_coverage = await conn.fetch(
            """
            SELECT DISTINCT ON (plan_type) *
            FROM benefit_elections
            WHERE employee_id = $1 AND status = 'approved'
            ORDER BY plan_type, decided_at DESC
            """,
            employee["id"],
        )

    return {
        "window": {
            "kind": window["kind"],
            "id": str(window["id"]),
            "ends_on": window["row"].get("ends_on") if window["kind"] == "oe" else window["row"].get("window_ends_on"),
        } if window else None,
        "plans": [
            {
                "id": str(p["id"]), "plan_type": p["plan_type"], "name": p["name"],
                "carrier_name": p["carrier_name"], "description": p["description"],
                "waivable": p["waivable"], "tiers": tiers_by_plan.get(p["id"], []),
            }
            for p in plans
        ],
        "my_elections": window_elections,
        "current_coverage": [_serialize_my_election(r) for r in current_coverage],
    }


@router.put("/me/benefits/elections", dependencies=_benefits_dep)
async def upsert_my_election(
    payload: ElectionUpsert,
    employee: dict = Depends(require_employee_record),
):
    org_id = employee["org_id"]
    async with get_connection() as conn:
        window = await _my_active_window(conn, org_id, employee["id"])
        if not window:
            raise HTTPException(status_code=409, detail="No active enrollment window")

        active_plans_of_type = await conn.fetch(
            "SELECT * FROM benefit_plans WHERE company_id = $1 AND plan_type = $2 AND status = 'active'",
            org_id, payload.plan_type,
        )
        if not active_plans_of_type:
            raise HTTPException(status_code=400, detail="This plan type is not offered")

        if payload.waived:
            if not all(p["waivable"] for p in active_plans_of_type):
                raise HTTPException(status_code=400, detail="This plan type cannot be waived")
            plan_id = None
            tier_id = None
        else:
            plan_row = next((p for p in active_plans_of_type if p["id"] == payload.plan_id), None)
            if not plan_row:
                raise HTTPException(status_code=404, detail="Plan not found")
            tier_row = await conn.fetchrow(
                "SELECT * FROM benefit_plan_tiers WHERE id = $1 AND plan_id = $2",
                payload.tier_id, plan_row["id"],
            )
            if not tier_row:
                raise HTTPException(status_code=404, detail="Tier not found")
            plan_id = plan_row["id"]
            tier_id = tier_row["id"]

        col = "open_enrollment_period_id" if window["kind"] == "oe" else "life_event_id"
        existing = await conn.fetchrow(
            f"SELECT * FROM benefit_elections WHERE employee_id = $1 AND plan_type = $2 AND {col} = $3",
            employee["id"], payload.plan_type, window["id"],
        )
        dependents_json = json.dumps([d.model_dump(mode="json") for d in payload.dependents])

        if existing:
            if existing["status"] in ("submitted", "approved"):
                raise HTTPException(status_code=409, detail=f"election is already {existing['status']} for this window")
            election = await conn.fetchrow(
                """
                UPDATE benefit_elections
                SET plan_id = $1, tier_id = $2, waived = $3, dependents = $4,
                    status = 'draft', updated_at = NOW()
                WHERE id = $5
                RETURNING *
                """,
                plan_id, tier_id, payload.waived, dependents_json, existing["id"],
            )
        else:
            oe_id = window["id"] if window["kind"] == "oe" else None
            le_id = window["id"] if window["kind"] == "life_event" else None
            election = await conn.fetchrow(
                """
                INSERT INTO benefit_elections
                    (company_id, employee_id, open_enrollment_period_id, life_event_id,
                     plan_type, plan_id, tier_id, waived, dependents)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
                """,
                org_id, employee["id"], oe_id, le_id, payload.plan_type, plan_id, tier_id,
                payload.waived, dependents_json,
            )
        await log_benefit_audit(
            conn, org_id, employee["user_id"], "employee",
            "election", election["id"], "upserted", {"plan_type": payload.plan_type, "waived": payload.waived},
        )
    return _serialize_my_election(election)


@router.post("/me/benefits/elections/submit", dependencies=_benefits_dep)
async def submit_my_elections(employee: dict = Depends(require_employee_record)):
    org_id = employee["org_id"]
    async with get_connection() as conn:
        window = await _my_active_window(conn, org_id, employee["id"])
        if not window:
            raise HTTPException(status_code=409, detail="No active enrollment window")
        col = "open_enrollment_period_id" if window["kind"] == "oe" else "life_event_id"
        rows = await conn.fetch(
            f"""
            UPDATE benefit_elections
            SET status = 'submitted', submitted_at = NOW(), updated_at = NOW()
            WHERE employee_id = $1 AND {col} = $2 AND status = 'draft'
            RETURNING *
            """,
            employee["id"], window["id"],
        )
        if not rows:
            raise HTTPException(status_code=400, detail="No draft elections to submit")
        await log_benefit_audit(
            conn, org_id, employee["user_id"], "employee",
            "election", None, "submitted", {"count": len(rows)},
        )
    return {"submitted": [_serialize_my_election(r) for r in rows]}


@router.delete("/me/benefits/elections/{election_id}", dependencies=_benefits_dep)
async def delete_my_election(
    election_id: UUID,
    employee: dict = Depends(require_employee_record),
):
    async with get_connection() as conn:
        election = await conn.fetchrow(
            "SELECT * FROM benefit_elections WHERE id = $1 AND employee_id = $2",
            election_id, employee["id"],
        )
        if not election:
            raise HTTPException(status_code=404, detail="Election not found")
        if election["status"] != "draft":
            raise HTTPException(status_code=409, detail="Can only delete draft elections")
        await conn.execute("DELETE FROM benefit_elections WHERE id = $1", election_id)
    return {"result": "deleted"}


@router.get("/me/benefits/life-events", dependencies=_benefits_dep)
async def list_my_life_events(employee: dict = Depends(require_employee_record)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM life_event_changes WHERE employee_id = $1 ORDER BY created_at DESC",
            employee["id"],
        )
    return {"life_events": [
        {
            "id": str(r["id"]), "event_type": r["event_type"], "event_date": r["event_date"],
            "description": r["description"], "status": r["status"],
            "window_ends_on": r["window_ends_on"], "review_note": r["review_note"],
        }
        for r in rows
    ]}


@router.post("/me/benefits/life-events", dependencies=_benefits_dep)
async def report_my_life_event(
    payload: LifeEventCreate,
    employee: dict = Depends(require_employee_record),
):
    async with get_connection() as conn:
        event = await conn.fetchrow(
            """
            INSERT INTO life_event_changes (company_id, employee_id, event_type, event_date, description)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            employee["org_id"], employee["id"], payload.event_type, payload.event_date, payload.description,
        )
        await log_benefit_audit(
            conn, employee["org_id"], employee["user_id"], "employee",
            "life_event", event["id"], "reported", {"event_type": payload.event_type},
        )
    return {
        "id": str(event["id"]), "event_type": event["event_type"], "event_date": event["event_date"],
        "description": event["description"], "status": event["status"],
    }
