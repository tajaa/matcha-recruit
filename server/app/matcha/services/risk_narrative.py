"""Risk-profile AI narrative — turns the composite risk index + components into a
plain-English "here's why your number is X and the top moves to improve your
insurance terms" with prioritized actions. Best-effort Gemini (never raises);
falls back to the deterministic top_fixes when AI is unavailable.
"""

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


async def narrative(result: dict, *, company_name: Optional[str] = None, audience: str = "business") -> dict:
    """result = compute_risk_index output. Returns {summary, actions:[...], available}."""
    if result.get("index") is None:
        return {"summary": "", "actions": [], "available": False}

    who = ("Address the business owner directly ('your')."
           if audience == "business"
           else "Write for the broker advising this client (refer to 'the client').")
    payload = {
        "company": company_name, "index": result["index"], "band": result["band"],
        "components": result.get("components"), "top_fixes": result.get("top_fixes"),
    }
    prompt = (
        "You are an insurance risk advisor. Given a client's composite workers'-comp + EPL + "
        "compliance risk index (0-100, higher = lower risk), explain it and give prioritized, "
        f"concrete moves to improve their insurance terms at renewal. {who} Be specific and use "
        "the component scores; no fluff.\n\n"
        f"Risk profile (JSON):\n{json.dumps(payload, default=str)}\n\n"
        'Return ONLY valid JSON: {"summary": "<2-3 sentence read of where they stand and why>", '
        '"actions": ["<concrete prioritized action>", ...]}. 3-5 actions, highest-impact first.'
    )
    analyzer = _get_analyzer()
    out: dict = {}
    try:
        resp = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=prompt),
            timeout=45,
        )
        out = analyzer._parse_json_response((getattr(resp, "text", None) or "").strip()) or {}
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("risk narrative failed: %s", exc)
        out = {}

    actions = out.get("actions") if isinstance(out.get("actions"), list) else []
    actions = [str(a) for a in actions if isinstance(a, str)][:5]
    summary = out.get("summary") if isinstance(out.get("summary"), str) else ""
    # `available` reflects whether the AI actually produced usable content, not
    # merely whether it returned *something* — a malformed-but-truthy response
    # (wrong types) still falls back, and must not be badged as AI-generated.
    ai_generated = bool(summary or actions)
    if not summary and not actions:
        # deterministic fallback from the index itself
        summary = f"Risk index {result['index']}/100 ({result['band']}). Focus on the lowest-scoring areas below."
        actions = result.get("top_fixes") or []
    return {"summary": summary, "actions": actions, "available": ai_generated}
