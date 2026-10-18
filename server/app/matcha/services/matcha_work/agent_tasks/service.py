"""Tasks, their rounds and findings. Pool-free, so the API and the worker share it.

Every read and write is scoped to the owner (`user_id`); another person's id
is "not found". A deleted task keeps a blanked row and its rounds (a
tombstone) so it still counts against the month's allowance; its findings and
runs are deleted.

Statuses: `queued` and `running` are a live chain; `waiting` needs the person
(a form, a confirmation) and holds no worker, so it doesn't count toward the
live limit; `done`, `failed` and `cancelled` are resting. A task left waiting
for `WAIT_DAYS` is cancelled, and that round is free.

A job search is a task too (`engine = 'job_search'`): a pointer row whose
state is read from the search (`job_tasks`). Reading, cancelling and deleting
one goes through the job search's own service.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from app.database import connection_or_direct, decode_jsonb

from . import items as items_mod
from . import job_tasks, playbooks

LIVE = ("queued", "running")
OPEN = (*LIVE, "waiting")
RESTING = ("done", "failed", "cancelled")
_LIVE_SQL = ", ".join(f"'{s}'" for s in LIVE)
_OPEN_SQL = ", ".join(f"'{s}'" for s in OPEN)
# A live task that has not moved in this long has lost its chain for good.
STALE_INTERVAL = "2 hours"
WAIT_DAYS = 7
MAX_LIST = 50
MAX_ITEMS_SHOWN = 200
# Which kinds of task a person sees: everyone with Tasks sees both; someone
# who has job search but not yet Tasks sees their searches.
ENGINES = ("chain", "job_search")


class AgentTaskError(ValueError):
    def __init__(self, message: str, code: int = 400, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def _iso(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def phase_name(row: dict) -> str | None:
    phase = row.get("phase")
    return phase.split(".", 1)[1] if isinstance(phase, str) and "." in phase else phase


def _playbook_label(key: str | None) -> str:
    from . import playbooks  # the registry imports the playbooks, which import this

    playbook = playbooks.get(key)
    return playbook.label if playbook else ""


def task_view(row) -> dict:
    row = job_tasks.overlay(dict(row))
    completed, seen = row.get("completed_at"), row.get("seen_at")
    return {
        "id": str(row["id"]),
        "playbook": row.get("playbook"),
        "playbook_label": _playbook_label(row.get("playbook")),
        "source": row.get("source") or "espresso",
        "engine": row.get("engine") or "chain",
        "title": row.get("title") or "",
        "directive": row.get("directive") or "",
        "brief": decode_jsonb(row.get("brief"), {}) or {},
        "status": row["status"],
        "phase": phase_name(row),
        "progress": decode_jsonb(row.get("progress"), {}) or {},
        "error": row.get("error"),
        "needs": decode_jsonb(row.get("needs"), None),
        "current_round": int(row.get("current_round") or 0),
        "item_count": int(row.get("item_count") or 0),
        "shown_count": int(row.get("shown_count") or 0),
        "input_ids": [str(i) for i in row.get("input_ids") or []],
        "job_search_id": str(row["job_search_id"]) if row.get("job_search_id") else None,
        "unseen": bool(completed and (seen is None or seen < completed)),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "started_at": _iso(row.get("started_at")),
        "completed_at": _iso(row.get("completed_at")),
    }


def round_view(row) -> dict:
    row = dict(row)
    return {
        "id": str(row["id"]),
        "n": row["n"],
        "kind": row["kind"],
        "directive": row.get("directive") or "",
        "status": row["status"],
        "units": int(row.get("units") or 0),
        "items_added": int(row.get("items_added") or 0),
        "summary": decode_jsonb(row.get("summary"), {}) or {},
        "document": decode_jsonb(row.get("document"), None),
        "error": row.get("error"),
        "created_at": _iso(row.get("created_at")),
        "completed_at": _iso(row.get("completed_at")),
    }


def plan_view(task: dict) -> dict:
    playbook = playbooks.get(task.get("playbook"))
    plan = decode_jsonb(task.get("plan"), {}) or {}
    if playbook is None or not plan:
        return {"columns": [], "constraints": [], "preferences": [], "summary": ""}
    describe = playbook.describe_constraint or (lambda _c: "")
    return {
        "summary": plan.get("summary") or "",
        "item_kind": plan.get("item_kind"),
        "location": plan.get("location"),
        "columns": [playbook.field_library[k].view() for k in plan.get("fields") or []
                    if k in playbook.field_library],
        "constraints": [{**c, "label": describe(c)} for c in plan.get("constraints") or []],
        "preferences": plan.get("preferences") or [],
    }


def fingerprint(row) -> str:
    row = job_tasks.overlay(dict(row))
    raw = json.dumps(
        [row.get("status"), row.get("phase"), _iso(row.get("updated_at")),
         decode_jsonb(row.get("progress"), {}), row.get("current_round")],
        default=str, sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_COUNTS = f"""(SELECT COUNT(*) FROM mw_agent_task_items i WHERE i.task_id = t.id) AS item_count,
             (SELECT COUNT(*) FROM mw_agent_task_items i WHERE i.task_id = t.id
                AND i.rank_band < 9) AS shown_count,
             {job_tasks.COLUMNS}"""
# Every read of a task row: its own counts, and its search's state when it is one.
_SELECT = f"SELECT t.*, {_COUNTS} FROM mw_agent_tasks t {job_tasks.JOIN}"


async def list_tasks(user_id: UUID, company_id: UUID, *, engines: tuple[str, ...] = ENGINES,
                     before: tuple[datetime, UUID] | None = None, limit: int = MAX_LIST) -> list[dict]:
    boundary = "AND (t.created_at, t.id) < ($4, $5)" if before else ""
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""{_SELECT}
                WHERE t.user_id = $1 AND t.company_id = $2 AND t.deleted_at IS NULL
                  AND t.engine = ANY($3::text[]) AND {job_tasks.VISIBLE}
                  {boundary}
                ORDER BY t.created_at DESC, t.id DESC LIMIT {limit}""",
            user_id, company_id, list(engines), *(before or ()),
        )
    return [task_view(row) for row in rows]


