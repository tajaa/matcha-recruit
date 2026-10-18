"""Open roles, right in chat: `find_jobs`, and the `job_postings` list.

"Find me senior product designer jobs in LA" used to be answered with
web_search alone: LinkedIn and Indeed pages the page loader can't read, board
links Brave still indexes months after the job closed (10 of 45 were still up
in a 2026-10-17 prod run), and pay restated from a snippet.

`find_jobs` runs the parts of a job search (`job_search/`) that need no model,
inside one tool call:

1. Google Jobs listings for the title and place (`job_search.providers`:
   SearchAPI, else SerpApi), queries built as a search builds them
   (`phases.plan_from_criteria`: a city goes in the query text).
2. Kept only where the person wants the job (`phases.keep_posting` →
   `places.fits`: within 50 miles of the place named, or remote when they'd
   take it), deduped within the run.
3. The top postings read from the employer's own posting, a few at a time
   (`phases.enrich_one`: the ATS's public API or the page's JobPosting data,
   title and employer matched), within the time the run has left. A posting
   read is `verified`: still up at that link, its pay in the posting's own
   words. It is `at_employer` only on an ATS or the employer's own host
   (`employer_host`); builtin.com and the like carry the same JobPosting
   data but are boards, and are said to be.

Every posting kept is in the run (and its id taken) before anything is read,
so a read that runs out of time costs that posting's check, not the list.

Pay is `ranking.comp_line` over evidence (`comp.py`), never the model's. The
block is rebuilt from what the run found, by id. Only the title and place
leave the server: never the résumé, so nothing needs switching on. A full
search (more sources, fit against the résumé, drafted outreach) is still a
job search task.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.matcha.services.matcha_work.search_apis import ProviderError

from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput

logger = logging.getLogger(__name__)

KEY = "job_listings"
MAX_PAGES = 2
# find_jobs calls a run, and paid listing pages across them.
MAX_CALLS = 4
MAX_PAID = 6
# Postings read from the employer's own posting per call, how many at once,
# the fetches one may use and how long the reading may take in all.
VERIFY = 10
VERIFY_AT_ONCE = 4
VERIFY_FETCHES = 4
# The employer's own board, for a posting first read on a job board: two
# guessed names on each of three ATSs.
BOARD_FETCHES = 6
VERIFY_SECONDS = 40.0
TOOL_SECONDS = 80.0
# Kept back from the tool's own deadline so the answer is written before it.
VERIFY_MARGIN = 5.0
MAX_BLOCK = 30
AUTO_BLOCK_AT = 3
SOURCE_LABELS = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby"}


@dataclass
class JobListingsSession:
    jobs: dict[str, dict] = field(default_factory=dict)  # short id -> job row, in found order
    keys: dict[str, str] = field(default_factory=dict)  # dedupe key -> short id
    paid: int = 0


def session_of(state: RunState) -> JobListingsSession:
    return state.sessions[KEY]


def _provider() -> Any:
    """Google Jobs through the search APIs with keys; None with none. Tests patch this seam."""
    from app.matcha.services.matcha_work.job_search.providers import choose_provider

    return choose_provider()


def _ready() -> bool:
    try:
        return _provider() is not None
    except Exception:  # settings not loaded (a bare script): not offered
        return False


async def _verify(lead: dict) -> dict | None:
    """The changes reading the posting made, or None when it couldn't be read
    (or isn't this job). Tests patch this seam.

    `enrich_one` stops at the first page that has the job, and that is often
    a board copying it (builtin.com): then the employer's own Greenhouse,
    Lever or Ashby board is looked up by name (`ats.find_on_board`, as enrich
    does when nothing reads) and, when it has the same job, read there."""
    from app.matcha.services.matcha_work.agent_runtime.chain import Budget
    from app.matcha.services.matcha_work.job_search import phases

    deps = phases.Deps()
    update = await phases.enrich_one(lead, deps, Budget(left=VERIFY_FETCHES))
    if not isinstance(update, dict):
        return None
    if update.get("source") != "web" or employer_host(update.get("source_url"), lead.get("company") or ""):
        return update
    posting = await deps.ats_find(lead.get("company") or "", lead.get("title") or "",
                                  take=Budget(left=BOARD_FETCHES).take)
    if posting is None or not phases._is_the_job(lead, posting.title, posting.employer):
        return update
    at_employer = {"description": update.get("description") or ""}
    at_employer["comp"] = phases._apply_ats(at_employer, posting, update.get("comp") or {})
    return at_employer


# What a careers site puts around the employer's name: jobs.netflix.com,
# disneycareers.com, lifeattiktok.com.
_CAREER_PREFIXES = ("careers", "career", "jobs", "lifeat", "workat", "joinus", "join")
_CAREER_SUFFIXES = ("careers", "career", "jobs", "hiring")
# The label before a country's TLD that isn't the site's name (example.co.uk).
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu"}


def _without_career_words(label: str) -> str:
    for prefix in _CAREER_PREFIXES:
        if label.startswith(prefix) and len(label) > len(prefix):
            label = label[len(prefix):]
            break
    for suffix in _CAREER_SUFFIXES:
        if label.endswith(suffix) and len(label) > len(suffix):
            return label[:-len(suffix)]
    return label


def employer_host(url: str | None, company: str) -> bool:
    """Whether a link is on the employer's own site: a label of the host is
    its name run together ("careers.bostonscientific.com", "bostonscientific.
    wd5.myworkdayjobs.com"), or the site's own domain is one of its distinctive
    words once a careers word is taken off ("jobs.disneycareers.com" for The
    Walt Disney Company, "jobs.netflix.com"). A word merely inside a label,
    or a subdomain of someone else's site, is not enough: builtinboston.com
    and boston.craigslist.org are not Boston Scientific. Boards (builtin.com,
    jobilize.com) carry the same JobPosting data, but they are not the employer."""
    from app.matcha.services.matcha_work.job_search import normalize

    labels = [label.replace("-", "") for label in normalize.host_of(url or "").split(".") if label]
    name = normalize.named_employer(company)
    if len(labels) < 2 or not name:
        return False
    if any(name in (label, _without_career_words(label)) for label in labels[:-1]):
        return True
    site = labels[-3] if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL else labels[-2]
    return _without_career_words(site) in normalize.name_words(company)


def _apply_url(lead: dict, update: dict | None) -> str | None:
    """Where to apply: an ATS posting or the employer's own site first (read
    there, else among the apply links), then the posting read on a board, then
    any apply link that isn't a known aggregator, else Google's own page."""
    from app.matcha.services.matcha_work.job_search import ats, normalize, phases

    company = lead.get("company") or ""
    read = normalize.http_url((update or {}).get("source_url"))
    links = [u for u in (normalize.http_url((link or {}).get("url")) for link in lead.get("apply_links") or []) if u]
    for url in ([read] if read else []) + links:
        if ats.detect(url) is not None or employer_host(url, company):
            return url
    if read:
        return read
    return (next((u for u in links if not phases.aggregator(u)), None) or next(iter(links), None)
            or normalize.http_url(lead.get("source_url")))


def job_row(lead: dict, update: dict | None, via: str) -> dict:
    """One posting as the run keeps it."""
    from app.matcha.services.matcha_work.job_search import comp as comp_mod
    from app.matcha.services.matcha_work.job_search import ranking

    comp = (update or {}).get("comp") or lead.get("comp") or {}
    base = comp.get("base") if isinstance(comp.get("base"), dict) else {}
    quote = ((base.get("evidence") or {}).get("quote") or "")[:200] if base.get("status") == "posted" else ""
    remote = (update or {}).get("remote", lead.get("remote"))
    source = (update or {}).get("source") or "google_jobs"
    apply_url = _apply_url(lead, update)
    read_url = (update or {}).get("source_url") or apply_url
    return {
        "title": lead["title"],
        "company": lead["company"],
        "location": lead.get("location") or "",
        "remote": remote,
        "posted": lead.get("posted_text"),
        "schedule": lead.get("schedule_type"),
        "pay": ranking.comp_line(comp),
        "pay_status": comp_mod.comp_status(comp),
        "pay_quote": quote,
        "verified": update is not None,
        # Read on the employer's ATS or its own site, not a board that copies postings.
        "at_employer": update is not None and (source in SOURCE_LABELS and source != "web"
                                               or employer_host(read_url, lead["company"])),
        "read_on": _read_on(source, read_url) if update is not None else None,
        "source": source,
        "via": via,
        "apply_url": apply_url,
    }


def _read_on(source: str, url: str | None) -> str:
    from app.matcha.services.matcha_work.job_search import normalize

    if source in SOURCE_LABELS and source != "web":
        return SOURCE_LABELS[source]
    host = normalize.host_of(url or "")
    return host[4:] if host.startswith("www.") else host or "the web"


def model_line(short_id: str, row: dict) -> str:
    parts = [short_id, row["title"], row["company"]]
    where = row["location"] or ("Remote" if row["remote"] else "")
    if where:
        parts.append(where + (" (remote)" if row["remote"] and "remote" not in where.lower() else ""))
    parts.append(row["pay"] + (f' ("{row["pay_quote"]}")' if row["pay_quote"] else ""))
    if row["posted"]:
        parts.append(f"posted {row['posted']}")
    if row["at_employer"]:
        parts.append(f"live at the employer ({row['read_on']})")
    elif row["verified"]:
        parts.append(f"live on {row['read_on']}, a job board, not the employer's own site")
    else:
        parts.append("listed on Google Jobs only, not read at the employer")
    parts.append(row["apply_url"] or "no link")
    return " | ".join(parts)


async def _read_some(leads: list[dict], seconds: float = VERIFY_SECONDS) -> list[dict | None]:
    """Each lead's employer posting, a few at a time, inside `seconds`; a read
    still going then counts as not read, and is stopped (so is every read,
    when the tool itself is called off)."""
    gate = asyncio.Semaphore(VERIFY_AT_ONCE)

    async def one(lead: dict) -> dict | None:
        async with gate:
            try:
                return await _verify(lead)
            except Exception:
                logger.info("find_jobs could not read a posting", exc_info=True)
                return None

    if not leads or seconds <= 0:
        return [None] * len(leads)
    tasks = [asyncio.ensure_future(one(lead)) for lead in leads]
    try:
        done, _pending = await asyncio.wait(tasks, timeout=seconds)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
    return [task.result() if task in done and not task.cancelled() else None for task in tasks]


async def _find(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
    from app.matcha.services.matcha_work.job_search import normalize, phases

    started = time.monotonic()
    session = session_of(state)
    title = " ".join(str(args.get("title") or "").split())[:120]
    if not title:
        return ToolOutput(payload={"error": "Say which role to look for, e.g. senior product designer."},
                          status="error")
    if session.paid >= MAX_PAID:
        return ToolOutput(payload={"error": "Job listing budget used up; finish with what you have."},
                          label="Job listing budget exhausted")
    location = " ".join(str(args.get("location") or "").split())[:120]
    remote_only = bool(args.get("remote_only")) or location.lower() in ("remote", "remote us", "us remote")
    criteria = {"titles": [title], "locations": [location] if location else [],
                "remote": "remote_only" if remote_only else None}
    provider = _provider()
    if provider is None:
        return ToolOutput(payload={"error": "Job listings aren't set up on this server. Use web_search instead."},
                          status="error")
    try:
        pages = int(args.get("pages") or 1)
    except (TypeError, ValueError):
        pages = 1
    queries = phases.plan_from_criteria(title, criteria)["queries"][:1]
    await ctx.progress.note(f"Looking for {title[:50]} jobs{' in ' + location[:40] if location else ''}…")
    postings = []
    try:
        for query in queries:
            token = None
            for _page in range(max(1, min(MAX_PAGES, pages))):
                if session.paid >= MAX_PAID:
                    break
                session.paid += 1  # counted before the call: a page that left may be billed
                found, token = await provider.search(query["q"], query["location"], page_token=token)
                postings.extend(found)
                if not token:
                    break
    except ProviderError as exc:
        logger.info("find_jobs listings failed: %s", exc)
        if not postings:
            return ToolOutput(payload={"error": "Job listings are unavailable right now. Try web_search instead."},
                              status="error", audit={"title": title, "location": location, "error": str(exc)[:200]})
    kept, outside, repeats = [], 0, 0
    for posting in postings:
        if not phases.keep_posting(posting, criteria):
            outside += 1
            continue
        key = normalize.dedupe_key(posting.company, posting.title, posting.location)
        if key in session.keys or any(normalize.same_posting(posting.title, posting.company, k.title, k.company)
                                      for k in kept):
            repeats += 1
            continue
        kept.append(posting)
    # In the run, unread, before anything is read: a read cut short loses its
    # check, not the job, and nothing else can count the same job as new.
    new: list[tuple[str, dict]] = []
    leads: list[tuple[str, Any, dict]] = []
    for posting in kept:
        lead = phases.lead_record(posting)
        short_id = f"J{len(session.jobs) + 1}"
        session.keys[lead["dedupe_key"]] = short_id
        session.jobs[short_id] = job_row(lead, None, posting.via)
        leads.append((short_id, posting, lead))
    if leads:
        await ctx.progress.note(f"Checking {min(len(leads), VERIFY)} postings at the employer…")
    # Inside the tool's own deadline (the runner's, or the run's time left).
    seconds = min(VERIFY_SECONDS, min(TOOL_SECONDS, left) - (time.monotonic() - started) - VERIFY_MARGIN)
    updates = await _read_some([lead for _, _, lead in leads[:VERIFY]], seconds)
    provenance: set[str] = set()
    for n, (short_id, posting, lead) in enumerate(leads):
        row = job_row(lead, updates[n] if n < len(updates) else None, posting.via)
        provenance.update(u for u in (row["apply_url"], lead.get("source_url"),
                                      *((l or {}).get("url") for l in lead.get("apply_links") or [])) if u)
        session.jobs[short_id] = row
        new.append((short_id, row))
    payload: dict[str, Any] = {
        "title": title,
        "location": location or "anywhere",
        "new_jobs": len(new),
        "live_at_employer": sum(1 for _, r in new if r["at_employer"]),
        "live_on_a_board": sum(1 for _, r in new if r["verified"] and not r["at_employer"]),
        "left_out_elsewhere": outside,
        "already_found": repeats,
        "jobs": [model_line(i, r) for i, r in new],
    }
    if not new:
        payload["note"] = ("No open postings matched there. Try a broader title, a nearby city, or remote."
                           if not postings else "Every posting found was outside the place asked for.")
    return ToolOutput(
        payload=payload,
        provenance=frozenset(provenance),
        label=f"Found {len(new)} {title[:60]} jobs{' in ' + location[:40] if location else ''}",
        audit={"title": title, "location": location, "listed": len(postings), "kept": len(new),
               "at_employer": payload["live_at_employer"], "on_a_board": payload["live_on_a_board"]},
    )


FIND_JOBS = AgentTool(
    name="find_jobs",
    effect="read",
    description=(
        "Find open job postings: Google Jobs listings for a role in a place, kept only within about 50 miles "
        "of it (or remote when allowed), then the top ones read from the employer's own posting to check they "
        "are still up and to read the pay. Each comes back with an id (J1, J2…), the pay exactly as posted "
        "('Pay not posted' when it isn't), whether it was read at the employer, and where to apply."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The role, as a job title: 'senior product designer'"},
            "location": {"type": "string",
                         "description": "A city and state, a state, 'Remote' or 'United States'. Leave out for anywhere"},
            "remote_only": {"type": "boolean", "description": "Only remote jobs"},
            "pages": {"type": "integer", "minimum": 1, "maximum": MAX_PAGES,
                      "description": "Pages of Google Jobs results (about 10 each)"},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
    step_kind="search",
    handler=_find,
    max_calls=MAX_CALLS,
    timeout_seconds=TOOL_SECONDS,
    min_seconds_left=20.0,
    describe=lambda args: f"Looked for {' '.join(str(args.get('title') or '').split())[:80]} jobs",
    exhausted_label="Job listing budget exhausted",
    exhausted_message="Job listing budget used up; finish with what you have.",
    timeout_message="The job listings took too long.",
    untrusted_output=True,
)

_PROMPT = """Finding jobs (find_jobs):
- When they ask for open roles ("find me product designer jobs in LA"), use find_jobs, not web_search: \
LinkedIn, Indeed and Glassdoor pages can't be read, and job boards stay indexed long after a job closes.
- One call per title and place; search two or three related titles or places in the same turn when the ask \
is broad (they run at the same time). A job found twice is kept once.
- Lead with the jobs live at the employer (read on its ATS or its own site). Say which were only found on a \
job board or only listed on Google Jobs. Pay is only what the posting states, with its quote: say "pay not \
posted" when it isn't, never estimate one, and when the quote gives several cities' ranges, say whose is whose.
- Show them with a `job_postings` block (empty job_ids: every job found, live-at-employer first).
- For a full search (more sources, fit against their résumé, drafted outreach and cover letters), start a \
job search with start_task (playbook job_search) when you have it; otherwise tell them Job search does that."""

JOB_POSTINGS_BLOCK: dict[str, Any] = {
    "type": "object",
    "description": "Open job postings find_jobs found, with pay as posted and where to apply.",
    "properties": {
        "job_ids": {
            "type": "array", "items": {"type": "string"},
            "description": "Ids find_jobs returned, in the order to show. Empty: every job found.",
        },
    },
}


def _view(short_id: str, row: dict) -> dict:
    keep = ("title", "company", "location", "remote", "posted", "pay", "pay_status", "verified", "at_employer",
            "read_on", "source", "via", "apply_url")
    return {"id": short_id, **{k: row.get(k) for k in keep if row.get(k) not in (None, "")}}


def _block(session: JobListingsSession, ids: list[str] | None) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    if ids:
        chosen = []
        for raw in ids:
            short_id = str(raw or "").strip().upper()
            if short_id in session.jobs and short_id not in chosen:
                chosen.append(short_id)
            elif short_id not in session.jobs:
                warnings.append("Dropped a job this run did not find")
    else:
        # Live at the employer first, then live on a board, then Google's order.
        chosen = sorted(session.jobs, key=lambda i: (not session.jobs[i]["at_employer"],
                                                      not session.jobs[i]["verified"]))
    if len(chosen) > MAX_BLOCK:
        warnings.append(f"Kept the first {MAX_BLOCK} jobs")
        chosen = chosen[:MAX_BLOCK]
    if not chosen:
        return None, warnings or ["Dropped an empty job_postings block"]
    return {"type": "job_postings", "jobs": [_view(i, session.jobs[i]) for i in chosen],
            "found": len(session.jobs)}, warnings


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    session = state.sessions.get(KEY)
    if session is None or not session.jobs:
        return None, ["Dropped a job_postings block: find_jobs found nothing in this run"]
    if not isinstance(raw, dict):
        return None, ["Dropped a job_postings block: not an object"]
    ids = raw.get("job_ids") if isinstance(raw.get("job_ids"), list) else None
    return _block(session, ids)


def auto_blocks(state: RunState) -> list[dict]:
    session = state.sessions.get(KEY)
    if session is None or len(session.jobs) < AUTO_BLOCK_AT:
        return []
    block, _ = _block(session, None)
    return [block] if block else []


def build() -> Ability:
    return Ability(
        key=KEY,
        label="Job listings",
        tools=(FIND_JOBS,),
        prompt_block=lambda _ctx: _PROMPT,
        env_ready=_ready,
        session_factory=lambda _ctx: JobListingsSession(),
        block_schemas={"job_postings": JOB_POSTINGS_BLOCK},
        gate=gate_block,
        auto_blocks=auto_blocks,
    )
