"""The deterministic phases of one job search. Each runs inside one worker task.

  discover  Google Jobs, page by page, deduped into leads (no model)
  enrich    each lead's ATS API or the company's posting page: full text, pay
            with evidence, application questions; then the ranking (no model).
            A posting is the lead's only when its title and employer match:
            Google lists other employers' jobs among a posting's apply links

`plan_from_criteria` is the plan when the model plan fails. The model phases
(plan, screen, approach) are in `model_phases.py`; the order is in
`orchestrator.PHASES`.

Every write checks the search's dispatch token (`Guard`), so a cancelled
search, or a chain a reconcile replaced, stops writing at the next check.

Paid calls (Google Jobs, page and ATS fetches) are reserved on the search row
BEFORE they are made (`grant`), and only what went unused is given back
(`refund`). A task killed mid-phase gives nothing back, so its retry works
from what is left and can never spend a second budget.

`Guard`, `grant`, `refund`, `Budget`, `PhaseOutcome` and `PhaseFailed` are the
chain engine's (`agent_runtime/chain.py`); the first three are bound here to
the search row (`orchestrator.JOB_CHAIN`).
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work.agent_card.page_extract import job_postings
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import Budget, PhaseFailed, PhaseOutcome

from . import ats, normalize, providers, ranking
from . import comp as comp_mod
from .service import fit_floor, rerank

logger = logging.getLogger(__name__)

MAX_QUERIES = 8
PAGES_PER_QUERY = 3
QUERY_CONCURRENCY = 3
# Per search, across retries: a retried discover never buys a second budget.
MAX_PROVIDER_CALLS = 30
MAX_LEADS = 120
ENRICH_BATCH = 24
ENRICH_CONCURRENCY = 4
MAX_FETCHES = 240
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
_NATIONWIDE = {"united states", "us", "usa", "u.s.", "nationwide", "anywhere",
               "across the country", "across the us", "the us", "america"}


def _default_client(model: str) -> Any:
    from .agent_phase import default_client

    return default_client(model)


async def _default_fetch_page(url: str) -> tuple[dict, set[str]]:
    from app.matcha.services.matcha_work.agent_card.agent import fetch_page_tool

    return await fetch_page_tool(url)


@dataclass
class Deps:
    provider: Callable[[], Any] = providers.choose_provider
    ats_fetch: Callable[..., Awaitable[Any]] = ats.fetch
    ats_find: Callable[..., Awaitable[Any]] = ats.find_on_board
    page_fetch: Callable[..., Awaitable[Any]] = fetch_public
    # Model phases: the model client for a model id, and the model's fetch_page.
    client: Callable[[str], Any] = _default_client
    fetch_page: Callable[[str], Awaitable[tuple[dict, set[str]]]] = _default_fetch_page


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

def plan_from_criteria(ask: str, criteria: dict) -> dict:
    """Search queries straight from what the person entered.

    Google Jobs' `location` parameter only takes Google's own place names, so
    a city goes into the query text and only the country goes in `location`.
    """
    titles = [t for t in (criteria.get("titles") or []) if t] or [" ".join(ask.split())[:100]]
    locations = [loc for loc in (criteria.get("locations") or []) if loc] or ["United States"]
    remote_only = criteria.get("remote") == "remote_only"
    queries = []
    for title in titles:
        for location in locations:
            key = location.strip().lower()
            if key in _NATIONWIDE:
                q, loc = title, "United States"
            elif key == "remote":
                q, loc = f"{title} remote", "United States"
            else:
                q, loc = f"{title} {location}", None
            if remote_only and "remote" not in q.lower():
                q = f"{q} remote"
            queries.append({"q": q[:160], "location": loc})
    seen, unique = set(), []
    for query in queries:
        key = (query["q"].lower(), query["location"])
        if key not in seen:
            seen.add(key)
            unique.append(query)
    return {"queries": unique[:MAX_QUERIES], "source": "criteria"}


# ── discover ─────────────────────────────────────────────────────────────────

def lead_record(posting: providers.Posting) -> dict:
    """One discovered posting as a `mw_job_leads` insert row."""
    url = posting.share_url or (posting.apply_links[0]["url"] if posting.apply_links else None)
    findings = []
    if posting.salary_text:
        findings += comp_mod.scan_base(posting.salary_text, origin="google_jobs", url=url, known_pay=True)
    findings += comp_mod.scan_text(posting.description, origin="google_jobs", url=url)
    comp = comp_mod.combine(findings)
    lo, hi, currency = comp_mod.annual_range(comp)
    return {
        "dedupe_key": normalize.dedupe_key(posting.company, posting.title, posting.location),
        "title": posting.title,
        "company": posting.company,
        "location": posting.location,
        "state_code": normalize.state_of(posting.location),
        "remote": posting.remote,
        "schedule_type": posting.schedule_type,
        "posted_text": posting.posted_text,
        "provider_job_id": posting.provider_job_id,
        "source_url": url,
        "apply_links": posting.apply_links,
        "description": posting.description,
        "highlights": posting.highlights,
        "comp": comp,
        "comp_status": comp_mod.comp_status(comp),
        "comp_annual_min": lo,
        "comp_annual_max": hi,
        "comp_currency": currency,
    }


def keep_posting(posting: providers.Posting, criteria: dict) -> bool:
    excluded = {normalize.company_key(c) for c in criteria.get("exclude_companies") or []}
    if normalize.company_key(posting.company) in excluded:
        return False
    remote = criteria.get("remote")
    if remote == "remote_only" and posting.remote is not True:
        return False
    if remote == "onsite_only" and posting.remote is True:
        return False
    return True


async def _insert_leads(search: dict, token: UUID, records: list[dict]) -> int:
    if not records:
        return 0
    async with connection_or_direct() as conn:
        inserted = await conn.fetchval(
            """WITH ins AS (
                   INSERT INTO mw_job_leads
                       (search_id, user_id, dedupe_key, title, company, location, state_code,
                        remote, schedule_type, posted_text, source, provider_job_id, source_url,
                        apply_links, description, highlights, comp, comp_status,
                        comp_annual_min, comp_annual_max, comp_currency)
                   SELECT $1, $2, r.dedupe_key, r.title, r.company, r.location, r.state_code,
                          r.remote, r.schedule_type, r.posted_text, 'google_jobs', r.provider_job_id,
                          r.source_url, r.apply_links, r.description, r.highlights, r.comp,
                          r.comp_status, r.comp_annual_min, r.comp_annual_max, r.comp_currency
                   FROM jsonb_to_recordset($3::jsonb) AS r(
                       dedupe_key text, title text, company text, location text, state_code text,
                       remote boolean, schedule_type text, posted_text text, provider_job_id text,
                       source_url text, apply_links jsonb, description text, highlights jsonb,
                       comp jsonb, comp_status text, comp_annual_min numeric,
                       comp_annual_max numeric, comp_currency text)
                   WHERE EXISTS (SELECT 1 FROM mw_job_searches
                                 WHERE id = $1 AND dispatch_token = $4)
                   ON CONFLICT (search_id, dedupe_key) DO NOTHING
                   RETURNING 1)
               SELECT COUNT(*) FROM ins""",
            search["id"], search["user_id"], json.dumps(records, default=str), token,
        )
    return int(inserted or 0)


async def discover(search: dict, deps: Deps, guard: chain.Guard) -> PhaseOutcome:
    provider = deps.provider()
    if provider is None:
        raise PhaseFailed("Job search isn't set up on this server.")
    criteria = decode_jsonb(search.get("criteria"), {}) or {}
    queries = ((decode_jsonb(search.get("plan"), {}) or {}).get("queries") or [])[:MAX_QUERIES]
    async with connection_or_direct() as conn:
        existing = int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1", search["id"],
        ) or 0)
    room = max(0, MAX_LEADS - existing)
    budget = Budget(left=await grant(search["id"], "provider_calls",
                                     len(queries) * PAGES_PER_QUERY, MAX_PROVIDER_CALLS))
    state = {"errors": 0, "refused": False}
    records: dict[str, dict] = {}
    gate = asyncio.Semaphore(QUERY_CONCURRENCY)

    async def run_query(query: dict) -> None:
        token = None
        for _page in range(PAGES_PER_QUERY):
            async with gate:
                # Checked once it's this query's turn: others may have refused meanwhile.
                if state["refused"] or len(records) >= room or not budget.take():
                    return
                try:
                    postings, token = await provider.search(
                        query["q"], query.get("location"), page_token=token,
                    )
                except providers.ProviderError as exc:
                    if exc.fatal:
                        # Every listings API refused for good (the provider logged it):
                        # nothing more is asked, and what was found is kept.
                        state["refused"] = True
                        return
                    state["errors"] += 1
                    logger.info("job search query failed search=%s: %s", search["id"], exc)
                    return
            for posting in postings:
                if keep_posting(posting, criteria):
                    record = lead_record(posting)
                    if record["dedupe_key"] in records or any(
                        normalize.same_posting(record["title"], record["company"], r["title"], r["company"])
                        for r in records.values()
                    ):
                        continue
                    records[record["dedupe_key"]] = record
            if not token:
                return

    await guard.note("Searching Google Jobs…")
    results = await asyncio.gather(*(run_query(q) for q in queries), return_exceptions=True)
    await refund(search["id"], "provider_calls", budget.left)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    await _insert_leads(search, guard.token, list(records.values())[:room])
    async with connection_or_direct() as conn:
        total = int(await conn.fetchval(
            "SELECT COUNT(*) FROM mw_job_leads WHERE search_id = $1", search["id"],
        ) or 0)
    if total == 0:
        if state["refused"]:
            raise PhaseFailed(UNAVAILABLE)
        if state["errors"] and state["errors"] >= budget.used:
            raise RuntimeError("every job listing query failed")  # retried
        raise PhaseFailed("No postings matched. Try broader titles or more locations.")
    return PhaseOutcome(
        status=NEXT_AFTER_DISCOVER,
        progress={"note": f"Found {total} jobs. Reading the postings for pay…", "found": total},
    )


NEXT_AFTER_DISCOVER = "screening"
# Every listings API refused for good (a refused key, no searches left): not
# the person's search, and retrying won't help. A failed search is free.
UNAVAILABLE = ("Job listings aren't available right now, so the search stopped. "
               "It didn't count against your allowance. Please try again later.")


# ── enrich ───────────────────────────────────────────────────────────────────

def _aggregator(url: str) -> bool:
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


def _pick_job(jobs: list[dict], title: str) -> dict | None:
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


async def _read_page(url: str, lead: dict, update: dict, comp: dict, deps: Deps, take) -> dict | None:
    """The lead's job from one company page (or the ATS it redirects to), or None."""
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
    # A careers page that redirected to an ATS: read the ATS instead.
    ref = ats.detect(fetched.final_url)
    if ref is not None and take():
        posting = await deps.ats_fetch(ref)
        if posting is not None and _is_the_job(lead, posting.title, posting.employer):
            update["comp"] = _apply_ats(update, posting, comp)
            return update
    try:
        jobs = await asyncio.to_thread(job_postings, fetched.body, fetched.final_url)
    except Exception:
        return None
    job = _pick_job(jobs, lead.get("title") or "")
    if job is None or not _is_the_job(lead, job.get("title") or "", job.get("company") or None):
        return None
    url_final = normalize.http_url(job.get("url")) or fetched.final_url
    findings = comp_mod.from_jsonld(job.get("base_salary"), url=url_final)
    findings += comp_mod.scan_text(job.get("description") or "", origin="jsonld", url=url_final)
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
        if not take():
            return NOT_TRIED if spent == 0 else None
        posting = await deps.ats_fetch(ats.detect(url))
        if posting is not None and _is_the_job(lead, posting.title, posting.employer):
            update["comp"] = _apply_ats(update, posting, comp)
            return update
    company_pages = [u for u in urls if not _aggregator(u) and ats.detect(u) is None]
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
    async with connection_or_direct() as conn:
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
                    RETURNING id, rank""",
                search["id"],
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
