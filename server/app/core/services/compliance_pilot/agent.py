"""The Compliance Pilot's agent loop — a bounded Gemini tool-calling loop,
structurally copied from `matcha/services/huume/agent.py` (fixed bounds on
model calls and wall clock, force-finish with partial work on a bound hit, an
async generator of SSE-shaped frames). Reimplemented here rather than imported
because core/ must not import matcha/ (see `core.py`'s module docstring) —
Huume stays byte-untouched.

Narrower than Huume in three ways, all because this domain has no in-memory
thread-state blob to update:

- No images/attachments — this is an admin research tool, not a chat surface
  with file uploads.
- No `state_updates` dict. Every "staged" tool here (`stage_research`,
  `stage_check_sources`, `stage_approve`) INSERTs a real `compliance_pilot_actions`
  row with status='proposed' directly — the row IS the staged state, so there
  is nothing to merge back into a document at turn end.
- No plans. A Compliance Pilot session stages at most one action at a time
  (single-slot, `actions.supersede_targets`), never several keyed sub-plans.

Confirm-first is still structural, not prompt-enforced: `confirm_action` only
executes when `actions.evaluate_confirm` says `proceed`, which requires the
action to have been proposed BEFORE this turn's `pre_turn_proposed_ids`
snapshot was taken — staging and confirming in the same turn is impossible by
construction, matching Huume's `pre_turn_action`/`pre_turn_plans` idiom.

Citations here are DB-sourced (rows the catalog already holds), never
model-generated — so unlike Huume's pilot skills there is no
`legal_defense.validate_citations` gate on the way out. `search_catalog`'s
`citation_records` are popped off its result and accumulated verbatim.

Contract with the caller (the route's agent-mode chat handler): an async
generator of dicts, `{"type": "status"|"step"|"error"|"agent_result"}`.
Exactly one `agent_result` frame is emitted last, carrying `error` when the
turn ended badly — a mid-turn failure (including a Gemini rate limit hit after
tools have already run) degrades into that frame rather than raising, because
the route only persists the assistant message when a terminal frame arrives and
the stage_* tools have by then written real action rows that need explaining.

The ONE case that still raises is `RateLimitExceeded` before any tool ran:
nothing happened, so there is no turn to record, and the route renders its own
message instead of persisting an empty one. This is the loop's whole raising
surface — deliberately narrower than Huume's, which re-raises unconditionally
because its staged state lives in a thread document the caller writes anyway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from google.genai import types

from app.core.services.ai_usage import feature_scope
from app.core.services.genai_client import get_genai_client
from app.core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded
from app.database import get_connection

from app.core.services.compliance_pilot import actions as actions_mod
from app.core.services.compliance_pilot import confirm as confirm_mod
from app.core.services.compliance_pilot import core as core_mod
from app.core.services.compliance_pilot.prompt import build_state_block, build_system_prompt
from app.core.services.compliance_pilot.tools import TOOLS_BY_NAME, tool_declarations

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"
_MAX_MODEL_CALLS = 8
_WALL_CLOCK_SECONDS = 240.0
_CALL_TIMEOUT = 60.0
_MAX_HISTORY_MESSAGES = 20
_MAX_MESSAGE_CHARS = 6_000
_STEP_PAYLOAD_CAP_CHARS = 4_000
_TOOL_HEARTBEAT_SECONDS = 15.0
# Rows returned by list_actions are an OVERVIEW — action_status is the detail
# call. Keep only scalar fields so a session with several finished research
# runs (each carrying a staged_rows array) doesn't balloon the prompt.
_BACKLOG_ITEM_CAP = 40


class _StepRecorder:
    """Accumulates step dicts for the run's audit trail + the frames yielded to
    the caller. `seq` is 1-based and monotonic across the whole turn."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def record(
        self, *, tool: str, kind: str, label: str, status: str, detail: Optional[str] = None,
        args: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        step = {"seq": len(self.steps) + 1, "tool": tool, "kind": kind, "label": label, "status": status}
        if detail:
            step["detail"] = detail
        if args is not None:
            step["args"] = _cap_payload(args)
        self.steps.append(step)
        return step