async def list_task_page(user_id: UUID, company_id: UUID, *, engines=ENGINES, cursor: str | None = None) -> dict:
    before = None
    if cursor:
        try:
            stamp, task_id = cursor.split("|", 1)
            created = datetime.fromisoformat(stamp)
            if created.tzinfo is None:
                raise ValueError("Timezone required")
            before = (created, UUID(task_id))
        except (ValueError, TypeError) as exc:
            raise AgentTaskError("Invalid task history cursor.", 400) from exc
    tasks = await list_tasks(user_id, company_id, engines=engines, before=before, limit=MAX_LIST + 1)
    page = tasks[:MAX_LIST]
    next_cursor = f"{page[-1]['created_at']}|{page[-1]['id']}" if len(tasks) > MAX_LIST else None
    return {"tasks": page, "next_cursor": next_cursor}


async def find_search_task(user_id: UUID, company_id: UUID, search_id: UUID) -> dict:
    """Resolve an old search link without the recent task list's limit.

    Read-only: missing or deleted pointers/searches are not recreated.
    """
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""{_SELECT}
                WHERE t.user_id = $1 AND t.company_id = $2 AND t.job_search_id = $3
                  AND t.engine = 'job_search' AND t.deleted_at IS NULL AND {job_tasks.VISIBLE}""",
            user_id, company_id, search_id,
        )
    if row is None:
        raise AgentTaskError("Job search not found.", 404)
    return task_view(row)


async def summary(user_id: UUID, company_id: UUID, *, engines: tuple[str, ...] = ENGINES) -> dict:
    """What the sidebar row shows: running, waiting for the person, finished unseen."""
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""WITH v AS (
                    SELECT CASE WHEN t.engine = 'job_search' THEN {job_tasks.STATUS_SQL} ELSE t.status END AS status,
                           CASE WHEN t.engine = 'job_search' THEN s.completed_at ELSE t.completed_at END
                               AS completed_at,
                           t.seen_at
                    FROM mw_agent_tasks t {job_tasks.JOIN}
                    WHERE t.user_id = $1 AND t.company_id = $2 AND t.deleted_at IS NULL
                      AND t.engine = ANY($3::text[]) AND {job_tasks.VISIBLE}
                )
                SELECT COUNT(*) FILTER (WHERE status IN ({_LIVE_SQL})) AS running,
                       COUNT(*) FILTER (WHERE status = 'waiting') AS waiting,
                       COUNT(*) FILTER (WHERE status IN ('done', 'failed') AND completed_at IS NOT NULL
                                          AND (seen_at IS NULL OR seen_at < completed_at)) AS unseen
                FROM v""",
            user_id, company_id, list(engines),
        )
    row = dict(row or {})
    return {k: int(row.get(k) or 0) for k in ("running", "waiting", "unseen")}


