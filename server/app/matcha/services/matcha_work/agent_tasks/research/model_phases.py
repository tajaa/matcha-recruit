"""The research phases that call a model: plan, discover, screen, summarize, refine.

Each is one bounded agent-runtime run (`model_run.run_model_phase`) whose
output is its finish contract (`contracts.py`). The model never writes: this
module stores what the contract let through, under the chain's token.

A model failure never sinks the task. The plan falls back to searching the
directive as written, a failed discovery run just finds nothing, a failed
screening keeps the batch in (no fit), a failed summary is written from the
ranking alone, and a refine that can't be read leaves the task as it was
(and that round is free).
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.matcha_work.agent_runtime import chain, inputs, runner
from app.matcha.services.matcha_work.agent_runtime.abilities import screenshots, web
from app.matcha.services.matcha_work.agent_runtime.chain import Guard, PhaseFailed, PhaseOutcome
from app.matcha.services.matcha_work.agent_runtime.context import RunLimits
from app.matcha.services.matcha_work.agent_runtime.phase_run import NoteProgress

from .. import items as items_mod
from .. import model_run
from . import contracts, prompts
from . import fields as F
from .phases import (
    BUDGETS, DISCOVER, ENRICH, PROVIDERS, RANK, SCREEN, SUMMARIZE, Deps, _chain, count_items,
    cursor_of, item_room, own_page, plan_of, rerank,
)

logger = logging.getLogger(__name__)

PLAN_LIMITS = RunLimits(max_model_calls=2, wall_seconds=90.0)
DISCOVER_LIMITS = RunLimits(max_model_calls=8, wall_seconds=330.0, max_hosted_per_response=4,
                            max_hosted_per_run=8)
SCREEN_LIMITS = RunLimits(max_model_calls=2, wall_seconds=150.0)
SUMMARY_LIMITS = RunLimits(max_model_calls=2, wall_seconds=120.0)
REFINE_LIMITS = RunLimits(max_model_calls=2, wall_seconds=90.0)
DISCOVER_FETCHES = 10
DISCOVER_VIEWS = 2
FETCH_SECONDS = 25.0
TARGET = 30
TARGET_MORE = 20
# Products and places: past this many from the provider, the web adds little.
PROVIDER_ENOUGH = 15
SCREEN_BATCH = 30
SUMMARY_TOP = 10
MIN_SURVIVORS = 5
REENRICH = 24
FOUND_LIST = 40


def _progress(guard: Guard) -> NoteProgress:
    return NoteProgress(note_fn=lambda text: guard.note(text))


async def _files(task: dict) -> tuple[str | None, list[dict]]:
    """The files the person gave the task: (text block, image parts)."""
    ids = [UUID(str(i)) for i in task.get("input_ids") or []]
    if not ids:
        return None, []
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT id, filename, content_type, kind, size_bytes, storage_path, text_excerpt,
                      extract_status, created_at
               FROM mw_agent_inputs WHERE id = ANY($1::uuid[]) AND user_id = $2
               ORDER BY created_at""",
            ids, task["user_id"],
        )
    if not rows:
        return None, []
    return await inputs.model_parts(inputs.RunFiles(fresh=[dict(r) for r in rows]))


def _first_input(user_text: str, files: tuple[str | None, list[dict]]) -> list[dict] | None:
    text, images = files
    if not text and not images:
        return None
    return [inputs.request_item(user_text, text, images)]


async def _round(conn, task: dict) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM mw_agent_task_rounds WHERE task_id = $1 AND n = $2", task["id"], task["current_round"],
    )
    return dict(row) if row else {}


# ── plan ─────────────────────────────────────────────────────────────────────

