"""Grounding tier-2b — adversarial LLM verifier (the impure half of the suite).

Tier 1 (grounding.py) is a pure string check and tier 2a (golden cross-check) is
pure comparison. This module is the only part that reaches Gemini, so it lives
apart to keep grounding.py unit-testable without a client. It settles the rows
tier 1 can't:

  * ``value_unverifiable`` — prose value, no numeric token to grep;
  * ``value_not_in_text``  — number absent from the cited excerpt (recall suspect).

For each, ONE independent Gemini call framed to REFUTE — "here is the statute text
and a claimed value; does the text state this value? default to false" — reads the
supplied excerpt, never outside knowledge. Refuter framing ≠ the extractor framing
that produced the value, so it catches recall the extractor smuggled past the
citation gate.

Guardrails: gated behind ``settings.grounding_llm_verifier_enabled`` (off = no
network), a hard per-run call cap, verdicts cached by (requirement, input_hash) so
re-runs on unchanged data cost nothing, and per-row isolation (one failure →
``llm_unclear``, not a dead suite). The decision function ``verifier_verdict`` is
pure and unit-tests without a client, mirroring ``grounding.evaluate_row``.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VERIFIER_MODEL = "gemini-3.1-flash-lite"
CALL_TIMEOUT_SECONDS = 45
DEFAULT_MAX_CALLS = 25

LLM_CONFIRMED = "llm_confirmed"
LLM_REFUTED = "llm_refuted"
LLM_UNCLEAR = "llm_unclear"

# Per-excerpt budget so a giant body can't blow the prompt / cost.
_EXCERPT_CAP = 8000


def input_hash(current_value: Optional[str], corpus: Optional[str]) -> str:
    """Stable cache key: the value + the exact text it's judged against. A change to
    either invalidates the cached verdict (re-verify); no change → cache hit."""
    h = hashlib.sha256()
    h.update((current_value or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((corpus or "").encode("utf-8"))
    return h.hexdigest()


def build_refute_prompt(current_value: str, corpus: str) -> str:
    """A strict, refute-framed prompt. Answers are grounded ONLY in the supplied
    text — the model is told not to use outside knowledge and to default to false."""
    excerpt = (corpus or "")[:_EXCERPT_CAP]
    return (
        "You are auditing a compliance database. Below is the exact text of an "
        "official statute/regulation excerpt, followed by a VALUE a database claims "
        "that text establishes. Your job is to REFUTE the claim unless the excerpt "
        "plainly states the value.\n\n"
        "Rules:\n"
        "- Judge ONLY from the excerpt below. Do NOT use outside knowledge or recall.\n"
        "- If the excerpt does not plainly state this value, answer false.\n"
        "- If the excerpt is about a different obligation, or states a different "
        "number/threshold, answer false.\n"
        "- Only answer true when the excerpt itself states this value for this "
        "obligation.\n"
        "- If you genuinely cannot tell from the excerpt, answer \"unclear\".\n\n"
        "Respond with ONLY a JSON object: "
        '{\"stated\": true | false | \"unclear\", \"reasoning\": \"<one sentence>\"}\n\n'
        f"=== STATUTE EXCERPT ===\n{excerpt}\n\n"
        f"=== CLAIMED VALUE ===\n{current_value}\n"
    )


def verifier_verdict(response_json: Any) -> str:
    """Map a parsed model response to a verdict (pure). Malformed → llm_unclear."""
    if not isinstance(response_json, dict):
        return LLM_UNCLEAR
    stated = response_json.get("stated")
    if isinstance(stated, bool):
        return LLM_CONFIRMED if stated else LLM_REFUTED
    if isinstance(stated, str):
        s = stated.strip().lower()
        if s in ("true", "yes"):
            return LLM_CONFIRMED
        if s in ("false", "no"):
            return LLM_REFUTED
    return LLM_UNCLEAR


async def _call_gemini(prompt: str) -> Any:
    """One grounded verifier call → parsed JSON (or raises). Impure."""
    from google.genai import types

    from app.core.services.genai_client import get_genai_client
    from app.core.services.gemini_compliance import _clean_json_text

    client = get_genai_client()
    resp = await asyncio.wait_for(
        client.aio.models.generate_content(
            model=VERIFIER_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0, response_modalities=["TEXT"]
            ),
        ),
        timeout=CALL_TIMEOUT_SECONDS,
    )
    return json.loads(_clean_json_text(resp.text or ""))


async def verify_rows(
    conn,
    candidates: List[Dict[str, Any]],
    *,
    max_calls: int = DEFAULT_MAX_CALLS,
) -> Dict[Any, Dict[str, Any]]:
    """Settle each candidate row with a cached-or-fresh verifier verdict.

    ``candidates``: ``[{id, current_value, corpus}]``. Returns
    ``{row_id: {verdict, cached: bool}}``. Reads/writes the
    ``compliance_eval_grounding_verdicts`` cache; a cache miss makes one Gemini call
    (up to ``max_calls`` fresh calls per run). Per-row try/except so one bad call
    downgrades that row to ``llm_unclear`` (uncached) rather than killing the suite.
    """
    out: Dict[Any, Dict[str, Any]] = {}
    calls_made = 0
    for cand in candidates:
        rid = cand["id"]
        h = input_hash(cand.get("current_value"), cand.get("corpus"))
        cached = await conn.fetchrow(
            "SELECT verdict FROM compliance_eval_grounding_verdicts "
            "WHERE requirement_id = $1 AND input_hash = $2",
            rid, h,
        )
        if cached is not None:
            out[rid] = {"verdict": cached["verdict"], "cached": True}
            continue

        if calls_made >= max_calls:
            # Budget spent — leave the row for a later run rather than silently
            # marking it. Not cached; not counted as a verdict.
            out[rid] = {"verdict": LLM_UNCLEAR, "cached": False, "skipped": True}
            continue

        try:
            parsed = await _call_gemini(
                build_refute_prompt(cand.get("current_value") or "", cand.get("corpus") or "")
            )
            verdict = verifier_verdict(parsed)
            reasoning = parsed.get("reasoning") if isinstance(parsed, dict) else None
            calls_made += 1
            await conn.execute(
                """
                INSERT INTO compliance_eval_grounding_verdicts
                    (requirement_id, input_hash, verdict, model, reasoning)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (requirement_id, input_hash) DO UPDATE
                    SET verdict = EXCLUDED.verdict, model = EXCLUDED.model,
                        reasoning = EXCLUDED.reasoning, checked_at = now()
                """,
                rid, h, verdict, VERIFIER_MODEL, reasoning,
            )
            out[rid] = {"verdict": verdict, "cached": False}
        except Exception:
            logger.warning("grounding verifier call failed for %s", rid, exc_info=True)
            out[rid] = {"verdict": LLM_UNCLEAR, "cached": False, "error": True}
    return out
