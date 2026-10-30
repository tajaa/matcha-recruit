"""A résumé tailored to one job, for the person to read before they apply.

"Tailor my résumé" on a job (`POST …/leads/{lead}/resume`) rewrites their
saved résumé for that posting: what the posting asks for first, in its words
where the résumé already shows the same work. It is one model run in the
worker (`workers/tasks/job_search.tailor_job_resume`), counted on the search
like its other runs and charged to the workspace's tokens. It isn't a search:
no allowance units, only an hourly limit.

What comes back is checked against the résumé before it is kept
(`contracts.normalize_tailored`): each line names the résumé lines it
rewrites, word for word, and holds no number they don't; a role, employer,
date or skill is kept only as the résumé writes it. Nothing new is ever added
to someone's record, and what the posting asks for that the résumé doesn't
show is listed apart (`gaps`), never written in. Nothing is sent or submitted.

The job row holds the result and where its run is (`resume_*`, `mwjobs05`).
A newer request replaces an older one's token, so only the latest run
writes. A run that died (the task was killed, the broker lost it) leaves its
row queued or drafting. `resume_requested_at` is reset when the worker picks
the ask up, so time waiting behind other work never counts against a run: one
queued past `QUEUED_STALE_MINUTES`, or drafting past `STALE_MINUTES`, reads as
failed, and the person can ask again (the new token keeps the old run from
starting late). A failed or newer ask leaves the last good résumé shown.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work.agent_runtime import phase_run, runner
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits

from . import contracts, prompts
from .agent_phase import run_owner

logger = logging.getLogger(__name__)

TAILORING = ("queued", "drafting")
# From when the worker picked it up: longer than the task's hard limit (360 s),
# so a run still going never reads as failed.
STALE_MINUTES = 7
# Waiting in the queue: the one worker can be busy with a search phase or a
# research task for a long while.
QUEUED_STALE_MINUTES = 30
# The whole résumé is what is rewritten, so it gets more room than a search's
# phases give it (`service.RESUME_CHARS`).
RESUME_CHARS = 20_000
DESCRIPTION_CHARS = 8_000
# A posting this short hasn't been read: there is nothing to tailor to.
MIN_POSTING_CHARS = 200
HOURLY_LIMIT = 10
LIMITS = RunLimits(max_model_calls=3, wall_seconds=240.0)
ENTITLEMENT = "job_search"


def status_of(row) -> str:
    """The job's tailoring as the person should see it: a run that has been
    queued or drafting past `STALE_MINUTES` died, and reads as failed."""
    row = dict(row)
    status = row.get("resume_status") or "none"
    if status in TAILORING:
        asked = row.get("resume_requested_at")
        minutes = QUEUED_STALE_MINUTES if status == "queued" else STALE_MINUTES
        if asked is None or asked < datetime.now(timezone.utc) - timedelta(minutes=minutes):
            return "failed"
    return status


def view(row) -> dict | None:
    """The last tailored résumé for the job pane (with its plain text, for
    Copy and Download), or None until there is one. It stays while a newer
    ask runs or after one fails; `resume_status` says which."""
    row = dict(row)
    tailored = decode_jsonb(row.get("resume_tailored"), {}) or {}
    if not tailored.get("experience"):
        return None
    return {**tailored, "text": as_text(tailored)}


def as_text(tailored: dict) -> str:
    """The résumé as plain text, in the order the page shows it."""
    parts: list[str] = []
    summary = (tailored.get("summary") or {}).get("text")
    if summary:
        parts.append(f"SUMMARY\n{summary}")
    roles = []
    for role in tailored.get("experience") or []:
        head = " — ".join(v for v in (role.get("role"), role.get("organization")) if v)
        if role.get("dates"):
            head = f"{head} ({role['dates']})" if head else role["dates"]
        lines = [head] + [f"• {b['text']}" for b in role.get("bullets") or []]
        roles.append("\n".join(lines))
    if roles:
        parts.append("EXPERIENCE\n" + "\n\n".join(roles))
    if tailored.get("skills"):
        parts.append("SKILLS\n" + ", ".join(tailored["skills"]))
    for section in tailored.get("sections") or []:
        parts.append(section["heading"].upper() + "\n" + "\n".join(f"• {line['text']}" for line in section["lines"]))
    return "\n\n".join(parts)


async def load_resume(user_id: UUID) -> tuple[str, Any] | None:
    """The saved résumé's own text (not the parsed summary a search's phases
    get) and when it was saved, or None when there is none to rewrite."""
    async with connection_or_direct() as conn:
        row = await conn.fetchrow("SELECT raw_text, updated_at FROM user_resumes WHERE user_id = $1", user_id)
    text = ((row["raw_text"] if row else None) or "").strip()
    return (text[:RESUME_CHARS], row["updated_at"]) if text else None


async def has_resume(user_id: UUID) -> bool:
    async with connection_or_direct() as conn:
        return bool(await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM user_resumes WHERE user_id = $1 AND btrim(COALESCE(raw_text, '')) <> '')",
            user_id,
        ))


async def _allowed(user_id: UUID, company_id: UUID) -> bool:
    """The same standing a search needs: a personal workspace, and the job
    search consent still given (it covers sending their résumé to the model)."""
    from app.matcha.services.matcha_work.agent_runtime.enqueue import workspace_enabled

    from .enqueue import consent_granted

    return await workspace_enabled(company_id) and await consent_granted(user_id)


async def request(user, search_id: UUID, lead_id: UUID) -> dict:
    """Tailor the résumé to this job (again). Returns the job as it is now:
    queued, or still tailoring from an earlier ask (which is left to finish
    and spends nothing)."""
    from app.core.services.redis_cache import check_rate_limit
    from app.matcha.services.billing import token_budget_service
    from app.matcha.services.billing.entitlements_service import PLAN_PRO, require_plan

    from .enqueue import _is_admin, queue_for
    from .service import JobSearchError, lead_detail

    if not _is_admin(user):
        await require_plan(user.id, PLAN_PRO, ENTITLEMENT)
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """SELECT l.*, s.company_id AS search_company_id FROM mw_job_leads l
               JOIN mw_job_searches s ON s.id = l.search_id
               WHERE l.id = $1 AND l.search_id = $2 AND s.user_id = $3 AND s.deleted_at IS NULL""",
            lead_id, search_id, user.id,
        )
    if row is None:
        raise JobSearchError("Job not found.", 404)
    if not await _allowed(user.id, row["search_company_id"]):
        raise JobSearchError("Job search is off for your account.", 403, {
            "code": "job_search_off",
            "message": "Job search is off for your account, so your résumé isn't sent anywhere. "
                       "Start a job search to turn it back on.",
        })
    if status_of(row) in TAILORING:
        return lead_detail(row)
    if len((row["description"] or "").strip()) < MIN_POSTING_CHARS:
        raise JobSearchError("This posting hasn't been read yet, so there's nothing to tailor to.", 409, {
            "code": "posting_unread",
            "message": "This posting hasn't been read yet, so there's nothing to tailor to.",
        })
    if not await has_resume(user.id):
        raise JobSearchError("Add your résumé first.", 422, {
            "code": "resume_required",
            "message": "Add your résumé in Tasks → Résumé first, then tailor it to this job.",
        })
    if not _is_admin(user):
        # Only once it would be accepted: a refusal above spends nothing.
        await check_rate_limit(str(user.id), "espresso_job_resume_tailor", HOURLY_LIMIT, 3600)
        await token_budget_service.check_token_budget(row["search_company_id"])

    token = uuid4()
    async with connection_or_direct() as conn, conn.transaction():
        row = await conn.fetchrow("SELECT * FROM mw_job_leads WHERE id = $1 FOR UPDATE", lead_id)
        if row is None:
            raise JobSearchError("Job not found.", 404)
        if status_of(row) in TAILORING:  # asked twice at once: the first one runs
            return lead_detail(row)
        row = await conn.fetchrow(
            """UPDATE mw_job_leads
               SET resume_status = 'queued', resume_token = $2, resume_requested_at = NOW(), updated_at = NOW()
               WHERE id = $1 RETURNING *""",
            lead_id, token,
        )
    try:
        from app.workers.tasks.job_search import tailor_job_resume

        tailor_job_resume.apply_async(args=[str(lead_id), str(token)], queue=queue_for())
    except Exception:
        logger.exception("résumé tailoring dispatch failed lead=%s", lead_id)
        await _finish(lead_id, token, "failed")
        raise JobSearchError("Couldn't start tailoring right now. Try again in a moment.", 503)
    logger.info("résumé tailoring queued lead=%s user=%s", lead_id, user.id)
    return lead_detail(row)


async def _finish(lead_id: UUID, token: UUID, status: str, tailored: dict | None = None) -> bool:
    """Write the run's outcome, only while it is still the latest ask."""
    async with connection_or_direct() as conn:
        written = await conn.fetchval(
            """UPDATE mw_job_leads
               SET resume_status = $3, resume_tailored = COALESCE($4::jsonb, resume_tailored),
                   resume_token = NULL, updated_at = NOW()
               WHERE id = $1 AND resume_token = $2 RETURNING id""",
            lead_id, token, status, json.dumps(tailored) if tailored is not None else None,
        )
    return written is not None


