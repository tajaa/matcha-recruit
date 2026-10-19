"""The deterministic parts of one job search. Each runs inside one worker task.

  enrich    each lead's ATS API or the company's posting page: full text, pay
            with evidence, application questions; then the ranking (no model).
            A posting is the lead's only when its title and employer match:
            Google Jobs, which searches used to start from, listed other
            employers' jobs among a posting's apply links

Postings come from Brave and Claude only (`discovery.py`): code's Brave
searches of the ATS boards and a Claude run's web search. The Google Jobs step
(SearchAPI, else SerpApi) was taken out on 2026-10-18; leads it found before
then keep `source = 'google_jobs'` and read as they did.

`plan_from_criteria` is the plan when the model plan fails. The model phases
(plan, the web search in discover, screen, approach) are in `model_phases.py`
and `discovery.py`; the order is in `orchestrator.PHASES`.

Every write checks the search's dispatch token (`Guard`), so a cancelled
search, or a chain a reconcile replaced, stops writing at the next check.

Paid calls (Brave's board searches, page and ATS fetches) are reserved on the search row
BEFORE they are made (`grant`), and only what went unused is given back
(`refund`). A task killed mid-phase gives nothing back, so its retry works
from what is left and can never spend a second budget.

`Guard`, `grant`, `refund`, `Budget` and `PhaseOutcome` are the chain
engine's (`agent_runtime/chain.py`); the first three are bound here to
the search row (`orchestrator.JOB_CHAIN`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work.agent_card.page_extract import job_postings
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import Budget, PhaseOutcome

from . import ats, normalize, places, ranking
from . import comp as comp_mod
from .contracts import titles_in
from .service import fit_floor, rerank

logger = logging.getLogger(__name__)

# Per search, across retries: a retried discover never buys a second budget.
# Brave's board searches take at most `boards.MAX_SEARCHES` (24) a pass. The
# room for two passes is kept: a boards step re-claimed after a worker restart
# runs again, and a search begun before 2026-10-18 had spent calls on Google
# Jobs, which would otherwise leave its boards step with none.
MAX_PROVIDER_CALLS = 48
MAX_LEADS = 120
ENRICH_BATCH = 24
ENRICH_CONCURRENCY = 4
# Shared, first come: discovery's reads on the web (`discovery.py`: at most
# 160 a web run, usually far fewer), then enrich (240 when discovery read
# nothing).
MAX_FETCHES = 400
# One lead's share: a few links, then a guess at the employer's own board.
LEAD_FETCHES = 10
LINKS_PER_KIND = 2
PAGE_BYTES = 2_000_000
PAGE_SECONDS = 20.0
# Boards that refuse servers or show the same posting without its details.
AGGREGATOR_HOSTS = (
    "linkedin.com", "indeed.com", "ziprecruiter.com", "glassdoor.com", "monster.com",
    "simplyhired.com", "careerbuilder.com", "talent.com", "jooble.org", "adzuna.com",
    "lensa.com", "google.com", "bebee.com", "learn4good.com", "jobrapido.com",
)
NATIONWIDE = {"united states", "us", "usa", "u.s.", "nationwide", "anywhere",
               "across the country", "across the us", "the us", "america"}


def _default_client(model: str) -> Any:
    from .agent_phase import default_client

    return default_client(model)


async def _default_fetch_page(url: str) -> tuple[dict, set[str]]:
    from app.matcha.services.matcha_work.agent_card.agent import fetch_page_tool

    return await fetch_page_tool(url)


async def _default_web_search(query: str, count: int, offset: int = 0) -> list[dict]:
    from app.matcha.services.matcha_work import brave_search

    return await brave_search.search(query, count=count, offset=offset)


@dataclass
class Deps:
    ats_fetch: Callable[..., Awaitable[Any]] = ats.fetch
    ats_find: Callable[..., Awaitable[Any]] = ats.find_on_board
    page_fetch: Callable[..., Awaitable[Any]] = fetch_public
    # Model phases: the model client for a model id, and the model's fetch_page.
    client: Callable[[str], Any] = _default_client
    fetch_page: Callable[[str], Awaitable[tuple[dict, set[str]]]] = _default_fetch_page
    # Code's own web search (Brave), for the board searches: (query, count, offset=page) -> results.
    web_search: Callable[..., Awaitable[list[dict]]] = _default_web_search


# The paid-call counters on the search row: `grant` and `refund` touch nothing else.
BUDGET_COLUMNS = frozenset({"provider_calls", "fetch_calls"})


def _chain() -> chain.ChainSpec:
    from .orchestrator import JOB_CHAIN  # orchestrator imports this module

    return JOB_CHAIN


async def grant(search_id: UUID, column: str, want: int, limit: int) -> int:
    """Reserve up to `want` calls against the search's lifetime `limit`; the
    number granted (0 when spent)."""
    return await chain.grant(_chain(), search_id, column, want, limit)


async def refund(search_id: UUID, column: str, unused: int) -> None:
    await chain.refund(_chain(), search_id, column, unused)


class Guard(chain.Guard):
    """The chain's guard on one search, built by hand: `Guard(search_id, token)`.
    Phases get theirs from `chain.run_phase`, so annotate with `chain.Guard`."""

    def __init__(self, search_id: UUID, token: UUID) -> None:
        super().__init__(_chain(), search_id, token)


# ── plan ─────────────────────────────────────────────────────────────────────

# The role in an ask, for a search with no typed title whose model plan
# failed: every search quotes its titles as an exact phrase, so the whole
# sentence would find nothing.
_ASK_OPENING = re.compile(
    r"^(?:(?:please|hi|hey)\W+)*(?:i\s*(?:'|\u2019)?m\s+|i\s+am\s+)?"
    r"(?:(?:looking|searching|hunting)\s+for|(?:i\s+)?(?:want|need)|find(?:\s+me)?|"
    r"search\s+for|help\s+me\s+find|get\s+me)\s+", re.I)
_ASK_FILLER = re.compile(
    r"^(?:an?|the|some|new|remote|hybrid|on-?site|full[- ]time|part[- ]time|contract|"
    r"(?:jobs?|roles?|positions?|work)\s+as(?:\s+an?)?)\s+", re.I)
_ASK_END = re.compile(
    r"\s+(?:jobs?|roles?|positions?|openings?|opportunities|in|at|near|around|for|with|that|"
    r"which|who|where|paying|making|remote(?:ly)?|hybrid)\b|[,.;:!?()]", re.I)
ASK_TITLE_WORDS = 6
# Not a role: a search with none is left to the web run's own searches.
_NOT_A_ROLE = {"something", "anything", "work", "job", "role", "position", "career", "opportunity"}


def title_from_ask(ask: str) -> str:
    """The role an ask names ("find me a senior product designer job in
    Austin" -> "senior product designer"), at most `ASK_TITLE_WORDS` words;
    empty when it names none."""
    text = _ASK_OPENING.sub("", " ".join(str(ask or "").split()))
    while (stripped := _ASK_FILLER.sub("", text)) != text:
        text = stripped
    end = _ASK_END.search(text)
    title = " ".join((text[:end.start()] if end else text).split()[:ASK_TITLE_WORDS])
    return "" if title.lower() in _NOT_A_ROLE else title


def plan_from_criteria(ask: str, criteria: dict) -> dict:
    """The titles to search, straight from what the person entered (or the
    role their ask names, when they entered none): the plan when the model
    plan fails."""
    titles = titles_in(criteria.get("titles")) or titles_in([title_from_ask(ask)])
    return {"titles": titles, "source": "criteria"}


def must_search(criteria: dict, plan: dict) -> int:
    """How many of the plan's first titles every code-written search takes:
    each one the person typed and each direction kept, which the plan lists
    first (`model_phases.plan`), however few titles a search usually takes."""
    directions = [d.get("title") for d in plan.get("directions") or [] if isinstance(d, dict)]
    return len(titles_in([*(criteria.get("titles") or []), *directions]))


def cover(firsts: list, seconds: list) -> list[tuple]:
    """Every (first, second) pair, ordered so each of both lists is reached
    before any pair repeats one: a capped list of searches still has every
    title and every place in it."""
    if not firsts or not seconds:
        return []
    reach = [(firsts[i % len(firsts)], seconds[i % len(seconds)]) for i in range(max(len(firsts), len(seconds)))]
    return list(dict.fromkeys([*reach, *((f, s) for f in firsts for s in seconds)]))


# ── discover ─────────────────────────────────────────────────────────────────

def keep_job(company: str, remote: bool | None, criteria: dict, location: str = "") -> bool:
    """Not an employer they excluded, remote the way they asked, and in a
    place they named when they named any (`places.fits`)."""
    excluded = {normalize.company_key(c) for c in criteria.get("exclude_companies") or []}
    if normalize.company_key(company) in excluded:
        return False
    wanted = criteria.get("remote")
    if wanted == "remote_only" and remote is not True:
        return False
    if wanted == "onsite_only" and remote is True:
        return False
    return places.fits(location, remote, criteria)


async def insert_leads(search: dict, token: UUID, records: list[dict]) -> int:
    """New leads, under the chain's token; a lead already found is kept as it
    was. One discovery already read from its own posting (`enriched`)
    carries its `ats` and is not read again by enrich."""
    if not records:
        return 0
    async with connection_or_direct() as conn:
        inserted = await conn.fetchval(
            """WITH ins AS (
                   INSERT INTO mw_job_leads
                       (search_id, user_id, dedupe_key, title, company, location, state_code,
                        remote, schedule_type, posted_text, source, provider_job_id, source_url,
                        apply_links, ats, description, highlights, comp, comp_status,
                        comp_annual_min, comp_annual_max, comp_currency, enriched_at)
                   SELECT $1, $2, r.dedupe_key, r.title, r.company, r.location, r.state_code,
                          r.remote, r.schedule_type, r.posted_text, COALESCE(r.source, 'web'),
                          r.provider_job_id, r.source_url, r.apply_links, COALESCE(r.ats, '{}'::jsonb),
                          r.description, r.highlights, r.comp, r.comp_status, r.comp_annual_min,
                          r.comp_annual_max, r.comp_currency,
                          CASE WHEN r.enriched THEN NOW() END
                   FROM jsonb_to_recordset($3::jsonb) AS r(
                       dedupe_key text, title text, company text, location text, state_code text,
                       remote boolean, schedule_type text, posted_text text, source text,
                       provider_job_id text, source_url text, apply_links jsonb, ats jsonb,
                       description text, highlights jsonb, comp jsonb, comp_status text,
                       comp_annual_min numeric, comp_annual_max numeric, comp_currency text,
                       enriched boolean)
                   WHERE EXISTS (SELECT 1 FROM mw_job_searches
                                 WHERE id = $1 AND dispatch_token = $4)
                   ON CONFLICT (search_id, dedupe_key) DO NOTHING
                   RETURNING 1)
               SELECT COUNT(*) FROM ins""",
            search["id"], search["user_id"], json.dumps(records, default=str), token,
        )
    return int(inserted or 0)


async def lead_count(search_id: UUID) -> int:
    async with connection_or_direct() as conn:
        return int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1", search_id,
        ) or 0)


# ── enrich ───────────────────────────────────────────────────────────────────

def aggregator(url: str) -> bool:
    host = normalize.host_of(url)
    return any(host == h or host.endswith("." + h) for h in AGGREGATOR_HOSTS)


def _apply_ats(update: dict, posting: ats.AtsPosting, comp: dict) -> dict:
    update["source"] = posting.ref.provider
    if posting.url:
        update["source_url"] = posting.url
    if posting.description and len(posting.description) >= len(update.get("description") or ""):
        update["description"] = posting.description
    if posting.remote is not None:
        update["remote"] = posting.remote
    update["ats"] = {**posting.ref.view(), "questions": posting.questions}
    return comp_mod.combine(posting.findings, comp)


def pick_job(jobs: list[dict], title: str) -> dict | None:
    words = set(normalize._words(title))
    best, best_overlap = None, -1
    for job in jobs:
        overlap = len(words & set(normalize._words(job.get("title") or "")))
        if overlap > best_overlap:
            best, best_overlap = job, overlap
    return best


def _is_the_job(lead: dict, title: str, employer: str | None) -> bool:
    """Whether a posting read from one of the lead's links is the lead's job.
    Google Jobs lists other employers' jobs among a posting's apply links, so
    the title must match, and so must the employer wherever the source names
    one (Greenhouse's company, an ATS board's name, a page's hiring
    organization)."""
    if not normalize.same_title(lead.get("title") or "", title):
        return False
    return normalize.same_employer(lead.get("company") or "", employer or "") is not False


class _NotTried:
    """`enrich_one` ran out of granted fetches before reading this lead."""


NOT_TRIED = _NotTried()


@dataclass
class JobPage:
    """A company page, read: where it ended up, the ATS posting it redirected
    into (read when there was budget for it), and its JobPosting data."""

    url: str
    posting: ats.AtsPosting | None
    jobs: list[dict]


async def read_job_page(url: str, deps: Deps, take: Callable[[], bool]) -> JobPage | None:
    """One company page; None when it can't be read. The page itself is paid
    for by the caller, a redirect into an ATS with `take()`."""
    try:
        fetched = await deps.page_fetch(url, max_bytes=PAGE_BYTES, accept="text/html,application/xhtml+xml",
                                        total_timeout=PAGE_SECONDS)
    except (UnsafeURL, TimeoutError, OSError):
        return None
    except Exception:
        logger.info("job page fetch failed", exc_info=True)
        return None
    if fetched.status != 200 or "html" not in (fetched.content_type or ""):
        return None
    # A careers page that redirected to an ATS: the ATS has the posting.
    ref = ats.detect(fetched.final_url)
    posting = await deps.ats_fetch(ref, more=take) if ref is not None and take() else None
    try:
        jobs = await asyncio.to_thread(job_postings, fetched.body, fetched.final_url)
    except Exception:
        jobs = []
    return JobPage(url=fetched.final_url, posting=posting, jobs=jobs)


def page_findings(job: dict, url: str) -> list[dict]:
    """Pay from a page's JobPosting: its `baseSalary`, then its text."""
    findings = comp_mod.from_jsonld(job.get("base_salary"), url=url)
    return findings + comp_mod.scan_text(job.get("description") or "", origin="jsonld", url=url)


async def _read_page(url: str, lead: dict, update: dict, comp: dict, deps: Deps, take) -> dict | None:
    """The lead's job from one company page (or the ATS it redirects to), or None."""
    page = await read_job_page(url, deps, take)
    if page is None:
        return None
    if page.posting is not None and _is_the_job(lead, page.posting.title, page.posting.employer):
        update["comp"] = _apply_ats(update, page.posting, comp)
        return update
    job = pick_job(page.jobs, lead.get("title") or "")
    if job is None or not _is_the_job(lead, job.get("title") or "", job.get("company") or None):
        return None
    url_final = normalize.http_url(job.get("url")) or page.url
    findings = page_findings(job, url_final)
    if job.get("description") and len(job["description"]) >= len(update["description"]):
        update["description"] = job["description"]
    update["source"] = "web"
    update["source_url"] = url_final
    if job.get("remote"):
        update["remote"] = True
    update["comp"] = comp_mod.combine(findings, comp)
    return update


async def enrich_one(lead: dict, deps: Deps, budget: Budget) -> dict | None | _NotTried:
    """The changes for one lead; None when nothing could be read; NOT_TRIED
    when the budget ran out first (the lead stays unread for a later batch).

    Its ATS links first, then company pages, a few of each; a posting that is
    another job is passed over. When none is the job, the employer's own
    board is looked up (`ats.find_on_board`). At most `LEAD_FETCHES` calls."""
    links = decode_jsonb(lead.get("apply_links"), []) or []
    comp = decode_jsonb(lead.get("comp"), {}) or {}
    update: dict = {"description": lead.get("description") or ""}
    urls = [normalize.http_url(link.get("url")) for link in links if isinstance(link, dict)]
    urls = [u for u in urls if u]
    spent = 0

    def take() -> bool:
        nonlocal spent
        if spent >= LEAD_FETCHES or not budget.take():
            return False
        spent += 1
        return True

    for url in [u for u in urls if ats.detect(u) is not None][:LINKS_PER_KIND]:
        ref = ats.detect(url)
        if not take():
            return NOT_TRIED if spent == 0 else None
        posting = await deps.ats_fetch(ref, more=take)
        if posting is not None and _is_the_job(lead, posting.title, posting.employer):
            update["comp"] = _apply_ats(update, posting, comp)
            return update
    company_pages = [u for u in urls if not aggregator(u) and ats.detect(u) is None]
    for url in company_pages[:LINKS_PER_KIND]:
        if not take():
            return NOT_TRIED if spent == 0 else None
        found = await _read_page(url, lead, update, comp, deps, take)
        if found is not None:
            return found
    posting = await deps.ats_find(lead.get("company") or "", lead.get("title") or "", take=take)
    if posting is not None and _is_the_job(lead, posting.title, posting.employer):
        update["comp"] = _apply_ats(update, posting, comp)
        return update
    if spent == 0 and budget.exhausted:
        return NOT_TRIED
    return None


async def _save_enrichment(conn, search_id: UUID, token: UUID, lead_id, update: dict | None) -> None:
    if update is None:
        await conn.execute(
            """UPDATE mw_job_leads SET enriched_at = NOW(), updated_at = NOW()
               WHERE id = $1 AND search_id = $2
                 AND EXISTS (SELECT 1 FROM mw_job_searches WHERE id = $2 AND dispatch_token = $3)""",
            lead_id, search_id, token,
        )
        return
    comp = update.get("comp") or {}
    lo, hi, currency = comp_mod.annual_range(comp)
    await conn.execute(
        """UPDATE mw_job_leads SET
               comp = $4::jsonb, comp_status = $5, comp_annual_min = $6, comp_annual_max = $7,
               comp_currency = $8, description = $9,
               source = COALESCE($10, source), source_url = COALESCE($11, source_url),
               remote = COALESCE($12, remote), ats = COALESCE($13::jsonb, ats),
               enriched_at = NOW(), updated_at = NOW()
           WHERE id = $1 AND search_id = $2
             AND EXISTS (SELECT 1 FROM mw_job_searches WHERE id = $2 AND dispatch_token = $3)""",
        lead_id, search_id, token, json.dumps(comp, default=str), comp_mod.comp_status(comp),
        lo, hi, currency, (update.get("description") or "")[:20_000],
        update.get("source"), update.get("source_url"), update.get("remote"),
        json.dumps(update["ats"]) if update.get("ats") else None,
    )


# A lead counts as a match at the search's fit floor when screening rated it
# at least that, or couldn't rate it (its batch failed). $2 is the floor.
_MATCH = "screen_status <> 'irrelevant' AND (fit_score IS NULL OR fit_score >= $2)"


async def enrich(search: dict, deps: Deps, guard: chain.Guard) -> PhaseOutcome:
    """Read the matches' postings, then rank and queue the top ones' drafts.

    Only jobs at the search's fit floor are read (`service.fit_floor`). The
    first pass settles it: 4/5, or 3/5 when screening rated nothing that high.
    A widened search (`service.widen`) reads its 3/5 jobs and ends without
    drafting."""
    floor = fit_floor(search)
    async with connection_or_direct() as conn:
        if floor is None:
            strong = await conn.fetchval(
                """SELECT EXISTS (SELECT 1 FROM mw_job_leads WHERE search_id = $1
                       AND screen_status <> 'irrelevant' AND fit_score >= $2)""",
                search["id"], ranking.FIT_FLOOR,
            )
            floor = ranking.FIT_FLOOR if strong else ranking.WIDER_FIT_FLOOR
        leads = await conn.fetch(
            f"""SELECT id, title, company, apply_links, comp, description FROM mw_job_leads
                WHERE search_id = $1 AND enriched_at IS NULL AND {_MATCH}
                ORDER BY fit_score DESC NULLS LAST, created_at, id LIMIT {ENRICH_BATCH}""",
            search["id"], floor,
        )
    budget = Budget(left=await grant(search["id"], "fetch_calls", LEAD_FETCHES * len(leads), MAX_FETCHES))
    if leads and budget.left <= 0:
        budget.exhausted = True
    gate = asyncio.Semaphore(ENRICH_CONCURRENCY)
    updates: dict = {}

    async def one(lead) -> None:
        async with gate:
            try:
                updates[lead["id"]] = await enrich_one(dict(lead), deps, budget)
            except Exception:
                logger.warning("job lead enrichment failed lead=%s", lead["id"], exc_info=True)
                updates[lead["id"]] = None

    if leads and budget.left > 0:
        await guard.note(f"Reading {len(leads)} postings for pay and application details…")
        await asyncio.gather(*(one(lead) for lead in leads))
    await refund(search["id"], "fetch_calls", budget.left)
    async with connection_or_direct() as conn:
        for lead_id, update in updates.items():
            if update is not NOT_TRIED:
                await _save_enrichment(conn, search["id"], guard.token, lead_id, update)
        remaining = int(await conn.fetchval(
            f"""SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1
               AND enriched_at IS NULL AND {_MATCH}""",
            search["id"], floor,
        ) or 0)
        counts = await conn.fetchrow(
            f"""SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE comp_status = 'posted') AS posted,
                      COUNT(*) FILTER (WHERE {_MATCH} AND user_state <> 'dismissed') AS matches,
                      COUNT(*) FILTER (WHERE screen_status <> 'irrelevant' AND fit_score = $3
                                       AND user_state <> 'dismissed') AS wider
               FROM mw_job_leads WHERE search_id = $1""",
            search["id"], floor, ranking.WIDER_FIT_FLOOR,
        )
    matches = int(counts.get("matches") or 0)
    if remaining and leads and not budget.exhausted:
        return PhaseOutcome(
            status="enriching",
            progress={"note": f"Read postings; {remaining} to go…", "posted_pay": counts["posted"],
                      "fit_floor": floor},
        )
    if not await guard.current():
        return PhaseOutcome(status="enriching")  # advance will find the chain retired
    cursor = decode_jsonb(search.get("phase_cursor"), {}) or {}
    widening = isinstance(cursor, dict) and bool(cursor.get("widen"))
    ranked = {"found": counts["total"], "posted_pay": counts["posted"], "matches": matches,
              "fit_floor": floor, "ranked": True}
    # One transaction, and the queue write checks the token too: a cancel
    # landing between the floor write and the queue write used to leave jobs
    # `queued` after `release_drafts` had run, shown as drafting for good.
    async with connection_or_direct() as conn, conn.transaction():
        # The floor goes on the row first: the re-rank reads it from there.
        fresh = await conn.fetchrow(
            """UPDATE mw_job_searches SET progress = progress || $2::jsonb
               WHERE id = $1 AND dispatch_token = $3 RETURNING *""",
            search["id"], json.dumps({"fit_floor": floor}), guard.token,
        )
        if fresh is None:
            return PhaseOutcome(status="enriching")  # cancelled meanwhile: nothing more to write
        await rerank(conn, fresh)
        if widening:
            top = []
        else:
            top = await conn.fetch(
                f"""UPDATE mw_job_leads SET approach_status = 'queued', updated_at = NOW()
                    WHERE id IN (SELECT id FROM mw_job_leads
                                 WHERE search_id = $1 AND rank_band < {ranking.BELOW_FLOOR_BAND}
                                 ORDER BY rank LIMIT {APPROACH_TOP})
                      AND EXISTS (SELECT 1 FROM mw_job_searches s WHERE s.id = $1 AND s.dispatch_token = $2)
                    RETURNING id, rank""",
                search["id"], guard.token,
            )
    if widening:
        # Back to where it was (`after`), with no drafts queued.
        return PhaseOutcome(status=cursor.get("after") or "done", cursor={}, progress={
            "note": f"Added {counts.get('wider') or 0} jobs at 3/5; {matches} matches in all.", **ranked})
    queue = [str(row["id"]) for row in sorted(top, key=lambda r: r["rank"] or 0)]
    found = (f"{matches} strong matches (4/5 or better)" if floor == ranking.FIT_FLOOR
             else f"{matches} matches at 3/5 or better") + f" of {counts['total']} jobs"
    if not queue:
        return PhaseOutcome(status="done", progress={
            "note": f"{found}; {counts['posted']} post their pay.", **ranked})
    return PhaseOutcome(
        status="approaching",
        cursor={"approach_queue": queue},
        progress={"note": f"{found} ({counts['posted']} post their pay). "
                          f"Drafting how to approach the top {len(queue)}…", **ranked},
    )


# How many of the top-ranked jobs get an approach drafted.
APPROACH_TOP = 8
