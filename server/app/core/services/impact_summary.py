"""Generate plain-English impact summaries for compliance change alerts.

Uses Gemini Flash Lite for fast, low-cost generation.  Falls back to a
deterministic template when the model is unavailable or rate-limited.
"""

import asyncio
import json
import os
from datetime import date
from typing import Any, Optional
from uuid import UUID

from google import genai
from google.genai import types

from ...config import get_settings

LITE_MODEL = "gemini-3.1-flash-lite-preview"
GENERATION_TIMEOUT = 15  # seconds


def _build_prompt(
    change_info: dict,
    location: dict,
    company_context: dict,
    employee_count: int,
) -> str:
    req = change_info.get("req", {})
    category = req.get("category", "unknown")
    title = req.get("title", "Unknown requirement")
    old_value = change_info.get("old_value", "N/A")
    new_value = change_info.get("new_value", "N/A")
    effective_date = req.get("effective_date", "unknown")
    jurisdiction_name = req.get("jurisdiction_name", "unknown")
    jurisdiction_level = req.get("jurisdiction_level", "")
    industry = company_context.get("industry", "general")
    description = req.get("description", "")

    loc_name = location.get("name") or f"{location.get('city', '')}, {location.get('state', '')}"

    return f"""You are a compliance analyst. Summarize this regulatory change in plain English for an HR administrator.

Change: {category} — {title}
Jurisdiction: {jurisdiction_name} ({jurisdiction_level})
Old value: {old_value}
New value: {new_value}
Effective date: {effective_date}
Location: {loc_name}
Industry: {industry}
Affected employees: approximately {employee_count}
Description: {description}

Write 2-3 concise sentences covering:
1. What changed (be specific about the old and new values)
2. Who it affects at this company
3. What action is needed before the effective date

Do NOT use markdown. Do NOT use bullet points. Write plain prose."""


def _fallback_summary(change_info: dict, location: dict) -> str:
    """Deterministic template when Gemini is unavailable."""
    req = change_info.get("req", {})
    title = req.get("title", "A compliance requirement")
    old_val = change_info.get("old_value", "the previous value")
    new_val = change_info.get("new_value", "a new value")
    jurisdiction = req.get("jurisdiction_name", "your jurisdiction")
    loc_name = location.get("name") or f"{location.get('city', '')}, {location.get('state', '')}"

    return (
        f"{title} changed from {old_val} to {new_val} in {jurisdiction}. "
        f"This may affect employees at {loc_name}. "
        f"Review and update your policies accordingly."
    )


async def generate_impact_summary(
    change_info: dict,
    location: dict,
    company_context: dict,
    conn: Any,
) -> str:
    """Generate a plain-English impact summary for a compliance change.

    Parameters
    ----------
    change_info : dict
        Keys: req, existing, old_value, new_value, requirement_key
    location : dict
        Keys: name, city, state (from business_locations row)
    company_context : dict
        Keys: industry, company_name
    conn : asyncpg.Connection

    Returns
    -------
    str  Plain-English summary (2-3 sentences).
    """
    # Count employees at this location for context
    employee_count = 0
    if location.get("id"):
        count = await conn.fetchval(
            """SELECT COUNT(*) FROM employees
               WHERE company_id = (SELECT company_id FROM business_locations WHERE id = $1)
                 AND status = 'active'""",
            location["id"],
        )
        employee_count = count or 0

    prompt = _build_prompt(change_info, location, company_context, employee_count)

    try:
        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        if not api_key:
            return _fallback_summary(change_info, location)

        client = genai.Client(api_key=api_key)
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=LITE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=300,
                ),
            ),
            timeout=GENERATION_TIMEOUT,
        )
        text = response.text.strip() if response.text else ""
        return text or _fallback_summary(change_info, location)

    except Exception as exc:
        print(f"[Impact Summary] Gemini failed, using fallback: {exc}")
        return _fallback_summary(change_info, location)


async def batch_generate_impact_summaries(
    alert_changes: list[tuple[UUID, dict]],
    location: dict,
    company_context: dict,
    conn: Any,
) -> None:
    """Generate and store impact summaries for a batch of alerts.

    Parameters
    ----------
    alert_changes : list of (alert_id, change_info)
    location : dict with name, city, state, id
    company_context : dict with industry, company_name
    conn : asyncpg.Connection
    """
    for alert_id, change_info in alert_changes:
        summary = await generate_impact_summary(
            change_info, location, company_context, conn
        )
        await conn.execute(
            "UPDATE compliance_alerts SET impact_summary = $1 WHERE id = $2",
            summary,
            alert_id,
        )
