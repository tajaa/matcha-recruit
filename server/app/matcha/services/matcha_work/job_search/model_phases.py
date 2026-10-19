"""The job search phases that call a model: plan, screen, approach (the web
search in discover is `discovery.py`).

Each is one bounded agent-runtime run (`agent_phase.run_model_phase`) whose
output is its finish contract (`contracts.py`). The model never writes: this
module persists what the contract let through, under the chain's token.

A model failure never sinks the search. Plan falls back to the criteria,
screening keeps unscreened jobs in (unranked fit), and a failed approach batch
is marked failed so the person can redraft that job.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work.agent_runtime import runner
from app.matcha.services.matcha_work.agent_runtime.abilities import web
from app.matcha.services.matcha_work.agent_runtime.chain import Guard
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits

from . import contracts, prompts, ranking
from .agent_phase import SearchProgress, run_model_phase
from .contracts import titles_in
from .phases import Deps, PhaseOutcome, plan_from_criteria
from .service import load_resume_for_model, resting_status

logger = logging.getLogger(__name__)

SCREEN_BATCH = 40
APPROACH_BATCH = 2
SNIPPET_CHARS = 600
APPROACH_DESCRIPTION_CHARS = 6_000
APPROACH_FETCHES = 8
FETCH_SECONDS = 25.0

PLAN_LIMITS = RunLimits(max_model_calls=2, wall_seconds=90.0)
SCREEN_LIMITS = RunLimits(max_model_calls=2, wall_seconds=150.0)
APPROACH_LIMITS = RunLimits(max_model_calls=10, wall_seconds=330.0, max_hosted_per_response=4,
                            max_hosted_per_run=8)


def _progress(guard: Guard) -> SearchProgress:
    return SearchProgress(note_fn=lambda text: guard.note(text))


async def _person(search: dict) -> tuple[str, str | None]:
    """(the person block for a prompt, the résumé text or None)."""
    criteria = decode_jsonb(search.get("criteria"), {}) or {}
    plan = decode_jsonb(search.get("plan"), {}) or {}
    resume = await load_resume_for_model(search["user_id"]) if search.get("use_resume") else None
    return prompts.person_block(search.get("ask") or "", criteria, resume, plan.get("profile_summary"),
                                plan.get("directions")), resume


# ── plan ─────────────────────────────────────────────────────────────────────

async def plan(search: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    criteria = decode_jsonb(search.get("criteria"), {}) or {}
    fallback = plan_from_criteria(search.get("ask") or "", criteria)
    person, resume = await _person(search)
    try:
        outcome = await run_model_phase(
            search, phase="plan", abilities=(),
            contract=runner.ResultContract(finish=contracts.PLAN_FINISH, normalize=contracts.normalize_plan),
            instructions=prompts.PLAN, user_text=person, limits=PLAN_LIMITS,
            progress=_progress(guard), client_factory=deps.client, first_note="Planning the search…",
        )
        planned = outcome.result
    except runner.AgentRunError:
        logger.info("job search plan fell back to criteria search=%s", search["id"])
        planned = fallback
    # What they typed always counts, first: every search takes each typed
    # title and each kept direction (`phases.must_search`).
    planned["titles"] = titles_in([*(criteria.get("titles") or []), *(planned.get("titles") or [])]) \
        or fallback["titles"]
    _add_directions(planned, criteria, resume)
    weights = planned.pop("weights", None)
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_job_searches SET plan = $3::jsonb,
                   weights = CASE WHEN weights_source = 'default' AND $4::jsonb IS NOT NULL
                                  THEN $4::jsonb ELSE weights END
               WHERE id = $1 AND dispatch_token = $2""",
            search["id"], guard.token, json.dumps(planned),
            json.dumps(ranking.clean_weights(weights)) if weights else None,
        )
    titles = planned["titles"]
    shown = ", ".join(titles[:3]) + (f" and {len(titles) - 3} more" if len(titles) > 3 else "")
    note = f"Searching employers' job boards for {shown[:160]}…" if titles else "Searching the web…"
    return PhaseOutcome(status="discovering", cursor={}, progress={"note": note, "titles": len(titles)})


