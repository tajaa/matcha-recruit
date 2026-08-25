"""Persistence boundary for individualized assignment break guidance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .schedule_break_rule_store import resolve_break_rules
from .schedule_breaks import MealWaiverAttestation, evaluate_break_plan, guidance_payload


async def refresh_assignment_break_guidance(
    conn,
    company_id: UUID,
    *,
    shift_id: UUID,
    employee_id: UUID,
    location_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    """Evaluate and store the break instructions shown for one assignment."""
    if location_id is None:
        return
    timezone_name = await conn.fetchval(
        "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    try:
        location_timezone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return
    shift_date = starts_at.astimezone(location_timezone).date()
    resolved = await resolve_break_rules(
        conn, company_id=company_id, location_id=location_id, shift_date=shift_date,
    )
    if resolved.timezone is None:
        return
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
        company_id, employee_id, starts_at.astimezone(resolved.timezone).date(),
    )
    waiver = None
    if waiver_row:
        waiver = MealWaiverAttestation(
            id=waiver_row["id"], on_file=waiver_row["value"],
            effective_from=waiver_row["effective_from"],
            confirmed_by=waiver_row["confirmed_by"],
            confirmed_at=waiver_row["confirmed_at"],
        )
    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=resolved.timezone,
        rules=resolved.rules, waiver=waiver,
    )
    payload = guidance_payload(
        plan, timezone=resolved.timezone.key, evaluated_at=datetime.now(timezone.utc),
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
