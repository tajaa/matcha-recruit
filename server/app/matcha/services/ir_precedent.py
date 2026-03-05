"""IR Precedent Service — Hybrid Similarity Scoring.

Two-phase pipeline:
  Phase 1: Structured pre-filter (pure Python, no AI)
  Phase 2: Semantic enrichment (single Gemini call for top candidates)

Combines 7 scoring dimensions into a final weighted score per precedent.
"""

import json
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ===========================================
# Constants
# ===========================================

SEVERITY_ORDINAL = {"critical": 4, "high": 3, "medium": 2, "low": 1}
LOOKBACK_MONTHS = 24
STRUCTURAL_THRESHOLD = 0.25
PHASE1_KEEP = 20
FINAL_KEEP = 10
GEMINI_CALL_TIMEOUT = 45

# Scoring weights
W_TYPE = 0.20
W_SEVERITY = 0.10
W_CATEGORY = 0.15
W_LOCATION = 0.10
W_TEMPORAL = 0.05
W_TEXT = 0.30
W_ROOT_CAUSE = 0.10


# ===========================================
# Phase 1: Structural Scorers
# ===========================================

def _score_type_match(current: dict, candidate: dict) -> float:
    """Binary: same incident_type = 1.0, else 0.0."""
    return 1.0 if current["incident_type"] == candidate["incident_type"] else 0.0


def _score_severity(current: dict, candidate: dict) -> float:
    """Ordinal proximity: 1 - |a-b| / 3."""
    a = SEVERITY_ORDINAL.get(current.get("severity", "medium"), 2)
    b = SEVERITY_ORDINAL.get(candidate.get("severity", "medium"), 2)
    return 1.0 - abs(a - b) / 3.0


def _tokenize(text: str) -> set[str]:
    """Normalize and tokenize a string for Jaccard comparison."""
    if not text:
        return set()
    return set(re.findall(r'\w+', text.lower()))


def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _score_location(current: dict, candidate: dict) -> float:
    """Token Jaccard on location strings. Same location_id = 1.0 override."""
    # location_id exact match overrides
    c_lid = current.get("location_id")
    h_lid = candidate.get("location_id")
    if c_lid and h_lid and str(c_lid) == str(h_lid):
        return 1.0

    c_loc = current.get("location") or ""
    h_loc = candidate.get("location") or ""
    if not c_loc and not h_loc:
        return 0.0
    return _jaccard(_tokenize(c_loc), _tokenize(h_loc))


