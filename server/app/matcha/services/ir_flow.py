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
    if incident_type == "near_miss":
        # A near miss is, by definition, an event where no one was actually
        # hurt — the report text still routinely uses injury-cue words
        # ("nearly slipped", "almost struck", "could have fallen") to
        # describe the hazard that *didn't* result in harm. The keyword
        # regex below can't distinguish that from a real injury narrative,
        # so it was intermittently firing the "Was any treatment provided
        # beyond first aid?" OSHA-recordability card on reports where no
        # treatment (or injury) ever happened. If a near-miss turns out to
        # have actually injured someone, the report should be recategorized
        # to "safety" — which still trips this gate unconditionally above.
        return False
    text = f"{incident.get('title') or ''} {incident.get('description') or ''}"
    return bool(_INJURY_KEYWORD_RE.search(text))


# ── Close-requirement predicates ─────────────────────────────────────────
# THE source of truth for "what still blocks closing this incident". Both the
# close intercept (``_close_incident_via_copilot``, which redirects the user to
# the blocking card) and the progress meter (``close_progress`` below, which
# tells the user how much is left) consume these. Keeping them in one place is
# load-bearing: a meter computed from its own copy of these rules drifts, and a
# progress bar that reads 100% while Close still bounces the user into another
# card is worse than no progress bar at all.


def osha_emergency_blocking(category_data: dict[str, Any]) -> bool:
    """A reportable-event alert is raised and not yet acknowledged."""
    return bool((category_data or {}).get("osha_emergency_alert_active"))


def root_cause_required(
    *, incident_type: Optional[str], severity: Optional[str],
) -> bool:
    """Whether this incident owes a root cause at all.

    Split out from ``needs_root_cause`` so the progress meter's *applicability*
    test and the close gate's *blocking* test read the same rule. Inlining the
    type/severity sets in a second place is how a widened requirement ends up
    blocking Close while the meter still calls the step not-applicable.
    """
    return (
        (incident_type or "").strip().lower() in {"safety", "near_miss"}
        or (severity or "").strip().lower() in {"high", "critical"}
    )


def needs_root_cause(
    *,
    incident_type: Optional[str],
    severity: Optional[str],
    root_cause: Optional[str],
    category_data: dict[str, Any],
) -> bool:
    """Root cause is required-but-missing.

    Required for safety / near-miss incidents and for high / critical severity.
    Satisfied by a logged root cause, an explicit decline, or an in-progress
    interview — declining counts, the point is a deliberate decision rather
    than a safety incident closing with no investigation captured at all.
    """
    cd = category_data or {}
    if (root_cause or "").strip():
        return False
    if cd.get("root_cause_declined") in (True, "true"):
        return False
    if bool(cd.get("root_cause_interview")):
        return False
    return root_cause_required(incident_type=incident_type, severity=severity)


def treatment_beyond_first_aid(category_data: dict[str, Any]) -> Optional[bool]:
    """Tri-state: True / False / None (unanswered)."""
    raw = (category_data or {}).get("treatment_beyond_first_aid")
    if raw is None:
        return None
    return str(raw).strip().lower() == "true"


def needs_osha_recordable(
    *, category_data: dict[str, Any], osha_recordable: Any,
) -> bool:
    """Treatment went beyond first aid but the OSHA 300 chain hasn't run."""
    return treatment_beyond_first_aid(category_data) is True and osha_recordable is None


# Ordered as the user encounters them. ``key`` is stable (the frontend keys
# off it); ``label`` is user-facing. One entry per close gate — adding a label
# here without a matching gate in _close_incident_via_copilot is what breaks
# the meter/gate contract documented on close_progress.
_STEP_LABELS = {
    "osha_emergency": "OSHA emergency reporting",
    "osha_recordable": "OSHA recordability",
    "root_cause": "Root cause",
    "close": "Close incident",
}


