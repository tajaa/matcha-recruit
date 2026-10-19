"""Open roles, right in chat: `find_jobs`, and the `job_postings` list.

"Find me senior product designer jobs in LA" used to be answered with
web_search alone: LinkedIn and Indeed pages the page loader can't read, board
links Brave still indexes months after the job closed (10 of 45 were still up
in a 2026-10-17 prod run), and pay restated from a snippet.

`find_jobs` runs the parts of a job search (`job_search/`) that need no model,
inside one tool call, on Brave alone:

1. Code's Brave searches of employers' job boards for the title, in the place
   named and anywhere (`boards.board_searches`): every Greenhouse, Lever or
   Ashby job link in the answers (`ats.detect`).
2. Each link read from its board's public API (`discovery.read_posting`), a
   few at a time, within the time the call has left. A job no longer posted
   is dropped, so Brave's stale index can't add one, and the title, place and
   pay are the posting's own.
3. Kept only with a related title (`normalize.related_title`), where the
   person wants the job (`phases.keep_job` → `places.fits`: within 50 miles of
   the place named, or remote when they'd take it), once each in the run.

So every job it shows is `verified` and `at_employer`: read on the employer's
own board. It started from Google Jobs (SearchAPI, else SerpApi) until
2026-10-18; Espresso's job search runs on Brave and Claude only.

Pay is `ranking.comp_line` over evidence (`comp.py`), never the model's. The
block is rebuilt from what the run found, by id. Only the title and place
leave the server: never the résumé, so nothing needs switching on. A full
search (the web too, fit against the résumé, drafted outreach) is still a job
search task.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.matcha.services.matcha_work import brave_search

from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput

logger = logging.getLogger(__name__)

KEY = "job_listings"
# Brave searches a call makes (one title on each board, in the place and
# anywhere: 8 at most), and a run's in all.
SEARCHES = 8
MAX_SEARCHES = 24
MAX_CALLS = 4
# Searching stops past this; Brave answers one a second on the free plan.
SEARCH_SECONDS = 25.0
# Board links read per call, how many at once, the fetches one may use (a
# Workable posting is two) and how long the reading may take in all. About 1
# in 5 of Brave's board links is still posted, so a call reads plenty.
READS = 80
READ_AT_ONCE = 8
READ_FETCHES = 2
READ_SECONDS = 40.0
TOOL_SECONDS = 80.0
# Kept back from the tool's own deadline so the answer is written before it.
READ_MARGIN = 5.0
# Rows in the `job_postings` block (and its CSV): all a run can find.
MAX_BLOCK = 120
AUTO_BLOCK_AT = 3
SOURCE_LABELS = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "workable": "Workable"}


@dataclass
class JobListingsSession:
    jobs: dict[str, dict] = field(default_factory=dict)  # short id -> job row, in found order
    keys: dict[str, str] = field(default_factory=dict)  # dedupe key -> short id
    read: set[tuple] = field(default_factory=set)  # board postings already read in the run
    searches: int = 0


def session_of(state: RunState) -> JobListingsSession:
    return state.sessions[KEY]


def _ready() -> bool:
    """Brave can answer. Tests patch this seam."""
    try:
        return brave_search.available()
    except Exception:  # settings not loaded (a bare script): not offered
        return False


async def _web_search(query: str, count: int) -> list[dict]:
    """One Brave search. Tests patch this seam."""
    return await brave_search.search(query, count=count)


async def _read(url: str) -> dict | None:
    """One board posting read from its board's API (`discovery.read_posting`):
    its lead record, or None when it is gone or unreadable. Tests patch this seam."""
    from app.matcha.services.matcha_work.agent_runtime.chain import Budget
    from app.matcha.services.matcha_work.job_search import discovery, phases

    posting = {"url": url, "title": "", "company": "", "location": ""}
    return await discovery.read_posting(posting, phases.Deps(), Budget(left=READ_FETCHES).take,
                                        today=datetime.now(timezone.utc).date())


def job_row(record: dict) -> dict:
    """One posting read on its board, as the run keeps it."""
    from app.matcha.services.matcha_work.job_search import comp as comp_mod
    from app.matcha.services.matcha_work.job_search import normalize, ranking

    comp = record.get("comp") or {}
    base = comp.get("base") if isinstance(comp.get("base"), dict) else {}
    quote = ((base.get("evidence") or {}).get("quote") or "")[:200] if base.get("status") == "posted" else ""
    source = record.get("source") or "web"
    url = normalize.http_url(record.get("source_url"))
    host = normalize.host_of(url or "")
    return {
        "title": record["title"],
        "company": record["company"],
        "location": record.get("location") or "",
        "remote": record.get("remote"),
        "pay": ranking.comp_line(comp),
        "pay_status": comp_mod.comp_status(comp),
        "pay_quote": quote,
        "verified": True,
        "at_employer": source in SOURCE_LABELS,
        "read_on": SOURCE_LABELS.get(source) or (host[4:] if host.startswith("www.") else host) or "the web",
        "source": source,
        "apply_url": url,
    }


def model_line(short_id: str, row: dict) -> str:
    parts = [short_id, row["title"], row["company"]]
    where = row["location"] or ("Remote" if row["remote"] else "")
    if where:
        parts.append(where + (" (remote)" if row["remote"] and "remote" not in where.lower() else ""))
    parts.append(row["pay"] + (f' ("{row["pay_quote"]}")' if row["pay_quote"] else ""))
    parts.append(f"live at the employer ({row['read_on']})" if row["at_employer"] else f"live on {row['read_on']}")
    parts.append(row["apply_url"] or "no link")
    return " | ".join(parts)


# Jobs the model always sees, however long the lines.
MIN_ROWS = 10


def fit_lines(lines: list[str], budget: int, min_rows: int = MIN_ROWS) -> tuple[list[str], int]:
    """As many lines as fit `budget` characters (never fewer than `min_rows`),
    and how many were left out; the block keeps every one."""
    kept, used = [], 0
    for line in lines:
        if len(kept) >= min_rows and used + len(line) + 4 > budget:
            break
        kept.append(line)
        used += len(line) + 4
    return kept, len(lines) - len(kept)


_LATE = object()  # a read still going at the deadline


async def _read_some(urls: list[str], seconds: float) -> list[Any]:
    """Each board posting, a few at a time, inside `seconds`: its record,
    None when it is gone, or `_LATE` when the read was still going then (it
    is stopped, and so is every read when the tool itself is called off)."""
    gate = asyncio.Semaphore(READ_AT_ONCE)

    async def one(url: str) -> dict | None:
        async with gate:
            try:
                return await _read(url)
            except Exception:
                logger.info("find_jobs could not read a posting", exc_info=True)
                return None

    if not urls or seconds <= 0:
        return [_LATE] * len(urls)
    tasks = [asyncio.ensure_future(one(url)) for url in urls]
    try:
        done, _pending = await asyncio.wait(tasks, timeout=seconds)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
    return [task.result() if task in done and not task.cancelled() else _LATE for task in tasks]


def _empty_note(links: int, known: int, posted: int, late: int, other: int, outside: int, repeats: int) -> str:
    if not links and known:
        return "Every posting found was already found in this run."
    if not links:
        return ("No Greenhouse, Lever or Ashby postings turned up for that. Try a broader title, a nearby "
                "city or remote; web_search can look at employers' own careers pages.")
    if not posted:
        if late:
            return "The postings found couldn't be read in time. Try again."
        return "None of the job-board postings found is still posted (Brave's index runs months behind)."
    why = [w for n, w in ((other, "another kind of role"), (outside, "outside the place asked for"),
                          (repeats, "already found in this run")) if n]
    return "Every posting still up was " + " or ".join(why) + "." if why else "Nothing new turned up."


async def _find(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
    from app.matcha.services.matcha_work.job_search import ats, boards, normalize, phases

    started = time.monotonic()
    session = session_of(state)
    title = " ".join(str(args.get("title") or "").split())[:120]
    if not title:
        return ToolOutput(payload={"error": "Say which role to look for, e.g. senior product designer."},
                          status="error")
    if session.searches >= MAX_SEARCHES:
        return ToolOutput(payload={"error": "Job search budget used up; finish with what you have."},
                          label="Job search budget exhausted")
    location = " ".join(str(args.get("location") or "").split())[:120]
    remote_only = bool(args.get("remote_only")) or location.lower() in ("remote", "remote us", "us remote")
    criteria = {"titles": [title], "locations": [location] if location else [],
                "remote": "remote_only" if remote_only else None}
    searches = boards.board_searches([title], criteria)[:min(SEARCHES, MAX_SEARCHES - session.searches)]
    where = f" in {location[:40]}" if location else ""
    await ctx.progress.note(f"Searching employers' job boards for {title[:50]} jobs{where}…")
    links: list[tuple[tuple, str]] = []
    seen: set[tuple] = set()
    answered = known = 0
    for i, query in enumerate(searches):
        if i and time.monotonic() - started > SEARCH_SECONDS:
            break
        session.searches += 1  # counted before the call: one that left may be billed
        try:
            results = await _web_search(query, boards.RESULTS)
        except brave_search.Unavailable as exc:
            if exc.out:
                break
            continue
        answered += 1
        for result in results:
            ref = ats.detect(result.get("url"))
            if ref is None:
                continue
            key = (ref.provider, ref.board.lower(), ref.job_id.lower())
            if key in seen:
                continue
            seen.add(key)
            if key in session.read:
                known += 1
            else:
                links.append((key, result["url"]))
    if not answered:
        return ToolOutput(payload={"error": "Brave search isn't answering right now, so the job boards "
                                            "couldn't be searched. Try again later."},
                          status="error", audit={"title": title, "location": location, "searches": len(searches)})
    todo = links[:READS]
    if todo:
        await ctx.progress.note(f"Reading {len(todo)} postings on employers' job boards…")
    # Inside the tool's own deadline (the runner's, or the run's time left).
    seconds = min(READ_SECONDS, min(TOOL_SECONDS, left) - (time.monotonic() - started) - READ_MARGIN)
    records = await _read_some([url for _, url in todo], seconds)
    new: list[tuple[str, dict]] = []
    counts = {"gone": 0, "late": 0, "other": 0, "outside": 0, "repeats": 0}
    for (key, _url), record in zip(todo, records):
        if record is _LATE:
            counts["late"] += 1  # not marked read: a later call may try it again
            continue
        session.read.add(key)
        if record is None:
            counts["gone"] += 1
        elif not normalize.related_title(record["title"], [title]):
            counts["other"] += 1
        elif not phases.keep_job(record["company"], record["remote"], criteria, record["location"]):
            counts["outside"] += 1
        elif record["dedupe_key"] in session.keys or any(
                normalize.same_posting(record["title"], record["company"], row["title"], row["company"])
                for row in session.jobs.values()):
            counts["repeats"] += 1
        else:
            short_id = f"J{len(session.jobs) + 1}"
            row = job_row(record)
            session.keys[record["dedupe_key"]] = short_id
            session.jobs[short_id] = row
            new.append((short_id, row))
    posted = len(todo) - counts["gone"] - counts["late"]
    # A long list can outgrow the output budget: the model gets what fits, the
    # block has every one.
    lines, hidden = fit_lines([model_line(i, r) for i, r in new], max(2000, ctx.limits.max_tool_output_chars - 1200))
    payload: dict[str, Any] = {
        "title": title,
        "location": location or "anywhere",
        "new_jobs": len(new),
        "board_postings_found": len(links),
        "still_posted": posted,
        "no_longer_posted": counts["gone"],
        "other_roles": counts["other"],
        "left_out_elsewhere": counts["outside"],
        "already_found": counts["repeats"] + known,
        "jobs": lines,
    }
    if counts["late"]:
        payload["not_read_in_time"] = counts["late"]
    if len(links) > len(todo):
        payload["not_read"] = (f"{len(links) - len(todo)} more board postings weren't read; another call "
                               "for the same role reads them (it skips what this run read).")
    if hidden:
        payload["not_shown_here"] = (f"{hidden} more were found and kept; the job_postings block shows them "
                                     "(leave job_ids empty to show everything).")
    if not new:
        payload["note"] = _empty_note(len(links), known, posted, counts["late"], counts["other"],
                                      counts["outside"], counts["repeats"])
    return ToolOutput(
        payload=payload,
        provenance=frozenset(row["apply_url"] for _, row in new if row["apply_url"]),
        label=f"Found {len(new)} {title[:60]} jobs{where}",
        audit={"title": title, "location": location, "searches": answered, "links": len(links),
               "read": len(todo) - counts["late"], "posted": posted, "kept": len(new)},
    )


FIND_JOBS = AgentTool(
    name="find_jobs",
    effect="read",
    description=(
        "Find open job postings on employers' own job boards (Greenhouse, Lever, Ashby): Brave searches for a "
        "role in a place, then every posting read from its board to check it is still up and to read the pay, "
        "kept only within about 50 miles of the place (or remote when allowed). Each comes back with an id "
        "(J1, J2…), the pay exactly as posted ('Pay not posted' when it isn't) and where to apply."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The role, as a job title: 'senior product designer'"},
            "location": {"type": "string",
                         "description": "A city and state, a state, 'Remote' or 'United States'. Leave out for anywhere"},
            "remote_only": {"type": "boolean", "description": "Only remote jobs"},
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
    exhausted_label="Job search budget exhausted",
    exhausted_message="Job search budget used up; finish with what you have.",
    timeout_message="The job search took too long.",
    untrusted_output=True,
)

_PROMPT = f"""Finding jobs (find_jobs):
- When they ask for open roles ("find me product designer jobs in LA"), use find_jobs, not web_search: \
LinkedIn, Indeed and Glassdoor pages can't be read, and job boards stay indexed long after a job closes.
- find_jobs searches employers' own job boards (Greenhouse, Lever, Ashby) and reads every posting it returns \
from the board itself, so each is still posted. It doesn't see jobs posted only elsewhere: when it finds few, \
say so, and web_search can look at employers' careers pages.
- One call per title and place; search two or three related titles or places in the same turn when the ask \
is broad. A job found twice is kept once. A run has {MAX_SEARCHES} board searches, about {MAX_SEARCHES // SEARCHES} \
calls with a place.
- Pay is only what the posting states, with its quote: say "pay not posted" when it isn't, never estimate \
one, and when the quote gives several cities' ranges, say whose is whose.
- Show them with a `job_postings` block (empty job_ids: every job found).
- A full search (the web too, fit against their résumé, drafted outreach and cover letters, roles beyond \
their title) is a job_search task: see "Job searches" under Tasks for when to start one or ask. Without \
Tasks, tell them Job search does that."""

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
    keep = ("title", "company", "location", "remote", "pay", "pay_status", "verified", "at_employer",
            "read_on", "source", "apply_url")
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
        # Live at the employer first (every job find_jobs keeps is), then found order.
        chosen = sorted(session.jobs, key=lambda i: not session.jobs[i]["at_employer"])
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
