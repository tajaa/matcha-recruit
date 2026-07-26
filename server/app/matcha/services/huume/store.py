"""Persistence for Huume agent runs (huume_runs/huume_steps — the tool-call
audit timeline) and the row-locked plan mutator used by the approve/execute
routes.

`huume_runs`/`huume_steps` are distinct from `mw_threads.current_state`,
which holds the PENDING intent (`huume_action`/`huume_plans`) — see the
huume03 migration docstring for the full justification.

Plans are keyed by `offer_id` in `current_state.huume_plans` (a thread can be
onboarding more than one candidate at once — each candidate's plan is its own
key, so building/approving/executing one never touches another's).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional
from uuid import UUID

from app.database import get_connection


async def create_run(*, company_id: UUID, thread_id: UUID, user_id: Optional[UUID], trigger: str = "user_turn") -> UUID:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "INSERT INTO huume_runs (company_id, thread_id, user_id, trigger, status) "
            "VALUES ($1, $2, $3, $4, 'running') RETURNING id",
            company_id, thread_id, user_id, trigger,
        )
        return row["id"]


async def add_step(
    *, run_id: UUID, seq: int, tool: str, kind: str, label: str,
    status: str, args: Optional[dict] = None, result: Optional[dict] = None,
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO huume_steps (run_id, seq, tool, kind, label, args, result, status) "
            "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8) "
            "ON CONFLICT (run_id, seq) DO NOTHING",
            run_id, seq, tool, kind, label,
            json.dumps(args or {}, default=str), json.dumps(result or {}, default=str), status,
        )


async def complete_run(*, run_id: UUID, status: str, model_calls: int, token_usage: Optional[dict] = None, error: Optional[str] = None) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE huume_runs SET status = $2, model_calls = $3, token_usage = $4::jsonb, "
            "error = $5, completed_at = NOW() WHERE id = $1",
            run_id, status, model_calls, json.dumps(token_usage or {}, default=str), error,
        )


async def update_huume_plan(
    thread_id: UUID, offer_id: str, mutator: Callable[[Optional[dict]], Optional[dict]],
) -> Optional[dict]:
    """Row-locked read-modify-write of `current_state.huume_plans[offer_id]`.

    `apply_update` (matcha_work_document) merges top-level keys only — two
    concurrent writers each doing their own `apply_update({"huume_plans": {...}})`
    would race on a read-then-write with no lock in between. This holds
    `mw_threads` FOR UPDATE for the whole read-mutate-write so the approve
    and execute routes (and the agent loop's own plan-building tool) can't
    clobber each other's step-status edits, and only ever touch the one
    offer's key — never the whole `huume_plans` dict.

    `mutator` returning `None` deletes the key (used by cancel_staged).
    """
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT current_state, version FROM mw_threads WHERE id = $1 FOR UPDATE",
                thread_id,
            )
            if row is None:
                raise ValueError("Thread not found")
            raw_state = row["current_state"]
            if isinstance(raw_state, str):
                state = json.loads(raw_state) if raw_state else {}
            else:
                state = dict(raw_state or {})

            plans = dict(state.get("huume_plans") or {})
            current_plan = plans.get(offer_id)
            new_plan = mutator(current_plan)
            if new_plan is None:
                plans.pop(offer_id, None)
            else:
                plans[offer_id] = new_plan
            state["huume_plans"] = plans
            new_version = row["version"] + 1

            await conn.execute(
                "UPDATE mw_threads SET current_state = $1, version = $2, updated_at = NOW() WHERE id = $3",
                json.dumps(state, default=str), new_version, thread_id,
            )
            await conn.execute(
                "INSERT INTO mw_document_versions (thread_id, version, state_json, diff_summary) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (thread_id, version) DO NOTHING",
                thread_id, new_version, json.dumps(state, default=str), "Huume plan updated",
            )
            return new_plan


async def execute_plan_locked(
    *,
    thread_id: UUID,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    offer_id: str,
    features: dict[str, Any],
    integrations: dict[str, bool],
    approve_steps: Optional[list[str]] = None,
) -> "actions.PlanExecutionResult":
    """THE single plan-execution path — both the REST route
    (`routes/matcha_work/huume.py`) and the chat tool
    (`agent.py`'s execute_approved_steps handler) call this, so two callers
    can never run the same plan's steps concurrently and clobber each
    other's `record_id`s (gap 6 in the Huume hardening review).

    Takes a Postgres SESSION advisory lock keyed on (thread_id, offer_id) —
    deliberately NOT a row lock/transaction, because plan steps call slow
    external provisioning (Google Workspace/Slack) and must not hold a
    transaction open for that long. The lock is scoped to its own dedicated
    connection so it isn't released early by pool connection reuse.

    `approve_steps`: None means "don't newly approve anything, just run
    whatever is already `approved`" (the REST execute route's contract —
    approval is a separate call). A list (possibly empty) means "approve
    these step keys first" (empty = approve all still-`proposed` steps) —
    the chat tool's `execute_approved_steps(step_keys=...)` contract, which
    folds approve+execute into one turn.
    """
    from . import actions

    async with get_connection() as conn:
        await conn.execute("SELECT pg_advisory_lock(hashtext($1), hashtext($2))", str(thread_id), offer_id)
        try:
            row = await conn.fetchrow("SELECT current_state FROM mw_threads WHERE id = $1", thread_id)
            if row is None:
                raise ValueError("Thread not found")
            raw_state = row["current_state"]
            state = json.loads(raw_state) if isinstance(raw_state, str) else dict(raw_state or {})
            plan = (state.get("huume_plans") or {}).get(offer_id)
            if not isinstance(plan, dict) or not plan.get("steps"):
                raise ValueError(f"No onboarding plan is staged for offer {offer_id}.")

            if approve_steps is not None:
                plan = actions.mark_steps_approved(plan, approve_steps or None)

            exec_result = await actions.execute_plan_steps(
                company_id=company_id, actor_user_id=actor_user_id, plan=plan,
                features=features, integrations=integrations,
            )

            merged = await update_huume_plan(
                thread_id, offer_id,
                lambda current: actions.merge_executed_steps(current, exec_result.plan),
            )
            return actions.PlanExecutionResult(plan=merged, summaries=exec_result.summaries)
        finally:
            await conn.execute("SELECT pg_advisory_unlock(hashtext($1), hashtext($2))", str(thread_id), offer_id)


async def get_thread_integrations(company_id: UUID) -> dict[str, bool]:
    """Just the integrations half of `get_thread_features_and_integrations` —
    for callers (e.g. the Huume dispatcher) that already have a fresh
    features dict from elsewhere and would otherwise re-fetch it."""
    async with get_connection() as conn:
        integ_rows = await conn.fetch(
            "SELECT provider FROM integration_connections WHERE company_id = $1", company_id,
        )
    return {r["provider"]: True for r in integ_rows}


async def get_thread_features_and_integrations(company_id: UUID) -> tuple[dict[str, Any], dict[str, bool]]:
    """Live-reload company features + connected integrations — called at
    every plan-step evaluation/execute so a flag flip or a newly-connected
    integration is picked up without a stale in-memory copy."""
    from app.core.feature_flags import merge_company_features

    async with get_connection() as conn:
        company_row = await conn.fetchrow(
            "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id,
        )
        integ_rows = await conn.fetch(
            "SELECT provider FROM integration_connections WHERE company_id = $1", company_id,
        )
    features = merge_company_features(
        dict(company_row["enabled_features"] or {}) if company_row else {},
        company_row["signup_source"] if company_row else None,
    )
    integrations = {r["provider"]: True for r in integ_rows}
    return features, integrations
