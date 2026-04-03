"""Research browse service — Gemini Computer Use + Playwright for structured data extraction."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

MAX_TURNS = 15
BROWSE_TIMEOUT_SECONDS = 180  # 3 minute hard limit per URL
VIEWPORT_W = 1440
VIEWPORT_H = 900


def _denorm_x(x) -> int:
    return int(float(x) * VIEWPORT_W / 1000)


def _denorm_y(y) -> int:
    return int(float(y) * VIEWPORT_H / 1000)


async def _execute_action(page, name: str, args: dict) -> None:
    """Translate Gemini Computer Use actions to Playwright calls."""
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
    elif name == "scroll_document":
        direction = args.get("direction", "down")
        ticks = int(args.get("amount", 3))
        dx = 100 * ticks * (1 if direction == "right" else -1) if direction in ("left", "right") else 0
        dy = 100 * ticks * (1 if direction == "down" else -1) if direction in ("up", "down") else 0
        await page.mouse.wheel(dx, dy)
    elif name == "scroll_at":
        x, y = _denorm_x(args["x"]), _denorm_y(args["y"])
        await page.mouse.move(x, y)
        direction = args.get("direction", "down")
        ticks = int(args.get("amount", 3))
        dx = 100 * ticks * (1 if direction == "right" else -1) if direction in ("left", "right") else 0
        dy = 100 * ticks * (1 if direction == "down" else -1) if direction in ("up", "down") else 0
        await page.mouse.wheel(dx, dy)
    elif name == "navigate":
        try:
            await page.goto(args["url"], wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
    elif name == "go_back":
        await page.go_back(wait_until="domcontentloaded", timeout=10000)
    elif name == "go_forward":
        await page.go_forward(wait_until="domcontentloaded", timeout=10000)
    elif name == "key_combination":
        keys = args.get("keys", "")
        await page.keyboard.press(keys.replace(" ", "+"))
    elif name in ("wait_5_seconds", "wait"):
        await asyncio.sleep(min(float(args.get("seconds", 5)), 5))
    elif name == "search":
        query = args.get("query", "")
        await page.goto(f"https://www.google.com/search?q={query}", wait_until="domcontentloaded", timeout=15000)
    else:
        logger.warning("Unknown action: %s %s", name, args)


async def browse_and_extract(
    url: str, instructions: str, model: str | None = None,
    on_status=None, capture_screenshot: bool = False, company_id: str | None = None,
) -> dict:
    """Browse a URL using Gemini Computer Use and extract structured data."""
    try:
        return await asyncio.wait_for(
            _browse_and_extract_inner(url, instructions, model, on_status, capture_screenshot, company_id),
            timeout=BROWSE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Research browse timed out after %ds for %s", BROWSE_TIMEOUT_SECONDS, url)
        return {"findings": {}, "summary": f"Timed out after {BROWSE_TIMEOUT_SECONDS}s", "error": "Timed out"}


async def _browse_and_extract_inner(
    url: str, instructions: str, model: str | None = None,
    on_status=None, capture_screenshot: bool = False, company_id: str | None = None,
) -> dict:
    from google import genai
    from google.genai import types
    from ...config import get_settings

    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    use_model = model or settings.analysis_model

    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(
        tools=[
            types.Tool(
                computer_use=types.ComputerUse(
                    environment=types.Environment.ENVIRONMENT_BROWSER,
                )
            )
        ],
    )

    system_prompt = (
        f"You are a research assistant browsing a website to extract specific data.\n\n"
        f"TASK:\n{instructions}\n\n"
        f"Browse the page, click through relevant sections (floor plans, pricing, availability, lease terms, etc.), "
        f"and gather the requested information. Navigate multiple pages if needed.\n\n"
        f"When you have enough data, stop browsing and return a JSON object with your findings. "
        f"Use descriptive key names based on what you found. Include a 'summary' key with a brief overview."
    )

    from playwright.async_api import async_playwright

    screenshot_url = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": VIEWPORT_W, "height": VIEWPORT_H})
        page = await context.new_page()

        if on_status:
            await on_status(f"Navigating to {url}...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(2)

        screenshot = await page.screenshot(type="png", full_page=False)

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=system_prompt),
                    types.Part.from_bytes(data=screenshot, mime_type="image/png"),
                ],
            )
        ]

        extracted = None
        total_tokens_used = 0
        for turn in range(MAX_TURNS):
            logger.info("Research browse %s turn %d/%d", url, turn + 1, MAX_TURNS)
            if on_status:
                await on_status(f"Analyzing page... (step {turn + 1}/{MAX_TURNS})")

            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=use_model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning("Gemini API call timed out on turn %d", turn)
                if on_status:
                    await on_status(f"Step {turn + 1}: API call timed out, finishing up...")
                break
            except Exception as exc:
                logger.error("Gemini API error on turn %d: %s", turn, exc)
                break

            # Track token usage from response metadata
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                um = response.usage_metadata
                turn_tokens = getattr(um, 'total_token_count', 0) or 0
                total_tokens_used += turn_tokens

            if not response.candidates:
                break

            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [pt for pt in candidate.content.parts if pt.function_call]

            if not function_calls:
                text_parts = [pt.text for pt in candidate.content.parts if pt.text]
                if text_parts:
                    raw_text = "\n".join(text_parts)
                    try:
                        start = raw_text.find("{")
                        end = raw_text.rfind("}") + 1
                        if start >= 0 and end > start:
                            extracted = json.loads(raw_text[start:end])
                        else:
                            extracted = {"summary": raw_text}
                    except json.JSONDecodeError:
                        extracted = {"summary": raw_text}
                break

            for fc in function_calls:
                action_name = fc.function_call.name
                action_args = dict(fc.function_call.args) if fc.function_call.args else {}
                if on_status:
                    action_desc = action_name.replace("_", " ")
                    if action_name == "navigate":
                        action_desc = f"navigating to {action_args.get('url', '')[:60]}"
                    elif action_name in ("click_at", "double_click_at"):
                        action_desc = "clicking on element"
                    elif action_name in ("scroll_document", "scroll_at"):
                        action_desc = f"scrolling {action_args.get('direction', 'down')}"
                    elif action_name == "type_text_at":
                        action_desc = f"typing text"
                    await on_status(f"Step {turn + 1}: {action_desc}...")
                try:
                    await _execute_action(page, action_name, action_args)
                except Exception as exc:
                    logger.warning("Action %s failed: %s", action_name, exc)

            await asyncio.sleep(1)
            screenshot = await page.screenshot(type="png", full_page=False)
            current_url = page.url

            fn_response_parts = []
            for fc in function_calls:
                fn_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.function_call.name,
                        response={"url": current_url, "status": "ok"},
                    )
                )

            contents.append(types.Content(role="user", parts=fn_response_parts))
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_bytes(data=screenshot, mime_type="image/png")],
                )
            )

        # If loop exhausted without extraction, ask Gemini to summarize what it found
        if not extracted:
            if on_status:
                await on_status("Compiling findings...")
            try:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=(
                        "Stop browsing. Based on everything you've seen so far, return a JSON object "
                        "with your findings. Use descriptive key names. Include a 'summary' key."
                    ))],
                ))
                final_resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=use_model,
                        contents=contents,
                        config=types.GenerateContentConfig(),  # no tools — force text response
                    ),
                    timeout=20,
                )
                if final_resp.candidates:
                    text_parts = [pt.text for pt in final_resp.candidates[0].content.parts if pt.text]
                    if text_parts:
                        raw_text = "\n".join(text_parts)
                        try:
                            start = raw_text.find("{")
                            end = raw_text.rfind("}") + 1
                            if start >= 0 and end > start:
                                extracted = json.loads(raw_text[start:end])
                        except json.JSONDecodeError:
                            extracted = {"summary": raw_text}
            except Exception as exc:
                logger.warning("Final extraction attempt failed: %s", exc)

        # Capture a reference screenshot before closing
        if capture_screenshot and company_id:
            try:
                final_screenshot = await page.screenshot(type="png", full_page=False)
                from ...core.services.storage import get_storage
                import hashlib
                fname = f"research-{hashlib.md5(url.encode()).hexdigest()[:8]}.png"
                screenshot_url = await get_storage().upload_file(
                    final_screenshot, fname,
                    prefix=f"matcha-work/{company_id}/research-screenshots",
                    content_type="image/png",
                )
            except Exception as exc:
                logger.warning("Failed to capture reference screenshot: %s", exc)

        await browser.close()

    if not extracted:
        return {"findings": {}, "summary": "Could not extract data", "error": "No data extracted", "screenshot_url": screenshot_url, "total_tokens": total_tokens_used}

    summary = extracted.pop("summary", "")
    return {"findings": extracted, "summary": summary, "error": None, "screenshot_url": screenshot_url, "total_tokens": total_tokens_used}


async def save_research_result(project_id: UUID, task_id: str, input_id: str, result: dict) -> None:
    """Atomically save a research result to project_data."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE",
                project_id,
            )
            data = json.loads(row["project_data"]) if isinstance(row["project_data"], str) else (row["project_data"] or {})

            for task in data.get("research_tasks", []):
                if task.get("id") == task_id:
                    for inp in task.get("inputs", []):
                        if inp["id"] == input_id:
                            inp["status"] = "error" if result.get("error") else "completed"
                            inp["completed_at"] = datetime.now(timezone.utc).isoformat()
                            if result.get("error"):
                                inp["error"] = result["error"]
                            break

                    results = task.get("results", [])
                    # Merge new findings with previous (for follow-up research)
                    prev = next((r for r in results if r.get("input_id") == input_id), None)
                    merged_findings = {**(prev.get("findings", {}) if prev else {}), **result.get("findings", {})}
                    results = [r for r in results if r.get("input_id") != input_id]
                    result_entry = {
                        "input_id": input_id,
                        "findings": merged_findings,
                        "summary": result.get("summary", "") or (prev.get("summary", "") if prev else ""),
                    }
                    if result.get("screenshot_url"):
                        result_entry["screenshot_url"] = result["screenshot_url"]
                    results.append(result_entry)
                    task["results"] = results
                    break

            data["research_tasks"] = data.get("research_tasks", [])
            await conn.execute(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                json.dumps(data), project_id,
            )


