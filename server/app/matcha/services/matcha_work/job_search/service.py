"""Saved job searches and their leads. Pool-free, so the API and the worker share it.

Every read and write is scoped to the owner (`user_id`); another person's id
is "not found". A deleted search keeps a blanked row (a tombstone) so it still
counts against the month's allowance; its leads and runs are deleted.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.database import connection_or_direct, decode_jsonb
from app.matcha.models.matcha_work.job_search import JobWeights, LeadPatch

from . import comp as comp_mod
from . import normalize, ranking

LIVE = ("queued", "planning", "discovering", "screening", "enriching", "approaching")
TERMINAL = ("done", "failed", "cancelled")
_LIVE_SQL = ", ".join(f"'{status}'" for status in LIVE)
# A live search that has not moved in this long has lost its chain for good.
STALE_INTERVAL = "2 hours"
MAX_LIST = 50
MAX_REDRAFTS = 20
# Searches that can draft more approaches: finished, or cancelled with jobs
# found before the cancel. A failed search has no ranked jobs to draft for.
REDRAFTABLE = ("done", "cancelled")
RESUME_CHARS = 6_000
# States with a pay-range law (in postings or on request): where "ask for the
# range" is backed by law. The employer-side list in workforce_compliance, plus
# Massachusetts (posting law in effect since October 2025).
PAY_LAW_STATES = sorted({
    "CA", "CO", "WA", "NY", "IL", "HI", "MN", "NJ", "VT", "DC", "MD", "CT", "NV", "RI", "MA",
})


class JobSearchError(ValueError):
    def __init__(self, message: str, code: int = 400, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def _iso(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def _num(value):
    return float(value) if value is not None else None


def search_view(row) -> dict:
    row = dict(row)
    return {
        "id": str(row["id"]),
        "title": row.get("title") or "",
        "ask": row.get("ask") or "",
        "criteria": decode_jsonb(row.get("criteria"), {}) or {},
        "plan": decode_jsonb(row.get("plan"), {}) or {},
        "weights": ranking.clean_weights(decode_jsonb(row.get("weights"), {}) or {}),
        "weights_source": row.get("weights_source") or "default",
        "use_resume": bool(row.get("use_resume")),
        "status": row["status"],
        "progress": decode_jsonb(row.get("progress"), {}) or {},
        "error": row.get("error"),
        "lead_count": int(row.get("lead_count") or 0),
        "posted_pay_count": int(row.get("posted_pay_count") or 0),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "started_at": _iso(row.get("started_at")),
        "completed_at": _iso(row.get("completed_at")),
    }


def _apply_url(links: list) -> str | None:
    for link in links:
        url = normalize.http_url((link or {}).get("url") if isinstance(link, dict) else None)
        if url:
            return url
    return None


def lead_summary(row) -> dict:
    row = dict(row)
    comp = decode_jsonb(row.get("comp"), {}) or {}
    links = decode_jsonb(row.get("apply_links"), []) or []
    explain = decode_jsonb(row.get("rank_explain"), {}) or {}
    return {
        "id": str(row["id"]),
        "title": row.get("title") or "",
        "company": row.get("company") or "",
        "location": row.get("location") or "",
        "state_code": row.get("state_code"),
        "remote": row.get("remote"),
        "source": row.get("source"),
        "source_url": row.get("source_url"),
        "apply_url": _apply_url(links),
        "posted_text": row.get("posted_text"),
        "comp_line": ranking.comp_line(comp),
        "comp_status": row.get("comp_status") or "not_disclosed",
        "comp_annual_min": _num(row.get("comp_annual_min")),
        "comp_annual_max": _num(row.get("comp_annual_max")),
        "comp_currency": row.get("comp_currency"),
        "bonus_pct": comp_mod.bonus_pct(comp),
        "equity_pct": comp_mod.equity_pct(comp),
        "has_bonus": bool(comp.get("bonus")),
        "has_equity": bool(comp.get("equity")),
        "fit_score": row.get("fit_score"),
        "screen_status": row.get("screen_status") or "pending",
        "rank": row.get("rank"),
        "rank_band": row.get("rank_band"),
        "rank_score": _num(row.get("rank_score")),
        "flags": list(explain.get("flags") or []),
        "user_state": row.get("user_state") or "new",
        "approach_status": row.get("approach_status") or "none",
    }


def lead_detail(row) -> dict:
    row = dict(row)
    ats = decode_jsonb(row.get("ats"), {}) or {}
    return {
        **lead_summary(row),
        "description": row.get("description") or "",
        "highlights": decode_jsonb(row.get("highlights"), []) or [],
        "apply_links": decode_jsonb(row.get("apply_links"), []) or [],
        "ats": {"provider": ats.get("provider"), "questions": ats.get("questions") or []},
        "comp": decode_jsonb(row.get("comp"), {}) or {},
        "pay_law_hint": row.get("pay_law_hint"),
        "screen_reason": row.get("screen_reason"),
        "fit_reasons": decode_jsonb(row.get("fit_reasons"), []) or [],
        "rank_explain": decode_jsonb(row.get("rank_explain"), {}) or {},
        "approach": decode_jsonb(row.get("approach"), {}) or {},
        "notes": row.get("notes") or "",
    }


def fingerprint(row) -> str:
    row = dict(row)
    raw = json.dumps(
        [row.get("status"), _iso(row.get("updated_at")), decode_jsonb(row.get("progress"), {})],
        default=str, sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_COUNTS = """(SELECT COUNT(*) FROM mw_job_leads l WHERE l.search_id = s.id) AS lead_count,
             (SELECT COUNT(*) FROM mw_job_leads l WHERE l.search_id = s.id
                AND l.comp_status = 'posted') AS posted_pay_count"""


async def list_searches(user_id: UUID, company_id: UUID) -> list[dict]:
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""SELECT s.*, {_COUNTS} FROM mw_job_searches s
                WHERE s.user_id = $1 AND s.company_id = $2 AND s.deleted_at IS NULL
                ORDER BY s.created_at DESC LIMIT {MAX_LIST}""",
            user_id, company_id,
        )
    return [search_view(row) for row in rows]


