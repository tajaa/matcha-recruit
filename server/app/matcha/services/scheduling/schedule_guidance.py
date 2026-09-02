"""Persistence boundary for individualized assignment break guidance."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .schedule_break_rule_store import resolve_break_rules
from .schedule_breaks import (
    BreakPlan,
    MealWaiverAttestation,
    evaluate_break_plan,
    guidance_payload,
)
from .shift_compliance import _age_on


async def resolve_shift_break_plan(
    conn,
    company_id: UUID,
    *,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    employee_id: UUID | None = None,
) -> BreakPlan:
    """Evaluate the approved plan for an open shift or one assignee."""
    if location_id is None:
        return evaluate_break_plan(
            starts_at=starts_at, ends_at=ends_at, timezone=ZoneInfo("UTC"), rules=(),
        )
    timezone_name = await conn.fetchval(
        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    try:
        location_timezone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return evaluate_break_plan(
            starts_at=starts_at, ends_at=ends_at, timezone=ZoneInfo("UTC"), rules=(),
        )
    shift_date = starts_at.astimezone(location_timezone).date()
    resolved = await resolve_break_rules(
        conn, company_id=company_id, location_id=location_id, shift_date=shift_date,
    )
    effective_timezone = resolved.timezone or location_timezone

    waiver = None
    employee_age = None
    age_unknown = False
    if employee_id is not None:
        employee_row = await conn.fetchrow(
            """
            SELECT ed.date_of_birth
            FROM employees e
            LEFT JOIN employee_demographics ed ON ed.employee_id = e.id
            WHERE e.id = $1 AND e.org_id = $2
            """,
            employee_id, company_id,
        )
        employee_age = _age_on(
            employee_row["date_of_birth"] if employee_row else None,
            starts_at.astimezone(effective_timezone).date(),
        )
        age_unknown = employee_age is None and any(
            rule.minimum_age is not None or rule.maximum_age is not None
            for rule in resolved.rules
        )
        waiver_row = await conn.fetchrow(
            """
            SELECT id, value, effective_from, confirmed_by, confirmed_at
            FROM employee_compliance_attestations
            WHERE company_id = $1 AND employee_id = $2
              AND attestation_type = 'meal_break_waiver_on_file'
              AND effective_from <= $3
            ORDER BY effective_from DESC, confirmed_at DESC
            LIMIT 1
            """,
            company_id, employee_id, starts_at.astimezone(effective_timezone).date(),
        )
        if waiver_row:
            waiver = MealWaiverAttestation(
                id=waiver_row["id"], on_file=waiver_row["value"],
                effective_from=waiver_row["effective_from"],
                confirmed_by=waiver_row["confirmed_by"],
                confirmed_at=waiver_row["confirmed_at"],
            )

    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=effective_timezone,
        rules=resolved.rules, waiver=waiver, employee_age=employee_age,
    )
    advisories = list(plan.advisories) + list(resolved.advisories)
    if age_unknown:
        advisories.append({
            "check": "break_rules",
            "code": "employee_age_unverified",
            "severity": "advisory",
            "message": "Employee age is not on file; age-specific break rules require manual review.",
        })
    status = "error" if resolved.source == "error" or age_unknown else plan.status
    return replace(plan, status=status, advisories=tuple(advisories))


async def refresh_assignment_break_guidance(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    employee_id: UUID,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
) -> BreakPlan:
    """Evaluate and store the break instructions shown for one assignment."""
    plan = await resolve_shift_break_plan(
        conn, company_id, location_id=location_id, starts_at=starts_at,
        ends_at=ends_at, employee_id=employee_id,
    )
    if location_id is None:
        return plan
    timezone_name = "UTC"
    if location_id is not None:
        timezone_name = await conn.fetchval(
            "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
            location_id, company_id,
        ) or "UTC"
    payload = guidance_payload(
        plan, timezone=timezone_name, evaluated_at=datetime.now(timezone.utc),
    )
    await conn.execute(
        """
        UPDATE schedule_shift_assignments
        SET compliance_guidance = $1::jsonb,
            guidance_evaluated_at = NOW(),
            guidance_ruleset_hash = $2
        WHERE company_id = $3 AND shift_id = $4 AND employee_id = $5
        """,
        json.dumps(payload), plan.rule_set_hash, company_id, shift_id, employee_id,
    )
    return plan