async def run_research_for_input(
    project_id: UUID, task_id: str, input_id: str, url: str, instructions: str,
    on_status=None, capture_screenshot: bool = False, company_id: str | None = None,
) -> dict:
    """Browse a URL and save results. Returns the result dict."""
    from . import token_budget_service

    # Check token budget before starting (if company_id available)
    if company_id:
        try:
            await token_budget_service.check_token_budget(UUID(company_id))
        except Exception:
            error_result = {"findings": {}, "summary": "", "error": "Token budget exhausted"}
            await save_research_result(project_id, task_id, input_id, error_result)
            return error_result

    try:
        result = await browse_and_extract(
            url, instructions, on_status=on_status,
            capture_screenshot=capture_screenshot, company_id=company_id,
        )
        await save_research_result(project_id, task_id, input_id, result)

        # Deduct tokens used
        total_tokens = result.get("total_tokens", 0)
        if total_tokens > 0 and company_id:
            try:
                async with get_connection() as conn:
                    async with conn.transaction():
                        await token_budget_service.deduct_tokens(conn, UUID(company_id), total_tokens)
                logger.info("Research deducted %d tokens for %s", total_tokens, url)
            except Exception as exc:
                logger.warning("Failed to deduct research tokens: %s", exc)

        logger.info("Research complete for %s (%d tokens): %s", url, total_tokens, result.get("summary", "")[:100])
        return result
    except Exception as exc:
        logger.error("Research failed for %s: %s", url, exc)
        error_result = {"findings": {}, "summary": "", "error": str(exc)[:500]}
        await save_research_result(project_id, task_id, input_id, error_result)
        return error_result
