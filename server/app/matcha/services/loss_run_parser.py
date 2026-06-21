"""Loss-run PDF auto-parse — Gemini extracts WC summary figures from a carrier
loss-run document so the broker doesn't hand-key them (WTW p.11 "digitize more of
the value chain"). Best-effort, never raises — returns a draft the broker reviews
and confirms before saving (it does NOT auto-commit to broker_external_wc).

Mirrors the broker_submission coverage-gap pattern: cached IRAnalyzer, the PDF
sent to Gemini as an inline part, JSON parsed back into the ExternalWc shape.
"""

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

# integer claim-count fields + float/text fields in the ExternalWc shape
_INT_FIELDS = (
    "recordable_cases", "dart_cases", "lost_days", "restricted_days", "ct_cases",
    "acute_cases", "post_termination_cases", "lost_time_open", "lost_time_resolved",
)
_FLOAT_FIELDS = ("avg_days_to_rtw", "current_emr", "annual_premium")

_PROMPT = """You are an insurance analyst. From the attached carrier workers'-compensation LOSS RUN, extract summary figures for the most recent complete policy period.

Return ONLY valid JSON with exactly these keys (use 0 for unknown counts, null for unknown text/numbers):
{"period_label": "<e.g. 2023-2024 policy year>",
 "recordable_cases": <int — total claims>,
 "dart_cases": <int — days-away/restricted/transfer claims>,
 "lost_days": <int — total lost workdays>,
 "restricted_days": <int — total restricted/light-duty days>,
 "ct_cases": <int — cumulative-trauma claims>,
 "acute_cases": <int — acute/specific-injury claims>,
 "post_termination_cases": <int — claims filed after employment ended>,
 "lost_time_open": <int — open lost-time claims>,
 "lost_time_resolved": <int — closed lost-time claims>,
 "avg_days_to_rtw": <number or null — average days to return to work>,
 "current_emr": <number or null — experience modification rate>,
 "carrier": "<carrier name or null>",
 "annual_premium": <number or null>}

Count CLAIMS (not dollar amounts) for the *_cases / *_days fields. Do not invent values."""


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


def _coerce(payload: dict) -> dict:
    """Clamp the model output into the ExternalWc field schema."""
    out: dict = {"period_label": payload.get("period_label") or None,
                 "carrier": payload.get("carrier") or None}
    for k in _INT_FIELDS:
        try:
            out[k] = max(0, int(payload.get(k) or 0))
        except (TypeError, ValueError):
            out[k] = 0
    for k in _FLOAT_FIELDS:
        v = payload.get(k)
        try:
            out[k] = float(v) if v is not None else None
        except (TypeError, ValueError):
            out[k] = None
    # respect the ExternalWcBody validators (emr 0<x<=10, others >=0)
    if out.get("current_emr") is not None and not (0 < out["current_emr"] <= 10):
        out["current_emr"] = None
    for k in ("avg_days_to_rtw", "annual_premium"):
        if out.get(k) is not None and out[k] < 0:
            out[k] = None
    return out


async def parse_loss_run(pdf_bytes: bytes) -> dict:
    """Best-effort parse → {"fields": {...ExternalWc...}, "available": bool}.
    Never raises; on failure returns zeroed fields with available=False."""
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
        logger.warning("Loss-run parse failed: %s", exc)
        payload = {}
    return {"fields": _coerce(payload), "available": bool(payload), "model": analyzer.model}
