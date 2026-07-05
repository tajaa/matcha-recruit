"""Legal Pilot intake auto-parse — Gemini reads an uploaded complaint /
subpoena / agency charge PDF and extracts a DRAFT matter (type, allegation,
parties, dates, jurisdiction) so the user never transcribes served papers.

Mirrors ``contract_parser``: cached IRAnalyzer, the PDF sent to Gemini as an
inline part, JSON parsed back and clamped to the matter shape, parse-and-
discard (the document is never stored). Best-effort, never raises — returns
an empty draft with available=False on any failure.

The draft NEVER auto-creates a matter — a legal record requires human review
before it exists (same rule as ir_voice_intake). The route returns it to the
intake form for the user to confirm/edit.
"""

import asyncio
import json
import logging
import re
from datetime import date
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

_MATTER_TYPES = ("subpoena", "class_action", "eeoc_charge", "single_plaintiff", "audit", "other")

_PROMPT = """You are a legal-intake assistant. From the attached LEGAL DOCUMENT (a served complaint, class-action filing, subpoena, EEOC or state-agency charge, or regulator audit notice), extract the intake facts an employer needs to open a matter file.

Return ONLY valid JSON with exactly these keys:
{"matter_type": "<one of: subpoena, class_action, eeoc_charge, single_plaintiff, audit, other>",
 "title": "<short case caption, e.g. 'Doe v. Acme Corp' or 'EEOC Charge 480-2026-01234', max 120 chars>",
 "allegation": "<neutral 1-3 sentence summary of what is being claimed/demanded, max 1200 chars>",
 "plaintiff": "<claimant / charging party / issuing agency, or null>",
 "defendant": "<the responding employer entity as named, or null>",
 "jurisdiction_state": "<2-letter US state the dispute is grounded in, or null>",
 "evidence_start": "<ISO date the claimed conduct window starts, or null>",
 "evidence_end": "<ISO date the claimed conduct window ends, or null>",
 "response_deadline": "<ISO date a response/appearance/production is due, or null>"}

Rules: state facts from the document only — never infer, never embellish. If the document gives a relative deadline ("within 30 days of service") and a service date, compute the date; otherwise null. Dates must be YYYY-MM-DD."""


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


_STATE_RE = re.compile(r"^[A-Za-z]{2}$")


def _clamp_date(v) -> str | None:
    """ISO date string or None — garbage never reaches the form. Pure."""
    if not v or not isinstance(v, str):
        return None
    try:
        return date.fromisoformat(v[:10]).isoformat()
    except ValueError:
        return None


def _clamp_str(v, limit: int) -> str | None:
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    return s[:limit] if s else None


def coerce_draft(payload: dict) -> dict:
    """Clamp model output into the intake-form shape. Pure (unit-tested)."""
    payload = payload if isinstance(payload, dict) else {}
    mt = payload.get("matter_type")
    matter_type = mt if mt in _MATTER_TYPES else "other"
    # Validate the FULL string before any truncation — clamping "Nevada" to
    # 2 chars first would mint "NE" (Nebraska), silently the wrong state.
    raw_state = payload.get("jurisdiction_state")
    state = raw_state.strip() if isinstance(raw_state, str) else ""
    if not _STATE_RE.match(state):
        state = None
    start = _clamp_date(payload.get("evidence_start"))
    end = _clamp_date(payload.get("evidence_end"))
    if start and end and start > end:
        start, end = end, start
    return {
        "matter_type": matter_type,
        "title": _clamp_str(payload.get("title"), 120),
        "allegation": _clamp_str(payload.get("allegation"), 1200),
        "plaintiff": _clamp_str(payload.get("plaintiff"), 200),
        "defendant": _clamp_str(payload.get("defendant"), 200),
        "jurisdiction_state": state.upper() if state else None,
        "evidence_start": start,
        "evidence_end": end,
        "response_deadline": _clamp_date(payload.get("response_deadline")),
    }


async def parse_intake_document(pdf_bytes: bytes) -> dict:
    """Best-effort parse → draft matter fields + available flag. Never raises;
    on failure returns an empty draft with available=False."""
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
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
        logger.warning("Legal intake parse failed: %s", exc)
        payload = {}
    return {**coerce_draft(payload), "available": bool(payload)}