def is_sole_finish(call_names: list[str]) -> bool:
    """True when `finish` is the ONLY call in a batch — the only case where it
    may end the turn. Batched alongside other tools it must be deferred: those
    tools still run, and their results have to reach the model before it
    summarizes, or the summary describes work whose outcome it never saw. Pure."""
    return len(call_names) == 1 and call_names[0] == "finish"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _cap_payload(value: Any) -> Any:
    """Bound a value before it's stored on a step's args/result — returns it
    unchanged when already small, else a truncated preview. Pure."""
    if value is None:
        return None
    safe = _json_safe(value)
    try:
        encoded = json.dumps(safe, default=str)
    except Exception:
        return {"_note": "unserializable"}
    if len(encoded) <= _STEP_PAYLOAD_CAP_CHARS:
        return safe
    return {"_truncated": True, "preview": encoded[:_STEP_PAYLOAD_CAP_CHARS]}


def _accumulate_usage(total: dict[str, int], usage: Any) -> None:
    for key, attr in (
        ("prompt_tokens", "prompt_token_count"),
        ("completion_tokens", "candidates_token_count"),
        ("total_tokens", "total_token_count"),
        ("thinking_tokens", "thoughts_token_count"),
        ("cached_tokens", "cached_content_token_count"),
    ):
        total[key] = total.get(key, 0) + (getattr(usage, attr, 0) or 0)


def _to_contents(history: list[dict[str, Any]]) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in history[-_MAX_HISTORY_MESSAGES:]:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = str(msg.get("content") or "").strip()
        if len(text) > _MAX_MESSAGE_CHARS:
            text = text[:_MAX_MESSAGE_CHARS] + "\n…[truncated]"
        if not text:
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    if not contents:
        contents.append(types.Content(role="user", parts=[types.Part(text="Hello.")]))
    return contents


def _compact_result(result: Any) -> Any:
    """Drop list/dict fields from an action's result — used for list_actions'
    overview, where nested detail (staged_rows, dead_rows, results) belongs to
    action_status instead. Scalars (counts, coordinates) survive."""
    if not isinstance(result, dict):
        return result
    return {k: v for k, v in result.items() if v is None or isinstance(v, (str, int, float, bool))}


def _action_overview(a: dict[str, Any]) -> dict[str, Any]:
    return _json_safe({
        "action_id": a.get("id"), "kind": a.get("kind"), "status": a.get("status"),
        "params": a.get("params"), "progress": a.get("progress"),
        "result": _compact_result(a.get("result")),
        "started_at": a.get("started_at"), "finished_at": a.get("finished_at"),
    })


async def _industry_coverage_map(conn, jurisdiction_ids: list, industry_tag: str) -> dict[str, str]:
    """Per-category ledger status for ONE industry's own categories — the
    industry-tagged analog of `vertical_coverage.general_coverage_map`, which
    hardcodes the general (industry_tag IS NULL) axis and can't answer this."""
    cats = [r["slug"] for r in await conn.fetch(
        "SELECT slug FROM compliance_categories WHERE industry_tag = $1", industry_tag)]
    result = {c: "unchecked" for c in cats}
    if not jurisdiction_ids or not cats:
        return result
    rows = await conn.fetch(
        "SELECT category, status FROM jurisdiction_vertical_coverage "
        "WHERE industry_tag = $1 AND jurisdiction_id = ANY($2::uuid[])",
        industry_tag, jurisdiction_ids,
    )
    rank = {"unchecked": 0, "empty": 1, "covered": 2}
    for r in rows:
        cat, st = r["category"], r["status"]
        if cat not in result:
            continue
        cand = st if st in rank else "unchecked"
        if rank.get(cand, 0) > rank.get(result[cat], 0):
            result[cat] = cand
    return result