async def owned_task(conn, task_id: UUID, user_id: UUID, *, lock: bool = False):
    row = await conn.fetchrow(
        f"""{_SELECT}
            WHERE t.id = $1 AND t.user_id = $2 AND t.deleted_at IS NULL"""
        if not lock else
        """SELECT * FROM mw_agent_tasks
           WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL FOR UPDATE""",
        task_id, user_id,
    )
    if row is None:
        raise AgentTaskError("Task not found.", 404)
    return row


_ITEM_ORDER = "ORDER BY rank NULLS LAST, created_at, id"


def _search_id(task) -> UUID | None:
    return task["job_search_id"] if task["engine"] == job_tasks.ENGINE else None


async def _job_call(operation):
    """A job search operation, its errors as a task's."""
    from app.matcha.services.matcha_work.job_search.service import JobSearchError

    try:
        return await operation
    except JobSearchError as exc:
        raise AgentTaskError(str(exc), exc.code, exc.detail) from exc


async def _job_task(conn, task, user_id: UUID, *, mark_seen: bool) -> dict:
    """A job search's task: its jobs as findings, and the search itself."""
    from app.matcha.services.matcha_work.job_search import service as job_service

    search = await _job_call(job_service.get_search(task["job_search_id"], user_id))
    view = task_view(task)
    if mark_seen and view["completed_at"] is not None and view["status"] in RESTING:
        await conn.execute("UPDATE mw_agent_tasks SET seen_at = NOW() WHERE id = $1", task["id"])
        view["unseen"] = False
    return {
        **view,
        "fingerprint": search["fingerprint"],
        "plan": plan_view({}),
        "rounds": [],
        "items": [job_tasks.lead_item(lead) for lead in search["leads"][:MAX_ITEMS_SHOWN]],
        "job_search": {k: v for k, v in search.items() if k != "leads"},
    }


async def get_task(task_id: UUID, user_id: UUID, *, mark_seen: bool = True, job_summary: bool = False) -> dict:
    async with connection_or_direct() as conn:
        task = await owned_task(conn, task_id, user_id)
        if _search_id(task) is not None:
            if job_summary:
                if task.get("js_status") is None or task.get("js_deleted_at") is not None:
                    raise AgentTaskError("Job search not found.", 404)
                view = task_view(task)
                if mark_seen and view["completed_at"] is not None and view["status"] in RESTING:
                    await conn.execute("UPDATE mw_agent_tasks SET seen_at = NOW() WHERE id = $1", task_id)
                    view["unseen"] = False
                return {**view, "fingerprint": fingerprint(task)}
            return await _job_task(conn, task, user_id, mark_seen=mark_seen)
        rows = await conn.fetch(
            f"SELECT * FROM mw_agent_task_items WHERE task_id = $1 {_ITEM_ORDER} LIMIT {MAX_ITEMS_SHOWN}",
            task_id,
        )
        rounds = await conn.fetch(
            "SELECT * FROM mw_agent_task_rounds WHERE task_id = $1 ORDER BY n", task_id,
        )
        if mark_seen and task["completed_at"] is not None and task["status"] in RESTING:
            await conn.execute("UPDATE mw_agent_tasks SET seen_at = NOW() WHERE id = $1", task_id)
    view = task_view(task)
    if mark_seen and task["completed_at"] is not None and task["status"] in RESTING:
        view["unseen"] = False
    return {
        **view,
        "fingerprint": fingerprint(task),
        "plan": plan_view(dict(task)),
        "rounds": [round_view(r) for r in rounds],
        "items": [items_mod.item_summary(r) for r in rows],
    }