def _score_temporal(current: dict, candidate: dict) -> float:
    """Average of: same time-of-day bucket (6hr), same weekday, same month."""
    c_dt = current.get("occurred_at")
    h_dt = candidate.get("occurred_at")
    if not c_dt or not h_dt:
        return 0.0

    if isinstance(c_dt, str):
        c_dt = datetime.fromisoformat(c_dt.replace("Z", "+00:00"))
    if isinstance(h_dt, str):
        h_dt = datetime.fromisoformat(h_dt.replace("Z", "+00:00"))

    # Time-of-day bucket (6hr windows: 0-5, 6-11, 12-17, 18-23)
    time_match = 1.0 if (c_dt.hour // 6) == (h_dt.hour // 6) else 0.0
    # Same weekday
    weekday_match = 1.0 if c_dt.weekday() == h_dt.weekday() else 0.0
    # Same month
    month_match = 1.0 if c_dt.month == h_dt.month else 0.0

    return (time_match + weekday_match + month_match) / 3.0


# --- Category sub-scorers ---

def _cost_proximity(a: Optional[float], b: Optional[float]) -> float:
    """Score proximity of two cost values. Returns 0-1."""
    if a is None or b is None:
        return 0.0
    if a == 0 and b == 0:
        return 1.0
    max_val = max(abs(a), abs(b))
    if max_val == 0:
        return 1.0
    return max(0.0, 1.0 - abs(a - b) / max_val)


TREATMENT_ORDINAL = {
    "first_aid": 1, "medical": 2, "er": 3, "hospitalization": 4,
}


def _score_safety_overlap(c_data: dict, h_data: dict) -> float:
    """Safety-specific sub-field comparison."""
    scores = []
    # injury_type match
    if c_data.get("injury_type") and h_data.get("injury_type"):
        scores.append(1.0 if c_data["injury_type"] == h_data["injury_type"] else 0.0)
    # body_parts Jaccard
    c_bp = set(c_data.get("body_parts") or [])
    h_bp = set(h_data.get("body_parts") or [])
    if c_bp or h_bp:
        scores.append(_jaccard(c_bp, h_bp))
    # equipment match
    if c_data.get("equipment_involved") and h_data.get("equipment_involved"):
        scores.append(_jaccard(
            _tokenize(c_data["equipment_involved"]),
            _tokenize(h_data["equipment_involved"]),
        ))
    # treatment proximity
    c_t = TREATMENT_ORDINAL.get(c_data.get("treatment", ""), 0)
    h_t = TREATMENT_ORDINAL.get(h_data.get("treatment", ""), 0)
    if c_t and h_t:
        scores.append(1.0 - abs(c_t - h_t) / 3.0)

    return sum(scores) / len(scores) if scores else 0.0


def _score_behavioral_overlap(c_data: dict, h_data: dict) -> float:
    """Behavioral-specific sub-field comparison."""
    scores = []
    # policy_violated match
    if c_data.get("policy_violated") and h_data.get("policy_violated"):
        scores.append(_jaccard(
            _tokenize(c_data["policy_violated"]),
            _tokenize(h_data["policy_violated"]),
        ))
    # parties count similarity
    c_cnt = len(c_data.get("parties_involved") or [])
    h_cnt = len(h_data.get("parties_involved") or [])
    if c_cnt or h_cnt:
        max_cnt = max(c_cnt, h_cnt)
        scores.append(1.0 - abs(c_cnt - h_cnt) / max_cnt if max_cnt else 1.0)

    return sum(scores) / len(scores) if scores else 0.0


def _score_property_overlap(c_data: dict, h_data: dict) -> float:
    """Property-specific sub-field comparison."""
    scores = []
    # estimated_cost proximity
    if c_data.get("estimated_cost") is not None and h_data.get("estimated_cost") is not None:
        scores.append(_cost_proximity(c_data["estimated_cost"], h_data["estimated_cost"]))
    # insurance_claim match
    if c_data.get("insurance_claim") is not None and h_data.get("insurance_claim") is not None:
        scores.append(1.0 if c_data["insurance_claim"] == h_data["insurance_claim"] else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


def _score_nearmiss_overlap(c_data: dict, h_data: dict) -> float:
    """Near-miss-specific sub-field comparison."""
    c_hazard = c_data.get("hazard_identified") or ""
    h_hazard = h_data.get("hazard_identified") or ""
    if not c_hazard and not h_hazard:
        return 0.0
    return _jaccard(_tokenize(c_hazard), _tokenize(h_hazard))


_CATEGORY_SCORERS = {
    "safety": _score_safety_overlap,
    "behavioral": _score_behavioral_overlap,
    "property": _score_property_overlap,
    "near_miss": _score_nearmiss_overlap,
}


def _score_category_overlap(current: dict, candidate: dict) -> float:
    """Type-specific category_data comparison. 0.0 if different types."""
    if current["incident_type"] != candidate["incident_type"]:
        return 0.0

    c_data = current.get("category_data") or {}
    h_data = candidate.get("category_data") or {}
    if not c_data and not h_data:
        return 0.0

    scorer = _CATEGORY_SCORERS.get(current["incident_type"])
    if not scorer:
        return 0.0

    return scorer(c_data, h_data)


def compute_structural_scores(current: dict, candidates: list[dict]) -> list[dict]:
    """Phase 1: Compute structured scores for all candidates.

    Returns candidates with `structural_score` and individual dimension scores,
    filtered to those above STRUCTURAL_THRESHOLD, sorted descending, limited to PHASE1_KEEP.
    """
    scored = []
    for cand in candidates:
        type_s = _score_type_match(current, cand)
        sev_s = _score_severity(current, cand)
        cat_s = _score_category_overlap(current, cand)
        loc_s = _score_location(current, cand)
        temp_s = _score_temporal(current, cand)

        structural_score = (
            type_s * W_TYPE +
            sev_s * W_SEVERITY +
            cat_s * W_CATEGORY +
            loc_s * W_LOCATION +
            temp_s * W_TEMPORAL
        )

        if structural_score >= STRUCTURAL_THRESHOLD:
            scored.append({
                **cand,
                "scores": {
                    "type_match": round(type_s, 3),
                    "severity_proximity": round(sev_s, 3),
                    "category_overlap": round(cat_s, 3),
                    "location_similarity": round(loc_s, 3),
                    "temporal_pattern": round(temp_s, 3),
                },
                "structural_score": round(structural_score, 4),
            })

    scored.sort(key=lambda x: x["structural_score"], reverse=True)
    return scored[:PHASE1_KEEP]


# ===========================================
# Phase 2: Semantic Enrichment (Gemini)
# ===========================================

PRECEDENT_SEMANTIC_PROMPT = """You are an incident analysis assistant. Score the semantic similarity between a current incident and {count} historical candidate incidents.

CURRENT INCIDENT:
Title: {title}
Description: {description}
Type: {incident_type}
Root Cause: {root_cause}

CANDIDATE INCIDENTS:
{candidates_text}

For EACH candidate, provide:
1. text_similarity (0.0-1.0): How semantically similar are the titles + descriptions? Consider the nature of the incident, not just keyword overlap.
2. root_cause_similarity (0.0-1.0): How similar are the root causes? Return 0.0 if either incident lacks a root cause.
3. common_factors: A list of 1-3 short phrases describing what makes these incidents similar.

Also provide a brief pattern_summary (1-2 sentences) about any overarching patterns you notice across the similar incidents.

Return ONLY a JSON object:
{{
  "scores": [
    {{
      "incident_id": "uuid",
      "text_similarity": 0.85,
      "root_cause_similarity": 0.72,
      "common_factors": ["Same wet floor scenario", "Loading dock area"]
    }}
  ],
  "pattern_summary": "Multiple slip incidents in the loading dock suggest a systemic floor maintenance issue."
}}"""


async def enrich_with_semantics(
    current: dict,
    top_candidates: list[dict],
    api_key: Optional[str] = None,
    vertex_project: Optional[str] = None,
) -> dict[str, Any]:
    """Phase 2: Single Gemini call to score semantic dimensions for top candidates.

    Returns dict with 'scores' list and 'pattern_summary'.
    """
    from google import genai
    from ...core.services.rate_limiter import get_rate_limiter

    if vertex_project:
        client = genai.Client(vertexai=True, project=vertex_project, location="us-central1")
    elif api_key:
        client = genai.Client(api_key=api_key)
    else:
        raise ValueError("Either api_key or vertex_project must be provided")

    # Rate limit check
    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("ir_analysis", "precedent_semantic")

    # Build candidates text
    candidates_lines = []
    for c in top_candidates:
        root_cause_text = c.get("root_cause") or "N/A"
        candidates_lines.append(
            f"ID: {c['id']}\n"
            f"  Title: {c['title']}\n"
            f"  Description: {(c.get('description') or 'N/A')[:300]}\n"
            f"  Type: {c['incident_type']}\n"
            f"  Root Cause: {root_cause_text[:200]}"
        )

    prompt = PRECEDENT_SEMANTIC_PROMPT.format(
        count=len(top_candidates),
        title=current.get("title", ""),
        description=(current.get("description") or "N/A")[:500],
        incident_type=current.get("incident_type", ""),
        root_cause=(current.get("root_cause") or "N/A")[:300],
        candidates_text="\n\n".join(candidates_lines),
    )

    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            ),
            timeout=GEMINI_CALL_TIMEOUT,
        )

        await rate_limiter.record_call("ir_analysis", "precedent_semantic")

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        result = json.loads(text.strip())
        return result

    except Exception as e:
        logger.warning(f"Gemini semantic enrichment failed: {e}")
        # Return empty scores — structural scores still work
        return {
            "scores": [],
            "pattern_summary": None,
        }


