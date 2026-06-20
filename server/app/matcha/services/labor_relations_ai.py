"""Gemini helpers for the Labor Relations feature.

Composes prompts and delegates to a cached ``ERAnalyzer`` instance (reusing its
model-fallback + client plumbing — see ``er_analyzer.py``). Never instantiate a
Gemini client per request.

Two capabilities (Phase 1):
- ``extract_clauses_from_cba`` — parse an uploaded CBA's text into a structured
  clause library + a best-effort grievance-procedure step config.
- ``assess_grievance_merit`` — stream a merit assessment grading a grievance's
  facts against the cited contract language.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Optional

from app.matcha.services.er_analyzer import ERAnalyzer

logger = logging.getLogger(__name__)

# Mirrors the lr_cba_clauses.category CHECK constraint (labor01).
_CLAUSE_CATEGORIES = (
    "wages", "hours", "seniority", "grievance_procedure", "discipline", "just_cause",
    "overtime", "benefits", "union_security", "management_rights", "health_safety",
    "layoff_recall", "holidays_leave", "other",
)

# CBA documents are long; cap the text we send so a giant contract can't blow the
# context window. The grievance procedure + economic articles are virtually
# always within the first chunk.
_MAX_CBA_CHARS = 500_000

_analyzer: Optional[ERAnalyzer] = None


def get_labor_analyzer() -> ERAnalyzer:
    """Return a process-wide cached analyzer (reuses ERAnalyzer's Gemini client)."""
    global _analyzer
    if _analyzer is None:
        from app.config import get_settings
        settings = get_settings()
        _analyzer = ERAnalyzer(api_key=settings.gemini_api_key)
    return _analyzer


def _parse_json_block(text: str) -> Any:
    """Best-effort JSON extraction from a model response (handles ``` fences)."""
    if not text:
        return None
    cleaned = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        # Fall back to the first balanced {...} or [...] span.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cleaned.find(opener)
            end = cleaned.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except (json.JSONDecodeError, TypeError):
                    continue
    return None


async def extract_clauses_from_cba(extracted_text: str) -> dict[str, Any]:
    """Extract a clause library + grievance step config from CBA text.

    Returns ``{"clauses": [...], "grievance_step_config": [...]}``. Clauses are
    advisory (``source='ai_extracted'``) and HR-confirmable; never enforce a
    deadline off the step config until a human confirms it.
    """
    if not extracted_text or not extracted_text.strip():
        return {"clauses": [], "grievance_step_config": []}

    text = extracted_text[:_MAX_CBA_CHARS]
    categories = ", ".join(_CLAUSE_CATEGORIES)
    prompt = f"""You are a labor-relations analyst extracting structured data from a collective bargaining agreement (CBA).

Return ONLY valid JSON (no prose, no markdown fences) with this exact shape:
{{
  "clauses": [
    {{
      "article_number": "Article 12" | null,
      "title": "short clause title",
      "clause_text": "the verbatim or lightly-trimmed clause text",
      "category": one of [{categories}],
      "confidence": 0.0-1.0
    }}
  ],
  "grievance_step_config": [
    {{"step": 1, "name": "Step 1 — Supervisor", "file_within_days": 10, "respond_within_days": 5, "day_basis": "calendar" | "working"}}
  ]
}}

Rules:
- Extract the substantive articles (wages, hours, seniority, grievance procedure, discipline/just cause, overtime, benefits, union security, management rights, health & safety, layoff/recall, holidays/leave). Use "other" only when nothing fits.
- For grievance_step_config: read the grievance-procedure article. Capture each step in order, its name, the number of days to FILE at that step and the number of days for management to RESPOND. Set day_basis to "working" if the contract says "working"/"business" days, else "calendar". If the procedure is unclear, return an empty array.
- Keep clause_text faithful to the contract; do not invent terms.

CBA TEXT:
{text}
"""
    analyzer = get_labor_analyzer()
    raw = await analyzer._generate_content_async(prompt)
    parsed = _parse_json_block(raw) or {}

    clauses = parsed.get("clauses") if isinstance(parsed, dict) else None
    steps = parsed.get("grievance_step_config") if isinstance(parsed, dict) else None
    return {
        "clauses": _clean_clauses(clauses if isinstance(clauses, list) else []),
        "grievance_step_config": _clean_steps(steps if isinstance(steps, list) else []),
    }


def _clean_clauses(raw: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = (item.get("clause_text") or "").strip()
        if not text:
            continue
        category = item.get("category")
        if category not in _CLAUSE_CATEGORIES:
            category = "other"
        try:
            confidence = float(item.get("confidence"))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = None
        out.append({
            "article_number": (item.get("article_number") or None),
            "title": (item.get("title") or None),
            "clause_text": text,
            "category": category,
            "confidence": confidence,
            "sort_order": i,
        })
    return out


def _clean_steps(raw: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            out.append({
                "step": int(item.get("step") or (i + 1)),
                "name": str(item.get("name") or f"Step {i + 1}"),
                "file_within_days": int(item.get("file_within_days") or 0),
                "respond_within_days": int(item.get("respond_within_days") or 0),
                "day_basis": "working" if item.get("day_basis") == "working" else "calendar",
            })
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda s: s["step"])
    return out


async def assess_grievance_merit(grievance: dict[str, Any]) -> AsyncIterator[str]:
    """Stream a merit assessment of a grievance vs its cited CBA clauses."""
    clauses = grievance.get("violated_clauses") or []
    clause_block = "\n\n".join(
        f"[{c.get('article_number') or 'Clause'}] {c.get('title') or ''}\n{c.get('clause_text') or ''}"
        for c in clauses
    ) or "(No specific CBA clauses cited.)"

    grievant = grievance.get("grievant") or {}
    grievant_name = " ".join(
        x for x in [grievant.get("first_name"), grievant.get("last_name")] if x
    ) or ("a class of employees" if grievance.get("is_class_grievance") else "the grievant")

    prompt = f"""You are an experienced labor-relations advisor assessing the merit of a union grievance for the EMPLOYER's HR team. Be candid and practical.

GRIEVANCE
- Number: {grievance.get('grievance_number')}
- Title: {grievance.get('title')}
- Type: {grievance.get('grievance_type') or 'unspecified'}
- Grievant: {grievant_name}
- Description: {grievance.get('description') or '(none provided)'}

CITED CONTRACT LANGUAGE
{clause_block}

Produce a concise assessment with these sections:
1. **Contract analysis** — does the cited language actually support the grievance? Quote the operative words.
2. **Strengths of the union's position**.
3. **Weaknesses / employer defenses** (past practice, management rights, procedural/timeliness issues).
4. **Likely outcome & settlement posture** — would this survive arbitration? What's a reasonable resolution?

Ground every point in the facts and contract language above. Do not invent contract terms. This is advisory, not legal advice.
"""
    analyzer = get_labor_analyzer()
    async for chunk in analyzer._generate_content_streaming(prompt):
        yield chunk