async def status_view(task_id: UUID, user_id: UUID) -> dict:
    async with connection_or_direct() as conn:
        task = await owned_task(conn, task_id, user_id)
    if (search_id := _search_id(task)) is not None:
        from app.matcha.services.matcha_work.job_search import service as job_service

        # The search's own status read nudges its chain when it has stalled.
        status = await _job_call(job_service.status_view(search_id, user_id))
        shown = task_view(task)
        return {
            "id": shown["id"], "status": job_tasks.task_status(status["status"]), "phase": status["status"],
            "progress": status["progress"], "error": status["error"], "item_count": status["lead_count"],
            "current_round": 0, "updated_at": status["updated_at"], "fingerprint": status["fingerprint"],
        }
    view = {
        "id": str(task["id"]),
        "status": task["status"],
        "phase": phase_name(dict(task)),
        "progress": decode_jsonb(task["progress"], {}) or {},
        "error": task["error"],
        "item_count": int(task["item_count"] or 0),
        "current_round": int(task["current_round"] or 0),
        "updated_at": _iso(task["updated_at"]),
        "fingerprint": fingerprint(task),
    }
    if task["status"] in LIVE and task["engine"] == "chain":
        # A chain whose task was lost is restarted by whoever looks at it.
        from . import orchestrator

        await orchestrator.nudge(task_id)
    return view


_JOB_ITEMS = "A job search's jobs are opened and marked on the search itself."


async def get_item(task_id: UUID, item_id: UUID, user_id: UUID, *, user=None) -> dict:
    """A finding with its evidence, what it can do (`actions`, checked for
    `user`) and what was done with it (`action_history`)."""
    async with connection_or_direct() as conn:
        task = await owned_task(conn, task_id, user_id)
        if _search_id(task) is not None:
            raise AgentTaskError(_JOB_ITEMS, 409)
        row = await conn.fetchrow(
            "SELECT * FROM mw_agent_task_items WHERE id = $1 AND task_id = $2", item_id, task_id,
        )
        if row is None:
            raise AgentTaskError("Finding not found.", 404)
        return await _detail(conn, task, row, user_id, user)


async def _detail(conn, task, row, user_id: UUID, user) -> dict:
    """A finding as the app shows it: with its actions and what was done."""
    from .actions import service as actions

    done = await actions.history(conn, row["id"], user_id)
    return {**items_mod.item_detail(row), "actions": actions.views(user, task, row), "action_history": done}


async def _rerank(conn, task) -> None:
    playbook = playbooks.get(task["playbook"])
    if playbook is not None:
        await playbook.rerank(conn, dict(task))


async def patch_item(task_id: UUID, item_id: UUID, user_id: UUID, *, user_state: str | None,
                     notes: str | None, user=None) -> dict:
    async with connection_or_direct() as conn, conn.transaction():
        task = await owned_task(conn, task_id, user_id, lock=True)
        if _search_id(task) is not None:
            raise AgentTaskError(_JOB_ITEMS, 409)
        row = await conn.fetchrow(
            "SELECT * FROM mw_agent_task_items WHERE id = $1 AND task_id = $2 FOR UPDATE", item_id, task_id,
        )
        if row is None:
            raise AgentTaskError("Finding not found.", 404)
        was_dismissed = row["user_state"] == "dismissed"
        state = user_state if user_state is not None else row["user_state"]
        row = await conn.fetchrow(
            """UPDATE mw_agent_task_items SET user_state = $3, notes = $4, updated_at = NOW()
               WHERE id = $1 AND task_id = $2 RETURNING *""",
            item_id, task_id, state, notes if notes is not None else row["notes"],
        )
        # Dismissing (or restoring) moves the finding in or out of the ranking.
        if (state == "dismissed") != was_dismissed:
            await _rerank(conn, task)
            row = await conn.fetchrow(
                "SELECT * FROM mw_agent_task_items WHERE id = $1 AND task_id = $2", item_id, task_id,
            )
        return await _detail(conn, task, row, user_id, user)