async def owned_search(conn, search_id: UUID, user_id: UUID, *, lock: bool = False):
    row = await conn.fetchrow(
        f"""SELECT s.*, {_COUNTS} FROM mw_job_searches s
            WHERE s.id = $1 AND s.user_id = $2 AND s.deleted_at IS NULL"""
        if not lock else
        """SELECT * FROM mw_job_searches
           WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL FOR UPDATE""",
        search_id, user_id,
    )
    if row is None:
        raise JobSearchError("Job search not found.", 404)
    return row


_LEAD_ORDER = "ORDER BY rank NULLS LAST, created_at, id"


async def get_search(search_id: UUID, user_id: UUID) -> dict:
    async with connection_or_direct() as conn:
        search = await owned_search(conn, search_id, user_id)
        leads = await conn.fetch(
            f"SELECT * FROM mw_job_leads WHERE search_id = $1 {_LEAD_ORDER}", search_id,
        )
    return {**search_view(search), "fingerprint": fingerprint(search),
            "leads": [lead_summary(row) for row in leads]}


async def status_view(search_id: UUID, user_id: UUID) -> dict:
    async with connection_or_direct() as conn:
        search = await owned_search(conn, search_id, user_id)
    view = {
        "id": str(search["id"]),
        "status": search["status"],
        "progress": decode_jsonb(search["progress"], {}) or {},
        "error": search["error"],
        "lead_count": int(search["lead_count"] or 0),
        "updated_at": _iso(search["updated_at"]),
        "fingerprint": fingerprint(search),
    }
    if search["status"] in LIVE:
        # A chain whose task was lost is restarted by whoever looks at it.
        from . import orchestrator

        await orchestrator.nudge(search_id)
    return view


