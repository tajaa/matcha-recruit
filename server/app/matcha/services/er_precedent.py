"""ER Precedent Service — Hybrid Similarity Scoring for ER Cases.

Two-phase pipeline:
  Phase 1: Structured pre-filter (pure Python, no AI)
  Phase 2: Semantic enrichment (single Gemini call for top candidates)

Combines 7 scoring dimensions into a final weighted score per precedent.
"""

import json
import asyncio
import logging
import math
import re
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ===========================================
# Constants
# ===========================================

LOOKBACK_MONTHS = 36
STRUCTURAL_THRESHOLD = 0.15
PHASE1_KEEP = 15
FINAL_KEEP = 8
GEMINI_CALL_TIMEOUT = 45
SIMILARITY_MIN_SCORE = 0.50

# Default scoring weights (total = 1.0) — overridable via platform_settings
DEFAULT_SIMILARITY_WEIGHTS = {
    "category": 0.30,
    "status": 0.05,
    "evidence": 0.10,
    "temporal": 0.05,
    "intake": 0.05,
    "text": 0.35,
    "investigation": 0.10,
}

STATUS_ORDINAL = {"open": 1, "in_review": 2, "pending_determination": 3, "closed": 4}

CATEGORY_RELATEDNESS = {
    ("harassment", "retaliation"): 0.5,
    ("harassment", "discrimination"): 0.4,
    ("harassment", "misconduct"): 0.3,
    ("discrimination", "retaliation"): 0.5,
    ("safety", "policy_violation"): 0.3,
    ("misconduct", "policy_violation"): 0.6,
    ("wage_hour", "policy_violation"): 0.4,
}


# ===========================================
# Phase 1: Structural Scorers
# ===========================================

def _score_category_match(current: dict, candidate: dict) -> float:
    """Same category = 1.0, related category via CATEGORY_RELATEDNESS, else 0.0."""
    c_cat = (current.get("category") or "").lower()
    h_cat = (candidate.get("category") or "").lower()
    if not c_cat or not h_cat:
        return 0.0
    if c_cat == h_cat:
        return 1.0
    return CATEGORY_RELATEDNESS.get(
        (c_cat, h_cat),
        CATEGORY_RELATEDNESS.get((h_cat, c_cat), 0.0),
    )


def _score_status_maturity(current: dict, candidate: dict) -> float:
    """Ordinal proximity: 1 - |a-b| / 3."""
    a = STATUS_ORDINAL.get((current.get("status") or "open").lower(), 1)
    b = STATUS_ORDINAL.get((candidate.get("status") or "open").lower(), 1)
    return 1.0 - abs(a - b) / 3.0


def _score_evidence_profile(current: dict, candidate: dict) -> float:
    """Jaccard similarity of doc type sets + doc count proximity, averaged."""
    c_types = set(current.get("doc_types") or [])
    h_types = set(candidate.get("doc_types") or [])
    c_count = current.get("doc_count", 0) or 0
    h_count = candidate.get("doc_count", 0) or 0

    # Jaccard of doc types
    if c_types or h_types:
        union = c_types | h_types
        jaccard = len(c_types & h_types) / len(union) if union else 0.0
    else:
        jaccard = 0.0

    # Count proximity
    max_count = max(c_count, h_count)
    if max_count > 0:
        count_prox = 1.0 - abs(c_count - h_count) / max_count
    else:
        count_prox = 1.0  # both zero

    return (jaccard + count_prox) / 2.0


def _score_temporal_recency(current: dict, candidate: dict) -> float:
    """Exponential decay based on candidate age. Score = exp(-days_old / 365)."""
    created = candidate.get("created_at")
    if not created:
        return 0.0
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))

    now = datetime.utcnow()
    # Handle timezone-aware datetimes
    if created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    days_old = max(0, (now - created).days)
    return math.exp(-days_old / 365.0)


