"""Research browse task — uses Gemini Computer Use + Playwright to extract structured data from URLs."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error, publish_task_progress
from ..utils import get_db_connection

logger = logging.getLogger(__name__)

MAX_TURNS = 20
VIEWPORT_W = 1440
VIEWPORT_H = 900


def _denorm_x(x: int) -> int:
    return int(x * VIEWPORT_W / 1000)


def _denorm_y(y: int) -> int:
    return int(y * VIEWPORT_H / 1000)


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
        ticks = args.get("amount", 3)
        dx = 100 * ticks * (1 if direction == "right" else -1) if direction in ("left", "right") else 0
        dy = 100 * ticks * (1 if direction == "down" else -1) if direction in ("up", "down") else 0
        await page.mouse.wheel(dx, dy)
    elif name == "scroll_at":
        x, y = _denorm_x(args["x"]), _denorm_y(args["y"])
        await page.mouse.move(x, y)
        direction = args.get("direction", "down")
        ticks = args.get("amount", 3)
        dx = 100 * ticks * (1 if direction == "right" else -1) if direction in ("left", "right") else 0
        dy = 100 * ticks * (1 if direction == "down" else -1) if direction in ("up", "down") else 0
        await page.mouse.wheel(dx, dy)
    elif name == "navigate":
        try:
            await page.goto(args["url"], wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass  # page may timeout but still be usable
    elif name == "go_back":
        await page.go_back(wait_until="domcontentloaded", timeout=10000)
    elif name == "go_forward":
        await page.go_forward(wait_until="domcontentloaded", timeout=10000)
    elif name == "key_combination":
        keys = args.get("keys", "")
        await page.keyboard.press(keys.replace(" ", "+"))
    elif name in ("wait_5_seconds", "wait"):
        await asyncio.sleep(min(args.get("seconds", 5), 5))
    elif name == "search":
        query = args.get("query", "")
        await page.goto(f"https://www.google.com/search?q={query}", wait_until="domcontentloaded", timeout=15000)
    else:
        logger.warning("Unknown action: %s %s", name, args)


async def _take_screenshot(page) -> bytes:
    return await page.screenshot(type="png", full_page=False)


async def _browse_and_extract(
    url: str,
    instructions: str,
    model: str | None = None,
    on_progress=None,
) -> dict:
    """Browse a URL using Gemini Computer Use and extract structured data."""
    from google import genai
    from google.genai import types
    from app.config import load_settings

    settings = load_settings()
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

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": VIEWPORT_W, "height": VIEWPORT_H})
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass  # page may partially load
        await asyncio.sleep(2)  # let JS render

        screenshot = await _take_screenshot(page)

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
        for turn in range(MAX_TURNS):
            if on_progress:
                on_progress(turn, MAX_TURNS)

            try:
                response = client.models.generate_content(
                    model=use_model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                logger.error("Gemini API error on turn %d: %s", turn, exc)
                break

            if not response.candidates:
                break

            candidate = response.candidates[0]
            contents.append(candidate.content)

            # Check for function calls (actions to execute)
            function_calls = [p for p in candidate.content.parts if p.function_call]

            if not function_calls:
                # No actions — Gemini is done, extract text response
                text_parts = [p.text for p in candidate.content.parts if p.text]
                if text_parts:
                    raw_text = "\n".join(text_parts)
                    # Try to parse JSON from the response
                    try:
                        # Find JSON in the response
                        start = raw_text.find("{")
                        end = raw_text.rfind("}") + 1
                        if start >= 0 and end > start:
                            extracted = json.loads(raw_text[start:end])
                        else:
                            extracted = {"raw_notes": raw_text}
                    except json.JSONDecodeError:
                        extracted = {"raw_notes": raw_text}
                break

            # Execute actions
            for fc in function_calls:
                action_name = fc.function_call.name
                action_args = dict(fc.function_call.args) if fc.function_call.args else {}
                try:
                    await _execute_action(page, action_name, action_args)
                except Exception as exc:
                    logger.warning("Action %s failed: %s", action_name, exc)

            await asyncio.sleep(1)  # wait for page to update
            screenshot = await _take_screenshot(page)
            current_url = page.url

            # Build function responses with screenshot attached
            fn_response_parts = []
            for fc in function_calls:
                fn_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.function_call.name,
                        response={"url": current_url, "status": "ok"},
                    )
                )

            # Append screenshot as a separate user turn so Gemini sees the new page state
            contents.append(
                types.Content(role="user", parts=fn_response_parts)
            )
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_bytes(data=screenshot, mime_type="image/png")],
                )
            )

        await browser.close()

    if not extracted:
        return {"findings": {}, "summary": "Could not extract data", "error": "No data extracted"}

    summary = extracted.pop("summary", "")
    return {"findings": extracted, "summary": summary, "error": None}


async def _save_research_result(project_id: str, task_id: str, input_id: str, result: dict) -> None:
    """Atomically save a research result to project_data."""
    conn = await get_db_connection()
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE",
                UUID(project_id),
            )
            data = json.loads(row["project_data"]) if isinstance(row["project_data"], str) else (row["project_data"] or {})

            tasks = data.get("research_tasks", [])
            for task in tasks:
                if task.get("id") == task_id:
                    # Update input status
                    for inp in task.get("inputs", []):
                        if inp["id"] == input_id:
                            inp["status"] = "error" if result.get("error") else "completed"
                            inp["completed_at"] = datetime.now(timezone.utc).isoformat()
                            if result.get("error"):
                                inp["error"] = result["error"]
                            break

                    # Append/replace result
                    results = task.get("results", [])
                    results = [r for r in results if r.get("input_id") != input_id]
                    results.append({
                        "input_id": input_id,
                        "findings": result.get("findings", {}),
                        "summary": result.get("summary", ""),
                    })
                    task["results"] = results
                    break

            data["research_tasks"] = tasks
            await conn.execute(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
                json.dumps(data), UUID(project_id),
            )
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1, time_limit=600, soft_time_limit=540)
def run_research_browse(
    self,
    project_id: str,
    task_id: str,
    input_id: str,
    url: str,
    instructions: str,
    company_id: str,
) -> dict:
    """Browse a URL and extract structured data using Gemini Computer Use."""
    channel = f"company:{company_id}"

    def on_progress(turn, total):
        publish_task_progress(
            channel=channel,
            task_type="research_browse",
            entity_id=input_id,
            progress=turn + 1,
            total=total,
            message=f"Browsing {url} (step {turn + 1}/{total})...",
        )

    async def _run():
        result = await _browse_and_extract(url, instructions, on_progress=on_progress)
        await _save_research_result(project_id, task_id, input_id, result)
        return result

    try:
        result = asyncio.run(_run())

        publish_task_complete(
            channel=channel,
            task_type="research_browse",
            entity_id=input_id,
            result={"url": url, "findings": result.get("findings", {})},
        )
        return {"status": "success", "url": url, "findings": result.get("findings", {})}

    except Exception as exc:
        logger.error("Research browse failed for %s: %s", url, exc)
        error_result = {
            "findings": {},
            "summary": "",
            "error": str(exc)[:500],
        }
        try:
            asyncio.run(_save_research_result(project_id, task_id, input_id, error_result))
        except Exception as save_exc:
            logger.warning("Failed to save error result for %s: %s", input_id, save_exc)

        publish_task_error(
            channel=channel,
            task_type="research_browse",
            entity_id=input_id,
            error=str(exc)[:500],
        )
        raise self.retry(exc=exc, countdown=60)
