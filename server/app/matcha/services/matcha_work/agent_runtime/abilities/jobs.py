"""The person's job searches, in the Espresso assistant.

Read the searches (`job_search/`), talk through the ranked jobs and their
drafted approaches, and keep the person's own notes and status on a job
("saved", "applied", "dismissed"). A search itself is started as a task (the
`tasks` ability's `start_task`, playbook `job_search`) or from Tasks in the
app; nothing here sends, applies or submits.

The `jobs` block is rebuilt from the jobs this run read, by id: pay shown in
chat is always the posting's own, never the model's restatement of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.matcha.models.matcha_work.job_search import JobWeights, LeadPatch
from app.matcha.services.matcha_work.job_search import ranking
from app.matcha.services.matcha_work.job_search import service as store

from .. import consent
from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput

KEY = "jobs"
PAGE = 25
MAX_BLOCK_JOBS = 8
DESCRIPTION_CHARS = 4_000


@dataclass
class JobsSession:
    searches: set[str] = field(default_factory=set)
    leads: dict[str, dict] = field(default_factory=dict)  # lead id -> its summary


def session_of(state: RunState) -> JobsSession:
    return state.sessions[KEY]


def _uuid(value: Any) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("Use an id from a search you listed or read.") from exc


def _compact_search(search: dict) -> dict:
    keep = ("id", "title", "status", "lead_count", "posted_pay_count", "created_at", "error")
    return {k: search.get(k) for k in keep}


def _compact_lead(lead: dict) -> dict:
    keep = ("id", "rank", "title", "company", "location", "remote", "comp_line", "comp_status",
            "fit_score", "screen_status", "user_state", "approach_status", "apply_url", "flags")
    return {k: lead.get(k) for k in keep}


def _shown(leads: list[dict], weaker: bool) -> list[dict]:
    """The search's matches; jobs below its fit floor only when asked for."""
    if weaker:
        return leads
    return [lead for lead in leads if lead.get("rank_band") != ranking.BELOW_FLOOR_BAND]


def _remember(session: JobsSession, search_id: str, leads: list[dict]) -> None:
    session.searches.add(search_id)
    for lead in leads:
        session.leads[lead["id"]] = {**lead, "search_id": search_id}


async def _list(ctx: RunContext, state: RunState, _args: dict) -> dict:
    searches = await store.list_searches(ctx.user_id, ctx.company_id)
    session_of(state).searches.update(s["id"] for s in searches)
    return {"searches": [_compact_search(s) for s in searches]}


async def _read(ctx: RunContext, state: RunState, args: dict) -> dict:
    search_id = _uuid(args.get("search_id"))
    view = await store.get_search(search_id, ctx.user_id)
    offset = max(0, int(args.get("offset") or 0))
    shown = _shown(view["leads"], bool(args.get("include_weaker")))
    leads = shown[offset: offset + PAGE]
    _remember(session_of(state), view["id"], leads)
    return {
        "search": {**_compact_search(view), "ask": view["ask"], "weights": view["weights"],
                   "progress": view["progress"], "fit_floor": view.get("fit_floor")},
        "jobs": [_compact_lead(lead) for lead in leads],
        "weaker_matches": len(view["leads"]) - len(_shown(view["leads"], False)),
        "next_offset": offset + len(leads) if offset + len(leads) < len(shown) else None,
    }


async def _read_lead(ctx: RunContext, state: RunState, args: dict) -> dict:
    search_id, lead_id = _uuid(args.get("search_id")), _uuid(args.get("job_id"))
    lead = await store.get_lead(search_id, lead_id, ctx.user_id)
    _remember(session_of(state), str(search_id), [lead])
    lead = dict(lead)
    lead["description"] = lead["description"][:DESCRIPTION_CHARS]
    lead.pop("rank_explain", None)
    return {"job": lead}


async def _update(ctx: RunContext, state: RunState, args: dict) -> dict:
    lead_id = str(args.get("job_id") or "")
    known = session_of(state).leads.get(lead_id)
    if known is None:
        raise ValueError("Read this job before changing it.")
    patch = LeadPatch(user_state=args.get("status"), notes=args.get("notes"))
    lead = await store.patch_lead(UUID(known["search_id"]), UUID(lead_id), ctx.user_id, patch)
    _remember(session_of(state), known["search_id"], [lead])
    return {"job": _compact_lead(lead), "saved": True}


async def _rank(ctx: RunContext, state: RunState, args: dict) -> dict:
    search_id = str(args.get("search_id") or "")
    if search_id not in session_of(state).searches:
        raise ValueError("Read this search before re-ranking it.")
    weights = JobWeights(**{k: args[k] for k in ("base", "bonus", "equity", "fit") if k in args})
    view = await store.update_weights(UUID(search_id), ctx.user_id, weights)
    leads = _shown(view["leads"], False)[:PAGE]
    _remember(session_of(state), view["id"], leads)
    return {"weights": view["weights"], "jobs": [_compact_lead(lead) for lead in leads]}