def _parse_intake_context(val: Any) -> dict:
    """Parse intake_context, handling string or dict."""
    if not val:
        return {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val if isinstance(val, dict) else {}


def _score_intake_context_overlap(current: dict, candidate: dict) -> float:
    """Compare intake_context answers: immediate_risk, objective, complaint_format."""
    c_ctx = _parse_intake_context(current.get("intake_context"))
    h_ctx = _parse_intake_context(candidate.get("intake_context"))

    c_answers = c_ctx.get("answers") or {}
    h_answers = h_ctx.get("answers") or {}

    if not c_answers or not h_answers:
        return 0.0

    compare_keys = ["immediate_risk", "objective", "complaint_format"]
    matches = 0
    total = 0
    for key in compare_keys:
        c_val = c_answers.get(key)
        h_val = h_answers.get(key)
        if c_val is not None and h_val is not None:
            total += 1
            if str(c_val).lower() == str(h_val).lower():
                matches += 1

    return matches / total if total > 0 else 0.0


def compute_structural_scores(current: dict, candidates: list[dict], weights: dict[str, float] | None = None) -> list[dict]:
    """Phase 1: Compute structured scores for all candidates.

    Returns candidates with `structural_score` and individual dimension scores,
    filtered to those above STRUCTURAL_THRESHOLD, sorted descending, limited to PHASE1_KEEP.
    """
    w = weights or DEFAULT_SIMILARITY_WEIGHTS
    scored = []
    for cand in candidates:
        cat_s = _score_category_match(current, cand)
        sta_s = _score_status_maturity(current, cand)
        evi_s = _score_evidence_profile(current, cand)
        tmp_s = _score_temporal_recency(current, cand)
        int_s = _score_intake_context_overlap(current, cand)

        structural_score = (
            cat_s * w["category"] +
            sta_s * w["status"] +
            evi_s * w["evidence"] +
            tmp_s * w["temporal"] +
            int_s * w["intake"]
        )

        if structural_score >= STRUCTURAL_THRESHOLD:
            scored.append({
                **cand,
                "scores": {
                    "category_match": round(cat_s, 3),
                    "status_maturity": round(sta_s, 3),
                    "evidence_profile": round(evi_s, 3),
                    "temporal_recency": round(tmp_s, 3),
                    "intake_context_overlap": round(int_s, 3),
                },
                "structural_score": round(structural_score, 4),
            })

    scored.sort(key=lambda x: x["structural_score"], reverse=True)
    return scored[:PHASE1_KEEP]


# ===========================================
# Phase 2: Semantic Enrichment (Gemini)
# ===========================================

ER_SEMANTIC_PROMPT = """You are an employment relations case analysis assistant. Score the semantic similarity between a current ER case and {count} historical candidate cases.

CURRENT CASE:
Title: {title}
Description: {description}
Category: {category}
Outcome: {outcome}
Analysis Summary: {analysis_summary}

CANDIDATE CASES:
{candidates_text}

For EACH candidate, provide:
1. text_similarity (0.0-1.0): How semantically similar are the titles + descriptions? Consider the nature of the case, not just keyword overlap.
2. investigation_pattern_similarity (0.0-1.0): How similar are the investigation patterns, evidence types, and analysis approaches? Return 0.0 if either case lacks analysis info.
3. common_factors: A list of 1-3 short phrases describing what makes these cases similar.
4. relevance_note: A brief sentence explaining why this case is or isn't relevant.

Also provide a brief pattern_summary (1-2 sentences) about any overarching patterns you notice across the similar cases.

Return ONLY a JSON object:
{{
  "scores": [
    {{
      "case_id": "uuid",
      "text_similarity": 0.85,
      "investigation_pattern_similarity": 0.72,
      "common_factors": ["Same harassment pattern", "Similar witness testimony"],
      "relevance_note": "Both cases involve supervisor misconduct with multiple witnesses."
    }}
  ],
  "pattern_summary": "Multiple harassment cases involving supervisors suggest a systemic management training gap."
}}"""


PRECEDENT_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")


def _is_model_unavailable_error(error: Exception) -> bool:
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
    from ...config import get_settings
    from ...core.services.rate_limiter import get_rate_limiter

    if vertex_project:
        client = genai.Client(vertexai=True, project=vertex_project, location="us-central1")
    elif api_key:
        client = genai.Client(api_key=api_key)
    else:
        raise ValueError("Either api_key or vertex_project must be provided")

    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("er_analysis", "precedent_semantic")

    # Build candidates text
    candidates_lines = []
    for c in top_candidates:
        analysis_text = c.get("analysis_summary") or "N/A"
        candidates_lines.append(
            f"ID: {c['id']}\n"
            f"  Title: {c['title']}\n"
            f"  Description: {(c.get('description') or 'N/A')[:300]}\n"
            f"  Category: {c.get('category') or 'N/A'}\n"
            f"  Outcome: {c.get('outcome') or 'N/A'}\n"
            f"  Analysis Summary: {str(analysis_text)[:200]}"
        )

    prompt = ER_SEMANTIC_PROMPT.format(
        count=len(top_candidates),
        title=current.get("title", ""),
        description=(current.get("description") or "N/A")[:500],
        category=current.get("category") or "N/A",
        outcome=current.get("outcome") or "N/A",
        analysis_summary=str(current.get("analysis_summary") or "N/A")[:300],
        candidates_text="\n\n".join(candidates_lines),
    )

    # Build model candidates: configured model first, then stable fallbacks
    settings = get_settings()
    primary_model = getattr(settings, "analysis_model", None) or "gemini-2.5-flash"
    model_candidates: list[str] = []
    for m in [primary_model, *PRECEDENT_FALLBACK_MODELS]:
        if m and m not in model_candidates:
            model_candidates.append(m)

    try:
        last_model_error: Exception | None = None
        response = None
        for model_name in model_candidates:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    ),
                    timeout=GEMINI_CALL_TIMEOUT,
                )
                if model_name != primary_model:
                    logger.warning(
                        "Precedent semantic model '%s' unavailable; fell back to '%s'",
                        primary_model,
                        model_name,
                    )
                break
            except Exception as exc:
                if _is_model_unavailable_error(exc):
                    last_model_error = exc
                    logger.warning("Precedent model candidate '%s' unavailable: %s", model_name, exc)
                    continue
                raise

        if response is None:
            if last_model_error:
                raise last_model_error
            raise RuntimeError("No Gemini model candidates available for precedent semantic enrichment")

        await rate_limiter.record_call("er_analysis", "precedent_semantic")

        text = response.text.strip()
        # Extract JSON object robustly — handles any fence format or stray text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            logger.warning("Gemini semantic enrichment returned no JSON object")
            return {"scores": [], "pattern_summary": None}

        result = json.loads(json_match.group())
        return result

    except Exception as e:
        logger.warning(f"Gemini semantic enrichment failed: {e}")
        return {
            "scores": [],
            "pattern_summary": None,
        }


