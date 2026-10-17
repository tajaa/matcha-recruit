"""Optional transactional observations and recovery from durable source records."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.database import decode_jsonb

from . import adapters, scope, settings
from app.matcha.models.matcha_work.recaps import Event, Fact

logger = logging.getLogger(__name__)


async def accepted(conn, table, source_id, token, *, phase, terminal, retry=False):
    if not settings.enabled() or retry:
        return
    try:
        async with conn.transaction():
            if table == "mw_job_searches":
                source = await conn.fetchrow(
                    """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_job_searches j ON j.id=s.job_search_id
                       AND j.recap_generation=s.generation WHERE j.id=$1 AND s.kind='jobs'""", source_id,
                )
            else:
                source = await conn.fetchrow(
                    """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_agent_task_rounds q ON q.id=s.task_round_id
                       JOIN mw_agent_tasks t ON t.id=q.task_id AND t.current_round=q.n
                       WHERE t.id=$1 AND s.kind='research'""", source_id,
                )
            if source:
                snapshot = await adapters.search_event(conn, source, terminal=terminal, phase=phase)
                await scope.event(conn, source, f"phase:{source['id']}:{token}", snapshot, reserve_final=terminal)
                if terminal:
                    await conn.execute("UPDATE mw_agent_recap_sources SET semantic_state='terminal' WHERE id=$1", source["id"])
    except Exception:
        logger.warning("recap phase observation missing source=%s", source_id, exc_info=True)


async def refresh_source(conn, source) -> str:
    """Called under the root lock; source writes and root enrollment take it too."""
    if source["semantic_state"] == "terminal":
        return "terminal"
    if source["kind"] == "run":
        run = await conn.fetchrow("SELECT status,result,created_at,completed_at FROM mw_project_agent_runs WHERE id=$1", source["run_id"])
        if not run:
            return "deleted"
        if run["status"] in ("queued", "running"):
            # Phase runs are supplementary evidence. A killed phase process
            # can leave its run row running after its owner advances/restarts.
            # The durable dispatch epoch, rather than that stale row, decides
            # whether it can still produce evidence for this recap.
            if source["role"] != "phase" or await scope.capture_current(conn, source):
                return "live"
        steps = await conn.fetch(
            "SELECT * FROM mw_project_agent_steps WHERE run_id=$1 ORDER BY seq LIMIT 128", source["run_id"],
        )
        for step in steps:
            snapshot = adapters.step_event(dict(step))
            if snapshot:
                await scope.event(conn, source, f"step:{source['run_id']}:{step['seq']}:{step['status']}", snapshot,
                                  reserve_final=snapshot.outcome in ("unknown", "failed", "partial", "cancelled", "declined"))
        result = decode_jsonb(run["result"], {}) or {}
        if result.get("question") or result.get("held"):
            prompt = await conn.fetchrow(
                """SELECT status,answer,expires_at FROM mw_agent_card_prompts WHERE run_id=$1
                   ORDER BY created_at DESC, id LIMIT 1""", source["run_id"],
            )
            continued = await conn.fetchval(
                "SELECT 1 FROM mw_agent_recap_sources WHERE parent_source_id=$1 LIMIT 1", source["id"],
            )
            if not continued:
                if not prompt or (prompt["expires_at"] > datetime.now(timezone.utc) and prompt["answer"] not in ("no", "cancel")):
                    return "waiting"
                outcome = "declined" if prompt["answer"] in ("no", "cancel") else "partial"
                await scope.event(conn, source, f"prompt-end:{source['id']}", Event(
                    kind="question_resolved", title="Action declined" if outcome == "declined" else "Question expired",
                    outcome=outcome, occurred_at=datetime.now(timezone.utc),
                ), reserve_final=True)
        if source["role"] != "phase":
            await scope.event(conn, source, f"run-end:{source['run_id']}", Event(
                kind="result", title="Request finished" if run["status"] == "done" else "Request stopped",
                outcome="observed" if run["status"] == "done" else "failed",
                occurred_at=run.get("completed_at") or run.get("created_at") or datetime.now(timezone.utc), facts=[Fact(label="Recorded actions", value=str(len(steps)))],
            ), reserve_final=True)
        return "terminal"
    if source["kind"] == "research":
        row = await conn.fetchrow(
            """SELECT q.status,q.n,t.current_round,t.status AS task_status,t.deleted_at FROM mw_agent_task_rounds q
               JOIN mw_agent_tasks t ON t.id=q.task_id WHERE q.id=$1""", source["task_round_id"],
        )
        if row and row.get("n", row.get("current_round")) != row.get("current_round"):
            await scope.event(conn, source, f"superseded:{source['id']}", Event(
                kind="result", title="Continued in a follow-up", outcome="partial",
                occurred_at=datetime.now(timezone.utc),
            ), reserve_final=True)
            return "terminal"
        state = "waiting" if row and row["task_status"] == "waiting" and row["status"] in ("queued", "running") else "live"
    else:
        row = await conn.fetchrow("SELECT status,deleted_at,recap_generation FROM mw_job_searches WHERE id=$1", source["job_search_id"])
        state = "live"
        if row and row["recap_generation"] != source["generation"]:
            # Accepted final snapshot belongs to the old generation. Never read
            # the newer mutable search to rewrite it.
            return "terminal" if source["semantic_state"] == "terminal" else "deleted"
    if not row or row["deleted_at"]:
        return "deleted"
    if row["status"] not in ("done", "failed", "cancelled"):
        return state
    await scope.event(conn, source, f"source-end:{source['id']}",
                      await adapters.search_event(conn, source, terminal=True), reserve_final=True)
    return "terminal"