# ===========================================
# Resolution Effectiveness (Batched)
# ===========================================

async def batch_check_resolution_effectiveness(
    conn, candidates: list[dict]
) -> dict[str, Optional[bool]]:
    """Batch check resolution effectiveness for multiple candidates.

    Returns {incident_id: bool | None} — True if effective, False if recurred, None if not resolved.
    Uses a single query instead of N+1.
    """
    # Collect resolved candidates with location info
    checks = []
    for cand in candidates:
        cand_id = str(cand["id"])
        resolved_at = cand.get("resolved_at")
        if not resolved_at:
            continue
        location_id = cand.get("location_id")
        location = cand.get("location")
        if not location_id and not location:
            continue
        checks.append({
            "id": cand_id,
            "incident_type": cand["incident_type"],
            "location_id": str(location_id) if location_id else None,
            "location": location,
            "resolved_at": resolved_at,
            "window_end": resolved_at + timedelta(days=90),
        })

    if not checks:
        return {}

    # Build a single query using LATERAL joins for all checks
    # For simplicity and correctness, use one query per batch via UNION ALL
    parts = []
    params = []
    idx = 1
    for c in checks:
        if c["location_id"]:
            parts.append(f"""
                SELECT ${idx}::text AS cand_id, COUNT(*) AS cnt
                FROM ir_incidents
                WHERE id != ${idx}::uuid
                AND incident_type = ${idx+1}
                AND location_id = ${idx+2}::uuid
                AND occurred_at > ${idx+3}
                AND occurred_at <= ${idx+4}
            """)
            params.extend([c["id"], c["incident_type"], c["location_id"], c["resolved_at"], c["window_end"]])
            idx += 5
        else:
            parts.append(f"""
                SELECT ${idx}::text AS cand_id, COUNT(*) AS cnt
                FROM ir_incidents
                WHERE id != ${idx}::uuid
                AND incident_type = ${idx+1}
                AND location = ${idx+2}
                AND occurred_at > ${idx+3}
                AND occurred_at <= ${idx+4}
            """)
            params.extend([c["id"], c["incident_type"], c["location"], c["resolved_at"], c["window_end"]])
            idx += 5

    query = " UNION ALL ".join(parts)
    rows = await conn.fetch(query, *params)

    results: dict[str, Optional[bool]] = {}
    for row in rows:
        results[row["cand_id"]] = row["cnt"] == 0

    return results


