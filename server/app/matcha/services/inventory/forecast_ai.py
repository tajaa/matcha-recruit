"""Parse-only Gemini demand-scenario suggestions for inventory forecasts."""

import asyncio
import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH
from app.matcha.services._shared.gemini import genai_env_client


logger = logging.getLogger(__name__)
MAX_ADJUSTMENTS = 12
MIN_MULTIPLIER = Decimal("0.5")
MAX_MULTIPLIER = Decimal("2.0")


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    value = json.loads(text)
    return value if isinstance(value, dict) else {}


def _coerce_adjustments(raw: dict, *, horizon_start: date, horizon_days: int) -> list[dict]:
    end = horizon_start + timedelta(days=horizon_days - 1)
    output = []
    for candidate in (raw.get("adjustments") or [])[:MAX_ADJUSTMENTS]:
        if not isinstance(candidate, dict):
            continue
        try:
            week_start = date.fromisoformat(str(candidate.get("week_start", ""))[:10])
            multiplier = Decimal(str(candidate.get("demand_multiplier")))
        except (TypeError, ValueError, ArithmeticError):
            continue
        if week_start < horizon_start or week_start > end or week_start.weekday() != 0:
            continue
        if not MIN_MULTIPLIER <= multiplier <= MAX_MULTIPLIER:
            continue
        reason = candidate.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            continue
        confidence = candidate.get("confidence")
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        output.append({
            "week_start": week_start,
            "demand_multiplier": multiplier,
            "reason": reason.strip()[:500],
            "confidence": confidence,
            "source": "ai_accepted",
        })
    return output


async def propose_forecast_adjustments(
    *,
    company_id,
    location_id,
    horizon_start: date,
    horizon_days: int,
    manager_context: str,
    historical_summary: dict,
) -> dict:
    """Return reviewable assumptions. This function never writes to the DB."""
    prompt = f"""You are assisting a store manager with a demand forecast.
Suggest only weekly demand multipliers for known operational context. Do not
invent sales, inventory counts, order quantities, prices, or suppliers.

Forecast horizon: {horizon_start.isoformat()} through {(horizon_start + timedelta(days=horizon_days - 1)).isoformat()}
Manager context: {manager_context[:4000]}
Aggregated historical summary: {json.dumps(historical_summary, default=str)}

Return only JSON:
{{"adjustments":[{{"week_start":"YYYY-MM-DD","demand_multiplier":1.15,"reason":"...","confidence":"low|medium|high"}}],"risks":["..."],"data_gaps":["..."]}}
Rules: week_start must be a Monday within the horizon; multiplier must be
between 0.5 and 2.0; include at most one adjustment per week; if context is
insufficient, return an empty adjustments array. Never include order quantities.
"""
    try:
        response = await asyncio.wait_for(
            genai_env_client().aio.models.generate_content(
                model=GEMINI_FLASH,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            ),
            timeout=60,
        )
        raw = _parse_json(getattr(response, "text", None) or "")
        return {
            "available": True,
            "model": GEMINI_FLASH,
            "adjustments": _coerce_adjustments(
                raw, horizon_start=horizon_start, horizon_days=horizon_days,
            ),
            "risks": [str(value)[:500] for value in (raw.get("risks") or [])[:10] if value],
            "data_gaps": [str(value)[:500] for value in (raw.get("data_gaps") or [])[:10] if value],
        }
    except Exception as exc:
        logger.warning("inventory forecast AI draft unavailable: %s", exc)
        return {
            "available": False,
            "model": GEMINI_FLASH,
            "adjustments": [],
            "risks": [],
            "data_gaps": ["The scenario assistant was unavailable; use deterministic forecast inputs."],
        }