async def _no_note(_text: str) -> None:
    """The search's own progress note says how the search went; a tailoring
    run leaves it alone."""


async def run(lead_id: UUID, token: UUID, *, client_factory=phase_run.default_client) -> None:
    """The worker's half: claim the ask, run the model, keep what checks out."""
    async with connection_or_direct() as conn:
        # The stale clock restarts here: time spent waiting in the queue isn't the run's.
        lead = await conn.fetchrow(
            """UPDATE mw_job_leads SET resume_status = 'drafting', resume_requested_at = NOW()
               WHERE id = $1 AND resume_token = $2 AND resume_status = 'queued'
               RETURNING id, search_id, user_id, title, company, location, description, highlights""",
            lead_id, token,
        )
        if lead is None:  # a duplicate delivery, or replaced by a newer ask
            return
        search = await conn.fetchrow(
            "SELECT * FROM mw_job_searches WHERE id = $1 AND deleted_at IS NULL", lead["search_id"],
        )
    resume = await load_resume(lead["user_id"]) if search is not None else None
    # The search was deleted, consent withdrawn or the résumé removed since it was asked for.
    if resume is None or not await _allowed(lead["user_id"], search["company_id"]):
        await _finish(lead_id, token, "failed")
        return
    resume_text, resume_saved = resume
    job = {
        "title": lead["title"], "company": lead["company"], "location": lead["location"],
        "highlights": decode_jsonb(lead["highlights"], []) or [],
        "posting": " ".join((lead["description"] or "").split())[:DESCRIPTION_CHARS],
    }
    # The search's run counters, never its recap: a recap is fenced to the
    # chain's token, and this run is not the chain's.
    owner = replace(await run_owner(dict(search)), dispatch_token=None, recap_generation=None)
    try:
        outcome = await phase_run.run_model_phase(
            owner, phase="tailor_resume", abilities=(),
            contract=runner.ResultContract(
                finish=contracts.TAILOR_FINISH,
                normalize=lambda args, _state: contracts.normalize_tailored(args, resume=resume_text),
            ),
            instructions=prompts.TAILOR, user_text=prompts.tailor_turn(job, resume_text), limits=LIMITS,
            progress=phase_run.NoteProgress(note_fn=_no_note), client_factory=client_factory,
        )
    except runner.AgentRunError:
        logger.info("résumé tailoring found nothing it could keep lead=%s", lead_id)
        await _finish(lead_id, token, "failed")
        return
    except Exception:
        logger.exception("résumé tailoring failed lead=%s", lead_id)
        await _finish(lead_id, token, "failed")
        return
    from .service import _iso

    tailored = {
        **(outcome.result or {}),
        "resume_saved_at": _iso(resume_saved),
        "made_at": datetime.now(timezone.utc).isoformat(),
    }
    await _finish(lead_id, token, "done", tailored)

