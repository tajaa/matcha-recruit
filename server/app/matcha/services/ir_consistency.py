"""IR Consistency Engine — Outcome Distribution from Precedents.

Computes weighted action probabilities, Kish effective sample size,
resolution stats, and a consistency insight from precedent data.
"""

import json
import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ===========================================
# Constants
# ===========================================

ACTION_CATEGORIES = [
    "verbal_warning",
    "written_warning",
    "suspension",
    "termination",
    "retraining",
    "policy_update",
    "equipment_fix",
    "osha_report",
    "process_change",
    "counseling",
    "investigation_referral",
    "no_action",
    "other",
]

GEMINI_CALL_TIMEOUT = 45

CATEGORIZE_PROMPT = """You are an incident response analyst. Categorize the corrective actions from each precedent incident into one or more action categories.

CATEGORIES (multi-label, assign all that apply):
{categories}

PRECEDENT INCIDENTS:
{precedents_text}

Return ONLY a JSON object:
{{
  "categorized": [
    {{
      "incident_id": "uuid",
      "categories": ["verbal_warning", "retraining"]
    }}
  ]
}}"""

INSIGHT_PROMPT = """You are an HR consistency advisor. Given the following action distribution from similar past incidents, write exactly ONE sentence summarizing the dominant pattern and what it means for decision-making consistency.

Action distribution:
{distribution_text}

Sample size: {sample_size} precedents (effective n={effective_n:.1f}, confidence: {confidence})

Return ONLY the single sentence, no JSON wrapping."""


# ===========================================
# Gemini Helpers
# ===========================================

async def _categorize_actions(
    precedents: list[dict],
    api_key: Optional[str] = None,
    vertex_project: Optional[str] = None,
) -> dict[str, list[str]]:
    """Single Gemini call to categorize corrective_actions for all precedents.

    Returns {incident_id: [category, ...]} mapping.
    """
    from google import genai
    from ...core.services.rate_limiter import get_rate_limiter

    if vertex_project:
        client = genai.Client(vertexai=True, project=vertex_project, location="us-central1")
    elif api_key:
        client = genai.Client(api_key=api_key)
    else:
        raise ValueError("Either api_key or vertex_project must be provided")

    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("ir_analysis", "consistency_categorize")

    lines = []
    for p in precedents:
        actions_text = p.get("corrective_actions") or "N/A"
        lines.append(
            f"ID: {p.get('incident_id', '')}\n"
            f"  Corrective Actions: {actions_text[:400]}"
        )

    prompt = CATEGORIZE_PROMPT.format(
        categories=", ".join(ACTION_CATEGORIES),
        precedents_text="\n\n".join(lines),
    )

    response = await asyncio.wait_for(
        client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        ),
        timeout=GEMINI_CALL_TIMEOUT,
    )

    await rate_limiter.record_call("ir_analysis", "consistency_categorize")

    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    result = json.loads(text.strip())

    mapping: dict[str, list[str]] = {}
    for item in result.get("categorized", []):
        iid = str(item.get("incident_id", ""))
        cats = [c for c in item.get("categories", []) if c in ACTION_CATEGORIES]
        if not cats:
            cats = ["other"]
        mapping[iid] = cats

    return mapping


async def _generate_insight(
    distribution: list[dict],
    sample_size: int,
    effective_n: float,
    confidence: str,
    api_key: Optional[str] = None,
    vertex_project: Optional[str] = None,
) -> Optional[str]:
    """Single Gemini call to produce a 1-sentence consistency insight."""
    from google import genai
    from ...core.services.rate_limiter import get_rate_limiter

    if vertex_project:
        client = genai.Client(vertexai=True, project=vertex_project, location="us-central1")
    elif api_key:
        client = genai.Client(api_key=api_key)
    else:
        raise ValueError("Either api_key or vertex_project must be provided")

    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("ir_analysis", "consistency_insight")

    dist_lines = [f"  {d['category']}: {d['probability']:.0%}" for d in distribution]

    prompt = INSIGHT_PROMPT.format(
        distribution_text="\n".join(dist_lines),
        sample_size=sample_size,
        effective_n=effective_n,
        confidence=confidence,
    )

    response = await asyncio.wait_for(
        client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        ),
        timeout=GEMINI_CALL_TIMEOUT,
    )

    await rate_limiter.record_call("ir_analysis", "consistency_insight")

    return response.text.strip()


# ===========================================
# Core Computation
# ===========================================

def _compute_kish_effective_n(weights: list[float]) -> float:
    """Kish effective sample size: (sum w_i)^2 / sum(w_i^2)."""
    if not weights:
        return 0.0
    sum_w = sum(weights)
    sum_w2 = sum(w * w for w in weights)
    if sum_w2 == 0:
        return 0.0
    return (sum_w * sum_w) / sum_w2


