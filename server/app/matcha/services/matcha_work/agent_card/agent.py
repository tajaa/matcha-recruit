"""Bounded web agent that answers one agent card with a structured result.

Hosted web_search (provider side) + our `fetch_page` + a `finish` tool whose
payload goes through `schema.normalize_result`'s provenance gate. A travel
request also gets `search_flights` (Duffel, `flights.py`) when a token is
configured. Read-only:
no tool here writes anywhere except the run's own audit rows and the card's
progress line.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from app.core.services.ai_usage import feature_scope
from app.core.services.openai_responses import cited_urls, web_search_calls
from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.matcha.services.huume.luna_client import (
    get_luna_client,
    text_item,
    tool_output_item,
)
from app.matcha.services.huume.routing import LUNA
from app.matcha.services.matcha_work.project_agent import store
from app.matcha.services.matcha_work.project_agent.agent import (
    _fold_usage,
    _safe_for_audit,
)

from . import board, flights, images
from .page_extract import extract_page, page_urls
from .prompt import build_system_prompt
from .schema import normalize_result
from .tools import RESPONSE_INCLUDE, declarations

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
_MAX_FLIGHT_SEARCHES = 3
# One search's time budget. The search itself stops at it and keeps whatever
# finished (flights.SEARCH_SECONDS); the wait_for below is only a backstop.
_FLIGHT_SEARCH_SECONDS = 100.0
_MIN_FLIGHT_SEARCH_SECONDS = 30.0
_AI_USAGE_FEATURE = "matcha.espresso.agent_card"
_FINISH_CHOICE = {"type": "function", "name": "finish"}


class CardAgentError(RuntimeError):
    """A run that ended without a usable result; the message is user-facing."""


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or url)[:60]
    except ValueError:
        return url[:60]


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
    started = time.monotonic()
    client = get_luna_client()
    usage: dict[str, Any] = {"model": CARD_AGENT_MODEL}
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

    model_calls = 0
    search_calls = 0
    fetches = 0
    repairs = 0
    seq = 0
    result: dict | None = None
    warnings: list[str] = []

    async def step(tool: str, kind: str, label: str, args: dict, out: dict, status: str = "ok") -> None:
        nonlocal seq
        seq += 1
        await store.record_step(run_id, seq, tool, kind, label[:200], _safe_for_audit(args), _safe_for_audit(out), status)

    async def progress(note: str) -> None:
        row = await board.set_progress(task_id, note)
        if row:
            await board.publish_task_updated(project_id, row)

    input_items = [text_item("user", _user_turn(ask, review_note, previous_result))]
    pending: list[dict[str, Any]] = []
    travel = flights.is_travel_ask(ask)
    flight_token = flights.token() if travel else None
    flight_session = flights.FlightSession(flight_token) if flight_token else None
    flight_searches = 0
    instructions = build_system_prompt(round, travel=travel, flight_search=flight_session is not None)
    tools = declarations(flights=flight_session is not None)
    await progress("Searching the web…" if round == 1 else "Working on your feedback…")

    while result is None and model_calls < _MAX_MODEL_CALLS:
        elapsed = time.monotonic() - started
        if elapsed >= _WALL_SECONDS:
            break
        model_calls += 1
        last_call = model_calls == _MAX_MODEL_CALLS or elapsed > _WALL_SECONDS * 0.8
        searches_left = max(0, _MAX_SEARCHES_PER_RUN - search_calls)
        call_timeout = max(5.0, _WALL_SECONDS - elapsed)
        with feature_scope(_AI_USAGE_FEATURE):
            response = await asyncio.wait_for(
                client.create_response(
                    model=CARD_AGENT_MODEL,
                    input=input_items if model_calls == 1 else pending,
                    instructions=instructions,
                    # Out of search budget (or out of turns): only our function
                    # tools remain, and the last turn must finish.
                    tools=tools if searches_left and not last_call else tools[1:],
                    tool_choice=_FINISH_CHOICE if last_call else "auto",
                    reasoning_effort="medium",
                    max_tool_calls=min(_MAX_SEARCHES_PER_RESPONSE, searches_left) if searches_left and not last_call else None,
                    include=RESPONSE_INCLUDE,
                    timeout_seconds=call_timeout,
                ),
                timeout=call_timeout,
            )
        _fold_usage(usage, response)
        searches = web_search_calls(response.output_items)
        search_calls += len(searches)
        stats.update(model_calls=model_calls, search_calls=search_calls, token_usage=usage)
        provenance.update(cited_urls(response.output_items))
        for search in searches:
            query = str((search.get("action") or {}).get("query") or "")
            await step("web_search", "search", f"Searched: {query[:120]}" if query else "Searched the web",
                       {"query": query}, {"status": search.get("status")})
        if searches:
            await progress(f"Searched the web ({search_calls})…")

        if not response.function_calls:
            # Prose instead of a tool call: nudge toward finish on the next turn.
            if model_calls >= _MAX_MODEL_CALLS:
                break
            pending = [text_item("user", "Call the finish tool with the structured result now.")]
            continue

        outputs: list[dict[str, Any]] = []
        for call in response.function_calls:
            name, args = call["name"], dict(call["arguments"] or {})
            if name == "fetch_page":
                url = str(args.get("url") or "").strip()
                if fetches >= _MAX_FETCHES:
                    out = {"error": "Page budget used up; finish with what you have."}
                    await step(name, "fetch", "Page budget exhausted", args, out, "skipped")
                else:
                    fetches += 1
                    await progress(f"Reading {_host(url)}…")
                    remaining = _WALL_SECONDS - (time.monotonic() - started)
                    try:
                        out, vouched = await asyncio.wait_for(
                            fetch_page_tool(url), timeout=max(1.0, min(_FETCH_SECONDS + 5, remaining)),
                        )
                    except TimeoutError:
                        out, vouched = {"error": "The page took too long to load."}, set()
                    provenance.update(vouched)
                    await step(name, "fetch", f"Read {_host(url)}", args,
                               {k: out.get(k) for k in ("url", "title", "error")} | {"products": len(out.get("products") or [])},
                               "error" if "error" in out else "ok")
                outputs.append(tool_output_item(call["call_id"], out))
            elif name == "search_flights" and flight_session is not None:
                seconds = min(_FLIGHT_SEARCH_SECONDS, _WALL_SECONDS - (time.monotonic() - started) - 5.0)
                if flight_searches >= _MAX_FLIGHT_SEARCHES:
                    out = {"error": "Flight search limit reached; finish with the offers you have."}
                    await step(name, "search", "Flight search limit reached", args, out, "skipped")
                elif seconds < _MIN_FLIGHT_SEARCH_SECONDS:
                    out = {"error": "Not enough time left for another flight search; finish with the offers you have."}
                    await step(name, "search", "No time left for a flight search", args, out, "skipped")
                else:
                    flight_searches += 1
                    await progress("Searching flights…")
                    try:
                        out = await asyncio.wait_for(flight_session.search(args, seconds=seconds), timeout=seconds + 10.0)
                    except TimeoutError:
                        out = {"error": "The flight search took too long. Try fewer options, or finish."}
                    except Exception as exc:
                        logger.warning("agent card flight search failed", exc_info=True)
                        out = {"error": f"The flight search failed: {type(exc).__name__}"}
                    options = out.get("options") or []
                    await step(
                        name, "search",
                        f"Searched flights: {out.get('searched') or 'failed'}"[:200], args,
                        {"options": len(options), "offer_requests": out.get("offer_requests"),
                         "error": out.get("error")},
                        "error" if "error" in out else "ok",
                    )
                    if options:
                        await progress(f"Comparing {len(options)} flight options…")
                outputs.append(tool_output_item(call["call_id"], out))
            elif name == "finish":
                try:
                    normalized, warnings = normalize_result(args.get("result"), provenance, flights=flight_session)
                except ValueError as exc:
                    await step(name, "finish", "Result rejected", {"error": str(exc)}, {}, "error")
                    if repairs >= _MAX_REPAIRS:
                        raise CardAgentError("The agent could not produce a usable result.") from exc
                    repairs += 1
                    outputs.append(tool_output_item(call["call_id"], {"error": f"Invalid result: {exc}. Call finish again."}))
                    continue
                result = normalized
                await step(name, "finish", "Prepared the result", {}, {"warnings": warnings[:20]})
                outputs.append(tool_output_item(call["call_id"], {"accepted": True}))
            else:
                outputs.append(tool_output_item(call["call_id"], {"error": f"Unknown tool: {name}"}))
        pending = outputs

    if result is None:
        raise CardAgentError("The agent ran out of time before finishing. Try again, or narrow the request.")

    await progress("Collecting photos…")
    image_warnings = await images.rehost_images(
        result, company_id=company_id, project_id=project_id, task_id=task_id,
        total_seconds=_PHOTO_SECONDS,
    )
    for pick in [result.get("top_pick"), *(result.get("alternatives") or [])]:
        if pick:
            await step("rehost_images", "image", f"Photos for {pick['name'][:80]}", {}, {"kept": len(pick["images"])})
    result["warnings"] = (warnings + image_warnings)[:30]
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
