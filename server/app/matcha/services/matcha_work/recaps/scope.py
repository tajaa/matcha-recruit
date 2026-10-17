"""Server-owned source identity. Optional registration is fenced before dispatch."""
from __future__ import annotations

import logging
from contextvars import ContextVar
from functools import wraps
from uuid import UUID

from app.database import connection_or_direct

from . import settings
from app.matcha.models.matcha_work.recaps import Event, clip

logger = logging.getLogger(__name__)
current_run: ContextVar[UUID | None] = ContextVar("recap_run", default=None)
SOURCE_COLUMNS = {"run": "run_id", "research": "task_round_id", "jobs": "job_search_id"}


def observe_run(fn):
    @wraps(fn)
    async def wrapped(ctx, *args, **kwargs):
        token = current_run.set(ctx.run_id)
        try:
            return await fn(ctx, *args, **kwargs)
        finally:
            current_run.reset(token)
    return wrapped


async def source_for_run(conn, run_id):
    if run_id is None:
        return None
    return await conn.fetchrow(
        """SELECT s.*, r.company_id, r.owner_user_id, r.state FROM mw_agent_recap_sources s
           JOIN mw_agent_recaps r ON r.id=s.recap_id
           WHERE s.run_id=$1 AND s.kind='run'""", run_id,
    )


async def register(conn, *, kind: str, source_id: UUID, user_id: UUID, company_id: UUID,
                   title: str, generation: int = 0, parent_run_id: UUID | None = None,
                   phase: bool = False) -> UUID | None:
    if not settings.enabled():
        return None
    parent_run_id = parent_run_id or current_run.get()
    parent = None
    try:
        async with conn.transaction():
            parent = await source_for_run(conn, parent_run_id)
            if parent and (parent["owner_user_id"] != user_id or parent["company_id"] != company_id):
                raise ValueError("source owner mismatch")
            if parent and parent["state"] not in ("collecting", "waiting"):
                parent = None
            if not settings.available(user_id):
                return None
            pref = await conn.fetchrow(
                "SELECT enabled, email_enabled FROM mw_agent_recap_preferences WHERE company_id=$1 AND user_id=$2",
                company_id, user_id,
            )
            if not pref or not pref["enabled"]:
                return None
            personal = await conn.fetchval(
                "SELECT is_personal FROM companies WHERE id=$1", company_id,
            )
            if not personal:
                return None
            if parent:
                recap_id = parent["recap_id"]
                # Serializes child enrollment against manifest finalization.
                state = await conn.fetchval("SELECT state FROM mw_agent_recaps WHERE id=$1 FOR UPDATE", recap_id)
                if state not in ("collecting", "waiting"):
                    return None
            else:
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"recap-cap:{user_id}")
                count = await conn.fetchval(
                    "SELECT count(*) FROM mw_agent_recaps WHERE owner_user_id=$1 AND created_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'", user_id,
                )
                if count >= 10:
                    return None
                recap_id = await conn.fetchval(
                    """INSERT INTO mw_agent_recaps(company_id, owner_user_id, root_key, title)
                       VALUES ($1,$2,$3,$4) ON CONFLICT(company_id, owner_user_id, root_key)
                       DO UPDATE SET root_key=EXCLUDED.root_key RETURNING id""",
                    company_id, user_id, f"{kind}:{source_id}:{generation}", clip(title or "Task recap"),
                )
            column = SOURCE_COLUMNS[kind]
            mail_owner = "none" if phase else ("recap" if kind != "run" or pref["email_enabled"] else "none")
            role = "phase" if phase else (("continuation" if kind == "run" else "child") if parent else "root")
            await conn.execute(
                f"""INSERT INTO mw_agent_recap_sources(recap_id,kind,{column},generation,role,completion_mail_owner,parent_source_id)
                    VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING""",
                recap_id, kind, source_id, generation, role, mail_owner, parent["id"] if parent else None,
            )
            if mail_owner == "recap":
                await conn.execute("INSERT INTO mw_agent_recap_deliveries(recap_id) VALUES($1) ON CONFLICT DO NOTHING", recap_id)
            return recap_id
    except Exception:
        logger.warning("recap registration unavailable source=%s kind=%s", source_id, kind, exc_info=True)
        if parent:
            await conn.execute(
                """UPDATE mw_agent_recaps SET state='skipped', render_token=NULL,
                   last_error_code='source_binding_failed', updated_at=NOW()
                   WHERE id=$1 AND state IN ('collecting','waiting','queued','rendering')""", parent["recap_id"],
            )
        return None


