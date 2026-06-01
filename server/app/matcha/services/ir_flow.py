"""IR Copilot compliance-gate resolver.

History: the Copilot first relied entirely on the LLM (``generate_guidance``)
to emit the right next-step card each round. That stalled. The fix over-
corrected into a fully **deterministic** 10-phase march (categorize → severity
→ injury/OSHA → root cause → documents → corrective actions → close) that ran
*ahead* of the LLM every round — it opened on robotic cards, surfaced empty
"corrective actions" set_field cards with nothing to set, and dead-ended on a
close button before root cause was even captured. That replaced the
conversational, fact-gathering copilot users actually wanted.

This module now does **only** the part determinism is good for: guaranteeing
the hard OSHA-compliance gates that must never be skipped or stalled.
``resolve_next_step`` returns a canonical card for exactly three states and
``None`` for everything else, handing the conversation back to the LLM:

  • OSHA emergency  — reportable event flagged at intake (fatality / in-patient
                      hospitalization / amputation / loss of eye). Freeze on the
                      reporting disclaimer immediately.
  • Injury gate     — once incident_type + severity are set, ask the
                      treatment-beyond-first-aid question (OSHA recordability).
  • OSHA recordable — treatment beyond first aid → kick off the 300/301 chain
                      (the accept handlers self-chain the follow-ups, then hand
                      back to the conversation).

Categorize, severity, clarifying questions, root cause, corrective actions, and
closure are conversational again (``generate_guidance`` / ``PROMPT_TEMPLATE``).
Root-cause-before-close and OSHA-recordable-before-close remain *enforced*
regardless of the conversation by the close-intercepts in
``_close_incident_via_copilot``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

VALID_INCIDENT_TYPES = {"safety", "behavioral", "property", "near_miss", "other"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}

# Physical-injury cues — mirrors the OSHA INJURY GATE wording in the
# orchestrator prompt so the deterministic path triggers on the same signals.
_INJURY_KEYWORD_RE = re.compile(
    r"\b("
    r"cut|fell|fall|slip|slipped|trip|tripped|sprain|strain|burn|burned|"
    r"struck|hit|twist|twisted|laceration|bruise|fracture|broke|broken|"
    r"scratched|pinched|crush|crushed|amputat|injur|wound|bleed|"
    r"caught\s+in|hurt"
    r")\b",
    re.IGNORECASE,
)

FLOW_MODEL_LABEL = "deterministic-flow"

# Resolver/chain card id -> flow gate key. A Skip on one of these cards records
# the gate in category_data.flow_skipped so resolve_next_step stops re-emitting
# it on later rounds (the resolver is state-driven and otherwise can't see a
# per-card skip).
_GATE_BY_CARD_ID = {
    "flow_categorize": "categorize",
    "flow_categorize_run": "categorize",
    "flow_severity": "severity",
    "flow_severity_run": "severity",
    "treatment_query": "treatment",
    "osha_recordable_query": "osha",
    "osha_days_type_query": "osha",
    "osha_injury_type_query": "osha",
    "log_root_cause_query": "root_cause",
    "flow_followup_run": "investigation",
    "investigation_notes": "investigation",
    "request_documents": "documents",
    "flow_recommendations_run": "actions",
    "flow_corrective_actions": "actions",
    "flow_status_action_required": "status",
    "close_incident": "close",
    "osha_close_confirmation": "close",
    "fallback_close": "close",
}


def gate_key_for_card(card_id) -> Optional[str]:
    """Map a card id to its flow gate key, or None if it isn't a flow gate."""
    cid = (card_id or "")
    cid = cid.strip() if isinstance(cid, str) else ""
    if cid in _GATE_BY_CARD_ID:
        return _GATE_BY_CARD_ID[cid]
    if cid.startswith("osha_days_count"):
        return "osha"
    return None