# ===========================================
# Outcome Effectiveness (Batched)
# ===========================================

async def batch_check_outcome_effectiveness(
    conn, candidates: list[dict]
) -> dict[str, Optional[bool]]:
    """Batch check if similar-category cases reopened within 90 days of closing.

    Returns {case_id: bool | None} -- True if effective (no recurrence),
    False if recurred, None if not closed.
    Uses a single query via UNION ALL.
    """
    checks = []
    for cand in candidates:
        cand_id = str(cand["id"])
        closed_at = cand.get("closed_at")
        if not closed_at:
            continue
        if isinstance(closed_at, str):
            closed_at = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
        company_id = cand.get("company_id")
        category = cand.get("category")
        if not company_id or not category:
            continue
        checks.append({
            "id": cand_id,
            "category": category,
            "company_id": str(company_id),
            "closed_at": closed_at,
            "window_end": closed_at + timedelta(days=90),
        })

    if not checks:
        return {}

    parts = []
    params = []
    idx = 1
    for c in checks:
        parts.append(f"""
            SELECT ${idx}::text AS cand_id, COUNT(*) AS cnt
            FROM er_cases
            WHERE id != ${idx}::uuid
            AND company_id = ${idx+1}::uuid
            AND category = ${idx+2}
            AND created_at > ${idx+3}
            AND created_at <= ${idx+4}
        """)
        params.extend([c["id"], c["company_id"], c["category"], c["closed_at"], c["window_end"]])
        idx += 5

    query = " UNION ALL ".join(parts)
    rows = await conn.fetch(query, *params)

    results: dict[str, Optional[bool]] = {}
    for row in rows:
        results[row["cand_id"]] = row["cnt"] == 0

    return results


# ===========================================
# Orchestrator (Streaming)
# ===========================================