async def get_lead(search_id: UUID, lead_id: UUID, user_id: UUID) -> dict:
    async with connection_or_direct() as conn:
        await owned_search(conn, search_id, user_id)
        row = await conn.fetchrow(
            "SELECT * FROM mw_job_leads WHERE id = $1 AND search_id = $2", lead_id, search_id,
        )
    if row is None:
        raise JobSearchError("Job not found.", 404)
    return lead_detail(row)


async def patch_lead(search_id: UUID, lead_id: UUID, user_id: UUID, body: LeadPatch) -> dict:
    async with connection_or_direct() as conn, conn.transaction():
        search = await owned_search(conn, search_id, user_id, lock=True)
        row = await conn.fetchrow(
            "SELECT * FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE",
            lead_id, search_id,
        )
        if row is None:
            raise JobSearchError("Job not found.", 404)
        was_dismissed = row["user_state"] == "dismissed"
        state = body.user_state if body.user_state is not None else row["user_state"]
        notes = body.notes if body.notes is not None else row["notes"]
        row = await conn.fetchrow(
            """UPDATE mw_job_leads SET user_state = $3, notes = $4, updated_at = NOW()
               WHERE id = $1 AND search_id = $2 RETURNING *""",
            lead_id, search_id, state, notes,
        )
        # Dismissing (or restoring) moves the job in or out of the ranking.
        if (state == "dismissed") != was_dismissed:
            await rerank(conn, search)
            row = await conn.fetchrow(
                "SELECT * FROM mw_job_leads WHERE id = $1 AND search_id = $2", lead_id, search_id,
            )
    return lead_detail(row)


async def update_weights(search_id: UUID, user_id: UUID, weights: JobWeights) -> dict:
    clean = ranking.clean_weights(weights.model_dump())
    async with connection_or_direct() as conn, conn.transaction():
        search = await owned_search(conn, search_id, user_id, lock=True)
        search = await conn.fetchrow(
            """UPDATE mw_job_searches SET weights = $2::jsonb, weights_source = 'user',
                      updated_at = NOW()
               WHERE id = $1 RETURNING *""",
            search_id, json.dumps(clean),
        )
        await rerank(conn, search)
    return await get_search(search_id, user_id)


async def release_drafts(conn, search_id: UUID) -> None:
    """A search that ended (finished early, cancelled, stalled) drafts nothing
    more: jobs still waiting for an approach become `failed`, which the person
    can redraft, instead of showing "drafting" forever."""
    await conn.execute(
        """UPDATE mw_job_leads SET approach_status = 'failed', updated_at = NOW()
           WHERE search_id = $1 AND approach_status IN ('queued', 'drafting')""",
        search_id,
    )


async def cancel_search(search_id: UUID, user_id: UUID) -> dict:
    async with connection_or_direct() as conn, conn.transaction():
        search = await owned_search(conn, search_id, user_id, lock=True)
        if search["status"] in LIVE:
            search = await conn.fetchrow(
                """UPDATE mw_job_searches
                   SET status = 'cancelled', dispatch_token = NULL, lease_until = NULL,
                       progress = progress || '{"note": "Cancelled."}'::jsonb,
                       completed_at = NOW(), updated_at = NOW()
                   WHERE id = $1 RETURNING *""",
                search_id,
            )
            # What was found so far stays useful, ranked.
            await rerank(conn, search)
            await release_drafts(conn, search_id)
    return await get_search(search_id, user_id)


