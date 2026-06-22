"""Experience-rating worksheet PDF auto-parse — Gemini extracts the published
experience mod (and its inputs) from the NCCI / state-bureau worksheet the employer
already receives, so the broker doesn't hand-key the trajectory.

Mirrors ``loss_run_parser`` exactly: cached IRAnalyzer, the PDF sent to Gemini as an
inline part, JSON parsed back into the company_wc_mods shape. Best-effort, never
raises — returns a draft the broker reviews and confirms before saving (it does NOT
auto-commit). The captured mod is the REAL bureau number (source='worksheet'),
distinct from the directional proxy computed from loss-runs.
"""

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

_PROMPT = """You are an insurance analyst. The attached document is a workers'-compensation EXPERIENCE RATING WORKSHEET issued by a rating bureau (NCCI, or a state bureau such as WCIRB / NYCIRB). It states the employer's experience modification factor (the "mod" / "EMR") and the values behind it.

Return ONLY valid JSON with exactly these keys (use null for anything not clearly stated — do not invent):
{"experience_mod": <number — the published experience modification factor, e.g. 1.05; null if absent>,
 "rating_effective_date": "<the rating effective date YYYY-MM-DD, or null>",
 "policy_period_start": "<policy/anniversary rating date YYYY-MM-DD if shown, else the rating effective date, else null>",
 "carrier": "<carrier / insurer name if shown, else null>",
 "expected_losses": <number — total expected losses in dollars, or null>,
 "actual_losses": <number — total actual/primary+excess actual losses in dollars, or null>,
 "state": "<2-letter state code if the worksheet is state-specific, else null>"}

The experience_mod is the single most important field — it is usually labelled "Experience Modification", "Mod", "E-Mod", or "Experience Rating Modification" and is a number near 1.00. Convert "$1,234,567" to 1234567. Do not invent values not in the document."""


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


def _coerce(payload: dict) -> dict:
    """Clamp the model output into the company_wc_mods field schema."""
    def _f(k):
        v = payload.get(k)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    mod = _f("experience_mod")
    # mirror WcModCreate's validator: 0 < mod <= 10
    if mod is not None and not (0 < mod <= 10):
        mod = None
    state = payload.get("state")
    state = state.strip().upper() if isinstance(state, str) and len(state.strip()) == 2 else None
    exp, act = _f("expected_losses"), _f("actual_losses")
    return {
        "experience_mod": mod,
        "policy_period_start": payload.get("policy_period_start") or payload.get("rating_effective_date") or None,
        "carrier": (payload.get("carrier") or None),
        "expected_losses": exp if (exp is None or exp >= 0) else None,
        "actual_losses": act if (act is None or act >= 0) else None,
        "state": state,
    }


async def parse_mod_worksheet(pdf_bytes: bytes) -> dict:
    """Best-effort parse of an experience-rating worksheet → the real mod + inputs.
    Never raises. Returns {fields, available, model}; available=True only when a
    usable mod was extracted (so the UI can fall back to manual entry)."""
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
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:  # never-raises contract
        logger.warning("WC mod worksheet parse failed: %s", exc)
        payload = {}
    fields = _coerce(payload)
    return {"fields": fields, "available": fields["experience_mod"] is not None, "model": analyzer.model}