async def register_run(conn, run_id, user_id, company_id, *, parent_run_id=None):
    return await register(conn, kind="run", source_id=run_id, user_id=user_id, company_id=company_id,
                          title="Assistant task recap", parent_run_id=parent_run_id)


async def register_task(conn, task: dict, *, parent_run_id=None):
    if not settings.enabled():
        return None
    round_id = await conn.fetchval(
        "SELECT id FROM mw_agent_task_rounds WHERE task_id=$1 AND n=$2", task["id"], task["current_round"],
    )
    return await register(conn, kind="research", source_id=round_id, user_id=task["user_id"],
                          company_id=task["company_id"], title=task.get("title") or "Research task recap",
                          parent_run_id=parent_run_id)


async def register_job(conn, search, *, parent_run_id=None):
    if not settings.enabled():
        return None
    generation = await conn.fetchval(
        "UPDATE mw_job_searches SET recap_generation=recap_generation+1 WHERE id=$1 RETURNING recap_generation", search["id"],
    )
    return await register(conn, kind="jobs", source_id=search["id"], user_id=search["user_id"],
                          company_id=search["company_id"], title=search["title"] or "Job search recap",
                          generation=generation, parent_run_id=parent_run_id)


async def phase_run(conn, run_id, owner):
    if not settings.enabled():
        return
    if owner.kind == "job_search":
        source = await conn.fetchrow(
            """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_job_searches j
               ON j.id=s.job_search_id AND j.recap_generation=s.generation
               WHERE j.id=$1 AND s.kind='jobs' AND j.recap_generation=$2 AND j.dispatch_token=$3""",
            owner.owner_id, owner.recap_generation, owner.dispatch_token,
        )
    else:
        source = await conn.fetchrow(
            """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_agent_task_rounds q ON q.id=s.task_round_id
               JOIN mw_agent_tasks t ON t.id=q.task_id AND t.current_round=q.n
               WHERE t.id=$1 AND s.kind='research' AND t.current_round=$2 AND t.dispatch_token=$3""",
            owner.owner_id, owner.recap_round, owner.dispatch_token,
        )
    if source:
        await conn.execute(
            """INSERT INTO mw_agent_recap_sources(recap_id,kind,run_id,role,completion_mail_owner,parent_source_id,execution_token)
               VALUES($1,'run',$2,'phase','none',$3,$4) ON CONFLICT DO NOTHING""",
            source["recap_id"], run_id, source["id"], owner.dispatch_token,
        )


async def capture_current(conn, source):
    if source["role"] != "phase":
        return True
    return bool(await conn.fetchval(
        """SELECT 1 FROM mw_agent_recap_sources s JOIN mw_agent_recap_sources p ON p.id=s.parent_source_id
           LEFT JOIN mw_job_searches j ON j.id=p.job_search_id
           LEFT JOIN mw_agent_task_rounds q ON q.id=p.task_round_id
           LEFT JOIN mw_agent_tasks t ON t.id=q.task_id
           WHERE s.id=$1 AND p.semantic_state<>'terminal' AND (
               (p.kind='jobs' AND j.recap_generation=p.generation AND j.dispatch_token=s.execution_token)
               OR (p.kind='research' AND t.current_round=q.n AND t.dispatch_token=s.execution_token))""", source["id"],
    ))


