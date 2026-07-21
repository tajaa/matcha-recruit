"""Shared precedent semantic-enrichment plumbing (CLEANUP L7).

`er_precedent.enrich_with_semantics` and `ir_precedent.enrich_with_semantics` had a
byte-for-byte identical Phase-2 skeleton — get client, rate-limit check, one Gemini call,
record, parse JSON, and return `{"scores": [], "pattern_summary": None}` on any failure.
They diverged only in (a) the domain string, (b) which model to call, and (c) JSON
extraction robustness. This module owns the shared skeleton; each precedent file keeps its
own domain-specific candidate/prompt builder and just hands the finished prompt here.

Canonicalized on ER's (more evolved) version: model-candidate **fallback** + a robust
regex JSON extractor. IR previously hardcoded a single model with fence-stripping — it now
gains the fallback and the robust extractor for free, a behavior improvement, not a change
to its scoring.
"""
import asyncio
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Stable fallbacks tried, in order, after the configured primary model when it is
# unavailable for the current account/project.
PRECEDENT_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")

# Timeout for a single precedent semantic-enrichment call (seconds).
GEMINI_CALL_TIMEOUT = 45


def is_model_unavailable_error(error: Exception) -> bool:
    """Return True when the model is unavailable for the current account/project."""
    message = str(error).lower()
    if "model" not in message:
        return False
    return (
        "not found" in message
        or "does not have access" in message
        or "unsupported model" in message
        or "404" in message
    )


async def run_semantic_enrichment(
    prompt: str,
    *,
    domain: str,
    api_key: Optional[str] = None,
    timeout: int = GEMINI_CALL_TIMEOUT,
) -> dict[str, Any]:
    """Run one precedent Phase-2 Gemini call and parse its JSON result.

    `prompt` is the fully-built, domain-specific prompt; `domain` is the rate-limiter
    bucket (`"er_analysis"` / `"ir_analysis"`). Returns the parsed dict, or
    `{"scores": [], "pattern_summary": None}` on any failure (unavailable model exhausted,
    timeout, no JSON, parse error) — the structural Phase-1 scores still stand on their own.
    """
    from app.core.services.genai_client import get_genai_client
    from app.config import get_settings
    from app.core.services.rate_limiter import get_rate_limiter

    client = get_genai_client(api_key=api_key)

    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit(domain, "precedent_semantic")

    settings = get_settings()
    primary_model = getattr(settings, "analysis_model", None) or "gemini-3-flash-preview"
    model_candidates: list[str] = []
    for m in [primary_model, *PRECEDENT_FALLBACK_MODELS]:
        if m and m not in model_candidates:
            model_candidates.append(m)

    try:
        last_model_error: Optional[Exception] = None
        response = None
        for model_name in model_candidates:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    ),
                    timeout=timeout,
                )
                if model_name != primary_model:
                    logger.warning(
                        "Precedent semantic model '%s' unavailable; fell back to '%s'",
                        primary_model,
                        model_name,
                    )
                break
            except Exception as exc:
                if is_model_unavailable_error(exc):
                    last_model_error = exc
                    logger.warning("Precedent model candidate '%s' unavailable: %s", model_name, exc)
                    continue
                raise

        if response is None:
            if last_model_error:
                raise last_model_error
            raise RuntimeError("No Gemini model candidates available for precedent semantic enrichment")

        await rate_limiter.record_call(domain, "precedent_semantic")

        text = response.text.strip()
        # Extract JSON object robustly — handles any fence format or stray text.
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            logger.warning("Gemini semantic enrichment returned no JSON object")
            return {"scores": [], "pattern_summary": None}

        return json.loads(json_match.group())

    except Exception as e:
        logger.warning(f"Gemini semantic enrichment failed: {e}")
        return {"scores": [], "pattern_summary": None}
