"""Job searches as Tasks.

A job search keeps its own tables and its own chain (`job_search/`): pay
evidence, the person's ranking weights and drafted approaches don't fit a
generic finding. In Tasks it is a pointer: a row in `mw_agent_tasks` with
`engine = 'job_search'` and `job_search_id`, written in the transaction that
creates the search (`insert_pointer`, from `job_search/enqueue.create_search`;
`agenttask04` for searches made before). Its `request_id` is the search's id.

What Tasks shows for one (status, note, counts, dates) is read from the search
on every read (`COLUMNS` + `overlay`), so the two never drift. The pointer's
own `status` stays `done`: the task chain's reconcile scans the table's live
rows, and a pointer must never look like a chain to it. Its own
`completed_at` records that the person was told the search finished, so a
redraft that finishes later doesn't tell them again.

Started like any task (the `tasks` ability, a submitted form): the playbook
below gives Espresso's form its fields, and `start` turns the checked brief
into a search. Refine, search more and documents don't apply; a search is
re-ranked and redrafted from its own page (`/job-searches`).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.database import decode_jsonb
from app.matcha.services.matcha_work.job_search.ranking import BELOW_FLOOR_BAND

from .playbook import IntakeField, Playbook

logger = logging.getLogger(__name__)

ENGINE = "job_search"
KEY = "job_search"

# A search's status as Tasks reads it; its phases (planning … approaching)
# are all `running`.
_STATUS = {"queued": "queued", "done": "done", "failed": "failed", "cancelled": "cancelled"}
STATUS_SQL = "CASE s.status " + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in _STATUS.items()) + " ELSE 'running' END"

JOIN = "LEFT JOIN mw_job_searches s ON s.id = t.job_search_id"
# A job counts as shown when it is a match at the search's fit floor: once
# ranked, a weaker fit sits in `BELOW_FLOOR_BAND` (`job_search.ranking`).
_MATCH_BAND = f"(l.rank_band IS NULL OR l.rank_band < {BELOW_FLOOR_BAND})"
COLUMNS = f"""s.status AS js_status, s.title AS js_title, s.ask AS js_ask, s.progress AS js_progress,
             s.error AS js_error, s.updated_at AS js_updated_at, s.started_at AS js_started_at,
             s.completed_at AS js_completed_at, s.deleted_at AS js_deleted_at,
             (SELECT COUNT(*) FROM mw_job_leads l WHERE l.search_id = s.id) AS js_lead_count,
             (SELECT COUNT(*) FROM mw_job_leads l WHERE l.search_id = s.id
                AND l.screen_status <> 'irrelevant' AND l.user_state <> 'dismissed'
                AND {_MATCH_BAND}) AS js_shown_count"""
# A pointer whose search is gone (deleted from an older app) isn't shown.
VISIBLE = "(t.engine <> 'job_search' OR (s.id IS NOT NULL AND s.deleted_at IS NULL))"

TOP_LEADS = 3


def task_status(search_status: str | None) -> str:
    return _STATUS.get(search_status or "", "running")


def overlay(row: dict) -> dict:
    """A task row as Tasks shows it: a pointer takes its search's state."""
    if row.get("engine") != ENGINE or row.get("js_status") is None:
        return row
    return {
        **row,
        "status": task_status(row["js_status"]),
        "phase": row["js_status"],
        "title": row.get("js_title") or row.get("title") or "",
        "directive": row.get("js_ask") or row.get("directive") or "",
        "progress": row.get("js_progress"),
        "error": row.get("js_error"),
        "updated_at": row.get("js_updated_at") or row.get("updated_at"),
        "started_at": row.get("js_started_at"),
        "completed_at": row.get("js_completed_at"),
        "item_count": row.get("js_lead_count"),
        "shown_count": row.get("js_shown_count"),
    }


def lead_item(lead: dict) -> dict:
    """A job (`job_search.service.lead_summary`) as a Tasks finding. Pay is
    verified only when the posting states it; "Not posted" is unknown."""
    location = lead.get("location") or ""
    if lead.get("remote") and "remote" not in location.lower():
        location = f"{location} · Remote" if location else "Remote"
    screen = lead.get("screen_status")
    fields = {
        "company": {"display": lead.get("company") or "", "value": lead.get("company"), "status": "verified"},
        "location": {"display": location, "value": location, "status": "verified"},
        "pay": {
            "display": lead.get("comp_line") or "Not posted",
            "value": lead.get("comp_annual_min"),
            "status": "verified" if lead.get("comp_status") == "posted" else "unknown",
            **({"currency": lead["comp_currency"]} if lead.get("comp_currency") else {}),
        },
    }
    return {
        "id": lead["id"],
        "kind": "other",
        "title": lead.get("title") or "",
        "subtitle": lead.get("company") or "",
        "url": lead.get("apply_url") or lead.get("source_url"),
        "origin": "provider",
        "provider": lead.get("source"),
        "fields": {k: v for k, v in fields.items() if v["display"]},
        "images": [],
        "status": "irrelevant" if screen == "irrelevant" else "verified" if screen == "relevant" else "candidate",
        "fit_score": lead.get("fit_score"),
        "rank": lead.get("rank"),
        "rank_band": lead.get("rank_band"),
        "flags": list(lead.get("flags") or []),
        "user_state": lead.get("user_state") or "new",
        "round": 1,
    }


# ── the playbook ─────────────────────────────────────────────────────────────

REMOTE = {"Any": "any", "Remote only": "remote_only", "On-site only": "onsite_only"}

