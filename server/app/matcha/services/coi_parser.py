"""Best-effort Gemini extraction of an inbound Certificate of Insurance (ACORD 25).

Mirrors ``contract_parser``: one multimodal Gemini call over the certificate PDF
→ carrier, certificate number, holder, and the CARRIED limits/dates per line.
Never raises — a failed/edge parse returns ``available: False`` so the caller can
fall back to manual entry ("a draft beats a 500"). The extracted limits become
the ``carried`` argument to ``limit_adequacy.analyze`` for auto-verification.
"""

import asyncio
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer
from . import limit_adequacy as la

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

_PROMPT = """You are an insurance certificate analyst. From the attached CERTIFICATE OF INSURANCE (ACORD 25 or similar), extract the CARRIED coverage the certificate evidences.

Return ONLY valid JSON with exactly these keys:
{"carrier": "<primary insurer / carrier name, or null>",
 "certificate_number": "<certificate number, or null>",
 "holder_name": "<the certificate holder (the party the cert is issued TO), or null>",
 "insured_name": "<the named insured on the policy, or null>",
 "lines": [
   {"line": "<one of: General Liability, Commercial Auto, Umbrella/Excess, Workers Compensation, Employers Liability, Employment Practices, Professional Liability, Cyber, Property>",
    "per_occurrence": <per-occurrence / each-accident limit in whole dollars, or null>,
    "aggregate": <aggregate limit in whole dollars, or null>,
    "effective_date": "<YYYY-MM-DD policy effective date, or null>",
    "expiry_date": "<YYYY-MM-DD policy expiration date, or null>",
    "additional_insured": <true if the ADDL INSD box is checked for this line>,
    "waiver_of_subrogation": <true if the SUBR WVD box is checked for this line>}
 ]}

Rules: only include lines the certificate actually shows. Convert "$1,000,000" / "$1M" to 1000000. Dates as YYYY-MM-DD. Do not invent coverage the certificate does not evidence."""


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


def _coerce_lines(raw) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        line = la.normalize_line(item.get("line"))
        if not line:
            continue
        out.append({
            "line": line,
            "per_occurrence": la._num(item.get("per_occurrence")),
            "aggregate": la._num(item.get("aggregate")),
            "effective_date": item.get("effective_date") if isinstance(item.get("effective_date"), str) else None,
            "expiry_date": item.get("expiry_date") if isinstance(item.get("expiry_date"), str) else None,
            "additional_insured": bool(item.get("additional_insured")),
            "waiver_of_subrogation": bool(item.get("waiver_of_subrogation")),
        })
    return out


async def parse_certificate(pdf_bytes: bytes) -> dict:
    """Extract carrier/holder/lines from a COI PDF. Best-effort; never raises."""
    analyzer = _get_analyzer()
    payload: dict = {}
    try:
        from google.genai import types
        part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        response = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(
                model=analyzer.model, contents=[_PROMPT, part]),
            timeout=90,
        )
        raw = (getattr(response, "text", None) or "").strip()
        payload = analyzer._parse_json_response(raw) or {}
    except Exception as exc:  # best-effort; never raises
        logger.warning("COI parse failed: %s", exc)
        payload = {}

    def _txt(v):
        return v.strip()[:255] if isinstance(v, str) and v.strip() else None

    lines = _coerce_lines(payload.get("lines"))
    return {
        "carrier": _txt(payload.get("carrier")),
        "certificate_number": _txt(payload.get("certificate_number")),
        "holder_name": _txt(payload.get("holder_name")),
        "insured_name": _txt(payload.get("insured_name")),
        "lines": lines,
        "available": bool(payload and lines),
        "model": analyzer.model,
    }


def earliest_expiry(lines: list[dict]) -> Optional[str]:
    """Earliest line expiry_date (YYYY-MM-DD string) across a cert's lines."""
    dates = [ln.get("expiry_date") for ln in lines if ln.get("expiry_date")]
    return min(dates) if dates else None