def _safe_json(value: Any, default: Any) -> Any:
    """category_data / analysis_data arrive as dict or JSON string (asyncpg)."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def _analyses_by_type(analyses: list[dict[str, Any]] | None) -> dict[str, dict]:
    """Map analysis_type -> analysis_data (latest wins)."""
    out: dict[str, dict] = {}
    for row in analyses or []:
        atype = row.get("analysis_type")
        if not atype:
            continue
        out[atype] = _safe_json(row.get("analysis_data"), {}) or {}
    return out


def _payload(summary: str, cards: list[dict], open_questions: Optional[list[str]] = None) -> dict:
    return {
        "summary": summary,
        "open_questions": open_questions or [],
        "cards": cards,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": FLOW_MODEL_LABEL,
    }


def _set_field_card(
    *, card_id: str, title: str, field_name: str, field_value: str,
    recommendation: str, rationale: str, priority: str = "high",
) -> dict:
    return {
        "id": card_id,
        "title": title,
        "recommendation": recommendation,
        "rationale": rationale,
        "priority": priority,
        "blockers": [],
        "action": {
            "type": "set_field",
            "label": f"Set {title.lower()}",
            "field_name": field_name,
            "field_value": field_value,
        },
    }


def _run_analysis_card(
    *, card_id: str, title: str, analysis_type: str,
    recommendation: str, rationale: str, label: str, priority: str = "high",
) -> dict:
    return {
        "id": card_id,
        "title": title,
        "recommendation": recommendation,
        "rationale": rationale,
        "priority": priority,
        "blockers": [],
        "action": {
            "type": "run_analysis",
            "label": label,
            "analysis_type": analysis_type,
        },
    }


def _close_card() -> dict:
    return {
        "id": "close_incident",
        "title": "Close incident",
        "recommendation": "Everything's documented. Close this incident?",
        "rationale": (
            "Type, severity, injury/OSHA status, root cause, documents, and "
            "corrective actions are all captured. Closing locks the record."
        ),
        "priority": "high",
        "blockers": [],
        "action": {
            "type": "close_incident",
            "label": "Close incident",
        },
    }


def _has_injury_signal(incident: dict[str, Any], incident_type: str) -> bool:
    if incident_type == "safety":
        return True
    text = f"{incident.get('title') or ''} {incident.get('description') or ''}"
    return bool(_INJURY_KEYWORD_RE.search(text))


def resolve_next_step(
    incident: dict[str, Any],
    analyses: list[dict[str, Any]] | None,
    documents_count: int = 0,
    is_cold_start: bool = False,
) -> Optional[dict]:
    """Return a card payload for a hard OSHA-compliance gate, or None.

    Returns a canonical card for exactly three states (OSHA emergency freeze,
    the injury/treatment recordability question, and the OSHA-recordable chain
    kickoff). For every other state it returns None, handing the round to the
    conversational LLM (``generate_guidance``). ``analyses`` and
    ``documents_count`` are accepted for call-site compatibility but no longer
    influence the result.
    """
    if not incident:
        return None

    status = (incident.get("status") or "").lower()
    if status in {"closed", "resolved"}:
        return None  # terminal — let the LLM field any follow-up questions

    incident_type = (incident.get("incident_type") or "").lower()
    severity = (incident.get("severity") or "").lower()
    category_data = _safe_json(incident.get("category_data"), {}) or {}
    # Gates the user explicitly skipped — don't re-emit them.
    raw_skipped = category_data.get("flow_skipped")
    flow_skipped = set(raw_skipped) if isinstance(raw_skipped, list) else set()

    # This resolver intentionally no longer drives categorize / severity /
    # clarifying questions / root cause / corrective actions / closure — those
    # are conversational again via generate_guidance. It returns a card ONLY for
    # the three hard OSHA-compliance gates below, and None otherwise.

    # ── OSHA emergency (mandatory reporting freeze) ──────────────────────
    # Fatality / in-patient hospitalization / amputation / loss of eye flagged
    # at intake. Freeze immediately — a legal 8/24-hour reporting duty trumps
    # any conversational triage.
    if category_data.get("osha_emergency_alert_active"):
        from app.matcha.routes.ir_incidents._shared import build_osha_emergency_alert_card
        return _payload(
            "This incident may require immediate OSHA reporting.",
            [build_osha_emergency_alert_card()],
        )

    # ── Injury assessment (OSHA recordability gate) ──────────────────────
    # The treatment-beyond-first-aid question is the entry to the recordable
    # chain. Don't open the copilot with it: skip the cold-start round so the
    # LLM gets the first word (greet, categorize, gather facts / severity), and
    # only fire once incident_type + severity are set. New incidents default to
    # incident_type='other' / severity='medium', so the cold-start guard — not
    # the type/severity check — is what prevents the old "asks treatment the
    # instant an injury word appears" behavior. (Emergency reporting above is
    # NOT cold-start-gated — a reportable event must freeze immediately.)
    treatment = category_data.get("treatment_beyond_first_aid")
    if (
        not is_cold_start
        and incident_type in VALID_INCIDENT_TYPES
        and severity in VALID_SEVERITIES
        and _has_injury_signal(incident, incident_type)
        and treatment is None
        and "treatment" not in flow_skipped
    ):
        from app.matcha.routes.ir_incidents._shared import build_treatment_query_card
        return _payload(
            "Let's assess the injury for OSHA recordability.",
            [build_treatment_query_card()],
        )

    # ── OSHA recordable chain ────────────────────────────────────────────
    treatment_true = str(treatment).strip().lower() == "true"
    if treatment_true and incident.get("osha_recordable") is None and "osha" not in flow_skipped:
        from app.matcha.routes.ir_incidents._shared import build_osha_recordable_query_card
        return _payload(
            "Let's capture the OSHA recordable details.",
            [build_osha_recordable_query_card()],
        )

    # Nothing compliance-critical is pending — hand the conversation back to the
    # LLM (generate_guidance). It drives root cause (log_root_cause_query),
    # clarifying follow-ups, corrective actions, and the eventual close
    # recommendation. Root-cause-before-close stays enforced by the
    # close-intercept in _close_incident_via_copilot even though we don't emit a
    # proactive root-cause card here.
    return None