async def plan(task: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    brief = decode_jsonb(task.get("brief"), {}) or {}
    today = deps.today()
    directive = task.get("directive") or ""
    user_text = prompts.plan_turn(directive, brief, None)
    files = await _files(task)
    try:
        outcome = await model_run.run_model_phase(
            task, phase="plan", abilities=(),
            contract=runner.ResultContract(
                finish=contracts.PLAN_FINISH,
                normalize=lambda args, _state: contracts.normalize_plan(args, brief=brief, today=today),
            ),
            instructions=prompts.PLAN.format(today=today.isoformat()), user_text=user_text,
            limits=PLAN_LIMITS, progress=_progress(guard), client_factory=deps.client,
            first_note="Planning…", first_input=_first_input(user_text, files),
        )
        planned = outcome.result
    except runner.AgentRunError:
        logger.info("research plan fell back to the directive task=%s", task["id"])
        planned = contracts.plan_from_brief(directive, brief, today=today)
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_agent_tasks SET plan = $3::jsonb,
                   title = CASE WHEN title = '' THEN $4 ELSE title END
               WHERE id = $1 AND dispatch_token = $2""",
            task["id"], guard.token, json.dumps(planned, default=str),
            (planned.get("title") or directive)[:120],
        )
    return PhaseOutcome(status="running", phase=PROVIDERS,
                        progress={"note": f"Searching {len(planned['queries'])} ways…"})


# ── discover ─────────────────────────────────────────────────────────────────

async def discover(task: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    plan_ = plan_of(task)
    cursor = cursor_of(task)
    today = deps.today()
    more = bool(cursor.get("more") or cursor.get("refine"))
    max_runs, target = (1, TARGET_MORE) if more else (2, TARGET)
    runs = int(cursor.get("web_runs") or 0)
    async with connection_or_direct() as conn:
        room = await item_room(conn, task["id"])
        added = int((await _round(conn, task)).get("items_added") or 0)
        found = [r["title"] for r in await conn.fetch(
            f"SELECT title FROM mw_agent_task_items WHERE task_id = $1 ORDER BY created_at DESC LIMIT {FOUND_LIST}",
            task["id"],
        )]
        like = [r["title"] for r in await conn.fetch(
            "SELECT title FROM mw_agent_task_items WHERE task_id = $1 AND id = ANY($2::uuid[])",
            task["id"], [UUID(i) for i in cursor.get("like") or []],
        )] if cursor.get("like") else []
    enough_from_provider = int(cursor.get("provider_added") or 0) >= PROVIDER_ENOUGH and not more
    new = 0
    if room > 0 and runs < max_runs and added < target and not enough_from_provider:
        new = await _discover_run(task, deps, guard, plan_=plan_, today=today, room=room,
                                  target=min(target - added, contracts.MAX_CANDIDATES),
                                  found=found, like=like, more=more)
        runs += 1
        added += new
        if new and runs < max_runs and added < target:
            return PhaseOutcome(status="running", phase=DISCOVER, cursor={**cursor, "web_runs": runs},
                                progress={"note": f"Found {added} so far; looking for more…", "found": added})
    async with connection_or_direct() as conn:
        total = await count_items(conn, task["id"])
    if total == 0:
        raise PhaseFailed("Couldn't find anything that matched. Try saying it another way, or more broadly.")
    if more and added == 0:
        return PhaseOutcome(status="running", phase=RANK, cursor={**cursor, "web_runs": runs,
                                                                  "note": "Nothing new turned up."},
                            progress={"note": "Nothing new turned up."})
    return PhaseOutcome(status="running", phase=ENRICH, cursor={**cursor, "web_runs": runs},
                        progress={"note": f"Found {added}. Reading their pages…", "found": total})


async def _discover_run(task: dict, deps: Deps, guard: Guard, *, plan_: dict, today, room: int,
                        target: int, found: list[str], like: list[str], more: bool) -> int:
    """One model search for candidates. Returns how many new findings it added."""
    spec = _chain()
    fetches = await chain.grant(spec, task["id"], "fetch_calls", DISCOVER_FETCHES, BUDGETS.fetch_calls)
    browser = deps.browser_ready()
    views = await chain.grant(spec, task["id"], "browser_views", DISCOVER_VIEWS, BUDGETS.browser_views) if browser else 0
    pages: dict[str, str] = {}
    used = {"fetch": 0, "view": 0}

    async def fetch_page(url: str) -> tuple[dict, set[str]]:
        used["fetch"] += 1
        page, vouched = await deps.fetch_page(url)
        if vouched and isinstance(page, dict) and not page.get("error"):
            text = " ".join([str(page.get("title") or ""), str(page.get("text") or ""),
                             json.dumps({k: page.get(k) for k in ("products", "listings", "places", "events",
                                                                    "offers") if page.get(k)}, default=str)])
            for seen in vouched | {page.get("url")}:
                if isinstance(seen, str):
                    pages[seen] = text
        return page, vouched

    async def view(url: str, prefix: str) -> dict:
        used["view"] += 1
        out = await deps.view(url, prefix)
        if isinstance(out, dict) and not out.get("error"):
            for seen in (url, out.get("url")):
                if isinstance(seen, str):
                    pages[seen] = f"{out.get('title') or ''} {out.get('text') or ''}"
        return out

    abilities: list = [web.build(fetch_page=fetch_page, max_fetches=max(fetches, 0),
                                 fetch_seconds=FETCH_SECONDS, untrusted=True)]
    if views > 0:
        abilities.append(screenshots.build(viewer=view, env_ready=lambda: True))
    queries = [q for q in plan_.get("queries") or [] if q]
    user_text = prompts.discover_turn(task.get("directive") or "", plan_, queries=queries, found=found,
                                      like=like, target=target)
    candidates: list[dict] = []
    try:
        outcome = await model_run.run_model_phase(
            task, phase="discover", abilities=tuple(abilities),
            contract=runner.ResultContract(
                finish=contracts.DISCOVER_FINISH,
                normalize=lambda args, state: _wrap(contracts.normalize_candidates(
                    args, plan=plan_, citable=state.citable(), pages=pages,
                    images=state.sessions.get(web._IMAGES) or {}, today=today,
                )),
            ),
            instructions=prompts.discover_instructions(plan_, browser=views > 0), user_text=user_text,
            limits=DISCOVER_LIMITS, progress=_progress(guard), client_factory=deps.client,
            reasoning_effort="medium",
            first_note="Looking for more…" if more else "Searching the web…",
            first_input=_first_input(user_text, await _files(task)),
        )
        candidates = outcome.result.get("candidates") or []
    except runner.AgentRunError:
        logger.info("research discovery run found nothing usable task=%s", task["id"])
    finally:
        await chain.refund(spec, task["id"], "fetch_calls", max(0, fetches - used["fetch"]))
        if views:
            await chain.refund(spec, task["id"], "browser_views", max(0, views - used["view"]))
    async with connection_or_direct() as conn:
        return await items_mod.insert_items(conn, task, guard.token, int(task["current_round"]),
                                            candidates, room=room)


def _wrap(normalized: tuple[list[dict], list[str]]) -> tuple[dict, list[str]]:
    candidates, warnings = normalized
    return {"candidates": candidates}, warnings


# ── screen ───────────────────────────────────────────────────────────────────

async def screen(task: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""SELECT id, title, subtitle, url, fields, fit_score, fit_reasons, rank_explain
                FROM mw_agent_task_items
                WHERE task_id = $1 AND screened_at IS NULL AND status <> 'unavailable'
                ORDER BY created_at, id LIMIT {SCREEN_BATCH}""",
            task["id"],
        )
    if not rows:
        return PhaseOutcome(status="running", phase=RANK, progress={"note": "Ranking…"})
    batch = {f"F{i + 1}": str(row["id"]) for i, row in enumerate(rows)}
    shown = [(short, items_mod.view_for_model(row)) for short, row in zip(batch, rows)]
    plan_ = plan_of(task)
    try:
        outcome = await model_run.run_model_phase(
            task, phase="screen", abilities=(),
            contract=runner.ResultContract(
                finish=contracts.SCREEN_FINISH,
                normalize=lambda args, _state: contracts.normalize_screen(args, batch),
            ),
            instructions=prompts.SCREEN, user_text=prompts.screen_turn(task.get("directive") or "", plan_, shown),
            limits=SCREEN_LIMITS, progress=_progress(guard), client_factory=deps.client,
            first_note=f"Checking {len(rows)} findings…",
        )
        verdicts: dict[str, dict] = outcome.result
    except runner.AgentRunError:
        logger.info("research screening failed; keeping the batch task=%s", task["id"])
        verdicts = {}
    ids = [row["id"] for row in rows]
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_agent_task_items AS i
               SET status = CASE WHEN v.relevant THEN i.status ELSE 'irrelevant' END,
                   fit_score = v.fit, fit_reasons = v.reasons::jsonb, screened_at = NOW(), updated_at = NOW()
               FROM unnest($3::uuid[], $4::bool[], $5::int[], $6::text[]) AS v(id, relevant, fit, reasons)
               WHERE i.id = v.id AND i.task_id = $1
                 AND EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $1 AND dispatch_token = $2)""",
            task["id"], guard.token, ids,
            [verdicts.get(str(i), {}).get("relevant", True) for i in ids],
            [verdicts.get(str(i), {}).get("fit") for i in ids],
            [json.dumps(verdicts.get(str(i), {}).get("reasons") or []) for i in ids],
        )
        left = await count_items(conn, task["id"], "AND screened_at IS NULL AND status <> 'unavailable'")
    if left:
        return PhaseOutcome(status="running", phase=SCREEN, progress={"note": f"Checked; {left} to go…"})
    return PhaseOutcome(status="running", phase=RANK, progress={"note": "Ranking…"})


# ── summarize ────────────────────────────────────────────────────────────────

def _item_text(item: dict) -> str:
    return " ".join([item.get("title") or "", item.get("subtitle") or "", F.check_text(item.get("fields") or {})])


def fallback_summary(shown: list[dict], *, total: int, hidden: int, note: str | None) -> dict:
    """The summary written from the ranking alone, when the model's fails."""
    if not shown:
        headline = "Nothing found meets every limit" if total else "Nothing found"
    else:
        headline = f"{len(shown)} that fit, of {total} found" if total > len(shown) else f"Found {total}"
    summary = note or (f"{hidden} were hidden for breaking a limit or not fitting." if hidden else "")
    return {
        "headline": headline, "summary": summary, "sections": [],
        "top": [{"item_id": item["id"], "why": (item.get("fit_reasons") or [""])[0]} for item in shown[:5]],
        "origin": "ranking",
    }


