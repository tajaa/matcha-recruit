"""Propose, confirm, carry out: the life of an action on a finding. Pool-free.

* `propose`: the action must be one the task's playbook names for this kind
  of finding, available for it, under its daily limit. `prepare` freezes what
  would happen; an earlier proposal for the same finding and action expires.
* `confirm`: claims the proposal (`proposed` -> `running`) only while it is
  fresh, so a second confirm never runs it twice; a retry of one that ran gets
  its result back. `perform` gets the frozen proposal and nothing else.
* `cancel`: the person said no.

Every read and write is scoped to the person (another person's ids are 404).
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import UUID

from app.database import connection_or_direct, decode_jsonb

from .. import intake, playbooks
from ..service import AgentTaskError, owned_task
from . import ACTIONS
from .base import ActionContext, ActionError, ItemAction, Proposal

logger = logging.getLogger(__name__)

HISTORY = 5
FAILED = "It didn't go through. Nothing was done."


def _iso(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def for_item(task, item) -> list[ItemAction]:
    """The actions this finding takes: its playbook's, for its kind."""
    playbook = playbooks.get(task["playbook"])
    if playbook is None or task["engine"] != "chain":
        return []
    kind = item["kind"] or "other"
    return [ACTIONS[k] for k in playbook.actions if k in ACTIONS and kind in ACTIONS[k].item_kinds]


def views(user, task, item) -> list[dict]:
    ctx = ActionContext(user=user, task=dict(task), item=dict(item))
    return [action.view(ctx) for action in for_item(task, item)]


def action_view(row) -> dict:
    row = dict(row)
    action = ACTIONS.get(row["action"])
    preview = decode_jsonb(row.get("preview"), {}) or {}
    return {
        "id": str(row["id"]),
        "action": row["action"],
        "label": action.label if action else row["action"],
        "status": row["status"],
        "preview": preview,
        "confirm_label": preview.get("confirm") or (action.confirm_label if action else "Go ahead"),
        "result": decode_jsonb(row.get("result"), None),
        "error": row.get("error"),
        "item_id": str(row["item_id"]),
        "created_at": _iso(row.get("created_at")),
        "expires_at": _iso(row.get("expires_at")),
        "finished_at": _iso(row.get("finished_at")),
    }


async def history(conn, item_id: UUID, user_id: UUID) -> list[dict]:
    """What was done (or is waiting) for this finding, newest first."""
    rows = await conn.fetch(
        f"""SELECT * FROM mw_agent_task_actions
            WHERE item_id = $1 AND user_id = $2 AND status NOT IN ('cancelled', 'expired')
              AND NOT (status = 'proposed' AND expires_at <= NOW())
            ORDER BY created_at DESC LIMIT {HISTORY}""",
        item_id, user_id,
    )
    return [action_view(r) for r in rows]


async def _task_and_item(conn, task_id: UUID, item_id: UUID, user_id: UUID):
    task = await owned_task(conn, task_id, user_id)
    item = await conn.fetchrow(
        "SELECT * FROM mw_agent_task_items WHERE id = $1 AND task_id = $2", item_id, task_id,
    )
    if item is None:
        raise AgentTaskError("Finding not found.", 404)
    return task, item


