"""One loop that drives a page with Gemini Computer Use.

The model sees a screenshot and asks for an action (click, type, scroll,
navigate); the action is carried out with Playwright and the next screenshot
goes back. `before_action` is the caller's hook: it sees every action before it
happens and can refuse it or end the run, which is how a booking stops at a
payment form instead of typing into it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal
from urllib.parse import quote_plus

from .session import VIEWPORT_H, VIEWPORT_W, BrowsePolicy, host_allowed

logger = logging.getLogger(__name__)

_MODEL_CALL_SECONDS = 30.0
SEARCH_URL = "https://www.google.com/search?q="


@dataclass(frozen=True)
class ActionVerdict:
    """What `before_action` decided. `stop` ends the loop with that reason."""

    allow: bool = True
    stop: str | None = None
    note: str | None = None
    args: dict | None = None  # replacement arguments (placeholders filled in)


@dataclass
class Outcome:
    text: str = ""
    turns: int = 0
    total_tokens: int = 0
    stopped: str | None = None  # a before_action stop reason, "turns", "time", or None
    error: str | None = None
    final_url: str | None = None
    refused: list[str] = field(default_factory=list)
    contents: list = field(default_factory=list)


BeforeAction = Callable[[Any, str, dict], Awaitable[ActionVerdict | None]]
OnStatus = Callable[[str], Awaitable[None]]


def _denorm_x(x) -> int:
    return int(float(x) * VIEWPORT_W / 1000)


def _denorm_y(y) -> int:
    return int(float(y) * VIEWPORT_H / 1000)


async def execute_action(page, name: str, args: dict, policy: BrowsePolicy) -> Literal["ok", "refused", "unknown"]:
    """Translate one Computer Use action to Playwright calls."""
    if name == "click_at":
        await page.mouse.click(_denorm_x(args["x"]), _denorm_y(args["y"]))
    elif name == "double_click_at":
        await page.mouse.dblclick(_denorm_x(args["x"]), _denorm_y(args["y"]))
    elif name == "hover_at":
        await page.mouse.move(_denorm_x(args["x"]), _denorm_y(args["y"]))
    elif name == "type_text_at":
        x, y = _denorm_x(args["x"]), _denorm_y(args["y"])
        await page.mouse.click(x, y)
        if args.get("clear_before_typing"):
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
        await page.keyboard.type(args.get("text", ""))
        if args.get("press_enter_after_typing"):
            await page.keyboard.press("Enter")
    elif name in ("scroll_document", "scroll_at"):
        if name == "scroll_at":
            await page.mouse.move(_denorm_x(args["x"]), _denorm_y(args["y"]))
        direction = args.get("direction", "down")
        ticks = int(args.get("amount", 3))
        dx = 100 * ticks * (1 if direction == "right" else -1) if direction in ("left", "right") else 0
        dy = 100 * ticks * (1 if direction == "down" else -1) if direction in ("up", "down") else 0
        await page.mouse.wheel(dx, dy)
    elif name == "navigate":
        url = str(args.get("url") or "")
        if not host_allowed(url, policy.allowed_hosts):
            return "refused"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
    elif name == "go_back":
        await page.go_back(wait_until="domcontentloaded", timeout=10000)
    elif name == "go_forward":
        await page.go_forward(wait_until="domcontentloaded", timeout=10000)
    elif name == "key_combination":
        await page.keyboard.press(str(args.get("keys", "")).replace(" ", "+"))
    elif name in ("wait_5_seconds", "wait"):
        await asyncio.sleep(min(float(args.get("seconds", 5)), 5))
    elif name == "search":
        url = SEARCH_URL + quote_plus(str(args.get("query", "")))
        if not host_allowed(url, policy.allowed_hosts):
            return "refused"
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
    else:
        logger.warning("Unknown browser action: %s", name)
        return "unknown"
    return "ok"


def describe_action(name: str, args: dict) -> str:
    if name == "navigate":
        return f"navigating to {str(args.get('url', ''))[:60]}"
    if name in ("click_at", "double_click_at"):
        return "clicking on element"
    if name in ("scroll_document", "scroll_at"):
        return f"scrolling {args.get('direction', 'down')}"
    if name == "type_text_at":
        return "typing text"
    return name.replace("_", " ")


async def run(
    page,
    *,
    instructions: str,
    model: str,
    policy: BrowsePolicy,
    client: Any | None = None,
    before_action: BeforeAction | None = None,
    on_status: OnStatus | None = None,
    settle_seconds: float = 1.0,
) -> Outcome:
    """Drive `page` until the model answers in text, a hook stops it, or the
    turn / time budget runs out. The page must already be where it should start."""
    from google.genai import types

    if client is None:
        from app.matcha.services._shared.gemini import genai_env_client

        client = genai_env_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(computer_use=types.ComputerUse(
            environment=types.Environment.ENVIRONMENT_BROWSER,
        ))],
    )
    started = time.monotonic()
    outcome = Outcome()
    screenshot = await page.screenshot(type="png", full_page=False)
    contents = [types.Content(role="user", parts=[
        types.Part(text=instructions),
        types.Part.from_bytes(data=screenshot, mime_type="image/png"),
    ])]
    outcome.contents = contents

    for turn in range(policy.max_turns):
        if time.monotonic() - started >= policy.wall_seconds:
            outcome.stopped = "time"
            break
        outcome.turns = turn + 1
        if on_status:
            await on_status(f"Analyzing page... (step {turn + 1}/{policy.max_turns})")
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(client.models.generate_content, model=model, contents=contents, config=config),
                timeout=_MODEL_CALL_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Browser model call timed out on turn %d", turn)
            if on_status:
                await on_status(f"Step {turn + 1}: API call timed out, finishing up...")
            outcome.error = "model_timeout"
            break
        except Exception as exc:
            logger.error("Browser model error on turn %d: %s", turn, exc)
            outcome.error = type(exc).__name__
            break

        usage = getattr(response, "usage_metadata", None)
        if usage:
            outcome.total_tokens += getattr(usage, "total_token_count", 0) or 0
        if not response.candidates:
            break
        candidate = response.candidates[0]
        contents.append(candidate.content)
        calls = [part for part in candidate.content.parts if part.function_call]
        if not calls:
            outcome.text = "\n".join(part.text for part in candidate.content.parts if part.text)
            break

        statuses: list[str] = []
        for call in calls:
            name = call.function_call.name
            args = dict(call.function_call.args) if call.function_call.args else {}
            verdict = await before_action(page, name, args) if before_action else None
            if verdict is not None and verdict.stop:
                outcome.stopped = verdict.stop
                outcome.final_url = page.url
                return outcome
            if verdict is not None and not verdict.allow:
                outcome.refused.append(verdict.note or name)
                statuses.append(f"refused: {verdict.note or 'not allowed'}")
                continue
            if verdict is not None and verdict.args is not None:
                args = verdict.args
            if on_status:
                await on_status(f"Step {turn + 1}: {describe_action(name, args)}...")
            try:
                result = await execute_action(page, name, args, policy)
            except Exception as exc:
                logger.warning("Browser action %s failed: %s", name, exc)
                result = "ok"
            if result == "refused":
                outcome.refused.append(f"{name} outside the allowed site")
                statuses.append("refused: that address is outside the site you may use")
            else:
                statuses.append("ok")

        await asyncio.sleep(settle_seconds)
        screenshot = await page.screenshot(type="png", full_page=False)
        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(
                name=call.function_call.name, response={"url": page.url, "status": status},
            )
            for call, status in zip(calls, statuses)
        ]))
        contents.append(types.Content(role="user", parts=[
            types.Part.from_bytes(data=screenshot, mime_type="image/png"),
        ]))
    else:
        outcome.stopped = "turns"

    outcome.final_url = page.url
    return outcome
