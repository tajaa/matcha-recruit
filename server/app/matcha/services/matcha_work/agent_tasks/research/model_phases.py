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
from . import batches, contracts, kinds, prompts, suggest
from . import fields as F
from . import fill as fill_mod
from .phases import (
    BUDGETS, DISCOVER, ENRICH, FILL, PROVIDERS, RANK, SCREEN, Deps, _chain, count_items,
    cursor_of, fill_plans, item_room, own_page, plan_of, rerank,
)

logger = logging.getLogger(__name__)

PLAN_LIMITS = RunLimits(max_model_calls=2, wall_seconds=90.0)
DISCOVER_LIMITS = RunLimits(max_model_calls=8, wall_seconds=330.0, max_hosted_per_response=4,
                            max_hosted_per_run=8)
SCREEN_LIMITS = RunLimits(max_model_calls=2, wall_seconds=150.0)
# Three calls: a summary sent as broken JSON text gets two repairs, not one.
SUMMARY_LIMITS = RunLimits(max_model_calls=3, max_repairs=2, wall_seconds=120.0)
REFINE_LIMITS = RunLimits(max_model_calls=2, wall_seconds=90.0)
DISCOVER_FETCHES = 10
DISCOVER_VIEWS = 2
FETCH_SECONDS = 25.0
TARGET = 30
TARGET_MORE = 20
SCREEN_BATCH = 30
SUMMARY_TOP = 10
TOP_PICKS = 5
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
    kind = kinds.of(task)
    user_text = prompts.plan_turn(directive, brief, None, labels=kind.labels() if kind else None)
    files = await _files(task)
    try:
        outcome = await model_run.run_model_phase(
            task, phase="plan", abilities=(),
            contract=runner.ResultContract(
                finish=contracts.PLAN_FINISH,
                normalize=lambda args, _state: contracts.normalize_plan(args, brief=brief, today=today, kind=kind),
            ),
            instructions=prompts.plan_instructions(today, kind), user_text=user_text,
            limits=PLAN_LIMITS, progress=_progress(guard), client_factory=deps.client,
            first_note="Planning…", first_input=_first_input(user_text, files), escalate=True,
        )
        planned = outcome.result
    except runner.AgentRunError:
        logger.info("research plan fell back to the directive task=%s", task["id"])
        planned = contracts.plan_from_brief(directive, brief, today=today, kind=kind)
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
    new = 0
    if room > 0 and runs < max_runs and added < target:
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
            f"""SELECT id, title, subtitle, url, fields, units, fit_score, fit_reasons, rank_explain
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
            first_note=f"Checking {len(rows)} findings…", escalate=True,
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
    homes = item.get("homes") or {}
    return " ".join([item.get("title") or "", item.get("subtitle") or "", F.check_text(item.get("fields") or {}),
                     *(homes.get("examples") or []), *(homes.get("homes_that_fit") or []),
                     *(homes.get("cheapest_not_fitting") or []), str(homes.get("listed") or ""),
                     str(homes.get("meet_every_limit") or "")])


def fallback_summary(shown: list[dict], *, total: int, hidden: int, note: str | None) -> dict:
    """The summary written from the ranking alone, when the model's fails."""
    fit = total - hidden  # `shown` is only the best few of them
    if not shown:
        headline = "Nothing found meets every limit" if total else "Nothing found"
    else:
        headline = f"{fit} that fit, of {total} found" if hidden else f"Found {total}"
    summary = note or (f"{hidden} were hidden for breaking a limit or not fitting." if hidden else "")
    return {
        "headline": headline, "summary": summary, "sections": [],
        "top": fill_top([], shown),
        "origin": "ranking",
    }