async def propose(user, task_id: UUID, item_id: UUID, key: str, params: dict) -> dict:
    async with connection_or_direct() as conn:
        task, item = await _task_and_item(conn, task_id, item_id, user.id)
    action = next((a for a in for_item(task, item) if a.key == key), None)
    if action is None:
        raise AgentTaskError("That can't be done with this finding.", 404)
    ctx = ActionContext(user=user, task=dict(task), item=dict(item))
    reason = action.available(ctx)
    if reason is not None:
        raise AgentTaskError(reason, 409)
    clean, errors = intake.clean_fields(action.params, params or {})
    if errors:
        raise AgentTaskError("Check the details.", 422,
                             {"code": "invalid", "message": "Check the details.", "errors": errors})
    async with connection_or_direct() as conn:
        done_today = int(await conn.fetchval(
            """SELECT COUNT(*) FROM mw_agent_task_actions
               WHERE user_id = $1 AND action = $2 AND status IN ('running', 'done')
                 AND created_at > NOW() - INTERVAL '1 day'""",
            user.id, action.key,
        ) or 0)
    if done_today >= action.per_day:
        raise AgentTaskError(f"That's {action.per_day} today, the most for a day. Try again tomorrow.", 429)
    try:
        proposal: Proposal = await action.prepare(ctx, clean)
    except ActionError as exc:
        raise AgentTaskError(str(exc), exc.code) from exc
    async with connection_or_direct() as conn:
        async with conn.transaction():
            await conn.execute(
                """UPDATE mw_agent_task_actions SET status = 'expired'
                   WHERE item_id = $1 AND user_id = $2 AND action = $3 AND status = 'proposed'""",
                item_id, user.id, action.key,
            )
            row = await conn.fetchrow(
                """INSERT INTO mw_agent_task_actions
                       (task_id, item_id, user_id, action, params, frozen, preview, expires_at)
                   VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, NOW() + $8::interval)
                   RETURNING *""",
                task_id, item_id, user.id, action.key, json.dumps(clean, default=str),
                json.dumps(proposal.frozen, default=str),
                json.dumps({**proposal.preview(), **({"confirm": proposal.confirm} if proposal.confirm else {})}),
                timedelta(minutes=action.proposal_minutes),
            )
    return action_view(row)


async def confirm(user, action_id: UUID) -> dict:
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_agent_task_actions SET status = 'running', decided_at = NOW()
               WHERE id = $1 AND user_id = $2 AND status = 'proposed' AND expires_at > NOW()
               RETURNING *""",
            action_id, user.id,
        )
        if row is None:
            existing = await conn.fetchrow(
                "SELECT * FROM mw_agent_task_actions WHERE id = $1 AND user_id = $2", action_id, user.id,
            )
            if existing is None:
                raise AgentTaskError("Not found.", 404)
            if existing["status"] in ("running", "done", "failed"):
                return action_view(existing)  # a retry: what came of it
            if existing["status"] == "proposed":
                await conn.execute(
                    "UPDATE mw_agent_task_actions SET status = 'expired' WHERE id = $1 AND status = 'proposed'",
                    action_id,
                )
            raise AgentTaskError("That has expired. Start it again to see it as it is now.", 409)
        try:
            task, item = await _task_and_item(conn, row["task_id"], row["item_id"], user.id)
        except AgentTaskError:
            await conn.execute(
                "UPDATE mw_agent_task_actions SET status = 'cancelled', finished_at = NOW() WHERE id = $1",
                action_id,
            )
            raise
    action = ACTIONS.get(row["action"])
    ctx = ActionContext(user=user, task=dict(task), item=dict(item))
    status, result, error = "failed", None, FAILED
    try:
        if action is None:
            raise ActionError(FAILED)
        result = await action.perform(ctx, decode_jsonb(row["frozen"], {}) or {})
        status, error = "done", None
    except ActionError as exc:
        error = str(exc)
    except Exception:
        logger.warning("task action failed action=%s id=%s", row["action"], action_id, exc_info=True)
    async with connection_or_direct() as conn:
        done = await conn.fetchrow(
            """UPDATE mw_agent_task_actions
               SET status = $2, result = $3::jsonb, error = $4, finished_at = NOW()
               WHERE id = $1 RETURNING *""",
            action_id, status, json.dumps(result, default=str) if result is not None else None, error,
        )
    return action_view(done)


async def cancel(user, action_id: UUID) -> dict:
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_agent_task_actions SET status = 'cancelled', decided_at = NOW()
               WHERE id = $1 AND user_id = $2 AND status = 'proposed' RETURNING *""",
            action_id, user.id,
        )
        if row is None:
            row = await conn.fetchrow(
                "SELECT * FROM mw_agent_task_actions WHERE id = $1 AND user_id = $2", action_id, user.id,
            )
    if row is None:
        raise AgentTaskError("Not found.", 404)
    return action_view(row)