async def delete_search(search_id: UUID, user_id: UUID) -> dict:
    """Blank the search and drop its leads and runs; the row stays as a tombstone
    so a deleted search still counts toward this month's allowance. Its row in
    Tasks goes too."""
    async with connection_or_direct() as conn, conn.transaction():
        await owned_search(conn, search_id, user_id, lock=True)
        await conn.execute("DELETE FROM mw_job_leads WHERE search_id = $1", search_id)
        await conn.execute(
            "DELETE FROM mw_project_agent_runs WHERE job_search_id = $1 AND kind = 'job_search'",
            search_id,
        )
        await conn.execute(
            f"""UPDATE mw_job_searches
               SET deleted_at = NOW(), title = '', ask = '', criteria = '{{}}'::jsonb,
                   plan = '{{}}'::jsonb, progress = '{{}}'::jsonb, phase_cursor = '{{}}'::jsonb,
                   error = NULL, dispatch_token = NULL, lease_until = NULL,
                   status = CASE WHEN status IN ({_LIVE_SQL}) THEN 'cancelled' ELSE status END,
                   completed_at = COALESCE(completed_at, NOW()), updated_at = NOW()
               WHERE id = $1""",
            search_id,
        )
        await conn.execute(
            """UPDATE mw_agent_tasks SET deleted_at = NOW(), title = '', directive = '', updated_at = NOW()
               WHERE job_search_id = $1 AND deleted_at IS NULL""",
            search_id,
        )
    return {"deleted": True}


async def end_stale(conn, user_id: UUID) -> int:
    """End this person's live searches that stopped moving STALE_INTERVAL ago,
    the way reconcile would: `done` (it counts) when it found jobs, which are
    ranked, else `failed` (free). Runs inside the caller's transaction."""
    rows = await conn.fetch(
        f"""SELECT * FROM mw_job_searches
            WHERE user_id = $1 AND status IN ({_LIVE_SQL}) AND deleted_at IS NULL
              AND updated_at < NOW() - INTERVAL '{STALE_INTERVAL}'
            FOR UPDATE""",
        user_id,
    )
    for row in rows:
        found = bool(await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM mw_job_leads WHERE search_id = $1)", row["id"],
        ))
        if found:
            await rerank(conn, row)
        ended = resting_status(row) or ("done" if found else "failed")
        await conn.execute(
            """UPDATE mw_job_searches
               SET status = $2, dispatch_token = NULL, lease_until = NULL,
                   error = COALESCE(error, 'Stopped: the search stopped making progress.'),
                   completed_at = NOW(), updated_at = NOW()
               WHERE id = $1""",
            row["id"], ended,
        )
        await release_drafts(conn, row["id"])
    return len(rows)


def resting_status(search: dict) -> str | None:
    """`cancelled` while a cancelled search drafts a requested approach (the
    status it goes back to whatever happens), else None."""
    cursor = decode_jsonb(search.get("phase_cursor"), {}) or {}
    return "cancelled" if isinstance(cursor, dict) and cursor.get("after") == "cancelled" else None


async def find_by_request(user_id: UUID, request_id: UUID) -> dict | None:
    """A search this person already started with this request id (a retry)."""
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mw_job_searches WHERE user_id = $1 AND request_id = $2", user_id, request_id,
        )
    return search_view(row) if row else None


def _rank_input(row) -> dict:
    row = dict(row)
    age = normalize.posted_age_hours(row.get("posted_text"))
    return {
        "id": row["id"],
        "comp": decode_jsonb(row.get("comp"), {}) or {},
        "fit_score": row.get("fit_score"),
        "screen_status": row.get("screen_status"),
        "user_state": row.get("user_state"),
        "posted_order": -age if age is not None else None,
    }


