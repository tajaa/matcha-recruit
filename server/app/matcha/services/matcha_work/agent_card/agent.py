"""Bounded web agent that answers one agent card with a structured result.

Hosted web_search (provider side) + our `fetch_page` + a `finish` tool whose
payload goes through `schema.normalize_result`'s provenance gate. Read-only:
no tool here writes anywhere except the run's own audit rows and the card's
progress line.

The loop itself is the agent runtime's (`agent_runtime/runner.py`). This module
is the card's caller of it: the card's limits, its abilities, its result
contract and what happens to the result afterwards. The limits and the
collaborators stay module attributes here, read at call time.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.matcha.services.huume.luna_client import get_luna_client, text_item
from app.matcha.services.huume.routing import LUNA
from app.matcha.services.matcha_work.agent_runtime import runner
from app.matcha.services.matcha_work.agent_runtime.abilities import shopping, web
from app.matcha.services.matcha_work.agent_runtime.context import RunContext, RunLimits
from app.matcha.services.matcha_work.project_agent import store
from app.matcha.services.matcha_work.project_agent.agent import _safe_for_audit

from . import board, images
from .page_extract import extract_page, page_urls
from .progress import CardProgress
from .prompt import build_system_prompt
from .schema import normalize_result
from .tools import FINISH_TOOL

logger = logging.getLogger(__name__)

CARD_AGENT_MODEL = LUNA
_MAX_MODEL_CALLS = 8
_MAX_SEARCHES_PER_RESPONSE = 6
_MAX_SEARCHES_PER_RUN = 12
_MAX_FETCHES = 10
_WALL_SECONDS = 300.0
_MAX_PAGE_BYTES = 2 * 1024 * 1024
# One page load, start to finish. httpx's timeouts are per socket operation, so
# a host that drips a byte at a time would otherwise hold the run indefinitely.
_FETCH_SECONDS = 25.0
_PHOTO_SECONDS = 60.0
_MAX_TOOL_OUTPUT_CHARS = 12_000
_MAX_REPAIRS = 1
_AI_USAGE_FEATURE = "matcha.espresso.agent_card"


class CardAgentError(RuntimeError):
    """A run that ended without a usable result; the message is user-facing."""


async def fetch_page_tool(url: str) -> tuple[dict, set[str]]:
    """(tool output, provenance URLs it vouches for)."""
    try:
        fetched = await fetch_public(
            url, max_bytes=_MAX_PAGE_BYTES, accept="text/html,application/xhtml+xml",
            total_timeout=_FETCH_SECONDS,
        )
    except UnsafeURL as exc:
        return {"error": f"Refused: {exc}"}, set()
    except Exception as exc:
        return {"error": f"Could not load the page: {type(exc).__name__}"}, set()
    if fetched.status >= 400:
        return {"error": f"The site answered HTTP {fetched.status}", "url": fetched.final_url}, set()
    if "html" not in fetched.content_type and "xml" not in fetched.content_type:
        return {"error": f"Not an HTML page ({fetched.content_type or 'unknown type'})"}, set()
    try:
        page = await asyncio.to_thread(extract_page, fetched.body, fetched.final_url)
    except Exception:
        # Hostile markup (absurd nesting -> RecursionError, parser errors) is a
        # bad page, not a failed run: tell the model and let it try another.
        logger.info("agent card page extraction failed for %s", url[:200], exc_info=True)
        return {"error": "Could not read that page's structure. Try another source."}, set()
    urls = page_urls(page) | {fetched.url}
    encoded = json.dumps(page, default=str)
    if len(encoded) > _MAX_TOOL_OUTPUT_CHARS:
        page["text"] = page["text"][: max(0, len(page["text"]) - (len(encoded) - _MAX_TOOL_OUTPUT_CHARS))]
        page["text_truncated"] = True
    return page, urls


def _user_turn(ask: str, review_note: str | None, previous_result: dict | None) -> str:
    parts = [f"Request (from the card):\n{ask.strip()}"]
    if review_note:
        parts.append(f"Reviewer's note on your previous result:\n{review_note.strip()}")
    if previous_result:
        parts.append(
            "Your previous result (JSON, for reference; its links were already verified):\n"
            + json.dumps(previous_result, default=str)[:12_000]
        )
    return "\n\n".join(parts)


async def run_card_agent(
    *,
    run_id: UUID,
    company_id: UUID,
    project_id: UUID,
    task_id: UUID,
    round: int,
    ask: str,
    review_note: str | None = None,
    previous_result: dict | None = None,
    stats: dict | None = None,
) -> dict:
    """Run the loop; persist and return the normalized result.

    Raises CardAgentError when no usable result was produced within limits.
    `stats` (if given) is kept current after every model call — model_calls,
    search_calls, token_usage — so a caller can still account for the spend of
    a run that raised.
    """
    stats = stats if stats is not None else {}
    provenance: set[str] = set()
    if previous_result:
        # Links a previous round already verified stay usable in a revision.
        for key in ("sources",):
            provenance.update(s.get("url") for s in previous_result.get(key) or [] if s.get("url"))
        for pick in [previous_result.get("top_pick"), *(previous_result.get("alternatives") or [])]:
            if not pick:
                continue
            for link in pick.get("buy_links") or []:
                provenance.add(link.get("url"))
            for review in pick.get("reviews") or []:
                provenance.add(review.get("url"))
            for field in ("price", "rating"):
                if pick.get(field):
                    provenance.add(pick[field].get("source_url"))
        provenance.discard(None)

    ctx = RunContext(
        run_id=run_id,
        user_id=run_id,  # a card run acts for nobody: it has no commit tools
        company_id=company_id,
        role="card",
        surface="card",
        ask=ask,
        storage_prefix=f"matcha-work/{company_id}/{project_id}/agent/{task_id}",
        progress=CardProgress(project_id=project_id, task_id=task_id),
        limits=RunLimits(
            max_model_calls=_MAX_MODEL_CALLS,
            wall_seconds=_WALL_SECONDS,
            max_repairs=_MAX_REPAIRS,
            max_hosted_per_response=_MAX_SEARCHES_PER_RESPONSE,
            max_hosted_per_run=_MAX_SEARCHES_PER_RUN,
            max_tool_output_chars=_MAX_TOOL_OUTPUT_CHARS,
        ),
        usage_feature=_AI_USAGE_FEATURE,
        model=CARD_AGENT_MODEL,
        project_id=project_id,
        task_id=task_id,
    )
    abilities = [
        # Resolved through this module on every call, so the page loader and the
        # budgets are whatever this module holds when the page is asked for.
        web.build(
            fetch_page=lambda url: fetch_page_tool(url),
            max_fetches=_MAX_FETCHES,
            fetch_seconds=_FETCH_SECONDS,
        ),
        shopping.build(),
    ]
    contract = runner.ResultContract(
        finish=FINISH_TOOL,
        normalize=lambda args, state: normalize_result(args.get("result"), state.provenance),
    )
    try:
        outcome = await runner.run_agent(
            ctx,
            client=get_luna_client(),
            abilities=abilities,
            contract=contract,
            instructions=build_system_prompt(round),
            first_input=[text_item("user", _user_turn(ask, review_note, previous_result))],
            first_note="Searching the web…" if round == 1 else "Working on your feedback…",
            seed_provenance=provenance,
            stats=stats,
        )
    except runner.AgentRunError as exc:
        raise CardAgentError(str(exc)) from exc.__cause__
    result = outcome.result
    assert result is not None  # a card run has no ask or commit tool to end on
    model_calls, search_calls, usage = outcome.model_calls, outcome.search_calls, outcome.token_usage

    seq = outcome.last_seq

    async def step(tool: str, kind: str, label: str, args: dict, out: dict, status: str = "ok") -> None:
        nonlocal seq
        seq += 1
        await store.record_step(run_id, seq, tool, kind, label[:200], _safe_for_audit(args), _safe_for_audit(out), status)

    await ctx.progress.note("Collecting photos…")
    image_warnings = await images.rehost_images(
        result, company_id=company_id, project_id=project_id, task_id=task_id,
        total_seconds=_PHOTO_SECONDS,
    )
    for pick in [result.get("top_pick"), *(result.get("alternatives") or [])]:
        if pick:
            await step("rehost_images", "image", f"Photos for {pick['name'][:80]}", {}, {"kept": len(pick["images"])})
    result["warnings"] = (outcome.warnings + image_warnings)[:30]
    result["round"] = round

    await store.mark_run(
        run_id,
        status="done",
        result=result,
        model_calls=model_calls,
        token_usage=usage,
        search_calls=search_calls,
    )
    return {"result": result, "model_calls": model_calls, "search_calls": search_calls, "token_usage": usage}