async def summarize(task: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    cursor = cursor_of(task)
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""SELECT id, title, subtitle, url, fields, fit_score, fit_reasons, rank_explain
                FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9
                ORDER BY rank LIMIT {SUMMARY_TOP}""",
            task["id"],
        )
        total = await count_items(conn, task["id"])
        visible = await count_items(conn, task["id"], "AND rank_band < 9")
        urls = [r["url"] for r in await conn.fetch(
            "SELECT url FROM mw_agent_task_items WHERE task_id = $1 AND url IS NOT NULL", task["id"],
        )]
    shown = [items_mod.view_for_model(row) for row in rows]
    note = cursor.get("note")
    plan_ = plan_of(task)
    # Numbers the summary may state besides the findings' own: the ask, its
    # limits and the counts it is told.
    context = " ".join([task.get("directive") or "", *prompts.plan_lines(plan_),
                        *(json.dumps(c.get("value"), default=str) for c in plan_.get("constraints") or []),
                        str(total), str(visible), str(total - visible), note or ""])
    summary = fallback_summary(shown, total=total, hidden=total - visible, note=note)
    if shown:
        batch = {f"F{i + 1}": item["id"] for i, item in enumerate(shown)}
        try:
            outcome = await model_run.run_model_phase(
                task, phase="summarize", abilities=(),
                contract=runner.ResultContract(
                    finish=contracts.SUMMARY_FINISH,
                    normalize=lambda args, _state: contracts.normalize_summary(
                        args, batch=batch, item_texts={i["id"]: _item_text(i) for i in shown},
                        citable={u for u in urls if u}, context=context,
                        titles={short: item["title"] for short, item in zip(batch, shown)},
                    ),
                ),
                instructions=prompts.SUMMARIZE,
                user_text=prompts.summary_turn(task.get("directive") or "", plan_, list(zip(batch, shown)),
                                               total=total, hidden=total - visible, note=note),
                limits=SUMMARY_LIMITS, progress=_progress(guard), client_factory=deps.client,
                first_note="Writing up what it found…",
            )
            summary = {**outcome.result, "origin": "model"}
        except runner.AgentRunError:
            logger.info("research summary fell back to the ranking task=%s", task["id"])
    summary["counts"] = {"found": total, "shown": visible, "hidden": total - visible}
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_agent_task_rounds SET summary = $4::jsonb
               WHERE task_id = $1 AND n = $3
                 AND EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $1 AND dispatch_token = $2)""",
            task["id"], guard.token, int(task["current_round"]), json.dumps(summary, default=str),
        )
    return PhaseOutcome(status="done", cursor={k: v for k, v in cursor.items() if k == "round_failed"},
                        progress={"note": summary["headline"], "found": total, "shown": visible})


