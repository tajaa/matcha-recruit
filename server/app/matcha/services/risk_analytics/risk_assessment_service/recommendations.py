"""Gemini-backed risk recommendations: the prompt, the JSON-reply parser, and
generate_recommendations with its model fallback loop.

`_parse_json_response` is NOT the `_shared/citations._parse_json` used by the
pilots -- that one swallows a parse failure and returns `{}` and only ever
returns a dict, this one raises and returns Any. Left as-is rather than
unified: swapping in the tolerant version would turn a malformed reply from a
logged failure into a silently empty recommendation set.
"""
import json
import logging
from dataclasses import asdict
from typing import Any
from app.core.services.genai_client import get_genai_client

from ._config import FALLBACK_MODELS
from app.matcha.services._shared.gemini import (
    is_model_unavailable_error as _is_model_unavailable_error,
)
from ._shared import RiskAssessmentResult

logger = logging.getLogger(__name__)


RISK_RECOMMENDATION_PROMPT = """You are a senior HR risk consultant and employment attorney with 20 years advising mid-market and enterprise companies. You are reviewing a client's automated HR risk dashboard before a quarterly board briefing. Your job is to produce the kind of written memo a senior HR law firm would deliver — legally specific, citing real fine amounts and enforcement precedents, grounded in actual employment law.

## Platform Context

This dashboard aggregates live data from an HR platform across 5 risk dimensions. Scores are 0–100 per dimension (weighted into an overall score). Bands: 0–25 = Low, 26–50 = Moderate, 51–75 = High, 76–100 = Critical.

Dimension weights: Compliance 30%, Incidents 25%, ER Cases 25%, Workforce 15%, Legislative 5%.

## What Each Dimension Means

**compliance** — Regulatory compliance alerts across all business locations. Unread alerts represent known regulatory exposure the company has not responded to. Critical alerts typically involve wage/hour violations, leave law non-compliance, or workplace posting failures. Every day an unread alert sits open is a day of documented, willful non-compliance. `last_check` is when the company last ran a compliance audit scan.

**incidents** — Open workplace incident reports (safety incidents, behavioral misconduct, harassment, discrimination complaints). Open incidents are unresolved legal exposure. OSHA willful violations carry penalties up to $156,259 per violation (2024 rates). Title VII harassment claims average $40,000–$300,000 in EEOC settlements; jury verdicts frequently exceed $1M. Delay in investigation is a primary factor in punitive damages awards.

**er_cases** — Employment Relations cases: disputes, disciplinary matters, accommodation requests, investigations. `pending_determination` cases are the most dangerous — open investigations without documented conclusions expose the company to EEOC complaints, wrongful termination suits, and failure-to-accommodate claims under the ADA (average EEOC resolution: $25,000–$75,000; litigation costs typically 3–5x settlement value). States like California, New York, and Illinois impose additional obligations beyond federal law.

**workforce** — Multi-state and workforce composition risk. Each state with employees creates a separate compliance jurisdiction with its own wage/hour, leave, and classification rules. Contingent workforce ratios above 20% trigger IRS/DOL worker misclassification scrutiny — the DOL recovered $274M in back wages in FY2023 alone. States like California (AB5), New Jersey, and Massachusetts apply the strictest misclassification tests; exposure includes back taxes, benefits liability, and per-worker civil penalties.

**legislative** — Upcoming laws affecting the company's locations that require policy, process, or handbook changes before their effective dates. Items effective within 30 days are in the emergency window — the company may already be non-compliant if it hasn't acted. State-level paid leave, pay transparency, and non-compete laws have been the most active legislative areas in 2023–2024.

## Risk Assessment Data

{assessment_json}

## Instructions

Produce 5–10 strategic consulting recommendations based on this data.

Rules:
- Only produce recommendations for dimensions where score > 0.
- Order by severity: critical first, then high, medium, low.
- Every recommendation must cite the specific numbers from the data AND specific legal/financial stakes (e.g. actual fine ranges, named statutes, enforcement agency, historical penalty amounts).
- Name the specific states from `unique_states` where relevant — multi-state exposure means multi-jurisdiction liability.
- Explain the trajectory risk: what does the current score mean, and what happens if it climbs one band higher?
- Give concrete next steps (not "address the issue" but "assign an owner, set a 48-hour deadline, document the response in writing").
- Write in the voice of a senior advisor briefing a CHRO or CEO — authoritative, direct, no filler.
- priority must be one of: critical, high, medium, low.
- dimension must be one of: compliance, incidents, er_cases, workforce, legislative.

Return ONLY a valid JSON object (no markdown fences) with two fields:

1. "report": A tight executive analysis — 2 paragraphs preferred, a 3rd only if the data genuinely demands it — written as a senior HR consultant addressing the company's leadership. Optimize for insight density, NOT length: say more in fewer words. A shorter, sharper memo beats a longer, padded one. Requirements:
   - Open with the overall score and band and what it means for the company's legal exposure right now — state the consequence, not a textbook definition of the band.
   - Every sentence must carry a distinct, non-obvious point: a causal link, a quantified stake, a named enforcement precedent, or a decision leadership must make. No sentence may merely restate the dashboard or repeat another sentence.
   - Tie named risks to the actual dimension scores with real dollar amounts (OSHA per-violation amounts, EEOC average settlements, DOL back-wage recovery figures, state-specific penalty structures).
   - Go beyond a per-dimension recap: surface how risks COMPOUND. An open ER case across a multi-state workforce is multi-jurisdiction class exposure; a stale compliance audit during a legislative-change window is documented willful non-compliance. The second-order interaction between dimensions is where the real exposure lives — name it explicitly.
   - Address trajectory: at the current band, what does one bad quarter cost? Cite what has happened to companies that let a similar profile deteriorate (named enforcement actions, class actions, DOL audits).
   - If the company is strong somewhere, say so in a single clause — then make clear that low risk is deferred liability, not safety.
   - Cut all filler: no throat-clearing, no hedging, no transitional padding ("it is important to note", "as you can see", "moving forward", "in conclusion"). Authoritative and grounded — the kind of memo a CHRO forwards to the board untouched.
   - Do NOT use bullet points or lists — write in flowing narrative paragraphs.

2. "recommendations": A JSON array of 5-10 objects, each with:
   - "dimension": string
   - "priority": "critical" | "high" | "medium" | "low"
   - "title": concise heading (6-10 words)
   - "guidance": 4-5 sentences — current situation with specific numbers, exact legal/financial consequence (statute name, fine range, enforcement agency), and concrete next steps"""


