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

from app.database import get_connection

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


def _decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


async def _load_proposed_run(
    conn, select: str, *, run_id: UUID, company_id: UUID, location_id: UUID,
    week_start: date, thread_id: UUID | None = None,
):
    """One scoped read of a still-proposed generation run.

    `select` is a fixed SQL expression, never caller input. `thread_id` admits
    that chat's own run; without it only an automatic run matches.
    """
    return _decode(await conn.fetchval(
        f"""SELECT {select} FROM schedule_generation_runs
            WHERE id=$1 AND company_id=$2 AND location_id=$3 AND week_start=$4
              AND status='proposed' AND (thread_id=$5 OR origin='automatic')""",
        run_id, company_id, location_id, week_start, thread_id,
    ))


_REVIEW_SOURCE_ID = {"schedule_week_draft": "generation_run_id", "schedule_change": "proposal_id"}


async def _load_frozen_review(
    conn, action_type: str, source_id: UUID, *, company_id: UUID, thread_id: UUID,
    location_id: UUID, week_start: date,
):
    """The full review a staged action was compacted from — the review only,
    not the frozen plan beside it, which can run to hundreds of shifts."""
    if action_type == "schedule_week_draft":
        return await _load_proposed_run(
            conn, "proposal->'schedule_review'", run_id=source_id, company_id=company_id,
            location_id=location_id, week_start=week_start, thread_id=thread_id,
        )
    review = _decode(await conn.fetchval(
        """SELECT proposal->'review' FROM schedule_chat_proposals
           WHERE id=$1 AND company_id=$2 AND status='proposed'""",
        source_id, company_id,
    ))
    # The row is written before its own id exists.
    return {**review, "proposal_id": str(source_id)} if isinstance(review, dict) else review


async def project_schedule_ui_state(
    state: dict | None, *, company_id: UUID, thread_id: UUID,
    location_id: UUID, week_start: date, include_cost: bool,
    actor_role: str | None = None, already_projected: bool = False,
) -> dict | None:
    """Expand a staged action's compact review for the board, without saving it.

    The model and durable thread keep their bounded summary. The UI needs the
    frozen assignment rows (and a week's demand curve), including when resuming
    an older chat. Callers must first authorize the schedule session's scope,
    and call this outside their own transaction: it is an optional read.
    """
    result = state if already_projected else project_schedule_payload(state, include_cost=include_cost)
    action = result.get("huume_action") if isinstance(result, dict) else None
    if (
        not isinstance(action, dict) or action.get("status") != "proposed"
        or action.get("type") not in _REVIEW_SOURCE_ID
    ):
        return result
    review = action.get("review")
    if isinstance(review, dict) and isinstance(review.get("assignments"), list):
        return result
    try:
        source_id = UUID(str(action.get(_REVIEW_SOURCE_ID[action["type"]])))
    except (TypeError, ValueError):
        return result
    try:
        async with get_connection() as conn:
            full_review = await _load_frozen_review(
                conn, action["type"], source_id, company_id=company_id, thread_id=thread_id,
                location_id=location_id, week_start=week_start,
            )
            if not isinstance(full_review, dict) or not isinstance(full_review.get("assignments"), list):
                return result
            automatic = action.get("auto_generated") or action.get("origin") == "automatic"
            # A manual review keeps the cost it was frozen with (per-person
            # rows included). An automatic run's cached price is never served:
            # it is priced for this recipient.
            full_review = project_schedule_payload(full_review, include_cost=include_cost and not automatic)
            action = {**action, "review": full_review}
            if automatic and include_cost:
                if isinstance(review, dict) and "cost" in review:
                    full_review["cost"] = review["cost"]
                else:
                    action = await price_automatic_action(
                        conn, company_id=company_id, location_id=location_id, week_start=week_start,
                        actor_role=actor_role, action=action,
                    )
                    full_review = action["review"]
            demand = action.get("demand_model")
            if isinstance(demand, dict) and "demand_model" not in full_review:
                full_review["demand_model"] = demand
            return {**result, "huume_action": action}
    except Exception:
        logger.warning("schedule review: preview read unavailable for %s", thread_id, exc_info=True)
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
                proposal = await _load_proposed_run(
                    conn, "proposal", run_id=UUID(str(action["generation_run_id"])),
                    company_id=company_id, location_id=location_id, week_start=week_start,
                )
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
                    incomplete = []
                    if open_positions:
                        incomplete.append(
                            f"{open_positions} seat{'s are' if open_positions != 1 else ' is'} still open"
                        )
                    unpriced = int(cost.get("unpriced_employee_count") or 0)
                    if unpriced:
                        incomplete.append(
                            f"{unpriced} employee{'s have' if unpriced != 1 else ' has'} no pay rate"
                        )
                    if incomplete:
                        labor["labor_pct"] = None
                        labor["note"] = "; ".join(incomplete) + ", so labor % isn't shown."
                    demand["labor"] = labor
                    review["demand_model"] = project_schedule_payload(demand, include_cost=True)
            return result
    except Exception:
        logger.warning("schedule review: automatic pricing unavailable for %s", company_id, exc_info=True)
        return project_schedule_payload(action, include_cost=False)