INTAKE = (
    IntakeField(key="titles", label="Job titles", type="list", help="Like “COO, VP Operations”"),
    IntakeField(key="locations", label="Where", type="list", help="Cities, states or countries"),
    IntakeField(key="remote", label="Remote or on-site", type="select", options=tuple(REMOTE)),
    IntakeField(key="base_floor", label="Lowest base salary you'd take", type="money"),
    IntakeField(key="use_resume", label="Use my saved résumé", type="boolean",
                help="To judge fit and write the drafts. Only Espresso's AI models read it."),
)


def validate_brief(raw: dict) -> dict:
    from pydantic import ValidationError

    from app.matcha.models.matcha_work.job_search import JobCriteria

    remote = raw.get("remote") or "Any"
    floor = raw.get("base_floor")
    try:
        criteria = JobCriteria(
            titles=list(raw.get("titles") or []), locations=list(raw.get("locations") or []),
            remote=REMOTE.get(remote, remote if remote in REMOTE.values() else "any"),
            base_floor=int(floor) if isinstance(floor, (int, float)) else None,
        )
    except ValidationError as exc:
        first = (exc.errors() or [{}])[0]
        raise ValueError(str(first.get("msg") or "Those job search details don't fit.")) from exc
    return {
        "titles": criteria.titles, "locations": criteria.locations, "remote": criteria.remote,
        "base_floor": criteria.base_floor, "use_resume": raw.get("use_resume") is True,
    }


async def _no_rerank(_conn, _task: dict) -> int:
    return 0


PLAYBOOK = Playbook(
    key=KEY,
    label="Job search",
    description=(
        "Find jobs to apply for: live postings from employers' own job boards and the web, each one's "
        "pay (only what it posts) and application questions, ranked by what the person cares about, "
        "with drafted approaches for the best. For anyone looking for a job or a role."
    ),
    engine=ENGINE,
    item_kinds=("other",),
    intake=INTAKE,
    validate_brief=validate_brief,
    field_library={},
    phases={},
    first_phase="",
    round_phases={},
    rerank=_no_rerank,
    consent="jobs",
)


# ── starting one ─────────────────────────────────────────────────────────────

async def insert_pointer(conn, search: Any, *, origin: tuple[UUID | None, UUID | None] | None = None) -> None:
    """The search's row in Tasks, on the caller's transaction. Idempotent."""
    search = dict(search)
    channel_id, message_id = origin or (None, None)
    await conn.execute(
        """INSERT INTO mw_agent_tasks
               (request_id, user_id, company_id, source, playbook, engine, title, directive, status,
                job_search_id, origin_channel_id, origin_message_id, created_at, updated_at)
           VALUES ($1, $2, $3, 'espresso', $4, $5, $6, $7, 'done', $1, $8, $9, $10, $10)
           ON CONFLICT DO NOTHING""",
        search["id"], search["user_id"], search["company_id"], KEY, ENGINE,
        (search.get("title") or "")[:120], search.get("ask") or "", channel_id, message_id,
        search["created_at"],
    )


async def start(user, company_id: UUID, body, brief: dict, *,
                origin: tuple[UUID | None, UUID | None] | None = None,
                recap_parent_run_id: UUID | None = None) -> dict:
    """Start the job search a task asked for; returns its task. `body`:
    `AgentTaskCreate`. Raises what `create_search` raises (plan, allowance,
    consent, a search already running)."""
    from app.matcha.models.matcha_work.job_search import JobCriteria, JobSearchCreate
    from app.matcha.services.matcha_work.job_search import enqueue as job_enqueue

    from . import service

    create = JobSearchCreate(
        request_id=body.request_id, title=(body.title or "")[:120], ask=body.directive[:4000],
        criteria=JobCriteria(titles=brief["titles"], locations=brief["locations"], remote=brief["remote"],
                             base_floor=brief["base_floor"]),
        use_resume=brief["use_resume"], consent_version=body.consent_version,
    )
    search = await job_enqueue.create_search(user, company_id, create, origin=origin,
                                            **({"recap_parent_run_id": recap_parent_run_id} if recap_parent_run_id else {}))
    return await service.task_for_search(user.id, UUID(search["id"]))


# ── when one stops ───────────────────────────────────────────────────────────

async def search_stopped(conn, search_id: UUID) -> None:
    """A search reached a resting status: tell the person once, email them
    the top jobs, and post the card where it was started from. Best effort,
    like a task's."""
    from app.matcha.services.matcha_work.job_search.service import lead_summary

    from . import chat, mail, notify

    try:
        row = await conn.fetchrow(
            f"""SELECT t.*, {COLUMNS} FROM mw_agent_tasks t {JOIN}
                WHERE t.job_search_id = $1 AND t.deleted_at IS NULL""",
            search_id,
        )
        if row is None or row["completed_at"] is not None:
            return
        task = overlay(dict(row))
        if task["status"] not in ("done", "failed"):
            return
        await conn.execute("UPDATE mw_agent_tasks SET completed_at = NOW() WHERE id = $1", task["id"])
        await notify.tell(conn, task)
        top = [lead_item(lead_summary(r)) for r in await conn.fetch(
            f"""SELECT * FROM mw_job_leads l WHERE search_id = $1 AND screen_status <> 'irrelevant'
                AND {_MATCH_BAND}
                ORDER BY rank NULLS LAST, created_at LIMIT {TOP_LEADS}""",
            search_id,
        )] if task["status"] == "done" else []
        progress = decode_jsonb(task.get("progress"), {}) or {}
        task = {**task, "progress": progress}
        await mail.search_finished(conn, task, top)
        if task.get("origin_channel_id") is None:
            return
        message = await chat.post_card(conn, task, company_id=task["company_id"],
                                       channel_id=task["origin_channel_id"], top=top)
        if message is not None:
            from app.matcha.services.matcha_work.project_agent.chat import broadcast_espresso_message

            await broadcast_espresso_message(message)
    except Exception:
        logger.warning("job search task card or notification failed search=%s", search_id, exc_info=True)
