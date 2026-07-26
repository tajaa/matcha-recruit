"""Persistence for Huume agent runs (huume_runs/huume_steps — the tool-call
audit timeline) and the row-locked plan mutator used by the approve/execute
routes.

`huume_runs`/`huume_steps` are distinct from `mw_threads.current_state`,
which holds the PENDING intent (`huume_action`/`huume_plan`) — see the
huume03 migration docstring for the full justification.
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


async def update_huume_plan(thread_id: UUID, mutator: Callable[[Optional[dict]], dict]) -> dict:
    """Row-locked read-modify-write of `current_state.huume_plan`.

    `apply_update` (matcha_work_document) merges top-level keys only — two
    concurrent approve calls each doing their own `apply_update({"huume_plan":
    ...})` would race on a read-then-write with no lock in between. This
    holds `mw_threads` FOR UPDATE for the whole read-mutate-write so the
    approve and execute routes (and the agent loop's own plan-building tool)
    can't clobber each other's step-status edits.
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

            current_plan = state.get("huume_plan")
            new_plan = mutator(current_plan)
            state["huume_plan"] = new_plan
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