async def close_round(conn, task_id: UUID) -> bool:
    """Settle the current round once its task stops: failed (free) when the
    task failed, the round was called off, or a "search more" found nothing
    new; cancelled when the task was; done otherwise. A task now waiting keeps
    its round open and starts its wait. True when this call settled the round
    (once a round: a settled round is never settled again)."""
    settled = await conn.execute(
        """UPDATE mw_agent_task_rounds r
           SET status = CASE
                   WHEN t.status = 'failed' THEN 'failed'
                   WHEN t.status = 'cancelled' THEN 'cancelled'
                   WHEN t.phase_cursor ? 'round_failed' THEN 'failed'
                   WHEN r.kind = 'more' AND r.items_added = 0 THEN 'failed'
                   ELSE 'done' END,
               error = CASE
                   WHEN t.status = 'failed' THEN t.error
                   WHEN t.phase_cursor ? 'round_failed' THEN t.phase_cursor->>'round_failed'
                   WHEN r.kind = 'more' AND r.items_added = 0 THEN 'Nothing new turned up.'
                   ELSE r.error END,
               completed_at = NOW()
           FROM mw_agent_tasks t
           WHERE t.id = $1 AND r.task_id = t.id AND r.n = t.current_round
             AND r.status IN ('queued', 'running') AND t.status <> 'waiting'""",
        task_id,
    )
    await conn.execute(
        """UPDATE mw_agent_tasks SET waiting_since = COALESCE(waiting_since, NOW())
           WHERE id = $1 AND status = 'waiting'""",
        task_id,
    )
    return isinstance(settled, str) and settled.startswith("UPDATE ") and settled.split()[-1] != "0"


async def cancel_task(task_id: UUID, user_id: UUID) -> dict:
    async with connection_or_direct() as conn:
        search_id = _search_id(await owned_task(conn, task_id, user_id))
    if search_id is not None:
        from app.matcha.services.matcha_work.job_search import service as job_service

        await _job_call(job_service.cancel_search(search_id, user_id))
        return await get_task(task_id, user_id, mark_seen=False)
    async with connection_or_direct() as conn, conn.transaction():
        task = await owned_task(conn, task_id, user_id, lock=True)
        if task["status"] in OPEN and task["engine"] == "chain":
            task = await conn.fetchrow(
                """UPDATE mw_agent_tasks
                   SET status = 'cancelled', dispatch_token = NULL, lease_until = NULL,
                       waiting_since = NULL, needs = NULL,
                       progress = progress || '{"note": "Cancelled."}'::jsonb,
                       completed_at = NOW(), updated_at = NOW()
                   WHERE id = $1 RETURNING *""",
                task_id,
            )
            await close_round(conn, task_id)
            # What was found so far stays useful, ranked.
            await _rerank(conn, task)
    return await get_task(task_id, user_id, mark_seen=False)


async def delete_task(task_id: UUID, user_id: UUID) -> dict:
    """Blank the task and drop its findings and runs; the row and its rounds
    stay as a tombstone so a deleted task still counts toward this month. A
    job search is deleted by its own service, which tombstones this row too."""
    async with connection_or_direct() as conn:
        search_id = _search_id(await owned_task(conn, task_id, user_id))
    if search_id is not None:
        from app.matcha.services.matcha_work.job_search import service as job_service

        return await _job_call(job_service.delete_search(search_id, user_id))
    async with connection_or_direct() as conn, conn.transaction():
        await owned_task(conn, task_id, user_id, lock=True)
        await conn.execute(
            f"""UPDATE mw_agent_tasks SET status = 'cancelled', dispatch_token = NULL, lease_until = NULL
                WHERE id = $1 AND status IN ({_OPEN_SQL})""",
            task_id,
        )
        await close_round(conn, task_id)
        await conn.execute("DELETE FROM mw_agent_task_items WHERE task_id = $1", task_id)
        await conn.execute(
            "DELETE FROM mw_project_agent_runs WHERE agent_task_id = $1 AND kind = 'agent_task'", task_id,
        )
        await conn.execute(
            """UPDATE mw_agent_task_rounds SET directive = '', scope = '{}'::jsonb, summary = '{}'::jsonb,
                      document = NULL, error = NULL
               WHERE task_id = $1""",
            task_id,
        )
        await conn.execute(
            """UPDATE mw_agent_tasks
               SET deleted_at = NOW(), title = '', directive = '', brief = '{}'::jsonb, plan = '{}'::jsonb,
                   progress = '{}'::jsonb, phase_cursor = '{}'::jsonb, needs = NULL, waiting_since = NULL,
                   input_ids = '{}', error = NULL, dispatch_token = NULL, lease_until = NULL,
                   completed_at = COALESCE(completed_at, NOW()), updated_at = NOW()
               WHERE id = $1""",
            task_id,
        )
    return {"deleted": True}


