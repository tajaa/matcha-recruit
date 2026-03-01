"""ER guidance helper utilities.

Utilities are kept separate from FastAPI route modules so they can be tested
without importing the entire routes package.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional


def _normalize_analysis_payload(raw_value: Any, default: dict[str, Any]) -> dict[str, Any]:
    """Normalize analysis payloads to dict with fallback defaults."""
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return default
    return default


def _guidance_card_id(raw_id: Any, title: str, idx: int) -> str:
    if isinstance(raw_id, str):
        cleaned = re.sub(r"[^a-z0-9-]+", "-", raw_id.strip().lower()).strip("-")
        if cleaned:
            return cleaned[:48]
    title_slug = re.sub(r"[^a-z0-9-]+", "-", title.strip().lower()).strip("-")
    if title_slug:
        return f"{title_slug[:40]}-{idx + 1}"
    return f"guidance-{idx + 1}"


def _normalize_guidance_action(
    raw_action: Any,
    can_run_discrepancies: bool,
) -> dict[str, Any]:
    valid_action_types = {"run_analysis", "open_tab", "search_evidence", "upload_document"}
    valid_tabs = {"timeline", "discrepancies", "policy", "search"}
    valid_analysis_types = {"timeline", "discrepancies", "policy"}

    action_type = "open_tab"
    label = "Open Timeline"
    tab = "timeline"
    analysis_type = None
    search_query = None

    if isinstance(raw_action, dict):
        maybe_type = raw_action.get("type")
        if isinstance(maybe_type, str) and maybe_type in valid_action_types:
            action_type = maybe_type

        maybe_label = raw_action.get("label")
        if isinstance(maybe_label, str) and maybe_label.strip():
            label = maybe_label.strip()[:80]

        maybe_tab = raw_action.get("tab")
        if isinstance(maybe_tab, str) and maybe_tab in valid_tabs:
            tab = maybe_tab

        maybe_analysis = raw_action.get("analysis_type")
        if isinstance(maybe_analysis, str) and maybe_analysis in valid_analysis_types:
            analysis_type = maybe_analysis

        maybe_query = raw_action.get("search_query")
        if isinstance(maybe_query, str) and maybe_query.strip():
            search_query = maybe_query.strip()[:140]

    if action_type == "run_analysis":
        if not analysis_type:
            analysis_type = tab if tab in valid_analysis_types else "timeline"
        if analysis_type == "discrepancies" and not can_run_discrepancies:
            return {
                "type": "upload_document",
                "label": "Upload More Evidence",
                "tab": None,
                "analysis_type": None,
                "search_query": None,
            }
        tab = analysis_type
        if not label:
            label = "Run Analysis"

    if action_type == "search_evidence":
        tab = "search"
        if not search_query:
            search_query = "timeline inconsistencies"
        if not label:
            label = "Search Evidence"

    if action_type == "upload_document":
        return {
            "type": "upload_document",
            "label": label or "Upload Evidence",
            "tab": None,
            "analysis_type": None,
            "search_query": None,
        }

    if action_type == "open_tab":
        if not tab:
            tab = "timeline"
        if not label:
            label = "Open Analysis"

    return {
        "type": action_type,
        "label": label,
        "tab": tab,
        "analysis_type": analysis_type,
        "search_query": search_query,
    }


def _normalize_guidance_cards(
    cards_value: Any,
    can_run_discrepancies: bool,
) -> list[dict[str, Any]]:
    normalized_cards: list[dict[str, Any]] = []
    priorities = {"high", "medium", "low"}

    if not isinstance(cards_value, list):
        return normalized_cards

    for idx, card in enumerate(cards_value):
        if not isinstance(card, dict):
            continue

        title = card.get("title")
        recommendation = card.get("recommendation")
        rationale = card.get("rationale")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(recommendation, str) or not recommendation.strip():
            continue
        if not isinstance(rationale, str) or not rationale.strip():
            continue

        priority = card.get("priority")
        if not isinstance(priority, str) or priority not in priorities:
            priority = "medium"

        blockers_raw = card.get("blockers")
        blockers = (
            [str(item).strip()[:120] for item in blockers_raw if isinstance(item, str) and item.strip()]
            if isinstance(blockers_raw, list)
            else []
        )

        normalized_cards.append(
            {
                "id": _guidance_card_id(card.get("id"), title, idx),
                "title": title.strip()[:90],
                "recommendation": recommendation.strip()[:320],
                "rationale": rationale.strip()[:320],
                "priority": priority,
                "blockers": blockers[:3],
                "action": _normalize_guidance_action(card.get("action"), can_run_discrepancies),
            }
        )

    return normalized_cards[:4]


def _build_fallback_guidance_payload(
    timeline_data: dict[str, Any],
    discrepancies_data: dict[str, Any],
    policy_data: dict[str, Any],
    completed_non_policy_docs: list[dict[str, Any]],
    objective: Optional[str],
    immediate_risk: Optional[str],
) -> dict[str, Any]:
    doc_count = len(completed_non_policy_docs)
    can_run_discrepancies = doc_count >= 2
    timeline_gaps = [
        gap for gap in (timeline_data.get("gaps_identified") or []) if isinstance(gap, str) and gap.strip()
    ]
    discrepancy_items = discrepancies_data.get("discrepancies") or []
    policy_violations = policy_data.get("violations") or []

    cards: list[dict[str, Any]] = []

    if timeline_gaps:
        cards.append(
            {
                "id": "timeline-gaps",
                "title": "Close timeline gaps",
                "recommendation": "Interview witnesses and gather records (timecards, emails, access logs) to fill the missing timeline windows.",
                "rationale": f"{len(timeline_gaps)} timeline gap(s) still block a confident sequence of events.",
                "priority": "high",
                "blockers": timeline_gaps[:2],
                "action": {
                    "type": "open_tab",
                    "label": "View Timeline",
                    "tab": "timeline",
                    "analysis_type": None,
                    "search_query": None,
                },
            }
        )

    if isinstance(discrepancy_items, list) and discrepancy_items:
        cards.append(
            {
                "id": "discrepancy-followup",
                "title": "Resolve witness inconsistencies",
                "recommendation": "Focus next interviews on the highest-severity contradiction and corroborate with objective artifacts.",
                "rationale": f"{len(discrepancy_items)} discrepancy flag(s) remain unresolved.",
                "priority": "high",
                "blockers": [],
                "action": {
                    "type": "open_tab",
                    "label": "Open Discrepancies",
                    "tab": "discrepancies",
                    "analysis_type": None,
                    "search_query": None,
                },
            }
        )
    elif not can_run_discrepancies:
        cards.append(
            {
                "id": "need-more-evidence",
                "title": "Enable discrepancy analysis",
                "recommendation": "Upload at least one more completed witness/evidence document to compare accounts.",
                "rationale": "Discrepancy analysis requires at least two completed non-policy documents.",
                "priority": "medium",
                "blockers": [],
                "action": {
                    "type": "upload_document",
                    "label": "Upload Evidence",
                    "tab": None,
                    "analysis_type": None,
                    "search_query": None,
                },
            }
        )

    if isinstance(policy_violations, list) and policy_violations:
        cards.append(
            {
                "id": "policy-risk",
                "title": "Document policy risk findings",
                "recommendation": "Review each flagged violation, gather supporting documentation, and note whether corrective action has already been taken.",
                "rationale": f"{len(policy_violations)} potential policy violation(s) were identified.",
                "priority": "high",
                "blockers": [],
                "action": {
                    "type": "open_tab",
                    "label": "View Policy Findings",
                    "tab": "policy",
                    "analysis_type": None,
                    "search_query": None,
                },
            }
        )

    if not cards:
        cards.append(
            {
                "id": "final-readiness",
                "title": "Validate determination readiness",
                "recommendation": "Run a focused evidence search for unresolved facts before drafting a final determination.",
                "rationale": "Current analysis shows no major blockers, but a final validation pass is still recommended.",
                "priority": "medium",
                "blockers": [],
                "action": {
                    "type": "search_evidence",
                    "label": "Search Evidence",
                    "tab": "search",
                    "analysis_type": None,
                    "search_query": "unresolved timeline fact",
                },
            }
        )

    objective_fragment = f" Objective focus: {objective}." if objective and objective != "general" else ""
    immediate_risk_fragment = (
        " Immediate risk was flagged at intake; prioritize retaliation/safety follow-up."
        if immediate_risk == "yes"
        else ""
    )
    summary = (
        f"Reviewed {doc_count} completed non-policy evidence document(s). "
        f"Prioritize the listed actions before final determination.{objective_fragment}{immediate_risk_fragment}"
    ).strip()

    return {
        "summary": summary,
        "cards": cards[:4],
        "generated_at": datetime.now(timezone.utc),
        "model": "deterministic-fallback",
        "fallback_used": True,
    }


def _determination_confidence_floor(
    completed_doc_count: int,
    transcript_count: int,
    has_analyses: bool,
    has_policy_violations: bool,
) -> float:
    """Return a deterministic minimum confidence based on simple evidence counts.

    This is the fallback if the LLM confidence call fails — ensures the system
    never returns 0.0 and has a reasonable baseline.
    """
    if has_policy_violations and transcript_count >= 2:
        return 0.35
    if has_policy_violations:
        return 0.30
    if has_analyses:
        return 0.20
    if transcript_count >= 1:
        return 0.15
    return 0.10


def _normalize_suggested_guidance_payload(
    raw_payload: Any,
    fallback_payload: dict[str, Any],
    can_run_discrepancies: bool,
    model_name: str,
) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        return fallback_payload

    summary = raw_payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = fallback_payload["summary"]
    else:
        summary = summary.strip()[:600]

    cards = _normalize_guidance_cards(raw_payload.get("cards"), can_run_discrepancies)
    if not cards:
        cards = fallback_payload["cards"]

    generated_at = raw_payload.get("generated_at")
    if isinstance(generated_at, str):
        try:
            generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except Exception:
            generated_at = datetime.now(timezone.utc)
    elif not isinstance(generated_at, datetime):
        generated_at = datetime.now(timezone.utc)

    return {
        "summary": summary,
        "cards": cards,
        "generated_at": generated_at,
        "model": model_name,
        "fallback_used": False,
    }
