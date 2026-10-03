"""Recipient projection for persisted schedule reviews and automatic pricing.

Saved JSON is not an authorization decision. Project it at every schedule
read/turn boundary; automatic drafts are priced for the authorized reader.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from math import isfinite
from uuid import UUID

from .labor_cost_service import (
    COST_ROLES, cost_delta_for_rows, is_labor_cost_visible, load_week_assignment_rows,
)

logger = logging.getLogger(__name__)

# All monetary fields currently carried by schedule state, review metadata,
# roster summaries and demand models. Staffing hours and sales stay visible.
_WAGE_FIELDS = frozenset({
    "cost", "labor", "labor_cost", "week_cost", "pay_rate",
    "default_hourly_rate", "blended_hourly_rate", "scheduled_cost_after", "labor_pct",
})


def project_schedule_payload(value, *, include_cost: bool):
    """Copy JSON without wage fields when the recipient lacks live access.

    The recursive copy also handles a review's nested demand_model and saved
    choices/step results. Never mutate a generation run shared by managers.
    """
    if isinstance(value, dict):
        return {
            key: project_schedule_payload(item, include_cost=include_cost)
            for key, item in value.items()
            if include_cost or key not in _WAGE_FIELDS
        }
    if isinstance(value, list):
        return [project_schedule_payload(item, include_cost=include_cost) for item in value]
    return value


def project_schedule_messages(messages: list[dict], *, include_cost: bool) -> list[dict]:
    """Withhold old assistant prose that could repeat previously visible pay.

    New turns record their visibility in metadata. Legacy assistant/system
    messages have no provenance, so they are withheld from an unauthorized
    reader rather than trying to redact arbitrary natural-language amounts.
    User messages are their own input and remain visible.
    """
    result = []
    for message in messages:
        metadata = message.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (ValueError, TypeError):
                metadata = {}
        metadata = metadata if isinstance(metadata, dict) else {}
        if not include_cost and message.get("role") != "user" and metadata.get("schedule_cost_visible") is not False:
            continue
        result.append(project_schedule_payload({**message, "metadata": metadata}, include_cost=include_cost))
    return result


async def schedule_cost_visible(conn, *, company_id: UUID, actor_role: str | None) -> bool:
    """A failed feature read must not serve previously cached wages."""
    if actor_role not in COST_ROLES:
        return False
    try:
        async with conn.transaction():
            return await is_labor_cost_visible(company_id, actor_role, conn=conn)
    except Exception:
        logger.warning("schedule review: cost visibility unavailable for %s", company_id)
        return False


async def price_automatic_action(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    actor_role: str | None, action: dict, proposal: dict | None = None,
) -> dict:
    """Price the frozen assignments, never regenerate demand or change consent.

    Read the whole location week so overtime uses the same basis as generation.
    Discard cached prices first: an unavailable/truncated read is unpriced,
    not yesterday's wage data or a confident partial total.
    """
    result = project_schedule_payload(action, include_cost=False)
    if not await schedule_cost_visible(conn, company_id=company_id, actor_role=actor_role):
        return result
    try:
        async with conn.transaction():
            if proposal is None:
                row = await conn.fetchrow(
                    """SELECT proposal FROM schedule_generation_runs
                       WHERE id=$1 AND company_id=$2 AND location_id=$3 AND week_start=$4
                         AND origin='automatic' AND status='proposed'""",
                    UUID(str(action["generation_run_id"])), company_id, location_id, week_start,
                )
                if not row:
                    return result
                proposal = row["proposal"]
                if isinstance(proposal, str):
                    proposal = json.loads(proposal)
            if not isinstance(proposal, dict) or not isinstance(proposal.get("shifts"), list):
                return result
            before, truncated = await load_week_assignment_rows(
                conn, company_id=company_id, location_id=location_id, week_start=week_start,
            )
            if truncated:
                return result
            added = [
                {
                    "employee_id": str(item["employee_id"]),
                    "starts_at": shift["starts_at"],
                    "worked_minutes": int(shift.get("worked_minutes") or 0),
                }
                for shift in proposal.get("shifts") or []
                for item in shift.get("proposed_assignments") or []
            ]
            cost = await cost_delta_for_rows(
                conn, company_id=company_id, location_id=location_id, actor_role=actor_role,
                weeks=[(week_start, before, [*before, *added])],
            )
            if cost is None:
                # The additive cost service catches SQL errors. Roll back this
                # savepoint too, so a failed query cannot poison the session write.
                raise ValueError("automatic pricing unavailable")
            review = result.get("review")
            if not isinstance(review, dict):
                return result
            review["cost"] = cost
            demand = result.get("demand_model")
            if isinstance(demand, dict) and demand.get("forecast_sales_week") is not None:
                forecast = float(demand["forecast_sales_week"])
                total = cost.get("after")
                if isfinite(forecast) and total is not None:
                    open_positions = int((result.get("metrics") or {}).get("open_positions") or 0)
                    labor = {
                        "forecast_sales_week": forecast, "scheduled_cost_after": total,
                        "labor_pct": round(float(total) * 100 / forecast, 2) if forecast > 0 else None,
                        "open_positions": open_positions,
                    }
                    if open_positions:
                        labor["labor_pct"] = None
                        labor["note"] = (
                            f"{open_positions} seat{'s are' if open_positions != 1 else ' is'} still open, "
                            "so labor % isn't shown."
                        )
                    demand["labor"] = labor
                    review["demand_model"] = project_schedule_payload(demand, include_cost=True)
            return result
    except Exception:
        logger.warning("schedule review: automatic pricing unavailable for %s", company_id, exc_info=True)
        return project_schedule_payload(action, include_cost=False)