async def end_stale(conn, user_id: UUID) -> int:
    """End this person's live tasks that stopped moving STALE_INTERVAL ago, the
    way reconcile would: `done` when it found something (ranked), else
    `failed` (free). Runs inside the caller's transaction."""
    rows = await conn.fetch(
        f"""SELECT * FROM mw_agent_tasks
            WHERE user_id = $1 AND status IN ({_LIVE_SQL}) AND deleted_at IS NULL AND engine = 'chain'
              AND updated_at < NOW() - INTERVAL '{STALE_INTERVAL}'
            FOR UPDATE""",
        user_id,
    )
    for row in rows:
        found = bool(await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM mw_agent_task_items WHERE task_id = $1)", row["id"],
        ))
        if found:
            await _rerank(conn, row)
        await conn.execute(
            """UPDATE mw_agent_tasks
               SET status = $2, dispatch_token = NULL, lease_until = NULL,
                   error = COALESCE(error, 'Stopped: the task stopped making progress.'),
                   completed_at = NOW(), updated_at = NOW()
               WHERE id = $1""",
            row["id"], "done" if found else "failed",
        )
        await close_round(conn, row["id"])
    return len(rows)


async def expire_waiting() -> int:
    """Cancel tasks nobody answered for WAIT_DAYS. That round is free."""
    async with connection_or_direct() as conn, conn.transaction():
        rows = await conn.fetch(
            f"""UPDATE mw_agent_tasks
                SET status = 'cancelled', waiting_since = NULL, needs = NULL, completed_at = NOW(),
                    progress = progress || '{{"note": "Cancelled: no answer for {WAIT_DAYS} days."}}'::jsonb,
                    updated_at = NOW()
                WHERE status = 'waiting' AND deleted_at IS NULL
                  AND waiting_since < NOW() - INTERVAL '{WAIT_DAYS} days'
                RETURNING id, current_round"""
        )
        if rows:
            await conn.execute(
                """UPDATE mw_agent_task_rounds r SET status = 'failed', completed_at = NOW(),
                          error = 'No answer in time.'
                   FROM unnest($1::uuid[], $2::int[]) AS v(task_id, n)
                   WHERE r.task_id = v.task_id AND r.n = v.n AND r.status IN ('queued', 'running')""",
                [row["id"] for row in rows], [row["current_round"] for row in rows],
            )
    return len(rows)


async def find_by_request(user_id: UUID, request_id: UUID) -> dict | None:
    """A task this person already started with this request id (a retry)."""
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"{_SELECT} WHERE t.user_id = $1 AND t.request_id = $2", user_id, request_id,
        )
    return task_view(row) if row else None


async def task_for_search(user_id: UUID, search_id: UUID) -> dict:
    """A job search's task. A search older than its pointer (one an older app
    made between deploy and agenttask04) gets one now."""
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"{_SELECT} WHERE t.user_id = $1 AND t.job_search_id = $2 AND t.deleted_at IS NULL",
            user_id, search_id,
        )
        if row is None:
            search = await conn.fetchrow(
                "SELECT * FROM mw_job_searches WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL",
                search_id, user_id,
            )
            if search is None:
                raise AgentTaskError("Job search not found.", 404)
            await job_tasks.insert_pointer(conn, search)
            row = await conn.fetchrow(f"{_SELECT} WHERE t.user_id = $1 AND t.job_search_id = $2",
                                      user_id, search_id)
    return task_view(row)