async def find_similar_cases_stream(case_id: str, conn, case_row=None):
    """Streaming orchestrator: yields phase events between pipeline stages.

    Yields dicts with {"type": "phase", ...} for progress updates,
    and a final {"type": "result", "data": {...}} with the result dict.
    """
    from ...config import get_settings
    from ...core.services.platform_settings import get_er_similarity_weights

    weights = await get_er_similarity_weights(conn=conn)

    if case_row:
        row = case_row
    else:
        row = await conn.fetchrow(
            """
            SELECT c.id, c.case_number, c.title, c.description, c.category,
                   c.outcome, c.status, c.intake_context, c.company_id,
                   c.created_at, c.closed_at,
                   COALESCE(d.doc_count, 0) as doc_count,
                   COALESCE(d.doc_types, ARRAY[]::text[]) as doc_types
            FROM er_cases c
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int as doc_count,
                       array_agg(DISTINCT document_type) as doc_types
                FROM er_case_documents WHERE case_id = c.id AND processing_status = 'completed'
            ) d ON true
            WHERE c.id = $1
            """,
            case_id,
        )
    if not row:
        yield {"type": "result", "data": {"matches": [], "pattern_summary": None, "outcome_distribution": {}, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}}
        return

    current = dict(row)
    # Parse intake_context if string
    if isinstance(current.get("intake_context"), str):
        try:
            current["intake_context"] = json.loads(current["intake_context"])
        except (json.JSONDecodeError, TypeError):
            current["intake_context"] = {}

    company_id = current.get("company_id")
    lookback = datetime.utcnow() - timedelta(days=LOOKBACK_MONTHS * 30)

    yield {"type": "phase", "step": "querying_history", "message": "Querying case history..."}

    if not company_id:
        yield {"type": "phase", "step": "no_history", "message": "No company context for case"}
        yield {"type": "result", "data": {"matches": [], "pattern_summary": None, "outcome_distribution": {}, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}}
        return

    historical = await conn.fetch(
        """
        SELECT c.id, c.case_number, c.title, c.description, c.category,
               c.outcome, c.status, c.intake_context, c.company_id,
               c.created_at, c.closed_at,
               COALESCE(d.doc_count, 0) as doc_count,
               COALESCE(d.doc_types, ARRAY[]::text[]) as doc_types
        FROM er_cases c
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int as doc_count,
                   array_agg(DISTINCT document_type) as doc_types
            FROM er_case_documents WHERE case_id = c.id AND processing_status = 'completed'
        ) d ON true
        WHERE c.id != $1 AND c.company_id = $2 AND c.created_at >= $3
        ORDER BY c.created_at DESC
        """,
        case_id,
        str(company_id),
        lookback,
    )

    if not historical:
        yield {"type": "phase", "step": "no_history", "message": "No historical cases found"}
        yield {"type": "result", "data": {"matches": [], "pattern_summary": None, "outcome_distribution": {}, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}}
        return

    yield {"type": "phase", "step": "structural_scoring", "message": f"Phase 1: Structural scoring ({len(historical)} candidates)..."}

    candidates = []
    for h in historical:
        d = dict(h)
        if isinstance(d.get("intake_context"), str):
            try:
                d["intake_context"] = json.loads(d["intake_context"])
            except (json.JSONDecodeError, TypeError):
                d["intake_context"] = {}
        candidates.append(d)

    top = compute_structural_scores(current, candidates, weights=weights)

    if not top:
        yield {"type": "phase", "step": "no_matches", "message": "No structurally similar cases found"}
        yield {"type": "result", "data": {"matches": [], "pattern_summary": None, "outcome_distribution": {}, "generated_at": datetime.utcnow().isoformat(), "from_cache": False}}
        return

    yield {"type": "phase", "step": "semantic_enrichment", "message": f"Phase 2: Semantic enrichment ({len(top)} candidates)..."}

    # Fetch analysis summaries for semantic enrichment
    case_ids = [str(current["id"])] + [str(c["id"]) for c in top]
    analysis_rows = await conn.fetch(
        """
        SELECT case_id, analysis_data
        FROM er_case_analysis
        WHERE case_id = ANY($1::uuid[]) AND analysis_type = 'summary'
        ORDER BY generated_at DESC
        """,
        case_ids,
    )
    analysis_lookup: dict[str, str] = {}
    for ar in analysis_rows:
        cid = str(ar["case_id"])
        if cid not in analysis_lookup:
            data = ar["analysis_data"]
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    data = {}
            if data:
                summary = (
                    data.get("summary")
                    or data.get("text")
                    or data.get("timeline_summary")
                    or ""
                )
                if not summary:
                    parts = []
                    if isinstance(data.get("analysis"), dict) and data["analysis"].get("summary"):
                        parts.append(data["analysis"]["summary"])
                    if isinstance(data.get("discrepancies"), list) and data["discrepancies"]:
                        parts.append(f"{len(data['discrepancies'])} discrepancies identified")
                    if isinstance(data.get("violations"), list) and data["violations"]:
                        parts.append(f"{len(data['violations'])} policy violations found")
                    if isinstance(data.get("events"), list) and data["events"]:
                        parts.append(f"Timeline with {len(data['events'])} events")
                    summary = ". ".join(parts) if parts else ""
            else:
                summary = ""
            analysis_lookup[cid] = summary

    current["analysis_summary"] = analysis_lookup.get(str(current["id"]))
    for c in top:
        c["analysis_summary"] = analysis_lookup.get(str(c["id"]))

    settings = get_settings()
    semantic_result = await enrich_with_semantics(
        current,
        top,
        api_key=settings.gemini_api_key if not settings.use_vertex else None,
        vertex_project=settings.vertex_project if settings.use_vertex else None,
    )

    semantic_lookup: dict[str, dict] = {}
    for s in semantic_result.get("scores", []):
        sid = str(s.get("case_id", ""))
        semantic_lookup[sid] = s

    yield {"type": "phase", "step": "outcome_check", "message": "Checking outcome effectiveness..."}

    effectiveness = await batch_check_outcome_effectiveness(conn, top)

    yield {"type": "phase", "step": "blending_scores", "message": "Blending scores and ranking cases..."}

    matches = []
    for cand in top:
        cand_id = str(cand["id"])
        sem = semantic_lookup.get(cand_id, {})

        text_sim = float(sem.get("text_similarity", 0.0))
        inv_sim = float(sem.get("investigation_pattern_similarity", 0.0))
        common_factors = sem.get("common_factors", [])
        relevance_note = sem.get("relevance_note")

        scores = cand["scores"]
        final_score = (
            scores["category_match"] * weights["category"] +
            scores["status_maturity"] * weights["status"] +
            scores["evidence_profile"] * weights["evidence"] +
            scores["temporal_recency"] * weights["temporal"] +
            scores["intake_context_overlap"] * weights["intake"] +
            text_sim * weights["text"] +
            inv_sim * weights["investigation"]
        )

        # Resolution days
        created_at = cand.get("created_at")
        closed_at = cand.get("closed_at")
        resolution_days = None
        if created_at and closed_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if isinstance(closed_at, str):
                closed_at = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            delta = closed_at - created_at
            resolution_days = max(0, delta.days)

        matches.append({
            "case_id": cand_id,
            "case_number": cand.get("case_number"),
            "title": cand.get("title"),
            "category": cand.get("category"),
            "outcome": cand.get("outcome"),
            "status": cand.get("status"),
            "created_at": cand["created_at"].isoformat() if isinstance(cand["created_at"], datetime) else cand["created_at"],
            "closed_at": cand["closed_at"].isoformat() if isinstance(cand.get("closed_at"), datetime) else cand.get("closed_at"),
            "resolution_days": resolution_days,
            "outcome_effective": effectiveness.get(cand_id),
            "similarity_score": round(final_score, 3),
            "score_breakdown": {
                "category_match": scores["category_match"],
                "status_maturity": scores["status_maturity"],
                "evidence_profile": scores["evidence_profile"],
                "temporal_recency": scores["temporal_recency"],
                "intake_context_overlap": scores["intake_context_overlap"],
                "text_similarity": round(text_sim, 3),
                "investigation_pattern_similarity": round(inv_sim, 3),
            },
            "common_factors": common_factors,
            "relevance_note": relevance_note,
        })

    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    matches = [m for m in matches if m["similarity_score"] >= SIMILARITY_MIN_SCORE]
    matches = matches[:FINAL_KEEP]

    # Build outcome distribution across matches
    outcome_dist: dict[str, int] = {}
    for m in matches:
        out = m.get("outcome")
        if out:
            outcome_dist[out] = outcome_dist.get(out, 0) + 1

    result = {
        "matches": matches,
        "pattern_summary": semantic_result.get("pattern_summary"),
        "outcome_distribution": outcome_dist,
        "generated_at": datetime.utcnow().isoformat(),
        "from_cache": False,
    }
    yield {"type": "result", "data": result}