def _tool(name: str, effect: str, description: str, parameters: dict, fn, *, untrusted: bool = False) -> AgentTool:
    async def handler(ctx: RunContext, state: RunState, args: dict, _left: float) -> ToolOutput:
        try:
            payload = await fn(ctx, state, args)
        except store.JobSearchError as exc:
            return ToolOutput(payload={"error": str(exc)}, status="error")
        except (ValueError, ValidationError) as exc:
            return ToolOutput(payload={"error": str(exc)[:300]}, status="error")
        return ToolOutput(payload=payload, audit={"tool": name, "search_id": args.get("search_id"),
                                                  "job_id": args.get("job_id")})

    return AgentTool(
        name=name, effect=effect, description=description,
        parameters={"type": "object", "properties": parameters.get("properties", {}),
                    "required": parameters.get("required", []), "additionalProperties": False},
        step_kind="draft" if effect == "draft" else "read",
        handler=handler, max_calls=20, untrusted_output=untrusted,
        describe=lambda args, _n=name: _n.replace("_", " ").capitalize(),
    )


_ID = {"type": "string"}
_WEIGHT = {"type": "number", "minimum": 0, "maximum": 1}

_PROMPT = """Job searches:
- The person's job searches are saved in Espresso (Tasks on the Mac, Job search on the web). Start a new one \
with start_task (playbook job_search) if you have it; otherwise they start it from Job search on the web or \
Tasks on the Mac. For a quick look at open roles right now, use find_jobs when you have it. \
list_job_searches, then read_job_search for the ranked jobs and read_job_lead for one job's posting, \
pay evidence and drafted approach (outreach, answers, cover letter).
- A search lists its strong matches (fit 4/5 or better) first; weaker_matches counts the jobs below \
its fit floor, which read_job_search shows with include_weaker. In the app, "Show more at 3/5" reads \
and ranks them.
- Pay is only what the posting states, with the text it came from; "Pay not posted" means unknown, \
never zero. Never estimate a salary as if it were posted.
- update_job_lead keeps the person's status (saved, applied, dismissed) and notes on a job you read. \
rank_job_search re-ranks with new weights for base, bonus, equity and fit.
- Nothing here sends, applies or submits. To show jobs, add a `jobs` block with the search_id and up \
to 8 job ids you read."""

JOBS_BLOCK = {
    "type": "object",
    "description": "Jobs from one search you read, by id (up to 8).",
    "properties": {
        "search_id": {"type": "string"},
        "job_ids": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_BLOCK_JOBS},
    },
    "required": ["search_id", "job_ids"],
}


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    session = state.sessions.get(KEY)
    if session is None or not isinstance(raw, dict):
        return None, ["Dropped a jobs block: no job search was read"]
    search_id = str(raw.get("search_id") or "")
    jobs, warnings = [], []
    for job_id in raw.get("job_ids") or []:
        lead = session.leads.get(str(job_id))
        if lead is None or lead.get("search_id") != search_id:
            warnings.append("Dropped a job this run did not read")
            continue
        jobs.append({
            "id": lead["id"], "rank": lead.get("rank"), "title": lead.get("title"),
            "company": lead.get("company"), "location": lead.get("location"),
            "comp_line": lead.get("comp_line"), "comp_status": lead.get("comp_status"),
            "fit_score": lead.get("fit_score"), "user_state": lead.get("user_state"),
            "approach_status": lead.get("approach_status"), "apply_url": lead.get("apply_url"),
        })
        if len(jobs) >= MAX_BLOCK_JOBS:
            break
    if not jobs:
        return None, warnings or ["Dropped an empty jobs block"]
    return {"type": "jobs", "search_id": search_id, "jobs": jobs}, warnings


def build() -> Ability:
    return Ability(
        key=KEY,
        label="Job search",
        tools=(
            _tool("list_job_searches", "read", "List the person's saved job searches.", {}, _list),
            _tool("read_job_search", "read",
                  "Read one search: its ask, weights and ranked jobs (25 at a time; follow next_offset). "
                  "Jobs below the search's fit floor are left out unless include_weaker is true.",
                  {"properties": {"search_id": _ID, "offset": {"type": "integer", "minimum": 0},
                                  "include_weaker": {"type": "boolean"}},
                   "required": ["search_id"]}, _read, untrusted=True),
            _tool("read_job_lead", "read",
                  "Read one job: the posting, pay with the text it came from, application questions "
                  "and the drafted approach.",
                  {"properties": {"search_id": _ID, "job_id": _ID}, "required": ["search_id", "job_id"]},
                  _read_lead, untrusted=True),
            _tool("update_job_lead", "draft",
                  "Save the person's status or notes on a job you read. Never applies or sends.",
                  {"properties": {"job_id": _ID,
                                  "status": {"type": ["string", "null"],
                                             "enum": ["new", "saved", "applied", "dismissed", None]},
                                  "notes": {"type": ["string", "null"]}},
                   "required": ["job_id", "status", "notes"]}, _update),
            _tool("rank_job_search", "draft",
                  "Re-rank a search you read with new weights (0-1) for base, bonus, equity and fit.",
                  {"properties": {"search_id": _ID, "base": _WEIGHT, "bonus": _WEIGHT, "equity": _WEIGHT,
                                  "fit": _WEIGHT},
                   "required": ["search_id", "base", "bonus", "equity", "fit"]}, _rank),
        ),
        prompt_block=lambda _ctx: _PROMPT,
        private_only=True,
        consent_version=consent.current_version(KEY),
        session_factory=lambda _ctx: JobsSession(),
        block_schemas={"jobs": JOBS_BLOCK},
        gate=gate_block,
    )