def _confidence_level(n_eff: float) -> str:
    if n_eff < 2:
        return "insufficient"
    elif n_eff <= 5:
        return "limited"
    else:
        return "strong"


def _compute_weighted_action_distribution(
    precedents: list[dict],
    categorized: dict[str, list[str]],
) -> list[dict]:
    """Compute P(action_k) = sum(w_i * 1[k in i]) / sum(w_i)."""
    weights = [p.get("similarity_score", 0.0) for p in precedents]
    total_weight = sum(weights)
    if total_weight == 0:
        return []

    category_weighted: dict[str, float] = {}
    for p, w in zip(precedents, weights):
        pid = p.get("incident_id", "")
        cats = categorized.get(pid, ["other"])
        for cat in cats:
            category_weighted[cat] = category_weighted.get(cat, 0.0) + w

    distribution = []
    for cat in ACTION_CATEGORIES:
        wc = category_weighted.get(cat, 0.0)
        if wc > 0:
            distribution.append({
                "category": cat,
                "probability": round(wc / total_weight, 4),
                "weighted_count": round(wc, 4),
            })

    distribution.sort(key=lambda x: x["probability"], reverse=True)
    return distribution


def _compute_resolution_stats(precedents: list[dict]) -> dict[str, Any]:
    """Weighted average resolution days and effectiveness rate."""
    weights = [p.get("similarity_score", 0.0) for p in precedents]

    # Resolution days
    res_weights = []
    res_days = []
    for p, w in zip(precedents, weights):
        rd = p.get("resolution_days")
        if rd is not None:
            res_weights.append(w)
            res_days.append(rd)

    avg_resolution = None
    if res_weights and sum(res_weights) > 0:
        avg_resolution = round(
            sum(w * d for w, d in zip(res_weights, res_days)) / sum(res_weights), 1
        )

    # Effectiveness rate
    eff_weights = []
    eff_vals = []
    for p, w in zip(precedents, weights):
        re = p.get("resolution_effective")
        if re is not None:
            eff_weights.append(w)
            eff_vals.append(1.0 if re else 0.0)

    effectiveness = None
    if eff_weights and sum(eff_weights) > 0:
        effectiveness = round(
            sum(w * v for w, v in zip(eff_weights, eff_vals)) / sum(eff_weights), 4
        )

    return {
        "weighted_avg_resolution_days": avg_resolution,
        "weighted_effectiveness_rate": effectiveness,
    }


# ===========================================
# Orchestrator
# ===========================================

async def compute_outcome_distribution(
    precedents: list[dict],
    api_key: Optional[str] = None,
    vertex_project: Optional[str] = None,
) -> dict[str, Any]:
    """Main entry point: compute consistency guidance from precedent list.

    Args:
        precedents: List of PrecedentMatch-shaped dicts (from cached similar analysis).
        api_key: Gemini API key.
        vertex_project: Vertex AI project ID.

    Returns a ConsistencyGuidance-shaped dict.
    """
    sample_size = len(precedents)
    weights = [p.get("similarity_score", 0.0) for p in precedents]
    n_eff = _compute_kish_effective_n(weights)
    confidence = _confidence_level(n_eff)

    # Resolution stats (pure Python, always computed)
    res_stats = _compute_resolution_stats(precedents)

    # Try Gemini categorization
    action_distribution = None
    dominant_action = None
    dominant_probability = None
    consistency_insight = None

    try:
        categorized = await _categorize_actions(
            precedents, api_key=api_key, vertex_project=vertex_project,
        )
        action_distribution = _compute_weighted_action_distribution(precedents, categorized)

        if action_distribution:
            dominant_action = action_distribution[0]["category"]
            dominant_probability = action_distribution[0]["probability"]

            # Generate insight
            try:
                consistency_insight = await _generate_insight(
                    action_distribution,
                    sample_size,
                    n_eff,
                    confidence,
                    api_key=api_key,
                    vertex_project=vertex_project,
                )
            except Exception as e:
                logger.warning(f"Consistency insight generation failed: {e}")

    except Exception as e:
        logger.warning(f"Action categorization failed: {e}")
        # Fallback: no action_distribution but resolution stats still returned

    return {
        "sample_size": sample_size,
        "effective_sample_size": round(n_eff, 2),
        "confidence": confidence,
        "unprecedented": False,
        "action_distribution": action_distribution,
        "dominant_action": dominant_action,
        "dominant_probability": dominant_probability,
        "weighted_avg_resolution_days": res_stats["weighted_avg_resolution_days"],
        "weighted_effectiveness_rate": res_stats["weighted_effectiveness_rate"],
        "consistency_insight": consistency_insight,
        "generated_at": datetime.utcnow().isoformat(),
        "from_cache": False,
    }