def close_progress(incident: dict[str, Any]) -> dict[str, Any]:
    """Completion state for the Copilot progress meter.

    Answers the question the transcript alone can't: *how much is left?* The
    Copilot is conversational, so from the user's side an unbounded exchange
    looks like it could loop forever.

    **Every counted step is a gate ``_close_incident_via_copilot`` actually
    enforces — no more, no less.** That equivalence is the whole contract, and
    both directions of breaking it are bugs users hit:

      • Counting something Close *doesn't* enforce (triage, or the
        treatment/injury question) let Close succeed at 60% and then render
        "Complete" over unfilled segments.
      • Excluding something Close *does* enforce (the meter used to drop a
        ``flow_skipped`` OSHA gate) produced a 100% meter with a Close button
        that bounced straight back into the skipped card. A skip is "not now",
        not "not required" — the intercept re-emits it, so the meter must keep
        counting it.

    Steps that don't apply to *this* incident (a property-damage report never
    enters the OSHA chain) are ``not_applicable`` and excluded from the
    denominator, so the meter tracks this incident's real remaining work rather
    than a fixed checklist most incidents can never complete.
    """
    incident = incident or {}
    category_data = _safe_json(incident.get("category_data"), {}) or {}
    status = (incident.get("status") or "").lower()
    is_terminal = status in {"closed", "resolved"}
    incident_type = (incident.get("incident_type") or "").lower()
    severity = (incident.get("severity") or "").lower()

    treatment = treatment_beyond_first_aid(category_data)

    def step(key: str, *, applicable: bool, done: bool, hint: str = "") -> dict:
        if not applicable:
            state = "not_applicable"
        elif done:
            state = "done"
        else:
            state = "pending"
        return {
            "key": key,
            "label": _STEP_LABELS[key],
            "status": state,
            "hint": hint if state == "pending" else "",
        }

    steps = [
        # Applicable only once an alert has actually been raised. The key is
        # set to false on acknowledgement rather than deleted, so presence —
        # not truthiness — is what marks this incident as having had one.
        step(
            "osha_emergency",
            applicable="osha_emergency_alert_active" in category_data,
            done=not osha_emergency_blocking(category_data),
            hint="Acknowledge the OSHA reporting alert.",
        ),
        # No flow_skipped exemption: needs_osha_recordable (the close gate)
        # ignores skips, so honouring one here would put the meter at 100%
        # while Close redirects into the skipped card.
        step(
            "osha_recordable",
            applicable=treatment is True,
            done=incident.get("osha_recordable") is not None,
            hint="Complete the OSHA 300 recordability details.",
        ),
        step(
            "root_cause",
            applicable=root_cause_required(incident_type=incident_type, severity=severity),
            done=not needs_root_cause(
                incident_type=incident_type,
                severity=severity,
                root_cause=incident.get("root_cause"),
                category_data=category_data,
            ),
            hint="Log a root cause, or explicitly decline one.",
        ),
        step("close", applicable=True, done=is_terminal, hint="Close the incident to lock the record."),
    ]

    applicable = [s for s in steps if s["status"] != "not_applicable"]
    completed = [s for s in applicable if s["status"] == "done"]
    total = len(applicable)
    next_step = next((s for s in applicable if s["status"] == "pending"), None)

    return {
        "completed": len(completed),
        "total": total,
        "percent": round(100 * len(completed) / total) if total else 0,
        "steps": steps,
        "next_step_key": next_step["key"] if next_step else None,
        "next_step_hint": next_step["hint"] if next_step else "",
        "is_complete": is_terminal,
    }


# ── Preponderance-of-evidence tracker ────────────────────────────────────
# Mirrors the ER Copilot's evidence-confidence banner (ERGuidancePanel /
# guidance.determination_confidence): a second, independent read on "how
# much is left" from close_progress above. close_progress answers "what does
# the law require"; this answers "how well-documented is the record" — a
# property-damage report can clear every close gate (no root cause required,
# no OSHA chain) while still having no photos, no witnesses, and no logged
# corrective action, and that gap is exactly what this surfaces.
EVIDENCE_SUFFICIENCY_THRESHOLD = 80