async def event(conn, source, key: str, snapshot: Event, *, reserve_final=False):
    # One row lock serializes the byte/event budget with freezing and capture.
    recap = await conn.fetchrow("SELECT state,event_count FROM mw_agent_recaps WHERE id=$1 FOR UPDATE", source["recap_id"])
    if not recap or recap["state"] not in ("collecting", "waiting"):
        return None
    consequential = snapshot.outcome in ("unknown", "failed", "partial", "cancelled", "declined", "handoff")
    if recap["event_count"] >= (128 if reserve_final or consequential else 120):
        if not consequential:
            return None
        if await conn.fetchval("SELECT id FROM mw_agent_recap_events WHERE recap_id=$1 AND event_key=$2", source["recap_id"], key):
            return None
        removed = await conn.fetchval(
            """DELETE FROM mw_agent_recap_events WHERE id=(SELECT id FROM mw_agent_recap_events
               WHERE recap_id=$1 AND snapshot->>'outcome' NOT IN ('unknown','failed','partial','cancelled','declined','handoff')
               AND snapshot->>'kind'<>'result' ORDER BY occurred_at,id LIMIT 1) RETURNING id""", source["recap_id"],
        )
        if not removed:
            # Finalization also aggregates authoritative action rows, so a
            # full evidence budget cannot erase an unknown external action.
            return None
        await conn.execute("UPDATE mw_agent_recaps SET event_count=event_count-1 WHERE id=$1", source["recap_id"])
    event_id = await conn.fetchval(
        """INSERT INTO mw_agent_recap_events(recap_id,source_id,event_key,snapshot,occurred_at)
           VALUES($1,$2,$3,$4::jsonb,$5) ON CONFLICT(recap_id,event_key) DO NOTHING RETURNING id""",
        source["recap_id"], source["id"], key, snapshot.model_dump_json(), snapshot.occurred_at,
    )
    if event_id:
        await conn.execute("UPDATE mw_agent_recaps SET event_count=event_count+1 WHERE id=$1", source["recap_id"])
    return event_id


async def revoke_source(conn, kind, source_id):
    if not settings.enabled() and not await conn.fetchval("SELECT to_regclass('mw_agent_recaps')"):
        return
    from .service import tombstone
    if kind == "research":
        rows = await conn.fetch(
            """SELECT DISTINCT s.recap_id FROM mw_agent_recap_sources s JOIN mw_agent_task_rounds q
               ON q.id=s.task_round_id WHERE q.task_id=$1""", source_id,
        )
    else:
        rows = await conn.fetch("SELECT DISTINCT recap_id FROM mw_agent_recap_sources WHERE job_search_id=$1", source_id)
    for row in rows:
        await tombstone(conn, row["recap_id"])


async def before_job_restart(conn, search_id):
    """Freeze the resting generation before mutable leads/status change again."""
    if not settings.enabled():
        return
    from .observe import refresh_source
    source = await conn.fetchrow(
        """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_job_searches j
           ON j.id=s.job_search_id AND j.recap_generation=s.generation WHERE j.id=$1 AND s.kind='jobs'""", search_id,
    )
    if source and source["semantic_state"] != "terminal":
        async with conn.transaction():
            await refresh_source(conn, source)
            await conn.execute("UPDATE mw_agent_recap_sources SET semantic_state='terminal' WHERE id=$1", source["id"])


async def supersede_round(conn, task):
    if not settings.enabled():
        return
    from .adapters import search_event
    source = await conn.fetchrow(
        """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_agent_task_rounds q
           ON q.id=s.task_round_id WHERE q.task_id=$1 AND q.n=$2 AND s.kind='research'""",
        task["id"], task["current_round"],
    )
    if source and source["semantic_state"] != "terminal":
        snapshot = await search_event(conn, source, terminal=True)
        snapshot = snapshot.model_copy(update={"title": "Continued in a follow-up", "outcome": "partial"})
        await event(conn, source, f"superseded:{source['id']}", snapshot, reserve_final=True)
        await conn.execute("UPDATE mw_agent_recap_sources SET semantic_state='terminal' WHERE id=$1", source["id"])
