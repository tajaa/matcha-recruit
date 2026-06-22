"""Contract insurance-requirement auto-parse — Gemini reads an uploaded customer/
vendor/lease contract and extracts the insurance limits + endorsements the
counterparty requires, so limit-adequacy (#6/#28) can diff them against what the
company carries.

Best-effort, never raises — returns a draft the company reviews and confirms
before it drives the adequacy gaps. Mirrors ``loss_run_parser``: cached
IRAnalyzer, the PDF sent to Gemini as an inline part, JSON parsed back into the
contract-requirement shape, line names normalized to our coverage keys.
"""

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer
from app.matcha.services import limit_adequacy as la

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

_PROMPT = """You are an insurance contract analyst. From the attached CONTRACT (customer/vendor master service agreement, lease, or similar), extract the INSURANCE REQUIREMENTS the other party imposes on our client — i.e. the coverage the client must carry.

Return ONLY valid JSON with exactly these keys:
{"counterparty": "<the other party / customer name, or null>",
 "requirements": [
   {"line": "<one of: General Liability, Commercial Auto, Umbrella/Excess, Workers Compensation, Employers Liability, Employment Practices, Professional Liability, Cyber>",
    "per_occurrence": <required per-occurrence limit in whole dollars, or null>,
    "aggregate": <required aggregate limit in whole dollars, or null>,
    "additional_insured": <true if the contract requires additional-insured status>,
    "waiver_of_subrogation": <true if a waiver of subrogation is required>,
    "primary_noncontributory": <true if primary & non-contributory wording is required>,
    "note": "<short quote or paraphrase of the requirement, or null>"}
 ]}

Only include lines the contract actually names. Convert "$1,000,000" / "$1M" / "one million" to 1000000. If a single combined limit is given, put it in per_occurrence. Do not invent requirements that are not in the document."""


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


def _coerce_requirements(payload: dict) -> list[dict]:
    """Clamp model output into the stored requirement shape; normalize line keys,
    drop rows whose line we don't recognize."""
    out: list[dict] = []
    for req in payload.get("requirements") or []:
        if not isinstance(req, dict):
            continue
        line = la.normalize_line(req.get("line"))
        if not line:
            continue
        out.append({
            "line": line,
            "per_occurrence": la._num(req.get("per_occurrence")),
            "aggregate": la._num(req.get("aggregate")),
            "additional_insured": bool(req.get("additional_insured")),
            "waiver_of_subrogation": bool(req.get("waiver_of_subrogation")),
            "primary_noncontributory": bool(req.get("primary_noncontributory")),
            "note": (str(req.get("note")).strip() or None) if req.get("note") else None,
        })
    return out


async def parse_contract(pdf_bytes: bytes) -> dict:
    """Best-effort parse → {"counterparty", "requirements": [...], "available": bool}.
    Never raises; on failure returns empty requirements with available=False."""
    analyzer = _get_analyzer()
    payload: dict = {}
    try:
        from google.genai import types
        part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        response = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=[_PROMPT, part]),
            timeout=90,
        )
        raw = (getattr(response, "text", None) or "").strip()
        payload = analyzer._parse_json_response(raw) or {}
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("Contract parse failed: %s", exc)
        payload = {}
    return {
        "counterparty": (payload.get("counterparty") or None),
        "requirements": _coerce_requirements(payload),
        "available": bool(payload),
        "model": analyzer.model,
    }