_EVIDENCE_FACTOR_LABELS = {
    "description": "Incident description",
    "witnesses": "Witness statements",
    "documents": "Supporting documents",
    "root_cause": "Root cause analysis",
    "corrective_actions": "Corrective actions",
}

# Severity-scaled ceiling on days an incident should stay open — the other
# half of "prevent indefinite pilot durations". A high evidence score doesn't
# help if nobody ever revisits a report that's been sitting untouched, so
# this is surfaced alongside the score rather than left to a separate sweep.
_MAX_OPEN_DAYS = {"critical": 7, "high": 14, "medium": 30, "low": 45}
_DEFAULT_MAX_OPEN_DAYS = 30


def copilot_evidence(
    incident: dict[str, Any],
    *,
    document_count: int = 0,
    witness_count: int = 0,
    corrective_action_count: int = 0,
) -> dict[str, Any]:
    """Weighted evidence-sufficiency score (0-100) plus a days-open budget.

    Each factor only counts toward the denominator when it applies to this
    incident — a near-miss with no injury never owes a root cause, and
    scoring it against a 100%-possible ceiling that includes an inapplicable
    factor would strand every near-miss report below "sufficient" forever.
    Counts (documents/witnesses/corrective actions) are computed by the
    caller — this function stays DB-free like ``close_progress`` above.
    """
    incident = incident or {}
    category_data = _safe_json(incident.get("category_data"), {}) or {}
    status = (incident.get("status") or "").lower()
    is_terminal = status in {"closed", "resolved"}
    incident_type = (incident.get("incident_type") or "").lower()
    severity = (incident.get("severity") or "").lower()

    # (key, weight, applicable, done)
    factors = [
        ("description", 15, True, bool((incident.get("description") or "").strip())),
        ("witnesses", 15, True, witness_count > 0),
        ("documents", 20, True, document_count > 0),
        (
            "root_cause", 25,
            root_cause_required(incident_type=incident_type, severity=severity),
            not needs_root_cause(
                incident_type=incident_type, severity=severity,
                root_cause=incident.get("root_cause"), category_data=category_data,
            ),
        ),
        (
            "corrective_actions", 25, True,
            corrective_action_count > 0 or bool((incident.get("corrective_actions") or "").strip()),
        ),
    ]

    applicable = [(key, weight, done) for key, weight, applies, done in factors if applies]
    total_weight = sum(weight for _, weight, _ in applicable) or 1
    earned_weight = sum(weight for _, weight, done in applicable if done)
    score = round(100 * earned_weight / total_weight)

    max_days = _MAX_OPEN_DAYS.get(severity, _DEFAULT_MAX_OPEN_DAYS)
    opened_at = incident.get("reported_at") or incident.get("created_at")
    if opened_at is None:
        days_open = 0
    else:
        # DB timestamps are naive (TIMESTAMP, not TIMESTAMPTZ) — compare
        # against a naive UTC "now" rather than reconciling tzinfo.
        end = (incident.get("resolved_at") if is_terminal else None) or datetime.now(timezone.utc).replace(tzinfo=None)
        days_open = max(0, (end - opened_at).days)

    return {
        "score": score,
        "threshold": EVIDENCE_SUFFICIENCY_THRESHOLD,
        "sufficient": score >= EVIDENCE_SUFFICIENCY_THRESHOLD,
        "signals": [_EVIDENCE_FACTOR_LABELS[k] for k, _, done in applicable if done],
        "missing": [_EVIDENCE_FACTOR_LABELS[k] for k, _, done in applicable if not done],
        "days_open": days_open,
        "max_days": max_days,
        "is_overdue": not is_terminal and days_open > max_days,
    }


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
    if osha_emergency_blocking(category_data):
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
    treatment = treatment_beyond_first_aid(category_data)
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
    # flow_skipped is honoured HERE (the resolver stops re-emitting a skipped
    # card) but deliberately NOT in needs_osha_recordable / close_progress —
    # skipping silences the prompt, it doesn't waive the close requirement.
    if needs_osha_recordable(
        category_data=category_data, osha_recordable=incident.get("osha_recordable"),
    ) and "osha" not in flow_skipped:
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
