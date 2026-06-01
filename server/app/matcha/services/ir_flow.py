"""Deterministic IR Copilot flow engine.

The Copilot used to depend on the LLM (``generate_guidance``) to emit the
correct next-step card every round, with a large net of post-hoc rewrites to
correct the model. In practice that stalled — the model would omit the next
step, emit a dead card, or return nothing, so the guided flow never reliably
advanced ("conceptual / doesn't work").

This module makes the flow **deterministic**. ``resolve_next_step`` inspects
the incident's current state and returns the single canonical next card,
reusing the existing card builders and accept-handlers in
``routes/ir_incidents``. The LLM is now only a fallback for free-form Q&A
(when this resolver returns ``None``).

Flow phases (in order — first unsatisfied gate wins):

  1. Categorize        — incident_type unset
  2. Severity          — severity unset
  3. OSHA emergency    — category_data.osha_emergency_alert_active (mandatory
                         reporting, requires confirmation notes)
  4. Injury assessment — safety/injury incident, treatment_beyond_first_aid unset
  5. OSHA recordable   — treatment beyond first aid + osha_recordable unset
  6. Root cause        — safety/near_miss or high/critical, not yet logged/declined
  7. Documents         — safety/recordable incident with nothing attached
  8. Corrective action — corrective_actions empty (suggest via recommendations)
  9. Action required   — actions captured, status not yet action_required
 10. Close             — everything captured

Every card shape here matches what the accept-handlers already dispatch, so no
handler changes are needed for the reused steps. Only the treatment_query
quick-reply and the request_documents action are new.
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
) -> Optional[dict]:
    """Return the canonical next-step guidance payload, or None for free-form.

    ``documents_count`` is the number of rows in ir_incident_documents for the
    incident (the caller supplies it; defaults to incident['documents_count']).
    """
    if not incident:
        return None

    status = (incident.get("status") or "").lower()
    if status in {"closed", "resolved"}:
        return None  # terminal — let the LLM field any follow-up questions

    if documents_count == 0:
        try:
            documents_count = int(incident.get("documents_count") or 0)
        except (TypeError, ValueError):
            documents_count = 0

    incident_type = (incident.get("incident_type") or "").lower()
    severity = (incident.get("severity") or "").lower()
    category_data = _safe_json(incident.get("category_data"), {}) or {}
    by_type = _analyses_by_type(analyses)
    # Gates the user explicitly skipped — don't re-emit them.
    raw_skipped = category_data.get("flow_skipped")
    flow_skipped = set(raw_skipped) if isinstance(raw_skipped, list) else set()

    # ── 1. Categorize ────────────────────────────────────────────────────
    if incident_type not in VALID_INCIDENT_TYPES and "categorize" not in flow_skipped:
        cat = by_type.get("categorization") or {}
        suggested = str(cat.get("suggested_type") or "").lower()
        if suggested in VALID_INCIDENT_TYPES:
            conf = cat.get("confidence")
            conf_str = f" ({round(float(conf) * 100)}% confidence)" if isinstance(conf, (int, float)) else ""
            reason = str(cat.get("reasoning") or "").strip()
            return _payload(
                "First, let's confirm what kind of incident this is.",
                [_set_field_card(
                    card_id="flow_categorize",
                    title="Incident type",
                    field_name="incident_type",
                    field_value=suggested,
                    recommendation=f"Classify this as a {suggested.replace('_', ' ')} incident{conf_str}.",
                    rationale=reason or "Categorizing routes the right compliance checks and analysis.",
                )],
            )
        return _payload(
            "First, let's categorize this incident.",
            [_run_analysis_card(
                card_id="flow_categorize_run",
                title="Categorize incident",
                analysis_type="categorization",
                recommendation="Run AI categorization to suggest the incident type.",
                rationale="Categorizing routes the right compliance checks and analysis.",
                label="Categorize",
            )],
        )

    # ── 2. Severity ──────────────────────────────────────────────────────
    if severity not in VALID_SEVERITIES and "severity" not in flow_skipped:
        sev = by_type.get("severity") or {}
        suggested = str(sev.get("suggested_severity") or "").lower()
        if suggested in VALID_SEVERITIES:
            reason = str(sev.get("reasoning") or "").strip()
            return _payload(
                "Now let's set the severity.",
                [_set_field_card(
                    card_id="flow_severity",
                    title="Severity",
                    field_name="severity",
                    field_value=suggested,
                    recommendation=f"Set severity to {suggested}.",
                    rationale=reason or "Severity drives escalation, OSHA, and reporting thresholds.",
                )],
            )
        return _payload(
            "Now let's assess the severity.",
            [_run_analysis_card(
                card_id="flow_severity_run",
                title="Assess severity",
                analysis_type="severity",
                recommendation="Run AI severity assessment to suggest a level.",
                rationale="Severity drives escalation, OSHA, and reporting thresholds.",
                label="Assess severity",
            )],
        )

    # ── 3. OSHA emergency (mandatory reporting) ──────────────────────────
    if category_data.get("osha_emergency_alert_active"):
        from app.matcha.routes.ir_incidents._shared import build_osha_emergency_alert_card
        return _payload(
            "This incident may require immediate OSHA reporting.",
            [build_osha_emergency_alert_card()],
        )

    # ── 4. Injury assessment (treatment beyond first aid) ────────────────
    treatment = category_data.get("treatment_beyond_first_aid")
    if _has_injury_signal(incident, incident_type) and treatment is None and "treatment" not in flow_skipped:
        from app.matcha.routes.ir_incidents._shared import build_treatment_query_card
        return _payload(
            "Let's assess the injury for OSHA recordability.",
            [build_treatment_query_card()],
        )

    # ── 5. OSHA recordable chain ─────────────────────────────────────────
    treatment_true = str(treatment).strip().lower() == "true"
    if treatment_true and incident.get("osha_recordable") is None and "osha" not in flow_skipped:
        from app.matcha.routes.ir_incidents._shared import build_osha_recordable_query_card
        return _payload(
            "Let's capture the OSHA recordable details.",
            [build_osha_recordable_query_card()],
        )

    # ── 6. Root cause ────────────────────────────────────────────────────
    root_cause = (incident.get("root_cause") or "").strip()
    rc_declined = bool(category_data.get("root_cause_declined"))
    rc_started = bool(category_data.get("root_cause_interview"))
    rc_required = incident_type in {"safety", "near_miss"} or severity in {"high", "critical"}
    if rc_required and not root_cause and not rc_declined and not rc_started and "root_cause" not in flow_skipped:
        from app.matcha.routes.ir_incidents._shared import build_log_root_cause_query_card
        return _payload(
            "Let's document the root cause.",
            [build_log_root_cause_query_card()],
        )

    # ── 7. Documents ─────────────────────────────────────────────────────
    docs_handled = (
        bool(category_data.get("documents_prompted"))
        or documents_count > 0
        or "documents" in flow_skipped
    )
    docs_relevant = incident_type == "safety" or bool(incident.get("osha_recordable"))
    if docs_relevant and not docs_handled:
        from app.matcha.routes.ir_incidents._shared import build_request_documents_card
        return _payload(
            "Attach any supporting documentation for the record.",
            [build_request_documents_card()],
        )

    # ── 8. Corrective actions ────────────────────────────────────────────
    actions = (incident.get("corrective_actions") or "").strip()
    if not actions and "actions" not in flow_skipped:
        recs = by_type.get("recommendations") or {}
        rec_items = recs.get("recommendations") if isinstance(recs.get("recommendations"), list) else None
        if rec_items:
            summary_text = str(recs.get("summary") or "").strip()
            if not summary_text:
                summary_text = "; ".join(
                    str(r.get("action")) for r in rec_items[:3] if isinstance(r, dict) and r.get("action")
                )
            summary_text = summary_text[:1500] or "Document and act on the recommended steps."
            return _payload(
                "Here are suggested corrective actions.",
                [_set_field_card(
                    card_id="flow_corrective_actions",
                    title="Corrective actions",
                    field_name="corrective_actions",
                    field_value=summary_text,
                    recommendation="Apply these recommended corrective actions.",
                    rationale="Captured on the incident and surfaced in reports.",
                    priority="medium",
                )],
            )
        return _payload(
            "Let's generate recommended corrective actions.",
            [_run_analysis_card(
                card_id="flow_recommendations_run",
                title="Suggest actions",
                analysis_type="recommendations",
                recommendation="Run AI recommendations to propose corrective actions.",
                rationale="Gives you concrete next steps tied to this incident.",
                label="Suggest actions",
                priority="medium",
            )],
        )

    # ── 9. Mark action required ──────────────────────────────────────────
    if status not in {"action_required", "resolved", "closed"} and "status" not in flow_skipped:
        return _payload(
            "Corrective actions are set — mark this as action required.",
            [_set_field_card(
                card_id="flow_status_action_required",
                title="Status",
                field_name="status",
                field_value="action_required",
                recommendation="Move the incident to Action Required.",
                rationale="Signals the incident is in remediation before closure.",
                priority="medium",
            )],
        )

    # ── 10. Close ────────────────────────────────────────────────────────
    if "close" in flow_skipped:
        return None
    return _payload(
        "Everything's captured. You can close this incident.",
        [_close_card()],
    )
