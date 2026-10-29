"""One monthly allowance for the work Espresso does in the background.

Agent-card runs, job searches and Espresso tasks draw from one pool of units
per person per UTC month, `AGENT_TASK_MONTHLY_UNITS`.
Each kind costs roughly what it costs us (`WEIGHTS`): a card run is one quick
web research pass; a job search is a long chain of searches, page loads and
model runs. Pro's 60 units keep today's totals: 40 card runs plus 4 job
searches.

Nothing is stored for it. `used_units` sums what each source already records,
so the old rules carry over unchanged: a failed card run or job search is
free; a cancelled or deleted search counts (deleting leaves a blanked row).
A card's send-backs, rounds 2 to 5, are free; after that each costs a run.
A task's rounds carry their own `units` (the playbook's weight for the first,
`ROUND_UNITS` after that) and count unless the round failed; a deleted task
keeps its rounds.

Every creator counts and inserts under one per-person lock (`lock`), so two
starts at once can't both slip under the allowance, whatever their kinds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.billing.entitlements_service import (
    AGENT_TASK_MONTHLY_UNITS,
    resolve_plan_for_user,
)

WEIGHTS: dict[str, int] = {
    "agent_card": 1,
    "research": 3,
    # The kinds of search (`research/kinds.py`): research with their own questions.
    "products": 3,
    "apartments": 3,
    "places": 3,
    "reservation": 2,
    "job_search": 5,
}
# A card's rounds 2..(1 + FREE_CARD_SENDBACKS) cost nothing.
FREE_CARD_SENDBACKS = 4
# A follow-up round on a task. A refine re-screens what was found in code and
# only looks up what is missing; "search more" is a new search; a document
# uses no model.
ROUND_UNITS: dict[str, int] = {"refine": 0, "more": 1, "document": 0, "action": 0}


# An admin's per-person top-up, stored in `users.beta_features` beside the comp
# flags (`PATCH /admin/users/{id}/beta-flags`). Units added to the plan's own
# monthly limit, every month, until the admin sets it back to zero.
BONUS_KEY = "matcha_work_bonus_units"
MAX_BONUS_UNITS = 2000


def limit_for_plan(plan: str | None) -> int:
    return AGENT_TASK_MONTHLY_UNITS.get(plan or "", 0)


def clean_bonus(value) -> int:
    """A stored bonus as a count of units; anything that isn't a whole number
    from 0 up reads as no bonus."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return 0
    try:
        return max(0, min(MAX_BONUS_UNITS, int(value)))
    except ValueError:
        return 0


async def bonus_units(user_id: UUID | str) -> int:
    async with connection_or_direct() as conn:
        raw = await conn.fetchval(
            "SELECT beta_features ->> $2 FROM users WHERE id = $1", UUID(str(user_id)), BONUS_KEY,
        )
    return clean_bonus(raw)


async def limit_for_user(user_id: UUID | str, plan: str | None) -> int:
    """The monthly units this person has: their plan's, plus the admin's top-up.
    A plan with no allowance (Free, Lite) stays at zero, whatever is stored."""
    base = limit_for_plan(plan)
    if base <= 0:
        return base
    return base + await bonus_units(user_id)


def card_round_cost(round_no: int) -> int:
    """What a card run of this round costs: the first, and send-backs past the free ones."""
    return WEIGHTS["agent_card"] if round_no <= 1 or round_no > 1 + FREE_CARD_SENDBACKS else 0


def next_month_start(now: datetime) -> datetime:
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)


def usage_payload(limit: int, used: int, *, now: datetime | None = None) -> dict:
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "resets_at": next_month_start(now or datetime.now(timezone.utc)).isoformat(),
    }


def as_count(usage: dict, weight: int) -> dict:
    """The allowance in one kind's own terms ("3 of 12 job searches left"), for
    the app builds and screens that count runs or searches, not units."""
    limit = usage["limit"] // weight
    remaining = min(limit, usage["remaining"] // weight)
    return {**usage, "limit": limit, "used": limit - remaining, "remaining": remaining}


async def lock(conn, user_id: UUID | str) -> None:
    """The per-person lock every creator counts and inserts under. Take it
    before any per-object lock, so creators never deadlock."""
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{user_id}:task_allowance")


async def used_units(conn, user_id: UUID | str) -> int:
    """Units used this UTC month. Takes the caller's connection, so a creator
    can count inside the transaction that holds `lock`."""
    used = await conn.fetchval(
        """WITH month AS (
               SELECT date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS start
           )
           SELECT
             (SELECT COUNT(*) FROM mw_project_agent_runs r, month
               WHERE r.kind = 'card_agent' AND r.requested_by = $1
                 AND r.status IN ('queued', 'running', 'done')
                 AND r.created_at >= month.start
                 AND (COALESCE(r.round, 1) <= 1 OR r.round > 1 + $2)) * $3
           + (SELECT COUNT(*) FROM mw_job_searches s, month
               WHERE s.user_id = $1 AND s.status <> 'failed'
                 AND s.created_at >= month.start) * $4
           + (SELECT COALESCE(SUM(r.units), 0) FROM mw_agent_task_rounds r, month
               WHERE r.user_id = $1 AND r.units > 0 AND r.status <> 'failed'
                 AND r.created_at >= month.start)""",
        UUID(str(user_id)), FREE_CARD_SENDBACKS, WEIGHTS["agent_card"], WEIGHTS["job_search"],
    )
    return int(used or 0)


async def task_usage(user_id: UUID | str, *, plan: str | None = None) -> dict:
    """`{limit, used, remaining, resets_at}` in units, for the current UTC month."""
    plan = plan or await resolve_plan_for_user(user_id)
    async with connection_or_direct() as conn:
        used = await used_units(conn, user_id)
    return usage_payload(await limit_for_user(user_id, plan), used)


def over(limit: int | None, used: int, cost: int) -> bool:
    """Whether starting something that costs `cost` goes past the allowance.
    No limit (an admin) and free work never do."""
    return limit is not None and cost > 0 and used + cost > limit