def _parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response, handling markdown fences and trailing text."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Gemini sometimes appends extra text after valid JSON — extract first object
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(text)
        return result


async def generate_recommendations(result: RiskAssessmentResult, settings) -> dict:
    """Generate executive report and strategic HR consulting recommendations via Gemini."""
    empty = {"report": None, "recommendations": []}
    try:
        import os
        api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        if not api_key:
            logger.warning("No Gemini API key configured — skipping recommendations")
            return empty
        client = get_genai_client(api_key=api_key)

        assessment_dict = {
            "overall_score": result.overall_score,
            "overall_band": result.overall_band,
            "dimensions": {
                key: asdict(dim) for key, dim in result.dimensions.items()
            },
            "computed_at": result.computed_at.isoformat(),
        }
        prompt = RISK_RECOMMENDATION_PROMPT.format(
            assessment_json=json.dumps(assessment_dict, indent=2, default=str)
        )

        models_to_try = [settings.analysis_model] + [
            m for m in FALLBACK_MODELS if m != settings.analysis_model
        ]

        last_error = None
        for model in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                break
            except Exception as e:
                last_error = e
                if _is_model_unavailable_error(e):
                    logger.warning("Model %s unavailable, trying next: %s", model, e)
                    continue
                raise
        else:
            raise last_error  # type: ignore[misc]

        parsed = _parse_json_response(response.text)
        if not isinstance(parsed, dict):
            logger.error("Gemini returned non-object for consultation")
            return empty

        report = parsed.get("report") or None
        recs = parsed.get("recommendations", [])
        if not isinstance(recs, list):
            recs = []

        valid_priorities = {"critical", "high", "medium", "low"}
        valid_dims = {"compliance", "incidents", "er_cases", "workforce", "legislative"}
        validated = []
        for r in recs:
            if (
                isinstance(r, dict)
                and r.get("priority") in valid_priorities
                and r.get("dimension") in valid_dims
                and r.get("title")
                and r.get("guidance")
            ):
                validated.append({
                    "dimension": r["dimension"],
                    "priority": r["priority"],
                    "title": r["title"],
                    "guidance": r["guidance"],
                })
        return {"report": report, "recommendations": validated}

    except Exception:
        logger.exception("Failed to generate Gemini consultation — returning empty")
        return empty
