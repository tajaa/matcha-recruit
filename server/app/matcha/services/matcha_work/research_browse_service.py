"""Research browse service — Gemini Computer Use + Playwright for structured data extraction."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from ....database import get_connection

logger = logging.getLogger(__name__)

MAX_TURNS = 15
BROWSE_TIMEOUT_SECONDS = 180  # 3 minute hard limit per URL


def _parse_findings(raw_text: str, *, prose_as_summary: bool = True) -> dict | None:
    """The JSON object in a model reply. Prose with no object in it becomes the
    summary, unless the caller would rather have nothing."""
    try:
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw_text[start:end])
    except json.JSONDecodeError:
        return {"summary": raw_text}
    return {"summary": raw_text} if prose_as_summary else None


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
    from google.genai import types
    from app.matcha.services._shared.gemini import genai_env_client
    from ....config import get_settings

    from .browser import computer_use
    from .browser.session import BrowsePolicy, host_allowed, open_page

    settings = get_settings()
    use_model = model or settings.analysis_model

    client = genai_env_client()

    system_prompt = (
        f"You are a research assistant browsing a website to extract specific data.\n\n"
        f"TASK:\n{instructions}\n\n"
        f"Browse the page, click through relevant sections (floor plans, pricing, availability, lease terms, etc.), "
        f"and gather the requested information. Navigate multiple pages if needed.\n\n"
        f"When you have enough data, stop browsing and return a JSON object with your findings. "
        f"Use descriptive key names based on what you found. Include a 'summary' key with a brief overview."
    )

    # Research follows links wherever they lead, so there is no navigation
    # allowlist. What the browser can CONNECT to is still limited to public
    # addresses by the egress proxy every session runs behind.
    policy = BrowsePolicy(allowed_hosts=None, max_turns=MAX_TURNS, wall_seconds=BROWSE_TIMEOUT_SECONDS)
    screenshot_url = None
    async with open_page(policy) as session:
        page = session.page

        if on_status:
            await on_status(f"Navigating to {url}...")
        if host_allowed(url, policy.allowed_hosts):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
        await asyncio.sleep(2)

        outcome = await computer_use.run(
            page, instructions=system_prompt, model=use_model, policy=policy,
            client=client, on_status=on_status,
        )
        total_tokens_used = outcome.total_tokens
        contents = outcome.contents
        extracted = _parse_findings(outcome.text) if outcome.text else None

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
                        extracted = _parse_findings("\n".join(text_parts), prose_as_summary=False) or extracted
            except Exception as exc:
                logger.warning("Final extraction attempt failed: %s", exc)

        # Capture a reference screenshot before closing
        if capture_screenshot and company_id:
            try:
                final_screenshot = await page.screenshot(type="png", full_page=False)
                from ....core.services.storage import get_storage
                import hashlib
                fname = f"research-{hashlib.md5(url.encode()).hexdigest()[:8]}.png"
                screenshot_url = await get_storage().upload_file(
                    final_screenshot, fname,
                    prefix=f"matcha-work/{company_id}/research-screenshots",
                    content_type="image/png",
                )
            except Exception as exc:
                logger.warning("Failed to capture reference screenshot: %s", exc)

    if not extracted:
        return {"findings": {}, "summary": "Could not extract data", "error": "No data extracted", "screenshot_url": screenshot_url, "total_tokens": total_tokens_used}

    # Auto-call if phone found + info missing + Twilio configured
    phone = _extract_phone_number(extracted)
    missing = _identify_missing_info(instructions, extracted)
    if phone and missing and _twilio_configured():
        apartment_name = extracted.get("name") or extracted.get("property_name") or extracted.get("apartment_name") or "the property"
        if on_status:
            await on_status(f"Calling {apartment_name} at {phone} to ask about: {', '.join(missing)}...")
        try:
            from ....core.services.twilio_call_service import get_twilio_call_service
            call_service = get_twilio_call_service()
            call_result = await call_service.initiate_and_wait(
                to_number=phone,
                apartment_name=str(apartment_name),
                missing_info=missing,
                timeout=330,
            )
            if call_result.findings:
                extracted.update(call_result.findings)
            if call_result.transcript:
                extracted["_phone_call_transcript"] = call_result.transcript
                extracted["_phone_call_made"] = True
            if call_result.error and on_status:
                await on_status(f"Phone call issue: {call_result.error}")
            elif on_status:
                await on_status(f"Phone call complete")
        except Exception as exc:
            logger.warning("Auto-call failed for %s: %s", phone, exc)
            if on_status:
                await on_status(f"Phone call failed: {str(exc)[:80]}")

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
    from ..billing import token_budget_service

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


# ── Phone call helpers ──


def _extract_phone_number(findings: dict) -> str | None:
    """Extract and normalize a phone number from research findings."""
    import re
    phone_keys = ("phone", "phone_number", "office_phone", "leasing_phone",
                  "contact_phone", "contact_info")
    for key, val in findings.items():
        if any(pk in key.lower() for pk in phone_keys):
            if isinstance(val, str):
                raw = val
            elif isinstance(val, dict):
                raw = val.get("phone", "") or val.get("phone_number", "") or str(val)
            else:
                continue
            from ....core.services.twilio_call_service import normalize_phone_number
            normalized = normalize_phone_number(raw)
            if normalized:
                return normalized
    return None


def _identify_missing_info(instructions: str, findings: dict) -> list[str]:
    """Identify what the instructions asked for that wasn't found in findings."""
    keywords_map = {
        "deposit": ["deposit", "security deposit"],
        "lease terms": ["lease", "lease term", "lease length", "short term"],
        "pet policy": ["pet", "pet deposit", "pet rent"],
        "utilities": ["utilities", "utility", "water", "electric"],
        "parking": ["parking", "garage"],
        "move-in costs": ["move-in", "move in cost", "application fee"],
        "availability": ["available", "availability", "move-in date"],
        "pricing": ["price", "pricing", "rent", "cost"],
    }

    instructions_lower = instructions.lower()
    findings_text = json.dumps(findings).lower()
    missing = []

    for field_name, keywords in keywords_map.items():
        # Was this asked for in instructions?
        if any(kw in instructions_lower for kw in keywords):
            # Is it missing or null in findings?
            if not any(kw in findings_text for kw in keywords):
                missing.append(field_name)

    return missing


def _twilio_configured() -> bool:
    """Check if Twilio is configured for outbound calls."""
    from ....config import get_settings
    settings = get_settings()
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_phone_number)