# ===========================================
# Company-Wide Analytics
# ===========================================

def _compute_aggregate_distribution(
    incidents: list[dict],
    categorized: dict[str, list[str]],
) -> list[dict]:
    """Simple frequency-based distribution (no similarity weighting)."""
    total = len(incidents)
    if total == 0:
        return []

    counts: dict[str, int] = {}
    for inc in incidents:
        iid = str(inc.get("id", ""))
        cats = categorized.get(iid, ["other"])
        for cat in cats:
            counts[cat] = counts.get(cat, 0) + 1

    distribution = []
    for cat in ACTION_CATEGORIES:
        c = counts.get(cat, 0)
        if c > 0:
            distribution.append({
                "category": cat,
                "probability": round(c / total, 4),
                "weighted_count": float(c),
            })

    distribution.sort(key=lambda x: x["probability"], reverse=True)
    return distribution


async def compute_consistency_analytics(
    incidents: list[dict],
    api_key: Optional[str] = None,
    vertex_project: Optional[str] = None,
) -> dict[str, Any]:
    """Compute company-wide consistency analytics across resolved incidents.

    Args:
        incidents: Resolved incident rows (dicts with id, incident_type, severity,
                   corrective_actions, resolved_at, occurred_at).
        api_key: Gemini API key.
        vertex_project: Vertex AI project ID.

    Returns a ConsistencyAnalytics-shaped dict.
    """
    with_actions = [i for i in incidents if i.get("corrective_actions")]

    if not with_actions:
        return {
            "total_resolved": len(incidents),
            "total_with_actions": 0,
            "action_distribution": [],
            "by_incident_type": [],
            "by_severity": [],
            "avg_resolution_by_action": {},
            "generated_at": datetime.utcnow().isoformat(),
            "from_cache": False,
        }

    # Categorize all corrective actions via Gemini
    # Reformat for _categorize_actions which expects incident_id key
    formatted = [
        {"incident_id": str(i["id"]), "corrective_actions": i["corrective_actions"]}
        for i in with_actions
    ]
    categorized = await _categorize_actions(formatted, api_key=api_key, vertex_project=vertex_project)

    # Overall distribution
    action_distribution = _compute_aggregate_distribution(with_actions, categorized)

    # By incident type
    by_type_map: dict[str, list[dict]] = {}
    for inc in with_actions:
        itype = inc.get("incident_type", "other")
        by_type_map.setdefault(itype, []).append(inc)

    by_incident_type = []
    for itype, type_incs in sorted(by_type_map.items()):
        type_dist = _compute_aggregate_distribution(type_incs, categorized)
        if type_dist:
            by_incident_type.append({
                "incident_type": itype,
                "total": len(type_incs),
                "actions": type_dist,
            })

    # By severity
    by_sev_map: dict[str, list[dict]] = {}
    for inc in with_actions:
        sev = inc.get("severity", "medium")
        by_sev_map.setdefault(sev, []).append(inc)

    by_severity = []
    for sev in ["critical", "high", "medium", "low"]:
        sev_incs = by_sev_map.get(sev, [])
        if sev_incs:
            sev_dist = _compute_aggregate_distribution(sev_incs, categorized)
            if sev_dist:
                by_severity.append({
                    "severity": sev,
                    "total": len(sev_incs),
                    "actions": sev_dist,
                })

    # Average resolution days by action category
    avg_resolution_by_action: dict[str, float] = {}
    action_days: dict[str, list[float]] = {}
    for inc in with_actions:
        iid = str(inc["id"])
        cats = categorized.get(iid, [])
        resolved_at = inc.get("resolved_at")
        occurred_at = inc.get("occurred_at")
        if resolved_at and occurred_at:
            days = max(0, (resolved_at - occurred_at).days)
            for cat in cats:
                action_days.setdefault(cat, []).append(days)

    for cat, days_list in action_days.items():
        if days_list:
            avg_resolution_by_action[cat] = round(sum(days_list) / len(days_list), 1)

    return {
        "total_resolved": len(incidents),
        "total_with_actions": len(with_actions),
        "action_distribution": action_distribution,
        "by_incident_type": by_incident_type,
        "by_severity": by_severity,
        "avg_resolution_by_action": avg_resolution_by_action,
        "generated_at": datetime.utcnow().isoformat(),
        "from_cache": False,
    }