def backlog_note(state: Optional[str], items: list[dict[str, Any]]) -> Optional[str]:
    """The corpus-boundary warning appended to `uncodified_backlog`. Pure, so the
    exact wording is pinned by a test rather than by whatever the tool handler
    happened to render.

    An empty backlog outside California is AMBIGUOUS: the scope registry only
    enumerates federal + CA authorities, so "no state-level items for TX" means
    the corpus doesn't reach Texas, not that Texas is covered. Returns None when
    the question doesn't arise (no state, CA, or state-level items present)."""
    if not state or state.upper() == "CA":
        return None
    if any(i.get("level") == "state" for i in items or ()):
        return None
    return (
        "The scope registry corpus is federal + California only today — zero "
        f"state-level items for {state} means the corpus doesn't reach there, "
        "NOT that this state is fully covered."
    )


def _backlog_item(item: dict[str, Any]) -> dict[str, Any]:
    return _json_safe({
        "regulation_key": item.get("regulation_key"), "category": item.get("category_slug"),
        "level": item.get("level"), "citation": item.get("citation"), "heading": item.get("heading"),
        "index_slug": item.get("index_slug"), "severity": item.get("severity"),
    })


async def run_pilot_turn(
    *,
    session_id: str,
    actor_id: Optional[UUID],
    history: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Run one agentic Compliance Pilot turn. `history` is the FULL turn
    history including the just-persisted latest user message as its last
    entry (same convention as `run_huume_turn` — the caller appends it before
    calling in).

    Yields `status`/`step`/`error` frames, then exactly one final
    `agent_result` frame:
        {"message": str, "steps": [...], "citations": [...],
         "proposal_action_ids": [...], "token_usage": {...},
         "model_calls": int, "error"?: str}
    """
    rate_limiter = GeminiRateLimiter()
    recorder = _StepRecorder()
    final_message: Optional[str] = None
    turn_error: Optional[str] = None
    model_calls = 0
    started = time.monotonic()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                   "thinking_tokens": 0, "cached_tokens": 0}
    turn_citations: dict[str, dict[str, Any]] = {}
    proposal_action_ids: list[str] = []

    def elapsed() -> float:
        return time.monotonic() - started

    async with get_connection() as conn:
        actions_snapshot = await core_mod.load_actions(conn, session_id)
    # Frozen at turn start — evaluate_confirm compares against THIS snapshot,
    # never against a proposal a tool call in this same turn just inserted.
    # This is what makes stage-then-confirm-same-turn structurally impossible.
    pre_turn_proposed_ids = {a["id"] for a in actions_snapshot if a.get("status") == "proposed"}

    def _collect_citations(result: dict[str, Any]) -> None:
        for rec in result.pop("citation_records", []) or []:
            if isinstance(rec, dict) and rec.get("cid"):
                turn_citations[rec["cid"]] = rec

    async def _insert_proposed(conn, kind: str, params: dict[str, Any]) -> str:
        row = await conn.fetchrow(
            "INSERT INTO compliance_pilot_actions (session_id, kind, params, status, actor_id) "
            "VALUES ($1, $2, $3::jsonb, 'proposed', $4) RETURNING id",
            session_id, kind, json.dumps(params), actor_id,
        )
        new_id = str(row["id"])
        siblings = await core_mod.load_actions(conn, session_id)
        stale = actions_mod.supersede_targets(siblings, exclude_id=new_id)
        if stale:
            await conn.execute(
                "UPDATE compliance_pilot_actions SET status='superseded', finished_at=NOW() "
                "WHERE id = ANY($1::uuid[])",
                [UUID(i) for i in stale],
            )
        return new_id

    async def call_tool(name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (function_response payload, step dict)."""
        try:
            if name == "coverage_snapshot":
                from app.core.services.scope_registry.jurisdiction_chain import resolve_jurisdiction_chain
                from app.core.services.compliance_service import _resolve_industry

                state = actions_mod.coerce_state(args.get("state"))
                if not state:
                    step = recorder.record(tool=name, kind="read", label="Coverage snapshot refused", status="rejected", detail="invalid state")
                    return {"error": "Need a valid 2-letter state code."}, step
                city = actions_mod.coerce_city(args.get("city"))
                industry_raw = args.get("industry")
                industry_tag = _resolve_industry(industry_raw) if industry_raw else None
                async with get_connection() as conn:
                    snap = await core_mod.build_scope_snapshot(conn, state, city, industry_tag)
                    result = {
                        "state": state, "city": city,
                        "state_found": snap["state_found"], "city_found": snap["city_found"],
                        "general_coverage": snap["general_coverage"],
                        "existing_active_rows": snap["existing_active_rows"],
                    }
                    if industry_raw and not industry_tag:
                        result["note"] = f"Couldn't resolve the industry '{industry_raw}'."
                    elif industry_tag:
                        chain = await resolve_jurisdiction_chain(conn, state, city)
                        ids = chain.get("ids") or []
                        result["industry_tag"] = industry_tag
                        result["industry_active_rows"] = snap["industry_active_rows"]
                        result["industry_coverage"] = await _industry_coverage_map(conn, ids, industry_tag)
                step = recorder.record(tool=name, kind="read", label=f"Checked coverage for {city or ''} {state}".strip(), status="ok")
                return _json_safe(result), step

            if name == "search_catalog":
                from app.core.services.scope_registry.jurisdiction_chain import resolve_jurisdiction_chain

                query = actions_mod.coerce_query(args.get("query"))
                if not query:
                    step = recorder.record(tool=name, kind="read", label="Search refused", status="rejected", detail="no query")
                    return {"error": "Need a search query."}, step
                state = actions_mod.coerce_state(args.get("state")) if args.get("state") else None
                city = actions_mod.coerce_city(args.get("city")) if args.get("city") else None
                async with get_connection() as conn:
                    jurisdiction_ids = None
                    if state:
                        chain = await resolve_jurisdiction_chain(conn, state, city)
                        jurisdiction_ids = chain.get("ids") or None
                    corpus = await core_mod.build_ask_corpus(conn, query, jurisdiction_ids=jurisdiction_ids)
                records = corpus.get("records") or []
                result = {"count": len(records), "results": records, "citation_records": list(records)}
                _collect_citations(result)
                step = recorder.record(tool=name, kind="read", label=f"Searched catalog for '{query}'", status="ok",
                                       detail=f"{len(records)} match(es)")
                return _json_safe(result), step

            if name == "uncodified_backlog":
                from app.core.services.scope_registry.codify import chain_uncodified

                state = actions_mod.coerce_state(args.get("state")) if args.get("state") else None
                city = actions_mod.coerce_city(args.get("city")) if args.get("city") else None
                async with get_connection() as conn:
                    backlog = await chain_uncodified(conn, state=state, city=city, labor_only=False)
                keyed, unkeyed = backlog.get("keyed") or [], backlog.get("unkeyed") or []
                result = {
                    "keyed_count": len(keyed), "unkeyed_count": len(unkeyed),
                    "keyed": [_backlog_item(i) for i in keyed[:_BACKLOG_ITEM_CAP]],
                    "unkeyed": [_backlog_item(i) for i in unkeyed[:_BACKLOG_ITEM_CAP]],
                }
                note = backlog_note(state, keyed + unkeyed)
                if note:
                    result["note"] = note
                step = recorder.record(
                    tool=name, kind="read", label=f"Checked research backlog for {city or ''} {state or 'federal'}".strip(),
                    status="ok", detail=f"{len(keyed)} keyed, {len(unkeyed)} unkeyed",
                )
                return _json_safe(result), step

            if name == "readiness":
                from app.core.services.compliance_evals import industry_keysets as iks
                from app.core.services.compliance_evals.runner import onboarding_readiness

                industry = str(args.get("industry") or "").strip()
                if not industry:
                    step = recorder.record(tool=name, kind="read", label="Readiness refused", status="rejected", detail="no industry")
                    return {"error": "Need an industry."}, step
                state = actions_mod.coerce_state(args.get("state")) if args.get("state") else None
                city = actions_mod.coerce_city(args.get("city")) if args.get("city") else None
                canonical = iks.resolve_industry(industry) or industry
                depth = "core" if iks.has_core(canonical) else "full"
                async with get_connection() as conn:
                    result = await onboarding_readiness(conn, industry=industry, state=state, city=city, depth=depth)
                step = recorder.record(
                    tool=name, kind="read", label=f"Checked {canonical} readiness for {city or ''} {state or ''}".strip(),
                    status="ok", detail=result.get("status"),
                )
                return _json_safe(result), step

            if name == "authority_status":
                async with get_connection() as conn:
                    rows = await conn.fetch(
                        "SELECT slug, name, level, jurisdiction_id, source_type, domain_categories, "
                        "domain_excludes, enumerable, item_count, unclassified_count, last_ingested_at "
                        "FROM authority_indexes ORDER BY level, slug"
                    )
                step = recorder.record(tool=name, kind="read", label="Checked authority index status", status="ok")
                return {"indexes": [_json_safe(dict(r)) for r in rows]}, step

            if name == "list_actions":
                async with get_connection() as conn:
                    current = await core_mod.load_actions(conn, session_id)
                step = recorder.record(tool=name, kind="read", label="Listed session actions", status="ok",
                                       detail=f"{len(current)} action(s)")
                return {"actions": [_action_overview(a) for a in current]}, step

            if name == "action_status":
                action_id = actions_mod.coerce_uuid(args.get("action_id"))
                if not action_id:
                    step = recorder.record(tool=name, kind="read", label="Action status refused", status="rejected", detail="invalid id")
                    return {"error": "That's not a valid action id — call list_actions for the real ids."}, step
                async with get_connection() as conn:
                    row = await core_mod.load_action(conn, UUID(action_id))
                if not row:
                    step = recorder.record(tool=name, kind="read", label="Action not found", status="rejected")
                    return {"error": "No action with that id in this session."}, step
                step = recorder.record(tool=name, kind="read", label=f"Checked action {row['kind']}", status="ok",
                                       detail=row.get("status"))
                return _json_safe(row), step

            if name == "stage_research":
                state = actions_mod.coerce_state(args.get("state"))
                if not state:
                    step = recorder.record(tool=name, kind="staged", label="Research proposal refused", status="rejected", detail="invalid state")
                    return {"status": "refused", "message": "Need a valid 2-letter state code."}, step
                proposal = {
                    "kind": "research", "state": state, "city": actions_mod.coerce_city(args.get("city")),
                    "industry": args.get("industry"), "categories": actions_mod.coerce_categories(args.get("categories")),
                    "rationale": actions_mod.coerce_text(args.get("rationale")),
                }
                async with get_connection() as conn:
                    resolved, errors = await core_mod.resolve_proposal(conn, proposal)
                    if not resolved:
                        msg = "; ".join(errors) or "Could not resolve that coordinate."
                        step = recorder.record(tool=name, kind="staged", label="Research proposal refused", status="rejected", detail=msg)
                        return {"status": "refused", "message": msg}, step
                    params = {
                        "state": resolved["state"], "city": resolved.get("city"),
                        "industry_tag": resolved["industry_tag"], "categories": resolved["categories"],
                        "rationale": resolved.get("rationale"),
                    }
                    new_id = await _insert_proposed(conn, "research", params)
                proposal_action_ids.append(new_id)
                result = {
                    "status": "staged", "action_id": new_id, "industry_tag": resolved["industry_tag"],
                    "state": resolved["state"], "city": resolved.get("city"),
                    "category_count": resolved["category_count"], "categories": resolved["category_labels"],
                    "coverage": resolved["coverage"], "existing_active_rows": resolved["existing_active_rows"],
                    "message": "Staged — waiting for the admin's confirmation.",
                }
                step = recorder.record(
                    tool=name, kind="staged",
                    label=f"Staged research: {resolved['industry_tag']} in {resolved.get('city') or resolved['state']}",
                    status="ok", detail=f"{resolved['category_count']} categor{'y' if resolved['category_count'] == 1 else 'ies'}",
                )
                return _json_safe(result), step

            if name == "stage_check_sources":
                state = actions_mod.coerce_state(args.get("state"))
                if not state:
                    step = recorder.record(tool=name, kind="staged", label="Source-check proposal refused", status="rejected", detail="invalid state")
                    return {"status": "refused", "message": "Need a valid 2-letter state code."}, step
                proposal = {
                    "kind": "check_sources", "state": state, "city": actions_mod.coerce_city(args.get("city")),
                    "rationale": actions_mod.coerce_text(args.get("rationale")),
                }
                async with get_connection() as conn:
                    resolved, errors = await core_mod.resolve_proposal(conn, proposal)
                    if not resolved:
                        msg = "; ".join(errors) or "Could not resolve that coordinate."
                        step = recorder.record(tool=name, kind="staged", label="Source-check proposal refused", status="rejected", detail=msg)
                        return {"status": "refused", "message": msg}, step
                    params = {"state": resolved["state"], "city": resolved.get("city")}
                    new_id = await _insert_proposed(conn, "check_sources", params)
                proposal_action_ids.append(new_id)
                result = {
                    "status": "staged", "action_id": new_id, "state": resolved["state"], "city": resolved.get("city"),
                    "source_urls": resolved.get("source_urls"),
                    "message": "Staged — waiting for the admin's confirmation.",
                }
                step = recorder.record(
                    tool=name, kind="staged",
                    label=f"Staged source check: {resolved.get('city') or resolved['state']}", status="ok",
                )
                return _json_safe(result), step

            if name == "stage_approve":
                from_action_id = actions_mod.coerce_uuid(args.get("from_action_id"))
                if not from_action_id:
                    step = recorder.record(tool=name, kind="staged", label="Commit proposal refused", status="rejected", detail="invalid id")
                    return {"status": "refused", "message": "Need a valid from_action_id — call list_actions for the real id."}, step
                async with get_connection() as conn:
                    from_row = await core_mod.load_action(conn, UUID(from_action_id))
                    verdict = actions_mod.evaluate_stage_approve(from_row, args.get("ids"))
                    if not verdict.ok:
                        step = recorder.record(tool=name, kind="staged", label="Commit proposal refused", status="rejected", detail=verdict.message)
                        return {"status": "refused", "message": verdict.message}, step
                    new_id = await _insert_proposed(conn, "approve", verdict.payload)
                proposal_action_ids.append(new_id)
                result = {
                    "status": "staged", "action_id": new_id,
                    "selected": verdict.payload["selected"], "gate_ok": verdict.payload["gate_ok"],
                    "gate_blocked": verdict.payload["gate_blocked"],
                    "message": "Staged — waiting for the admin's confirmation.",
                }
                step = recorder.record(
                    tool=name, kind="staged",
                    label=f"Staged commit: {verdict.payload['selected']} polic{'y' if verdict.payload['selected'] == 1 else 'ies'}",
                    status="ok", detail=f"{verdict.payload['gate_ok']} pass the codify gate",
                )
                return _json_safe(result), step

            if name == "confirm_action":
                action_id = actions_mod.coerce_uuid(args.get("action_id"))
                if not action_id:
                    step = recorder.record(tool=name, kind="write", label="Confirm refused", status="rejected", detail="invalid id")
                    return {"status": "refused", "message": "That's not a valid action id — call list_actions for the real ids."}, step
                async with get_connection() as conn:
                    row = await core_mod.load_action(conn, UUID(action_id))
                verdict = actions_mod.evaluate_confirm(row, pre_turn_proposed_ids)
                if verdict.kind == "stage":
                    step = recorder.record(tool=name, kind="write", label="Confirm deferred (staged this turn)", status="rejected", detail=verdict.message)
                    return {"status": "wait", "message": verdict.message}, step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="write", label="Confirm refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                try:
                    out = await confirm_mod.confirm_and_launch(action_id, actor_id)
                except confirm_mod.ActionConflict as exc:
                    step = recorder.record(tool=name, kind="write", label="Confirm refused", status="rejected", detail=str(exc))
                    return {"status": "refused", "message": str(exc)}, step
                except (LookupError, ValueError) as exc:
                    step = recorder.record(tool=name, kind="write", label="Confirm refused", status="rejected", detail=str(exc))
                    return {"status": "refused", "message": str(exc)}, step
                step = recorder.record(tool=name, kind="write", label="Started run", status="ok", detail=out["action_id"])
                return {
                    "status": "running", "action_id": out["action_id"],
                    "message": "Started — this runs in the background; call action_status to check on it.",
                }, step

            if name == "cancel_action":
                action_id = actions_mod.coerce_uuid(args.get("action_id"))
                if not action_id:
                    step = recorder.record(tool=name, kind="write", label="Cancel refused", status="rejected", detail="invalid id")
                    return {"status": "refused", "message": "That's not a valid action id."}, step
                async with get_connection() as conn:
                    row = await core_mod.load_action(conn, UUID(action_id))
                verdict = actions_mod.evaluate_cancel(row)
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="write", label="Cancel refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                try:
                    out = await confirm_mod.cancel_proposed(action_id)
                except (LookupError, ValueError) as exc:
                    step = recorder.record(tool=name, kind="write", label="Cancel refused", status="rejected", detail=str(exc))
                    return {"status": "refused", "message": str(exc)}, step
                step = recorder.record(tool=name, kind="write", label="Cancelled staged action", status="ok")
                return {"status": "cancelled", "action_id": out["action_id"]}, step

            step = recorder.record(tool=name, kind="write", label=f"Unknown tool '{name}'", status="error")
            return {"error": f"unknown tool '{name}'"}, step
        except Exception:
            logger.exception("compliance_pilot agent tool %s failed for session %s", name, session_id)
            step = recorder.record(tool=name, kind="write", label=f"{name} failed", status="error", detail="unexpected error")
            return {"error": "unexpected error"}, step

    client = get_genai_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=tool_declarations())],
        system_instruction=build_system_prompt(
            today=date.today().isoformat(),
            state_block=build_state_block(actions_snapshot),
        ),
    )
    contents = _to_contents(history)

    try:
        while True:
            if model_calls >= _MAX_MODEL_CALLS or elapsed() >= _WALL_CLOCK_SECONDS:
                logger.info("Compliance Pilot agent hit its bound (calls=%s, elapsed=%.1fs)", model_calls, elapsed())
                yield {"type": "status", "message": "Wrapping up…"}
                break

            await rate_limiter.check_limit("compliance_pilot", "agent")
            model_calls += 1
            call_timeout = min(_CALL_TIMEOUT, max(1.0, _WALL_CLOCK_SECONDS - elapsed()))
            try:
                with feature_scope("core.compliance_pilot.loop"):
                    response = await asyncio.wait_for(
                        client.aio.models.generate_content(model=_MODEL, contents=contents, config=config),
                        timeout=call_timeout,
                    )
            finally:
                await rate_limiter.record_call("compliance_pilot", "agent")

            usage = getattr(response, "usage_metadata", None)
            if usage:
                _accumulate_usage(total_usage, usage)

            all_parts = [
                part
                for candidate in (response.candidates or [])
                for part in (candidate.content.parts or [] if candidate.content else [])
            ]
            call_parts = [part for part in all_parts if getattr(part, "function_call", None)]
            calls = [p.function_call for p in call_parts]

            if not calls:
                final_message = (getattr(response, "text", None) or "").strip() or None
                break

            contents.append(types.Content(role="model", parts=all_parts))

            response_parts: list[types.Part] = []
            finished = False
            finish_message: Optional[str] = None
            sole_finish_call = is_sole_finish([c.name for c in calls])

            for call in calls:
                name = call.name
                args = dict(call.args or {})
                if name == "finish":
                    if not sole_finish_call:
                        recorder.record(
                            tool="finish", kind="finish", label="Finish deferred (other tools pending)",
                            status="ok", args=args,
                        )
                        response_parts.append(types.Part.from_function_response(
                            name=name,
                            response={
                                "status": "deferred",
                                "message": "Other tool calls this turn haven't reported back yet — "
                                           "call finish again once you've reviewed their results.",
                            },
                        ))
                        continue
                    finish_message = str(args.get("message") or "").strip() or None
                    finished = True
                    recorder.record(tool="finish", kind="finish", label="Done", status="ok", args=args)
                    continue

                tool = TOOLS_BY_NAME.get(name)
                if tool and tool.kind == "staged":
                    yield {"type": "status", "message": f"Proposing: {name.replace('_', ' ')}…"}
                elif tool and tool.kind == "write":
                    yield {"type": "status", "message": f"Working on: {name.replace('_', ' ')}…"}
                elif tool and tool.kind == "read":
                    yield {"type": "status", "message": f"Checking: {name.replace('_', ' ')}…"}

                task = asyncio.ensure_future(call_tool(name, args))
                remaining = max(1.0, _WALL_CLOCK_SECONDS - elapsed())
                timed_out = False
                while True:
                    wait_for = min(_TOOL_HEARTBEAT_SECONDS, remaining)
                    done, _pending = await asyncio.wait({task}, timeout=wait_for)
                    if task in done:
                        break
                    remaining -= wait_for
                    if remaining <= 0:
                        timed_out = True
                        task.cancel()
                        break
                    yield {"type": "status", "message": f"Still working on: {name.replace('_', ' ')}…"}

                if timed_out:
                    step = recorder.record(
                        tool=name, kind=(tool.kind if tool else "write"),
                        label=f"{name.replace('_', ' ')} timed out", status="error",
                        detail="Timed out waiting for a response.", args=args,
                    )
                    payload = {"error": "timed out"}
                else:
                    payload, step = task.result()
                    if step is not None:
                        step.setdefault("args", _cap_payload(args))
                        step.setdefault("result", _cap_payload(payload))
                if step:
                    yield {"type": "step", "data": step}
                response_parts.append(types.Part.from_function_response(name=name, response=payload))

            if finished:
                final_message = finish_message
                break

            contents.append(types.Content(role="user", parts=response_parts))

    except RateLimitExceeded:
        # A turn that never got off the ground re-raises: there is no turn to
        # record, so the route renders its own friendly rate-limit message and
        # persists nothing. But once tools have run, re-raising throws away the
        # ONLY narrative of writes that already happened — the stage_* tools
        # INSERT real `compliance_pilot_actions` rows, and the route's shielded
        # persist is skipped when no `agent_result` frame ever arrives, leaving
        # proposals sitting in the session with no message explaining them.
        # So a turn with work behind it degrades into a normal terminal frame.
        if not recorder.steps:
            raise
        logger.warning(
            "Compliance Pilot agent hit the Gemini rate limit after %s step(s) — "
            "finishing the turn with partial work", len(recorder.steps),
        )
        turn_error = (
            "Gemini's rate limit was reached partway through this turn, so I stopped early. "
            "Everything listed above already happened — check the staged proposals before retrying."
        )
    except Exception as exc:
        logger.warning("Compliance Pilot agent turn failed: %s", exc, exc_info=True)
        turn_error = "The Pilot hit a problem mid-turn — keeping what worked."

    # An `error` frame is deliberately NOT yielded for either case above: the
    # `agent_result` frame below IS the terminal error report, and it is the one
    # that gets persisted. Yielding both leaves the console showing the same
    # sentence twice — once as a live "⚠" bubble that never reconciles against
    # the transcript (it can't: the persisted content lacks the marker) and once
    # as the assistant message. The route keeps its own error frame for the case
    # this generator dies before reaching here.
    if not final_message:
        if turn_error:
            final_message = turn_error
        elif not recorder.steps:
            final_message = "I wasn't able to finish that — nothing was changed."
        else:
            final_message = "Done for now — see the steps above."

    total_usage["model"] = _MODEL
    total_usage["estimated"] = False

    result_data: dict[str, Any] = {
        "message": final_message,
        "steps": recorder.steps,
        "citations": list(turn_citations.values()),
        "proposal_action_ids": proposal_action_ids,
        "token_usage": total_usage,
        "model_calls": model_calls,
    }
    if turn_error:
        result_data["error"] = turn_error

    yield {"type": "agent_result", "data": result_data}