def fill_top(top: list[dict], shown: list[dict], want: int = TOP_PICKS) -> list[dict]:
    """The model's picks, then the ranking's best it didn't pick, up to `want`:
    a finished task always shows its best few, whatever the model chose."""
    out, picked = list(top), {p["item_id"] for p in top}
    for item in shown:
        if len(out) >= want:
            break
        if item["id"] not in picked:
            out.append({"item_id": item["id"], "why": (item.get("fit_reasons") or [""])[0]})
    return out


async def summarize(task: dict, deps: Deps, guard: Guard) -> PhaseOutcome:
    cursor = cursor_of(task)
    plan_ = plan_of(task)
    batched = batches.uses_batches(plan_)
    item_kind = plan_.get("item_kind")
    diagnosis = None
    async with connection_or_direct() as conn:
        if batched:
            round_kind = await fill_mod.round_kind(conn, task)
            released, _looked = await fill_mod.released_and_looked_up(conn, task["id"])
            ranked = await fill_mod.ranked_rows(conn, task["id"])
            # A refine re-picks the best ten under the changed plan; other rounds show the next ten.
            exclude = set() if round_kind == "refine" else set(released)
            rows = batches.pick(ranked, item_kind=item_kind, plan=plan_, exclude=exclude)
            picked = {str(r["id"]) for r in rows}
            waiting = [r for r in ranked if str(r["id"]) not in exclude | picked]
            hidden_by = {r["field"]: int(r["n"]) for r in await conn.fetch(
                """SELECT v->>'field' AS field, COUNT(DISTINCT i.id) AS n
                   FROM mw_agent_task_items i,
                        jsonb_array_elements(CASE WHEN jsonb_typeof(i.violations) = 'array'
                                                  THEN i.violations ELSE '[]'::jsonb END) v
                   WHERE i.task_id = $1 AND i.rank_band >= 9
                   GROUP BY 1""",
                task["id"],
            ) if r["field"]}
            hidden_prices = [float(r["price"]) for r in await conn.fetch(
                """SELECT (fields->'price'->>'value')::float8 AS price FROM mw_agent_task_items
                   WHERE task_id = $1 AND rank_band >= 9 AND fields->'price'->>'status' = 'verified'
                     AND jsonb_typeof(fields->'price'->'value') = 'number'""",
                task["id"],
            ) if r["price"] is not None]
            room = await item_room(conn, task["id"])
        else:
            rows = await conn.fetch(
                f"""SELECT id, title, subtitle, url, fields, units, fit_score, fit_reasons, rank_explain
                    FROM mw_agent_task_items WHERE task_id = $1 AND rank_band < 9
                    ORDER BY rank LIMIT {SUMMARY_TOP}""",
                task["id"],
            )
        total = await count_items(conn, task["id"])
        visible = await count_items(conn, task["id"], "AND rank_band < 9")
        urls = [r["url"] for r in await conn.fetch(
            "SELECT url FROM mw_agent_task_items WHERE task_id = $1 AND url IS NOT NULL", task["id"],
        )]
    if batched:
        ready_waiting = len(batches.pick(waiting, item_kind=item_kind, plan=plan_, n=len(waiting)))
        diagnosis = suggest.diagnose(
            plan=plan_, shown=len(rows), ready_waiting=ready_waiting,
            short=batches.shortfall(waiting, item_kind=item_kind, plan=plan_), hidden_by=hidden_by,
            hidden_prices=hidden_prices, room=room,
            waiting_prices=[p for p in (_price(r) for r in waiting) if p is not None],
            # What other sites say the ones over the limit cost: the limit it would take.
            over_prices=[p for p in (_price(r) for r in waiting if batches.over_limit(r, plan_)) if p is not None],
        )
    shown = [items_mod.view_for_model(row) for row in rows]
    note = cursor.get("note")
    # Numbers the summary may state besides the findings' own: the ask, its
    # limits and the counts it is told.
    context = " ".join([task.get("directive") or "", *prompts.plan_lines(plan_),
                        *(json.dumps(c.get("value"), default=str) for c in plan_.get("constraints") or []),
                        str(total), str(visible), str(total - visible), note or "",
                        suggest.numbers_allowed(diagnosis)])
    summary = fallback_summary(shown, total=total, hidden=total - visible, note=note)
    if batched and not shown:
        summary["headline"] = "Nothing ready to show yet" if total else summary["headline"]
    phrased = None
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
                                               total=total, hidden=total - visible, note=note,
                                               suggestion=diagnosis),
                limits=SUMMARY_LIMITS, progress=_progress(guard), client_factory=deps.client,
                first_note="Writing up what it found…", escalate=True,
            )
            phrased = outcome.result.pop("question", None)
            summary = {**outcome.result, "top": fill_top(outcome.result["top"], shown), "origin": "model"}
        except runner.AgentRunError:
            logger.info("research summary fell back to the ranking task=%s", task["id"])
    summary["counts"] = {"found": total, "shown": visible, "hidden": total - visible}
    if batched:
        summary["batch"] = [str(r["id"]) for r in rows]
        summary["looked_up"] = list(cursor.get("looked_up") or [])
        everyone = set(released) | set(summary["batch"])
        summary["counts"] = {"found": total, "shown": len(everyone), "hidden": total - visible,
                             "waiting": len(waiting), "ready_waiting": ready_waiting}
        question = suggest.view(diagnosis, phrased)
        if question is not None:
            summary["question"] = question
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_agent_task_rounds SET summary = $4::jsonb
               WHERE task_id = $1 AND n = $3
                 AND EXISTS (SELECT 1 FROM mw_agent_tasks WHERE id = $1 AND dispatch_token = $2)""",
            task["id"], guard.token, int(task["current_round"]), json.dumps(summary, default=str),
        )
    return PhaseOutcome(status="done", cursor={k: v for k, v in cursor.items() if k == "round_failed"},
                        progress={"note": summary["headline"], "found": total,
                                  "shown": summary["counts"]["shown"]})


def _price(row: Any) -> float | None:
    price = (decode_jsonb(row["fields"], {}) or {}).get("price")
    value = price.get("value") if isinstance(price, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


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
                normalize=lambda args, _state: contracts.normalize_refine(args, plan=plan_, brief=brief, today=today,
                                                                          kind=kinds.of(task)),
            ),
            instructions=prompts.refine_instructions(today, kinds.of(task)),
            user_text=prompts.refine_turn(task.get("directive") or "", plan_, change),
            limits=REFINE_LIMITS, progress=_progress(guard), client_factory=deps.client,
            first_note="Reading your change…", escalate=True,
        )
    except runner.AgentRunError:
        message = "Couldn't work out that change. Try saying it another way."
        return PhaseOutcome(status="done", cursor={"round_failed": message}, progress={"note": message})
    changed = outcome.result["plan"]
    note = outcome.result["note"] or "Updated."
    old_fields = set(plan_.get("fields") or []) | {c["field"] for c in plan_.get("constraints") or []}
    new_keys = [k for k in dict.fromkeys([*changed["fields"], *(c["field"] for c in changed["constraints"])])
                if k not in old_fields]
    nxt = PhaseOutcome(status="running", phase=FILL, cursor={"note": note}, progress={"note": note})
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
            nxt = PhaseOutcome(
                status="running", phase=PROVIDERS,
                cursor={"refine": True, "note": note, "provider_page": 1, "web_runs": 0},
                progress={"note": f"{note} Searching again…"},
            )
        elif new_keys:
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
                nxt = PhaseOutcome(status="running", phase=ENRICH, cursor={"note": note},
                                   progress={"note": f"{note} Checking {len(stale)} pages for it…"})
    # Homes that fit only now: their floor plans, if they were never copied.
    try:
        await fill_plans(task, changed, deps, guard)
    except Exception:
        logger.warning("research floor plans after a refine failed task=%s", task["id"], exc_info=True)
    return nxt