# ===========================================
# Orchestrator
# ===========================================

async def find_precedents(incident_id: str, conn, incident_row=None) -> dict[str, Any]:
    """Main orchestrator: query -> Phase 1 -> Phase 2 -> format response.

    Args:
        incident_id: UUID string of the current incident.
        conn: asyncpg connection.
        incident_row: Optional pre-fetched incident row to avoid redundant query.

    Returns a PrecedentAnalysis-shaped dict.
    """
    from ...config import get_settings

    # Use provided row or fetch it
    if incident_row:
        row = incident_row
    else:
        row = await conn.fetchrow(
            """
            SELECT id, incident_number, title, description, incident_type, severity,
                   status, occurred_at, location, location_id, company_id,
                   root_cause, corrective_actions, category_data, resolved_at
            FROM ir_incidents WHERE id = $1
            """,
            incident_id,
        )
    if not row:
        return {"precedents": [], "pattern_summary": None, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}

    current = dict(row)
    # Parse category_data if it's a string
    if isinstance(current.get("category_data"), str):
        try:
            current["category_data"] = json.loads(current["category_data"])
        except (json.JSONDecodeError, TypeError):
            current["category_data"] = {}

    company_id = current.get("company_id")
    lookback = datetime.utcnow() - timedelta(days=LOOKBACK_MONTHS * 30)

    # Query historical incidents for the same company (last 24 months)
    if company_id:
        historical = await conn.fetch(
            """
            SELECT id, incident_number, title, description, incident_type, severity,
                   status, occurred_at, location, location_id,
                   root_cause, corrective_actions, category_data, resolved_at, reported_at
            FROM ir_incidents
            WHERE id != $1 AND company_id = $2 AND occurred_at >= $3
            ORDER BY occurred_at DESC
            """,
            incident_id,
            str(company_id),
            lookback,
        )
    else:
        historical = await conn.fetch(
            """
            SELECT id, incident_number, title, description, incident_type, severity,
                   status, occurred_at, location, location_id,
                   root_cause, corrective_actions, category_data, resolved_at, reported_at
            FROM ir_incidents
            WHERE id != $1 AND occurred_at >= $2
            ORDER BY occurred_at DESC
            """,
            incident_id,
            lookback,
        )

    if not historical:
        return {
            "precedents": [],
            "pattern_summary": None,
            "generated_at": datetime.utcnow().isoformat(),
            "from_cache": False,
        }

    # Convert rows to dicts and parse category_data
    candidates = []
    for h in historical:
        d = dict(h)
        if isinstance(d.get("category_data"), str):
            try:
                d["category_data"] = json.loads(d["category_data"])
            except (json.JSONDecodeError, TypeError):
                d["category_data"] = {}
        candidates.append(d)

    # Phase 1: Structural scoring
    top = compute_structural_scores(current, candidates)

    if not top:
        return {
            "precedents": [],
            "pattern_summary": None,
            "generated_at": datetime.utcnow().isoformat(),
            "from_cache": False,
        }

    # Phase 2: Semantic enrichment
    settings = get_settings()
    semantic_result = await enrich_with_semantics(
        current,
        top,
        api_key=settings.gemini_api_key if not settings.use_vertex else None,
        vertex_project=settings.vertex_project if settings.use_vertex else None,
    )

    # Build semantic score lookup
    semantic_lookup: dict[str, dict] = {}
    for s in semantic_result.get("scores", []):
        sid = str(s.get("incident_id", ""))
        semantic_lookup[sid] = s

    # Batch check resolution effectiveness (single query)
    effectiveness = await batch_check_resolution_effectiveness(conn, top)

    # Blend scores and build final precedents
    precedents = []
    for cand in top:
        cand_id = str(cand["id"])
        sem = semantic_lookup.get(cand_id, {})

        text_sim = float(sem.get("text_similarity", 0.0))
        root_cause_sim = float(sem.get("root_cause_similarity", 0.0))
        common_factors = sem.get("common_factors", [])

        scores = cand["scores"]
        final_score = (
            scores["type_match"] * W_TYPE +
            scores["severity_proximity"] * W_SEVERITY +
            scores["category_overlap"] * W_CATEGORY +
            scores["location_similarity"] * W_LOCATION +
            scores["temporal_pattern"] * W_TEMPORAL +
            text_sim * W_TEXT +
            root_cause_sim * W_ROOT_CAUSE
        )

        # Resolution details
        resolved_at = cand.get("resolved_at")
        reported_at = cand.get("reported_at") or cand.get("occurred_at")
        resolution_days = None
        if resolved_at and reported_at:
            delta = resolved_at - reported_at
            resolution_days = max(0, delta.days)

        resolution_effective = effectiveness.get(cand_id)

        precedents.append({
            "incident_id": cand_id,
            "incident_number": cand["incident_number"],
            "title": cand["title"],
            "incident_type": cand["incident_type"],
            "severity": cand.get("severity", "medium"),
            "status": cand.get("status", "reported"),
            "occurred_at": cand["occurred_at"].isoformat() if isinstance(cand["occurred_at"], datetime) else cand["occurred_at"],
            "resolved_at": resolved_at.isoformat() if isinstance(resolved_at, datetime) else resolved_at,
            "resolution_days": resolution_days,
            "root_cause": cand.get("root_cause"),
            "corrective_actions": cand.get("corrective_actions"),
            "resolution_effective": resolution_effective,
            "similarity_score": round(final_score, 3),
            "score_breakdown": {
                "type_match": scores["type_match"],
                "severity_proximity": scores["severity_proximity"],
                "category_overlap": scores["category_overlap"],
                "location_similarity": scores["location_similarity"],
                "temporal_pattern": scores["temporal_pattern"],
                "text_similarity": round(text_sim, 3),
                "root_cause_similarity": round(root_cause_sim, 3),
            },
            "common_factors": common_factors,
        })

    # Sort by final score and keep top 10
    precedents.sort(key=lambda x: x["similarity_score"], reverse=True)
    precedents = precedents[:FINAL_KEEP]

    return {
        "precedents": precedents,
        "pattern_summary": semantic_result.get("pattern_summary"),
        "generated_at": datetime.utcnow().isoformat(),
        "from_cache": False,
    }


