"""The compliance scan over a handbook: gap dedup, severity ordering, the empty
result shape, and run_compliance_scan.
"""
import asyncio
import logging
from datetime import datetime, timezone

from ._config import _SEVERITY_ORDER

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Deep compliance scan — on-demand Gemini grade of the in-progress drafts,
# reusing the handbook-audit grader (no PDF; grades in-memory draft sections).
# --------------------------------------------------------------------------- #

def _dedupe_matched(state: str, results: list[dict]) -> list[dict]:
    """Covered results for a state, deduped by requirement key — the grader's
    positive signal ('this topic IS addressed, in section X')."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in results or []:
        if not r.get("covered"):
            continue
        key = r.get("requirement_key") or r.get("requirement_title") or ""
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "state": state,
            "requirement_key": r.get("requirement_key"),
            "requirement_title": r.get("requirement_title"),
            "matched_section_title": r.get("matched_section_title"),
            "citation": r.get("citation"),
        })
    return out


def _sort_gaps_by_severity(gaps: list[dict]) -> list[dict]:
    return sorted(
        gaps,
        key=lambda g: (_SEVERITY_ORDER.get((g.get("severity") or "").lower(), 9),
                       g.get("requirement_title") or ""),
    )


def _empty_scan(sections_graded: int) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_state": {},
        "gaps": [],
        "matched": [],
        "counts": {"critical": 0, "important": 0, "recommended": 0, "covered": 0},
        "states": [],
        "sections_graded": sections_graded,
    }


async def run_compliance_scan(session: dict, drafts: list[dict], grounding: dict) -> dict:
    """Grade the session's in-progress drafts against the applicable jurisdiction
    requirements, per state, reusing the handbook-audit grader. Returns a
    covered/gap map: each gap carries severity + `what_good_looks_like` (the "why
    this element isn't compliant" copy) + `matched_section_title`. Never raises —
    a dead grader degrades to an empty scan, matching the audit module's pattern."""
    from app.core.services.handbook_audit_service import (
        MAX_REQUIREMENTS_PER_STATE,
        _collapse_same_level_jurisdictions,
        _grade_state_coverage,
        _merge_duplicate_gaps_for_state,
    )

    drafts = drafts or []
    industry = session.get("industry") if session else None

    draft_sections: list[dict] = []
    for d in drafts:
        title = str(d.get("title") or "").strip()
        content = str(d.get("content") or "").strip()
        if title and content:
            draft_sections.append({"title": title[:240], "excerpt": content[:600]})

    requirements_map = (grounding or {}).get("requirements") or {}

    prepared: list[tuple[str, list[dict]]] = []
    for state, reqs in requirements_map.items():
        if not state or not reqs:
            continue
        collapsed = _collapse_same_level_jurisdictions(reqs)[:MAX_REQUIREMENTS_PER_STATE]
        if collapsed:
            prepared.append((state, collapsed))

    if not draft_sections or not prepared:
        return _empty_scan(len(draft_sections))

    async def _grade(state: str, reqs: list[dict]):
        try:
            results = await _grade_state_coverage(
                state=state, industry=industry, requirements=reqs, sections=draft_sections,
            )
        except Exception:  # noqa: BLE001
            logger.warning("handbook_pilot: compliance grade failed for %s", state)
            results = None
        return state, results

    graded = await asyncio.gather(*[_grade(s, r) for s, r in prepared])

    by_state: dict[str, dict] = {}
    all_gaps: list[dict] = []
    all_matched: list[dict] = []
    totals = {"critical": 0, "important": 0, "recommended": 0, "covered": 0}

    for state, results in graded:
        counts = {"critical": 0, "important": 0, "recommended": 0, "covered": 0}
        if not results:
            by_state[state] = {"counts": counts, "gaps": [], "matched": []}
            continue
        gaps = _merge_duplicate_gaps_for_state(state, results, counts)
        matched = _dedupe_matched(state, results)
        by_state[state] = {"counts": counts, "gaps": gaps, "matched": matched}
        all_gaps.extend(gaps)
        all_matched.extend(matched)
        for k in totals:
            totals[k] += counts.get(k, 0)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_state": by_state,
        "gaps": _sort_gaps_by_severity(all_gaps),
        "matched": all_matched,
        "counts": totals,
        "states": [s for s, _ in prepared],
        "sections_graded": len(draft_sections),
    }