def _add_directions(planned: dict, criteria: dict, resume: str | None) -> None:
    """Keep the directions the résumé supports, listed right after the titles
    they typed: the searches take every one of both (`phases.must_search`),
    then the plan's own titles while there is room."""
    own = [*(criteria.get("titles") or []), *(planned.get("titles") or [])]
    directions = contracts.check_directions(planned.pop("directions", []), resume, own)
    if not directions:
        return
    titles = planned.get("titles") or []
    typed = len(titles_in(criteria.get("titles")))
    planned["titles"] = titles_in(titles[:typed] + [d["title"] for d in directions] + titles[typed:])
    # Only the directions the plan still lists (it keeps `MAX_TITLES`).
    listed = {t.lower() for t in planned["titles"]}
    planned["directions"] = [d for d in directions if d["title"].lower() in listed]
    if not planned["directions"]:
        planned.pop("directions")


# ── screen ───────────────────────────────────────────────────────────────────

def _screen_job(short: str, row) -> dict:
    comp = decode_jsonb(row["comp"], {}) or {}
    return {
        "id": short, "title": row["title"], "company": row["company"], "location": row["location"],
        "remote": row["remote"], "pay": ranking.comp_line(comp), "posted": row["posted_text"],
        "snippet": " ".join((row["description"] or "").split())[:SNIPPET_CHARS],
    }


