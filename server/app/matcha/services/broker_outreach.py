"""AI consultative-outreach engine for the broker Action Center.

Given ONE client's aggregate safety trends, generates a handful of broker-facing
talking points ("send them the ergonomics kit", "open a renewal-prep
conversation") to shift the broker–client relationship from reactive reporting
to proactive consultation.

"AI-shielded" guarantee: the model only ever sees `_anonymize_context()` output —
aggregate counts / rates / trend deltas. Individual employee names, incident
narratives, and eligibility-exception PII are never serialized into the prompt.
`_anonymize_context` is a pure function so the no-PII property is unit-testable.

Mirrors the IR copilot generation pattern (ir_ai_orchestrator.generate_guidance):
reuse the cached IRAnalyzer (Gemini client + JSON parser), rate-limit on the
shared `ir_analysis` bucket, `generate_content` under a 60s timeout, fall back to
an empty result on any error.
"""

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer

logger = logging.getLogger(__name__)

# Resource slugs the model may reference. Anything else is dropped — the model
# never gets to invent a URL (SSRF / hallucination guard).
ALLOWED_RESOURCES = {
    "safety-guide", "eap-overview", "renewal-prep", "ergonomics-kit", "return-to-work",
}
ALLOWED_TONES = {"celebratory", "advisory", "urgent"}
MAX_PROMPTS = 4

# Keys that must NEVER appear in the anonymized context (unit-test asserts this).
PII_DENYLIST = (
    "first_name", "last_name", "name", "employee_name", "full_name",
    "email", "phone", "external_id", "employee_id", "description",
    "narrative", "hot_location",
)

_analyzer: Optional[IRAnalyzer] = None


def get_broker_outreach_analyzer() -> IRAnalyzer:
    """Cached IRAnalyzer reused for outreach generation (Gemini client + parser)."""
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


def _coerce_triggers(value) -> list:
    if isinstance(value, list):
        return [t for t in value if isinstance(t, str)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [t for t in parsed if isinstance(t, str)] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _anonymize_context(
    *,
    wc_metrics: dict,
    renewal_risk: Optional[dict],
    milestones: Optional[list],
) -> dict:
    """Strip everything except aggregate counts / rates / trends. The returned
    dict is the ONLY company data the model sees. No names, no incident text."""
    wc = wc_metrics or {}
    prior = wc.get("prior") or {}
    benchmark = wc.get("benchmark") or {}
    premium = wc.get("premium_impact") or {}

    ctx: dict = {
        "industry": wc.get("industry"),
        "headcount": wc.get("headcount"),
        "trir": wc.get("trir"),
        "dart_rate": wc.get("dart_rate"),
        "recordable_cases": wc.get("recordable_cases"),
        "dart_cases": wc.get("dart_cases"),
        "lost_days": wc.get("lost_days"),
        "days_since_last_recordable": wc.get("days_since_last_recordable"),
        "severity_band": wc.get("severity_band"),
        "benchmark_trir": benchmark.get("trir"),
        "benchmark_sector": benchmark.get("label") or benchmark.get("sector"),
        "trir_delta_pct": prior.get("trir_delta_pct"),
        "dart_delta_pct": prior.get("dart_delta_pct"),
        "lost_days_delta_pct": prior.get("lost_days_delta_pct"),
        "premium_direction": premium.get("direction"),
        # quarterly[] is already counts-only and aggregate by construction.
        "quarterly": [
            {
                "quarter": q.get("quarter"),
                "recordable": q.get("recordable"),
                "dart": q.get("dart"),
                "lost_days": q.get("lost_days"),
            }
            for q in (wc.get("quarterly") or [])
            if isinstance(q, dict)
        ],
    }

    if renewal_risk:
        ctx["renewal_risk"] = {
            "risk_band": renewal_risk.get("risk_band"),
            "turnover_pct": float(renewal_risk["turnover_pct"]) if renewal_risk.get("turnover_pct") is not None else None,
            "turnover_delta_pct": float(renewal_risk["turnover_delta_pct"]) if renewal_risk.get("turnover_delta_pct") is not None else None,
            "lost_workdays": renewal_risk.get("lost_workdays"),
            "near_misses": renewal_risk.get("near_misses"),
            "behavioral_incidents": renewal_risk.get("behavioral_incidents"),
            "triggers": _coerce_triggers(renewal_risk.get("triggers")),
        }

    if milestones:
        ctx["milestones"] = [
            {"family": m.get("milestone_family"), "tier": m.get("tier"), "title": m.get("title")}
            for m in milestones if isinstance(m, dict)
        ]

    return ctx


PROMPT_TEMPLATE = """You are a workers-compensation / safety consultant helping an insurance broker \
decide how to proactively engage one of their client companies. You are given ONLY aggregate, \
anonymized safety trends for the client "{company_name}" — never individual incidents or people.

Client trend data (JSON):
{context}

Produce up to {max_prompts} short, consultative outreach talking points the broker could use to \
open a proactive conversation. Favor: celebrating genuine improvement (incident-free streaks, \
falling TRIR/DART), flagging emerging risk early (rising lost days, turnover), \
and suggesting a concrete next step or resource.

Rules:
- NEVER reference an individual employee, a specific incident, or any name. Speak only to aggregate trends.
- Each point must be grounded in a specific number/trend from the data.
- `resource_link` MUST be one of: {resources} — or null. Never invent a URL.
- `tone` MUST be one of: celebratory, advisory, urgent.

Return ONLY valid JSON of this exact shape:
{{"prompts": [{{"title": "...", "rationale": "...", "suggested_action": "...", "resource_link": null, "tone": "advisory"}}]}}
"""


def _normalize_prompts(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        action = item.get("suggested_action")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(action, str) or not action.strip():
            continue
        rationale = item.get("rationale") if isinstance(item.get("rationale"), str) else ""
        link = item.get("resource_link")
        if link not in ALLOWED_RESOURCES:
            link = None
        tone = item.get("tone")
        if tone not in ALLOWED_TONES:
            tone = "advisory"
        out.append({
            "title": title.strip()[:100],
            "rationale": rationale.strip()[:400],
            "suggested_action": action.strip()[:300],
            "resource_link": link,
            "tone": tone,
        })
        if len(out) >= MAX_PROMPTS:
            break
    return out


async def generate_outreach_prompts(
    *,
    company_name: str,
    wc_metrics: dict,
    renewal_risk: Optional[dict] = None,
    milestones: Optional[list] = None,
) -> dict:
    """Return {"prompts": [...], "model": "..."} grounded only in anonymized
    aggregate trends. Never raises on model/parse failure — returns empty prompts."""
    ctx = _anonymize_context(
        wc_metrics=wc_metrics,
        renewal_risk=renewal_risk, milestones=milestones,
    )

    from ...core.services.rate_limiter import get_rate_limiter
    await get_rate_limiter().check_limit("ir_analysis", "broker_outreach")

    prompt = PROMPT_TEMPLATE.format(
        company_name=company_name,
        context=json.dumps(ctx, default=str),
        max_prompts=MAX_PROMPTS,
        resources=", ".join(sorted(ALLOWED_RESOURCES)),
    )

    analyzer = get_broker_outreach_analyzer()
    payload: dict = {}
    try:
        response = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=prompt),
            timeout=60,
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        payload = analyzer._parse_json_response(raw_text)
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("Broker outreach generation failed: %s", exc)
        payload = {}

    return {"prompts": _normalize_prompts(payload.get("prompts")), "model": analyzer.model}