async def find_precedents_stream(incident_id: str, conn, incident_row=None):
    """Streaming orchestrator: yields phase events between pipeline stages.

    Yields dicts with {"type": "phase", ...} for progress updates,
    and a final {"type": "result", "data": {...}} with the PrecedentAnalysis-shaped dict.
    """
    from ...config import get_settings

    if incident_row:
        row = incident_row
    else:
        row = await conn.fetchrow(
            """
            SELECT id, incident_number, title, description, incident_type, severity,
                   status, occurred_at, location, location_id, company_id,
                   root_cause, corrective_actions, category_data, resolved_at
            FROM ir_incidents WHERE id = $1
            """,
            incident_id,
        )
    if not row:
        yield {"type": "result", "data": {"precedents": [], "pattern_summary": None, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}}
        return

    current = dict(row)
    if isinstance(current.get("category_data"), str):
        try:
            current["category_data"] = json.loads(current["category_data"])
        except (json.JSONDecodeError, TypeError):
            current["category_data"] = {}

    company_id = current.get("company_id")
    lookback = datetime.utcnow() - timedelta(days=LOOKBACK_MONTHS * 30)

    yield {"type": "phase", "step": "querying_history", "message": "Querying incident history..."}

    if company_id:
        historical = await conn.fetch(
            """
            SELECT id, incident_number, title, description, incident_type, severity,
                   status, occurred_at, location, location_id,
                   root_cause, corrective_actions, category_data, resolved_at, reported_at
            FROM ir_incidents
            WHERE id != $1 AND company_id = $2 AND occurred_at >= $3
            ORDER BY occurred_at DESC
            """,
            incident_id,
            str(company_id),
            lookback,
        )
    else:
        historical = await conn.fetch(
            """
            SELECT id, incident_number, title, description, incident_type, severity,
                   status, occurred_at, location, location_id,
                   root_cause, corrective_actions, category_data, resolved_at, reported_at
            FROM ir_incidents
            WHERE id != $1 AND occurred_at >= $2
            ORDER BY occurred_at DESC
            """,
            incident_id,
            lookback,
        )

    if not historical:
        yield {"type": "phase", "step": "no_history", "message": "No historical incidents found"}
        yield {"type": "result", "data": {"precedents": [], "pattern_summary": None, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}}
        return

    yield {"type": "phase", "step": "structural_scoring", "message": f"Phase 1: Structural scoring ({len(historical)} candidates)..."}

    candidates = []
    for h in historical:
        d = dict(h)
        if isinstance(d.get("category_data"), str):
            try:
                d["category_data"] = json.loads(d["category_data"])
            except (json.JSONDecodeError, TypeError):
                d["category_data"] = {}
        candidates.append(d)

    top = compute_structural_scores(current, candidates)

    if not top:
        yield {"type": "phase", "step": "no_matches", "message": "No structurally similar incidents found"}
        yield {"type": "result", "data": {"precedents": [], "pattern_summary": None, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}}
        return

    yield {"type": "phase", "step": "semantic_enrichment", "message": f"Phase 2: Semantic enrichment ({len(top)} candidates)..."}

    settings = get_settings()
    semantic_result = await enrich_with_semantics(
        current,
        top,
        api_key=settings.gemini_api_key if not settings.use_vertex else None,
        vertex_project=settings.vertex_project if settings.use_vertex else None,
    )

    semantic_lookup: dict[str, dict] = {}
    for s in semantic_result.get("scores", []):
        sid = str(s.get("incident_id", ""))
        semantic_lookup[sid] = s

    yield {"type": "phase", "step": "resolution_check", "message": "Checking resolution effectiveness..."}

    effectiveness = await batch_check_resolution_effectiveness(conn, top)

    yield {"type": "phase", "step": "blending_scores", "message": "Blending scores and ranking precedents..."}

    precedents = []
    for cand in top:
        cand_id = str(cand["id"])
        sem = semantic_lookup.get(cand_id, {})

        text_sim = float(sem.get("text_similarity", 0.0))
        root_cause_sim = float(sem.get("root_cause_similarity", 0.0))
        common_factors = sem.get("common_factors", [])

        scores = cand["scores"]
        final_score = (
            scores["type_match"] * W_TYPE +
            scores["severity_proximity"] * W_SEVERITY +
            scores["category_overlap"] * W_CATEGORY +
            scores["location_similarity"] * W_LOCATION +
            scores["temporal_pattern"] * W_TEMPORAL +
            text_sim * W_TEXT +
            root_cause_sim * W_ROOT_CAUSE
        )

        resolved_at = cand.get("resolved_at")
        reported_at = cand.get("reported_at") or cand.get("occurred_at")
        resolution_days = None
        if resolved_at and reported_at:
            delta = resolved_at - reported_at
            resolution_days = max(0, delta.days)

        resolution_effective = effectiveness.get(cand_id)

        precedents.append({
            "incident_id": cand_id,
            "incident_number": cand["incident_number"],
            "title": cand["title"],
            "incident_type": cand["incident_type"],
            "severity": cand.get("severity", "medium"),
            "status": cand.get("status", "reported"),
            "occurred_at": cand["occurred_at"].isoformat() if isinstance(cand["occurred_at"], datetime) else cand["occurred_at"],
            "resolved_at": resolved_at.isoformat() if isinstance(resolved_at, datetime) else resolved_at,
            "resolution_days": resolution_days,
            "root_cause": cand.get("root_cause"),
            "corrective_actions": cand.get("corrective_actions"),
            "resolution_effective": resolution_effective,
            "similarity_score": round(final_score, 3),
            "score_breakdown": {
                "type_match": scores["type_match"],
                "severity_proximity": scores["severity_proximity"],
                "category_overlap": scores["category_overlap"],
                "location_similarity": scores["location_similarity"],
                "temporal_pattern": scores["temporal_pattern"],
                "text_similarity": round(text_sim, 3),
                "root_cause_similarity": round(root_cause_sim, 3),
            },
            "common_factors": common_factors,
        })

    precedents.sort(key=lambda x: x["similarity_score"], reverse=True)
    precedents = precedents[:FINAL_KEEP]

    result = {
        "precedents": precedents,
        "pattern_summary": semantic_result.get("pattern_summary"),
        "generated_at": datetime.utcnow().isoformat(),
        "from_cache": False,
    }
    yield {"type": "result", "data": result}