async def screen(search: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""SELECT id, title, company, location, remote, posted_text, comp, description
                FROM mw_job_leads WHERE search_id = $1 AND screen_status = 'pending'
                ORDER BY created_at, id LIMIT {SCREEN_BATCH}""",
            search["id"],
        )
    if not rows:
        return PhaseOutcome(status="enriching", progress={"note": "Reading the postings for pay…"})
    batch = {f"J{i + 1}": str(row["id"]) for i, row in enumerate(rows)}
    jobs = [_screen_job(short, row) for short, row in zip(batch, rows)]
    person, _resume = await _person(search)
    worked = True
    try:
        outcome = await run_model_phase(
            search, phase="screen", abilities=(),
            contract=runner.ResultContract(
                finish=contracts.SCREEN_FINISH,
                normalize=lambda args, _state: contracts.normalize_screen(args, batch),
            ),
            instructions=prompts.SCREEN, user_text=prompts.screen_turn(person, jobs),
            limits=SCREEN_LIMITS, progress=_progress(guard), client_factory=deps.client,
            first_note=f"Screening {len(rows)} jobs…",
        )
        verdicts: dict[str, dict] = outcome.result
    except runner.AgentRunError:
        logger.info("job search screening failed; keeping the batch search=%s", search["id"])
        verdicts, worked = {}, False
    # A job the model skipped (the contract lets a few go) stays pending and
    # is shown once more in the next batch; skipped again, it is kept in with
    # no fit, as a batch the model couldn't rate at all is. Counted as
    # matches, up to 8 of 40 skipped jobs could be drafted unseen.
    cursor = decode_jsonb(search.get("phase_cursor"), {}) or {}
    asked_again = {str(i) for i in (cursor.get("rescreen") or []) if isinstance(cursor, dict)}
    rescreen = [i for i in batch.values() if worked and i not in verdicts and i not in asked_again]
    ids = [UUID(lead_id) for lead_id in batch.values() if lead_id not in rescreen]
    relevant = [verdicts.get(str(i), {}).get("relevant", True) for i in ids]
    async with connection_or_direct() as conn:
        if ids:
            await _write_verdicts(conn, search, guard, ids, relevant, verdicts)
        left = int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1 AND screen_status = 'pending'",
            search["id"],
        ) or 0)
        kept = int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1 AND screen_status = 'relevant'",
            search["id"],
        ) or 0)
    if left:
        return PhaseOutcome(status="screening", cursor={"rescreen": sorted(asked_again | set(rescreen))},
                            progress={"note": f"Screened; {left} to go…", "relevant": kept})
    return PhaseOutcome(
        status="enriching", cursor={},
        progress={"note": f"{kept} jobs fit. Reading the postings for pay…", "relevant": kept},
    )


async def _write_verdicts(conn, search: dict, guard: Guard, ids: list[UUID], relevant: list[bool],
                          verdicts: dict[str, dict]) -> None:
    await conn.execute(
        """UPDATE mw_job_leads AS l
           SET screen_status = CASE WHEN v.relevant THEN 'relevant' ELSE 'irrelevant' END,
               fit_score = v.fit, fit_reasons = v.reasons::jsonb, screen_reason = NULLIF(v.reason, ''),
               updated_at = NOW()
           FROM unnest($3::uuid[], $4::bool[], $5::int[], $6::text[], $7::text[])
                AS v(id, relevant, fit, reasons, reason)
           WHERE l.id = v.id AND l.search_id = $1
             AND EXISTS (SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2)""",
        search["id"], guard.token, ids, relevant,
        [verdicts.get(str(i), {}).get("fit") for i in ids],
        [json.dumps(verdicts.get(str(i), {}).get("reasons") or []) for i in ids],
        [verdicts.get(str(i), {}).get("reason") or "" for i in ids],
    )


# ── approach ─────────────────────────────────────────────────────────────────

def _evidence(comp: dict) -> list[dict]:
    out = []
    for key in ("base", "bonus", "equity"):
        item = comp.get(key) or {}
        evidence = item.get("evidence") or {}
        if evidence.get("quote"):
            out.append({"part": key, "status": item.get("status"), "quote": evidence["quote"]})
    return out


def _approach_job(short: str, row) -> dict:
    comp = decode_jsonb(row["comp"], {}) or {}
    ats_data = decode_jsonb(row["ats"], {}) or {}
    return {
        "id": short, "title": row["title"], "company": row["company"], "location": row["location"],
        "remote": row["remote"], "posting_url": row["source_url"],
        "pay": ranking.comp_line(comp), "pay_evidence": _evidence(comp),
        "pay_law": row["pay_law_hint"],
        "questions": [
            {"key": q.get("key"), "label": q.get("label"), "type": q.get("type"),
             "options": q.get("options") or [], "kind": q.get("kind")}
            for q in ats_data.get("questions") or [] if isinstance(q, dict)
        ],
        "description": (row["description"] or "")[:APPROACH_DESCRIPTION_CHARS],
    }


def _queue(search: dict) -> list[str]:
    cursor = decode_jsonb(search.get("phase_cursor"), {}) or {}
    return [str(i) for i in cursor.get("approach_queue") or []]


def _finished(search: dict, note: str) -> PhaseOutcome:
    """The queue is drafted: `done`, or back to `cancelled` for a cancelled
    search that drafted one approach on request."""
    if resting_status(search) == "cancelled":
        return PhaseOutcome(status="cancelled", cursor={}, progress={"note": "Cancelled. The approach you asked for is drafted."})
    return PhaseOutcome(status="done", cursor={}, progress={"note": note})


async def approach(search: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    queue = _queue(search)
    take, rest = queue[:APPROACH_BATCH], queue[APPROACH_BATCH:]
    if not take:
        return _finished(search, "Done.")
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT id, title, company, location, remote, source_url, comp, ats, description, pay_law_hint
               FROM mw_job_leads WHERE search_id = $1 AND id = ANY($2::uuid[])""",
            search["id"], [UUID(i) for i in take],
        )
        # Under the token: a cancel just before this write has already
        # released the queue, and a `drafting` written after it would stay.
        await conn.execute(
            """UPDATE mw_job_leads SET approach_status = 'drafting', updated_at = NOW()
               WHERE search_id = $1 AND id = ANY($2::uuid[])
                 AND EXISTS (SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $3)""",
            search["id"], [row["id"] for row in rows], guard.token,
        )
    batch = {f"J{i + 1}": str(row["id"]) for i, row in enumerate(rows)}
    questions = {
        str(row["id"]): [q for q in (decode_jsonb(row["ats"], {}) or {}).get("questions") or [] if isinstance(q, dict)]
        for row in rows
    }
    jobs = [_approach_job(short, row) for short, row in zip(batch, rows)]
    person, _resume = await _person(search)
    pages: dict[str, str] = {}

    async def fetch_page(url: str) -> tuple[dict, set[str]]:
        page, vouched = await deps.fetch_page(url)
        if vouched and isinstance(page, dict) and not page.get("error"):
            text = " ".join([str(page.get("title") or ""), str(page.get("text") or ""),
                             json.dumps(page.get("jobs") or [], default=str)])
            for url_seen in vouched | {page.get("url")}:
                if isinstance(url_seen, str):
                    pages[url_seen] = text
        return page, vouched

    ability = web.build(fetch_page=fetch_page, max_fetches=APPROACH_FETCHES,
                        fetch_seconds=FETCH_SECONDS, untrusted=True)
    user_text = prompts.approach_turn(person, jobs)
    drafted: dict[str, dict] = {}
    if batch:
        try:
            outcome = await run_model_phase(
                search, phase="approach", abilities=(ability,),
                contract=runner.ResultContract(
                    finish=contracts.APPROACH_FINISH,
                    normalize=lambda args, state: contracts.normalize_approaches(
                        args, batch=batch, questions=questions, citable=state.citable(), pages=pages,
                        observed_emails=state.observed_emails, user_text=search.get("ask") or "",
                    ),
                ),
                instructions=prompts.APPROACH, user_text=user_text, limits=APPROACH_LIMITS,
                progress=_progress(guard), client_factory=deps.client, reasoning_effort="medium",
                first_note=f"Working out how to approach {', '.join(r['company'] for r in rows)[:120]}…",
            )
            drafted = outcome.result
        except runner.AgentRunError:
            logger.info("job search approach batch failed search=%s", search["id"])
    ids = [row["id"] for row in rows]
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_job_leads AS l
               SET approach = COALESCE(v.approach::jsonb, l.approach),
                   approach_status = CASE WHEN v.approach IS NULL THEN 'failed' ELSE 'done' END,
                   updated_at = NOW()
               FROM unnest($3::uuid[], $4::text[]) AS v(id, approach)
               WHERE l.id = v.id AND l.search_id = $1
                 AND EXISTS (SELECT 1 FROM mw_job_searches WHERE id = $1 AND dispatch_token = $2)""",
            search["id"], guard.token, ids,
            [json.dumps(drafted[str(i)]) if str(i) in drafted else None for i in ids],
        )
    if rest:
        after = (decode_jsonb(search.get("phase_cursor"), {}) or {}).get("after")
        return PhaseOutcome(status="approaching",
                            cursor={"approach_queue": rest, **({"after": after} if after else {})},
                            progress={"note": f"Drafted approaches; {len(rest)} jobs to go…"})
    if resting_status(search) == "cancelled":
        return _finished(search, "")
    return _finished(search, await _drafted_note(search))


async def _drafted_note(search: dict) -> str:
    """What the last note says, from the jobs as they now are: on prod a search
    whose every draft had failed still said "approaches drafted" (2026-10-17)."""
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """SELECT COUNT(*) FILTER (WHERE approach_status = 'done') AS done,
                      COUNT(*) FILTER (WHERE approach_status = 'failed') AS failed
               FROM mw_job_leads WHERE search_id = $1""",
            search["id"],
        )
    done, failed = (int(row["done"] or 0), int(row["failed"] or 0)) if row else (0, 0)
    if not done and not failed:
        return "Done: ranked."
    if not failed:
        return "Done: ranked, with approaches drafted."
    if not done:
        return "Done: ranked. The approaches couldn't be drafted; Redraft a job to try again."
    return f"Done: ranked, with {done} of {done + failed} approaches drafted; Redraft the others to try again."