# ── refine ───────────────────────────────────────────────────────────────────

def _needs_reading(row: Any, keys: list[str]) -> bool:
    fields = decode_jsonb(row["fields"], {}) or {}
    return own_page(row["url"]) and any((fields.get(k) or {}).get("status") != "verified" for k in keys)


async def refine(task: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    """The person's follow-up as a change to the plan, applied to what was found."""
    plan_ = plan_of(task)
    brief = decode_jsonb(task.get("brief"), {}) or {}
    today = deps.today()
    async with connection_or_direct() as conn:
        change = (await _round(conn, task)).get("directive") or ""
    try:
        outcome = await model_run.run_model_phase(
            task, phase="refine", abilities=(),
            contract=runner.ResultContract(
                finish=contracts.REFINE_FINISH,
                normalize=lambda args, _state: contracts.normalize_refine(args, plan=plan_, brief=brief, today=today),
            ),
            instructions=prompts.REFINE.format(today=today.isoformat()),
            user_text=prompts.refine_turn(task.get("directive") or "", plan_, change),
            limits=REFINE_LIMITS, progress=_progress(guard), client_factory=deps.client,
            first_note="Reading your change…",
        )
    except runner.AgentRunError:
        message = "Couldn't work out that change. Try saying it another way."
        return PhaseOutcome(status="done", cursor={"round_failed": message}, progress={"note": message})
    changed = outcome.result["plan"]
    note = outcome.result["note"] or "Updated."
    old_fields = set(plan_.get("fields") or []) | {c["field"] for c in plan_.get("constraints") or []}
    new_keys = [k for k in dict.fromkeys([*changed["fields"], *(c["field"] for c in changed["constraints"])])
                if k not in old_fields]
    async with connection_or_direct() as conn:
        written = await conn.fetchval(
            """UPDATE mw_agent_tasks SET plan = $3::jsonb WHERE id = $1 AND dispatch_token = $2 RETURNING 1""",
            task["id"], guard.token, json.dumps(changed, default=str),
        )
        if not written:
            return PhaseOutcome(status="running")  # retired; advance won't write
        await rerank(conn, {**task, "plan": changed})
        visible = await count_items(conn, task["id"], "AND rank_band < 9")
        room = await item_room(conn, task["id"])
        if (outcome.result["search_again"] or visible < MIN_SURVIVORS) and room > 0:
            return PhaseOutcome(
                status="running", phase=PROVIDERS,
                cursor={"refine": True, "note": note, "provider_page": 1, "web_runs": 0},
                progress={"note": f"{note} Searching again…"},
            )
        if new_keys:
            rows = await conn.fetch(
                f"""SELECT id, url, fields FROM mw_agent_task_items
                    WHERE task_id = $1 AND rank_band < 9 ORDER BY rank LIMIT {REENRICH}""",
                task["id"],
            )
            stale = [row["id"] for row in rows if _needs_reading(row, new_keys)]
            if stale:
                await conn.execute(
                    """UPDATE mw_agent_task_items SET enriched_at = NULL
                       WHERE task_id = $1 AND id = ANY($2::uuid[])""",
                    task["id"], stale,
                )
                return PhaseOutcome(status="running", phase=ENRICH, cursor={"note": note},
                                    progress={"note": f"{note} Checking {len(stale)} pages for it…"})
    return PhaseOutcome(status="running", phase=SUMMARIZE, cursor={"note": note}, progress={"note": note})