async def rerank(conn, search) -> int:
    """Recompute every lead's rank from stored facts. Returns how many leads."""
    search = dict(search)
    criteria = decode_jsonb(search.get("criteria"), {}) or {}
    leads = await conn.fetch(
        """SELECT id, comp, fit_score, screen_status, user_state, posted_text
           FROM mw_job_leads WHERE search_id = $1""",
        search["id"],
    )
    if not leads:
        return 0
    ranked = ranking.rank(
        [_rank_input(row) for row in leads],
        decode_jsonb(search.get("weights"), {}) or {},
        floor=criteria.get("base_floor"),
        currency=criteria.get("currency") or "USD",
    )
    await conn.execute(
        """UPDATE mw_job_leads AS l
           SET rank_score = v.score, rank = v.rank, rank_band = v.band,
               rank_explain = v.explain::jsonb,
               pay_law_hint = CASE WHEN l.comp_status <> 'posted' AND l.state_code = ANY($7::text[])
                                   THEN l.state_code || ' has a pay-range law: ask for the range.'
                                   ELSE NULL END,
               updated_at = NOW()
           FROM unnest($2::uuid[], $3::float8[], $4::int[], $5::int[], $6::text[])
                AS v(id, score, rank, band, explain)
           WHERE l.id = v.id AND l.search_id = $1""",
        search["id"],
        [UUID(r.lead_id) for r in ranked],
        [r.score for r in ranked],
        [r.rank for r in ranked],
        [r.band for r in ranked],
        [json.dumps(r.explain) for r in ranked],
        PAY_LAW_STATES,
    )
    return len(ranked)


async def load_resume_for_model(user_id: UUID) -> str | None:
    """The person's saved résumé as text for a model, or None. Only read when
    the search was started with "use my résumé" (covered by `jobs-1`)."""
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            "SELECT raw_text, parsed_data FROM user_resumes WHERE user_id = $1", user_id,
        )
    if row is None:
        return None
    parsed = decode_jsonb(row["parsed_data"], {}) or {}
    head = []
    for key, label in (("current_title", "Current title"), ("experience_years", "Years of experience"),
                       ("location", "Location"), ("summary", "Summary")):
        if parsed.get(key):
            head.append(f"{label}: {parsed[key]}")
    if parsed.get("skills"):
        head.append("Skills: " + ", ".join(str(s) for s in parsed["skills"][:30]))
    text = "\n".join(head)
    raw = (row["raw_text"] or "").strip()
    if raw:
        text = f"{text}\n\n{raw}" if text else raw
    return text[:RESUME_CHARS] or None


async def requeue_approach(search_id: UUID, lead_id: UUID, user_id: UUID):
    """Put a finished search back into `approaching` for one job.

    Returns (search row, new token) for the caller to dispatch. Free: it is
    not a new search, but capped per search.
    """
    token = uuid4()
    async with connection_or_direct() as conn, conn.transaction():
        search = await owned_search(conn, search_id, user_id, lock=True)
        if search["status"] in LIVE:
            raise JobSearchError("This search is still running. Try again when it finishes.", 409)
        if search["status"] not in REDRAFTABLE:
            raise JobSearchError("Only a finished or cancelled search can draft more approaches.", 409)
        if int(search["redrafts"] or 0) >= MAX_REDRAFTS:
            raise JobSearchError("This search has used its redrafts.", 429)
        lead = await conn.fetchrow(
            "SELECT id, approach_status FROM mw_job_leads WHERE id = $1 AND search_id = $2 FOR UPDATE",
            lead_id, search_id,
        )
        if lead is None:
            raise JobSearchError("Job not found.", 404)
        await conn.execute(
            "UPDATE mw_job_leads SET approach_status = 'queued', updated_at = NOW() WHERE id = $1",
            lead_id,
        )
        try:
            search = await conn.fetchrow(
                """UPDATE mw_job_searches
                   SET status = 'approaching', dispatch_token = $2, lease_until = NULL, attempts = 0,
                       phase_cursor = $3::jsonb, redrafts = redrafts + 1, completed_at = NULL,
                       progress = progress || '{"note": "Drafting the approach…"}'::jsonb,
                       updated_at = NOW()
                   WHERE id = $1 RETURNING *""",
                search_id, token,
                # `after`: the status to return to once drafted, so a cancelled
                # search stays cancelled instead of turning into a finished one.
                json.dumps({"approach_queue": [str(lead_id)], "after": search["status"]}),
            )
        except asyncpg.UniqueViolationError as exc:
            raise JobSearchError("Another job search is running. Try again when it finishes.", 409) from exc
    return search, token
