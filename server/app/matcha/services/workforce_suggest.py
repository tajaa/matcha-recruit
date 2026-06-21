"""AI scan & suggest — Gemini proposes starter register rows from the company's
existing data (industry, headcount, job titles, locations, incident history), so
the AI-hiring-tool / biometric / resident-care-safety registers don't start empty
and hand-typed. Best-effort, never raises; the caller confirms before any write.
"""

import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

_COLLECTION_TYPES = {"fingerprint", "face", "iris", "voice", "hand_geometry", "other"}
_PROGRAM_TYPES = {"fall_prevention", "infection_control", "abuse_prevention",
                  "emergency_prep", "medication_safety", "other"}

# kind → (instruction, json shape hint, validator)
_KINDS = {
    "ai_audits": (
        "automated/AI HIRING TOOLS this employer most likely uses (ATS, resume screeners, "
        "video-interview or assessment tools) that need periodic bias audits",
        '[{"tool_name": "<tool>", "vendor": "<vendor or null>", "purpose": "<what it screens>"}]',
    ),
    "biometric": (
        "BIOMETRIC collection points this employer likely operates (e.g. fingerprint/face time "
        "clocks, access control) that need BIPA consent",
        '[{"collection_type": "<fingerprint|face|iris|voice|hand_geometry|other>", "purpose": "<use>"}]',
    ),
    "safety_programs": (
        "resident-care / workplace SAFETY PROGRAMS this employer should run given its industry "
        "and incident history (fall prevention, infection control, abuse prevention, emergency prep, "
        "medication safety)",
        '[{"program_type": "<fall_prevention|infection_control|abuse_prevention|emergency_prep|medication_safety|other>", "name": "<program name>"}]',
    ),
}


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


async def company_context(conn, company_id: UUID) -> dict:
    comp = await conn.fetchrow("SELECT name, industry FROM companies WHERE id = $1", company_id)
    headcount = await conn.fetchval(
        "SELECT headcount FROM company_handbook_profiles WHERE company_id = $1", company_id
    )
    titles = await conn.fetch(
        "SELECT DISTINCT job_title FROM employees WHERE org_id = $1 AND job_title IS NOT NULL LIMIT 25",
        company_id,
    )
    states = await conn.fetch(
        "SELECT DISTINCT state FROM business_locations WHERE company_id = $1 AND state IS NOT NULL", company_id
    )
    cats = await conn.fetch(
        "SELECT incident_type, COUNT(*) n FROM ir_incidents WHERE company_id = $1 "
        "AND incident_type IS NOT NULL GROUP BY incident_type ORDER BY n DESC LIMIT 6",
        company_id,
    )
    return {
        "name": comp["name"] if comp else None,
        "industry": comp["industry"] if comp else None,
        "headcount": int(headcount) if headcount else None,
        "job_titles": [r["job_title"] for r in titles],
        "states": [r["state"] for r in states],
        "incident_types": [r["incident_type"] for r in cats if r["incident_type"]],
    }


def _clean(kind: str, items: list) -> list[dict]:
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if kind == "ai_audits" and it.get("tool_name"):
            out.append({"tool_name": str(it["tool_name"])[:255],
                        "vendor": (str(it["vendor"])[:255] if it.get("vendor") else None),
                        "purpose": (str(it["purpose"])[:255] if it.get("purpose") else None)})
        elif kind == "biometric" and it.get("collection_type") in _COLLECTION_TYPES:
            out.append({"collection_type": it["collection_type"],
                        "purpose": (str(it["purpose"])[:255] if it.get("purpose") else None)})
        elif kind == "safety_programs" and it.get("program_type") in _PROGRAM_TYPES and it.get("name"):
            out.append({"program_type": it["program_type"], "name": str(it["name"])[:255]})
    return out[:8]


async def suggest(conn, company_id: UUID, kind: str) -> dict:
    """{suggestions:[...], available:bool}. Never raises."""
    instruction, shape = _KINDS[kind]
    ctx = await company_context(conn, company_id)
    prompt = (
        f"You are an insurance risk advisor. Given this employer, list the {instruction}.\n\n"
        f"Employer (JSON): {json.dumps(ctx, default=str)}\n\n"
        f"Return ONLY valid JSON of the form {shape}. 3-6 realistic items, specific to this "
        f"employer's industry/size/roles. Do not invent vendor names you're unsure of (use null)."
    )
    analyzer = _get_analyzer()
    items: list = []
    try:
        resp = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=prompt),
            timeout=45,
        )
        parsed = analyzer._parse_json_response((getattr(resp, "text", None) or "").strip())
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            items = parsed.get("suggestions") or parsed.get("items") or []
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("suggest(%s) failed: %s", kind, exc)
    cleaned = _clean(kind, items)
    return {"suggestions": cleaned, "available": bool(cleaned)}
