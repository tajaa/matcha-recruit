"""IR AI Copilot orchestrator.

Composes a single guidance prompt from incident core + cached analyses + chat
history. Returns structured cards (run_analysis / set_field / escalate /
close_incident / request_info) the user can accept inline. Reuses
er_guidance normalization helpers with IR-specific valid_tabs /
valid_analysis_types.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from ..services.er_guidance import _guidance_card_id, _normalize_guidance_cards
from ..services.ir_analysis import get_ir_analyzer
from ...core.services.rate_limiter import get_rate_limiter
from ...database import get_connection

logger = logging.getLogger(__name__)


# IR-specific tab keys + analysis types the AI is allowed to reference.
IR_VALID_TABS = {"copilot", "overview", "analysis", "documents", "interviews"}
IR_VALID_ANALYSIS_TYPES = {
    "categorization",
    "severity",
    "root_cause",
    "recommendations",
    "similar",
    "policy_mapping",
    "followup_questions",
}

# AI commonly emits abbreviated / alternate names. Map them to canonical IDs
# so "policy" / "rca" / "categorize" all resolve. Keys are lowercased before
# lookup; values must be in IR_VALID_ANALYSIS_TYPES.
ANALYSIS_TYPE_ALIASES = {
    "policy": "policy_mapping",
    "policies": "policy_mapping",
    "policy-mapping": "policy_mapping",
    "policy_check": "policy_mapping",
    "policy_violations": "policy_mapping",
    "rca": "root_cause",
    "root-cause": "root_cause",
    "five_whys": "root_cause",
    "categorize": "categorization",
    "categorise": "categorization",
    "category": "categorization",
    "similar_incidents": "similar",
    "precedents": "similar",
    "recommendation": "recommendations",
    "recommended_actions": "recommendations",
    "severity_assessment": "severity",
    "followup": "followup_questions",
    "follow_up": "followup_questions",
    "follow_up_questions": "followup_questions",
    "investigation": "followup_questions",
    "questions": "followup_questions",
}


def _canonical_analysis_type(raw: Optional[str]) -> Optional[str]:
    """Resolve aliases to a canonical IR analysis_type, or None if unknown."""
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    if key in IR_VALID_ANALYSIS_TYPES:
        return key
    if key in ANALYSIS_TYPE_ALIASES:
        return ANALYSIS_TYPE_ALIASES[key]
    return None

# Action types the orchestrator may emit and the accept endpoint dispatches.
# The last three (quick_reply, numeric_input, osha_emergency_alert) are
# emitted by the backend OSHA recordable chain — not by Gemini — but live
# in the allowlist so the response filter keeps them when round-tripped
# through transcript fetches.
IR_ACTION_TYPES = {
    "run_analysis",
    "set_field",
    "request_info",
    "escalate",
    "close_incident",
    "quick_reply",
    "numeric_input",
    "text_input",
    "osha_emergency_alert",
    "request_documents",
}

# Mirrors copilot.py:_handle_quick_reply allowed_by_kind. Filter uses
# this to drop or rewrite quick_reply cards whose kind the backend
# dispatcher doesn't route — surfacing them would just trigger the
# "Unknown quick_reply kind:" banner when the user clicks an option.
IR_VALID_QUICK_REPLY_KINDS = {
    "treatment_query",
    "osha_recordable_query",
    "osha_days_type_query",
    "osha_injury_type_query",
    "log_root_cause_query",
    "privacy_case_query",
}


# Mirror the route's _FIELD_WHITELIST + enum sets so the orchestrator can drop
# cards with hallucinated field_values (e.g. AI proposing
# `incident_type = "Tardiness"`) before the user ever sees them. Backend route
# revalidates as defense in depth.
IR_SETTABLE_FIELDS = {
    "incident_type",
    "category",  # alias for incident_type — accepted by route
    "severity",
    "status",
    "root_cause",
    "corrective_actions",
    # JSONB-stashed OSHA intake flag — captured early so the close-time
    # OSHA recordable chain knows whether to fire. Stored under
    # ir_incidents.category_data->>'treatment_beyond_first_aid' (true/false).
    "treatment_beyond_first_aid",
}

IR_FIELD_VALUE_ENUMS: dict[str, set[str]] = {
    "incident_type": {"safety", "behavioral", "property", "near_miss", "other"},
    "category": {"safety", "behavioral", "property", "near_miss", "other"},
    "severity": {"critical", "high", "medium", "low"},
    "status": {"reported", "investigating", "action_required", "resolved", "closed"},
    "treatment_beyond_first_aid": {"true", "false"},
}


# User-message close-intent detection. When the user types "close it out" /
# "documentation only" / similar, the copilot short-circuits the LLM and
# surfaces a close_incident card directly. Cheap regex — false positives are
# safer than false negatives here (user can still Skip the card).
_CLOSE_INTENT_PATTERNS = re.compile(
    r"\b("
    r"close\s+(it|this)\s*(out|up)?"
    r"|close\s+(the\s+)?(incident|case|report|ticket)"
    r"|(just\s+)?(for\s+)?documentation\s+only"
    r"|no\s+(further|more)\s+action"
    r"|mark\s+(as\s+)?(closed|resolved|complete)"
    r"|resolve\s+(this|the\s+incident)"
    r"|wrap\s+(this\s+)?up"
    r")\b",
    re.IGNORECASE,
)


def _detect_close_intent(user_message: Optional[str]) -> bool:
    if not user_message:
        return False
    return bool(_CLOSE_INTENT_PATTERNS.search(user_message))


def _close_intent_payload(model_label: str = "intent-shortcircuit") -> dict[str, Any]:
    return {
        "summary": "You asked to close this incident. Confirm below to finalize.",
        "open_questions": [],
        "cards": [{
            "id": "user_requested_close",
            "title": "Close this incident",
            "recommendation": "Mark this incident closed and clear other open recommendations.",
            "rationale": "You said you wanted to close it out — confirm to finalize.",
            "priority": "medium",
            "blockers": [],
            "action": {
                "type": "close_incident",
                "label": "Close incident",
                "tab": None,
                "analysis_type": None,
                "search_query": None,
                "field_name": None,
                "field_value": None,
            },
            "interview_questions": None,
        }],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model_label,
    }


def _is_valid_set_field(field_name: Optional[str], field_value: Any) -> bool:
    """True when field_name is settable AND field_value (if enum-constrained)
    matches the canonical lowercase enum. Free-text fields (root_cause,
    corrective_actions) accept any non-empty string."""
    if not isinstance(field_name, str) or field_name not in IR_SETTABLE_FIELDS:
        return False
    enum = IR_FIELD_VALUE_ENUMS.get(field_name)
    if enum is None:
        return isinstance(field_value, str) and bool(field_value.strip())
    if not isinstance(field_value, str):
        return False
    return field_value.strip().lower() in enum


PROMPT_TEMPLATE = """You are an HR incident-response copilot. Your job is to help an HR
administrator manage a workplace incident report. You see the current incident
state, all AI analyses already run on it, and the running conversation between
you and the user.

Your goal: identify what the user should do next. If the incident is too vague,
ask clarifying questions. If an analysis would help, recommend running it. If
the incident has enough information to close, recommend closing it. Always be
concrete and actionable.

INCIDENT CORE:
{incident_core}

CACHED ANALYSES:
{cached_analyses}

RECENT CONVERSATION (oldest first, last message is the user's latest input):
{conversation}

LATEST USER MESSAGE: {latest_user_message}

Return JSON with the following shape — no preamble, no markdown fences:
{{
  "summary": "1-2 sentence overview of where the incident stands",
  "open_questions": [
    "Free-text question to ask the user when key info is missing.",
    "Up to 3 questions, prioritized by importance."
  ],
  "cards": [
    {{
      "id": "lowercase_snake_case_unique_id",
      "title": "Short title — 90 chars max",
      "recommendation": "What to do, in 1-2 sentences",
      "rationale": "Why this matters now",
      "priority": "high" | "medium" | "low",
      "blockers": ["thing blocking", ...],
      "action": {{
        "type": "run_analysis" | "set_field" | "request_info" | "escalate" | "close_incident",
        "label": "Button label, ~30 chars",
        "analysis_type": "categorization" | "severity" | "root_cause" | "recommendations" | "similar" | "policy_mapping" | null,
        "field_name": "incident_type" | "severity" | "status" | "root_cause" | "corrective_actions" | null,
        "field_value": "string or null — see SET_FIELD VALUES below"
      }}
    }}
  ]
}}

SET_FIELD VALUES — when field_name is set, field_value MUST be one of the
exact strings below (lowercase). Do NOT invent new values; if no enum value
fits the situation, omit the set_field card and ask via open_questions
instead. Backend rejects unknown values and the user sees an error.
- incident_type: "safety" | "behavioral" | "property" | "near_miss" | "other"
  (a tardiness or attendance issue is "behavioral", not "tardiness")
- severity: "critical" | "high" | "medium" | "low"
- status: "reported" | "investigating" | "action_required" | "resolved" | "closed"
- root_cause: free text (1-3 sentences)
- corrective_actions: free text (1-3 sentences)
- treatment_beyond_first_aid: BACKEND-OWNED — never set this yourself. The
  deterministic OSHA gate writes it once incident_type and severity are set
  (see OSHA INJURY GATE below).

ACTION RULES:
- run_analysis: pick analysis_type from IR's valid set. Don't recommend an
  analysis that's already in CACHED ANALYSES unless re-running adds value.
  NEVER emit `run_analysis` with `analysis_type="root_cause"`. Root cause is
  captured via a structured 3-question user interview (Hazard / Why /
  Prevention) — not by AI inference. If you would otherwise have proposed
  RCA, emit ONE `quick_reply` card instead with
  `quick_reply_kind="log_root_cause_query"` and choices
  `[{{"label":"Yes","value":"yes"}},{{"label":"No","value":"no"}}]`. The
  backend chains the follow-up text_input cards and writes the user's
  verbatim answers to ir_incidents.root_cause. Skip the prompt entirely
  when the incident's root_cause field is already non-empty OR
  category_data.root_cause_declined is true (user said No earlier) OR
  category_data.root_cause_interview has any keys (interview already
  in progress — never re-prompt mid-interview) OR
  category_data.flow_skipped includes "root_cause" (user skipped the card —
  don't re-offer it; the close step still enforces root cause when required).
- set_field: when you can confidently propose a value (e.g. incident_type
  from description), pre-fill field_name + field_value. The user clicks
  accept and the system writes it. field_value MUST be from SET_FIELD
  VALUES above — never a free-form word like "tardiness" or "harassment".
- request_info: use sparingly — open_questions cover this; only add as a card
  when the missing info is high-stakes (disputed facts, intent unclear,
  legally protected category, or severity high/critical). Do NOT propose
  request_info for routine low-severity behavioral issues like tardiness,
  dress-code violations, or minor performance lapses — those need ACTION,
  not more investigation.
- escalate: recommend when severity is high/critical OR when an investigation
  would benefit from ER Copilot case management.
- close_incident: recommend when status is action_required and a corrective
  action plan exists. HOLD if OSHA INJURY GATE applies (see below) — the
  backend will intercept and emit the OSHA recordable chain instead.

OSHA INJURY GATE — Injury incidents carry a mandatory OSHA recordability
determination (treatment beyond first aid → recordable 300/301 chain). The
BACKEND owns this gate end to end: once incident_type and severity are set it
deterministically surfaces the "Was any treatment provided beyond basic
on-site first aid?" question and every recordable follow-up, and it intercepts
any close_incident card while that chain is unfinished. So do NOT ask the
first-aid/treatment question, do NOT emit a card for it, and do NOT set
treatment_beyond_first_aid or osha_recordable yourself. Spend your rounds
instead on establishing the incident type, setting severity, and gathering the
clarifying facts an investigator needs (what happened, who/what was involved,
witnesses, evidence to collect) — the OSHA chain fires on its own once the
basics are in place, and root cause / corrective actions / closure follow it.

INVESTIGATION-VS-ACTION DECISION:
When the incident facts are clear and the policy violation is unambiguous
(e.g. attendance / tardiness, missed deadline, minor dress-code), prefer
ACTION cards over INVESTIGATION cards:

  Prefer (in order):
    1. set_field corrective_actions = "<concrete next step, 1-2 sentences>"
       (e.g. "Coach employee on attendance policy. Document conversation in
       writing. Note that next occurrence triggers written warning.")
    2. set_field status = "action_required" once corrective_actions is set
    3. close_incident once status is action_required and the user
       acknowledges the action plan

  Avoid for clear minor violations:
    - request_info / "Interview the employee for their statement" cards —
      attendance is cut and dry; the employee's reason rarely changes the
      corrective step.
    - run_analysis similar — overkill for routine policy violations with
      a single obvious cause. (run_analysis root_cause is forbidden
      entirely — see ACTION RULES above; emit log_root_cause_query only
      for complex or high-severity cases where the user wants to capture
      the cause in their own words.)

Only recommend interviewing the subject when (a) facts are disputed
between accounts, (b) intent or context materially affects the response
(harassment, theft, retaliation), or (c) severity is high/critical.

QUALITY RULES:
- AT MOST 1 primary card per round. A second card is allowed ONLY when it
  represents a clear branch the user must choose between (e.g. set_field
  severity vs escalate).
  NEVER offer two set_field cards for the same field in the same round
  (e.g. two "Set status to action_required" cards is a bug — pick one).
  If you have multiple ideas, pick the single best one and put the others
  in open_questions.
- COLD START (first round, no prior assistant message in RECENT
  CONVERSATION): lead with (a) a 1-2 sentence summary explaining what the
  incident is and how you'll help, (b) at most ONE primary action card —
  the next concrete step (categorize / set severity / set status / interview
  / close), and (c) up to 2 open_questions for what's unclear. Do NOT
  generate multiple status updates or alternative paths in cold start.
- ADVANCE on accept: if the most recent CARD/ACCEPTED entry in RECENT
  CONVERSATION shows the user accepted a step, the next round MUST advance
  to the next step in the workflow (status set → propose corrective_actions
  or close_incident; categorized → propose severity or status; etc).
  Re-offering the same step the user just accepted is a bug.
- Sort cards by priority (high first).
- summary always present, even when no cards.
- Do NOT restate prior summaries. If the incident state hasn't materially
  changed since the last assistant message in RECENT CONVERSATION, write a
  short progress note instead (e.g. "Awaiting your reply on X" or
  "Ready to close — accept the recommendation below"). Repeating yesterday's
  facts in new words wastes the user's attention.
"""


def _serialize_incident_core(incident: dict[str, Any]) -> str:
    fields = {
        "incident_number": incident.get("incident_number"),
        "title": incident.get("title"),
        "incident_type": incident.get("incident_type"),
        "severity": incident.get("severity"),
        "status": incident.get("status"),
        "occurred_at": str(incident.get("occurred_at")) if incident.get("occurred_at") else None,
        "location": incident.get("location"),
        "description": incident.get("description"),
        "root_cause": incident.get("root_cause"),
        "corrective_actions": incident.get("corrective_actions"),
        "witnesses": incident.get("witnesses") or [],
        "category_data": incident.get("category_data") or {},
    }
    return json.dumps(fields, indent=2, default=str)


def _serialize_analyses(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(none)"
    summary = {}
    for row in rows:
        analysis_type = row.get("analysis_type")
        data = row.get("analysis_data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                pass
        summary[analysis_type] = data
    return json.dumps(summary, indent=2, default=str)


def _serialize_conversation(messages: list[dict[str, Any]], limit: int = 12) -> tuple[str, str]:
    """Return (conversation_text, latest_user_message)."""
    if not messages:
        return "(no prior messages)", "(none — cold start)"

    recent = messages[-limit:]
    lines = []
    for m in recent:
        role = m.get("role", "user")
        message_type = m.get("message_type", "text")
        content = (m.get("content") or "")[:600]
        if message_type == "card":
            md = _coerce_metadata(m.get("metadata")) or {}
            accepted = md.get("accepted")
            tag = "ACCEPTED" if accepted else "OFFERED"
            lines.append(f"[{role}/card/{tag}] {content}")
        elif message_type == "event":
            md = _coerce_metadata(m.get("metadata")) or {}
            responses = md.get("responses")
            if isinstance(responses, list) and responses:
                qa = " | ".join(
                    f"Q: {r.get('question', '')} A: {r.get('answer', '')}"
                    for r in responses if isinstance(r, dict)
                )
                lines.append(f"[system/event] {content} {qa}")
            else:
                lines.append(f"[system/event] {content}")
        else:
            lines.append(f"[{role}] {content}")

    latest_user = "(none — cold start)"
    for m in reversed(recent):
        if m.get("role") == "user" and m.get("message_type") == "text":
            latest_user = (m.get("content") or "").strip()[:1000]
            break

    return "\n".join(lines), latest_user


async def load_incident_state(
    conn,
    incident_id: UUID,
    company_id: UUID,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (incident_row, analysis_rows, message_rows)."""
    incident = await conn.fetchrow(
        "SELECT * FROM ir_incidents WHERE id = $1 AND company_id = $2",
        incident_id, company_id,
    )
    if not incident:
        return None, [], []  # caller raises 404

    analyses = await conn.fetch(
        "SELECT analysis_type, analysis_data, generated_at FROM ir_incident_analysis "
        "WHERE incident_id = $1 ORDER BY generated_at",
        incident_id,
    )
    messages = await conn.fetch(
        "SELECT id, role, message_type, content, metadata, created_by, created_at "
        "FROM ir_incident_ai_messages WHERE incident_id = $1 ORDER BY created_at, id",
        incident_id,
    )
    incident_dict = dict(incident)
    # Document count powers the deterministic flow's document-capture gate.
    incident_dict["documents_count"] = await conn.fetchval(
        "SELECT COUNT(*) FROM ir_incident_documents WHERE incident_id = $1",
        incident_id,
    ) or 0
    return incident_dict, [dict(a) for a in analyses], [dict(m) for m in messages]


def _coerce_metadata(value) -> Optional[dict]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


async def generate_guidance(
    *,
    incident: dict[str, Any],
    analyses: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a single guidance round against the current incident state."""
    # Short-circuit: when the user explicitly asks to close (and the incident
    # isn't already closed/resolved), skip the LLM round entirely and surface
    # a close_incident card directly. Avoids the case where the LLM gets the
    # request as conversation noise and emits a generic request_info card.
    #
    # Only fires when that request is the NEWEST thing in the transcript. The
    # search walks back past non-user rows, so without this guard a months-old
    # "close this out" stays the latest user text forever and re-triggers on
    # rounds the user didn't start — notably the background auto-resume after
    # an external info-request submission, which would answer the respondent
    # with a stale close card and never analyse what they actually said.
    last_message = (messages or [])[-1] if messages else None
    last_is_user_text = bool(
        last_message
        and last_message.get("role") == "user"
        and last_message.get("message_type") == "text"
    )
    last_user_text = last_message.get("content") if last_is_user_text else None
    incident_status = (incident or {}).get("status")
    if (
        _detect_close_intent(last_user_text)
        and incident_status not in {"closed", "resolved"}
    ):
        return _close_intent_payload()

    # Hard OSHA-compliance gates run deterministically (emergency-reporting
    # freeze, injury/treatment recordability, the 300/301 recordable chain);
    # everything else — categorize, severity, clarifying questions, root cause,
    # corrective actions, closure — is conversational and handled by the LLM
    # below. is_cold_start = no assistant turn yet, so the LLM gets the opening
    # round to greet / categorize / gather facts before the injury gate fires
    # (the emergency freeze still fires immediately, even cold).
    is_cold_start = not any(
        (m or {}).get("role") == "assistant" for m in (messages or [])
    )
    from .ir_flow import resolve_next_step
    flow_payload = resolve_next_step(
        incident,
        analyses,
        documents_count=int((incident or {}).get("documents_count") or 0),
        is_cold_start=is_cold_start,
    )
    if flow_payload is not None:
        return flow_payload

    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("ir_analysis", "ir_copilot")

    conversation_text, latest_user_message = _serialize_conversation(messages)
    prompt = PROMPT_TEMPLATE.format(
        incident_core=_serialize_incident_core(incident),
        cached_analyses=_serialize_analyses(analyses),
        conversation=conversation_text,
        latest_user_message=latest_user_message,
    )

    # Location-resolved safety-statute grounding, appended AFTER .format() (plain
    # concat — no new template slot, no brace risk). Advisory context only; the
    # deterministic OSHA gates above own anything deadline-related.
    try:
        from .ir_statute_grounding import get_incident_statutes, map_incident_to_statutes, serialize_statute_context

        # asyncpg returns JSONB as a raw string here; the incident-type heuristic
        # only scans category_data when it's a dict, so parse it before grounding
        # or the copilot narrows differently from the policy-mapping panel.
        _cd = incident.get("category_data")
        if isinstance(_cd, str):
            try:
                _cd = json.loads(_cd)
            except (ValueError, TypeError):
                _cd = {}
        _grounding_incident = {**incident, "category_data": _cd}
        _statutes = await get_incident_statutes(_grounding_incident, incident.get("company_id"))
        _statute_context = serialize_statute_context(map_incident_to_statutes(_grounding_incident, _statutes))
    except Exception:
        logger.exception("ir copilot: statute grounding failed for incident %s", (incident or {}).get("id"))
        _statute_context = ""
    if _statute_context:
        prompt += (
            "\n\nAPPLICABLE SAFETY / WORKERS-COMP REQUIREMENTS FOR THIS LOCATION "
            "(informational — may be empty):\n" + _statute_context +
            "\n\nUse these to inform guidance where relevant. Do not invent statutes "
            "not listed, and do not compute reporting deadlines yourself — the "
            "deterministic OSHA gates handle those."
        )

    analyzer = get_ir_analyzer()
    try:
        response = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(
                model=analyzer.model,
                contents=prompt,
            ),
            timeout=60,
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        payload = analyzer._parse_json_response(raw_text)
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("IR Copilot guidance generation failed: %s", exc)
        payload = {}

    summary = ""
    if isinstance(payload.get("summary"), str):
        summary = payload["summary"].strip()[:600]

    open_questions_raw = payload.get("open_questions")
    open_questions: list[str] = []
    if isinstance(open_questions_raw, list):
        open_questions = [
            q.strip()[:280]
            for q in open_questions_raw
            if isinstance(q, str) and q.strip()
        ][:3]

    cards = _normalize_guidance_cards(
        payload.get("cards"),
        can_run_discrepancies=False,
        valid_tabs=IR_VALID_TABS,
        valid_analysis_types=IR_VALID_ANALYSIS_TYPES,
    )

    # Layer IR-specific action fields (analysis_type / field_name / field_value)
    # back onto the normalized cards. _normalize_guidance_action stripped them
    # to its own schema; we re-attach from the raw payload by id and drop any
    # card whose action doesn't match an IR-supported type. The shared ER
    # normalizer silently coerces unknown types to open_tab/timeline, which is
    # a no-op for IR — filtering here keeps the user from seeing dead cards.
    # Key by the SAME normalized id _normalize_guidance_cards uses, since the
    # AI may emit snake_case ids that get slugified to kebab-case by
    # _guidance_card_id. Without this match, every card silently failed the
    # IR-specific re-attach and fell back to the ER normalizer's open_tab
    # default — which is exactly the bug we're fixing.
    raw_cards_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(payload.get("cards"), list):
        for idx, raw in enumerate(payload["cards"]):
            if isinstance(raw, dict):
                title = raw.get("title") if isinstance(raw.get("title"), str) else ""
                normalized_id = _guidance_card_id(raw.get("id"), title, idx)
                raw_cards_by_id[normalized_id] = raw
    # Resolve the root-cause skip signals once per round so the safety-net
    # rewrite can drop / shortcut without re-parsing JSONB per card. Both
    # "already logged" (root_cause non-empty) and "user said no last round"
    # (category_data.root_cause_declined) mean we must NOT re-prompt with
    # the interview kick-off card.
    existing_root_cause = (incident.get("root_cause") or "").strip()
    raw_category_data = incident.get("category_data") or {}
    if isinstance(raw_category_data, str):
        try:
            raw_category_data = json.loads(raw_category_data)
        except json.JSONDecodeError:
            raw_category_data = {}
    root_cause_declined = bool(raw_category_data.get("root_cause_declined")) if isinstance(raw_category_data, dict) else False
    root_cause_interview_started = (
        isinstance(raw_category_data, dict)
        and bool(raw_category_data.get("root_cause_interview"))
    )
    suppress_root_cause_card = (
        bool(existing_root_cause)
        or root_cause_declined
        or root_cause_interview_started
    )
    treatment_already_set = (
        isinstance(raw_category_data, dict)
        and raw_category_data.get("treatment_beyond_first_aid") not in (None, "")
    )
    # The close-time gate itself — imported, not mirrored. This used to be a
    # hand-copied duplicate of the rule in _close_incident_via_copilot; when
    # the two drifted the AI would front-load a close_incident card that the
    # intercept then bounced. ir_flow owns the rule for all three consumers
    # (this safety net, the intercept, and the progress meter).
    from app.matcha.services.ir_flow import needs_root_cause
    incident_type_lower = (incident.get("incident_type") or "").strip().lower()
    severity_lower = (incident.get("severity") or "").strip().lower()
    root_cause_required_before_close = needs_root_cause(
        incident_type=incident.get("incident_type"),
        severity=incident.get("severity"),
        root_cause=incident.get("root_cause"),
        category_data=raw_category_data if isinstance(raw_category_data, dict) else {},
    )

    filtered_cards: list[dict[str, Any]] = []
    saw_log_root_cause_query = False
    rewrote_close_to_root_cause = False
    for card in cards:
        raw = raw_cards_by_id.get(card["id"]) or {}
        raw_action = raw.get("action") or {}
        raw_type = raw_action.get("type")
        raw_analysis = raw_action.get("analysis_type")
        canonical_analysis = _canonical_analysis_type(raw_analysis)
        # Safety net: if the AI emits run_analysis root_cause despite the
        # prompt rule forbidding it, rewrite the card in-place to the
        # log_root_cause_query interview kick-off. The analyzer-driven path
        # only has the initial title+description and produces unhelpful
        # output for thin reports; the customer feedback that drove this
        # change ("system shouldn't be running root cause") is preserved
        # even when the AI doesn't comply with prompt instructions.
        if raw_type == "run_analysis" and canonical_analysis == "root_cause":
            from app.matcha.routes.ir_incidents._shared import build_log_root_cause_query_card
            if suppress_root_cause_card:
                # Already logged or user already declined — drop entirely,
                # do not re-prompt. Prevents the No-then-AI-re-emits loop.
                logger.info(
                    "IR copilot dropped root_cause card %s (existing=%s declined=%s)",
                    card["id"], bool(existing_root_cause), root_cause_declined,
                )
                continue
            if saw_log_root_cause_query:
                logger.info(
                    "IR copilot dropped duplicate log_root_cause_query rewrite for card %s",
                    card["id"],
                )
                continue
            replacement = build_log_root_cause_query_card()
            card["id"] = replacement["id"]
            card["title"] = replacement["title"]
            card["recommendation"] = replacement["recommendation"]
            card["rationale"] = replacement["rationale"]
            card["priority"] = replacement["priority"]
            card["blockers"] = replacement["blockers"]
            card["action"] = dict(replacement["action"])
            raw_type = card["action"]["type"]
            raw_action = card["action"]
            raw_analysis = None
            canonical_analysis = None
            saw_log_root_cause_query = True
            filtered_cards.append(card)
            logger.info(
                "IR copilot rewrote run_analysis root_cause card to log_root_cause_query"
            )
            continue
        # Safety net: AI may emit close_incident for a safety / near-miss /
        # high-severity incident before any root-cause prompt has surfaced
        # (prompt rule at line 312-314 lets Gemini judge log_root_cause_query
        # optional, so it skips it on routine reports). User-facing symptom
        # is "prompting me to close without prompting for root cause."
        # Rewrite to the interview kick-off so the close card never reaches
        # the transcript until root_cause is logged or declined. Backend
        # close-time check at copilot.py:497-553 stays as defense-in-depth.
        if raw_type == "close_incident" and root_cause_required_before_close:
            rewrote_close_to_root_cause = True
            if saw_log_root_cause_query:
                logger.info(
                    "IR copilot dropped close_incident card %s "
                    "(root cause not yet logged, type=%s sev=%s)",
                    card["id"], incident_type_lower, severity_lower,
                )
                continue
            from app.matcha.routes.ir_incidents._shared import build_log_root_cause_query_card
            replacement = build_log_root_cause_query_card()
            card["id"] = replacement["id"]
            card["title"] = replacement["title"]
            card["recommendation"] = replacement["recommendation"]
            card["rationale"] = replacement["rationale"]
            card["priority"] = replacement["priority"]
            card["blockers"] = replacement["blockers"]
            card["action"] = dict(replacement["action"])
            raw_type = card["action"]["type"]
            raw_action = card["action"]
            saw_log_root_cause_query = True
            filtered_cards.append(card)
            logger.info(
                "IR copilot rewrote close_incident to log_root_cause_query "
                "(type=%s sev=%s)",
                incident_type_lower, severity_lower,
            )
            continue
        if raw_type not in IR_ACTION_TYPES:
            logger.warning(
                "IR copilot dropped card %s: unsupported action_type=%r",
                card["id"], raw_type,
            )
            continue
        # Safety net for quick_reply hallucinations: Gemini sometimes emits
        # a quick_reply card with Yes/No choices but no quick_reply_kind
        # (or an invented kind the dispatcher doesn't route). User-facing
        # symptom is the "Unknown quick_reply kind:" banner on accept.
        # When the title or recommendation clearly signals root-cause
        # intent, rewrite via the canonical builder. Otherwise drop —
        # surfacing the broken card is worse than no card.
        if raw_type == "quick_reply":
            qrk = (raw_action.get("quick_reply_kind") or "").strip()
            if qrk not in IR_VALID_QUICK_REPLY_KINDS:
                title_lower = (card.get("title") or "").lower()
                rec_lower = (card.get("recommendation") or "").lower()
                looks_like_rc = (
                    "root cause" in title_lower
                    or "root cause" in rec_lower
                    or "root_cause" in qrk.lower()
                )
                if looks_like_rc and not suppress_root_cause_card:
                    if saw_log_root_cause_query:
                        logger.info(
                            "IR copilot dropped duplicate quick_reply card "
                            "%s (already rewrote a root cause card)",
                            card["id"],
                        )
                        continue
                    from app.matcha.routes.ir_incidents._shared import build_log_root_cause_query_card
                    replacement = build_log_root_cause_query_card()
                    card["id"] = replacement["id"]
                    card["title"] = replacement["title"]
                    card["recommendation"] = replacement["recommendation"]
                    card["rationale"] = replacement["rationale"]
                    card["priority"] = replacement["priority"]
                    card["blockers"] = replacement["blockers"]
                    card["action"] = dict(replacement["action"])
                    raw_type = card["action"]["type"]
                    raw_action = card["action"]
                    saw_log_root_cause_query = True
                    filtered_cards.append(card)
                    logger.info(
                        "IR copilot rewrote quick_reply with invalid "
                        "kind=%r to log_root_cause_query (title=%r)",
                        qrk, card.get("title"),
                    )
                    continue
                logger.warning(
                    "IR copilot dropped quick_reply card %s with unknown "
                    "kind=%r (title=%r)",
                    card["id"], qrk, card.get("title"),
                )
                continue
        # Safety net for the OSHA INJURY GATE: drop any set_field card the
        # AI emits for treatment_beyond_first_aid when category_data already
        # has a value. The prompt rule asks for one gate prompt + one
        # set_field card per incident, but Gemini routinely re-emits the
        # same card on subsequent rounds (especially after severity is
        # upgraded to critical). User-facing symptom: "treatment beyond
        # first aid?" asked twice with no chain progress between asks.
        if (
            raw_type == "set_field"
            and raw_action.get("field_name") == "treatment_beyond_first_aid"
            and treatment_already_set
        ):
            logger.info(
                "IR copilot dropped duplicate set_field treatment_beyond_first_aid"
                " (value already %r)",
                raw_category_data.get("treatment_beyond_first_aid"),
            )
            continue
        # Safety net for the root-cause interview: drop direct AI-emitted
        # quick_reply log_root_cause_query cards when suppression applies
        # (interview is in progress, root_cause already logged, or user
        # already declined). The run_analysis-root_cause rewrite branch
        # above handles the indirect path; this handles the direct one.
        # User-facing symptom: "begin root cause?" asked twice before the
        # first interview question is shown.
        if (
            raw_type == "quick_reply"
            and raw_action.get("quick_reply_kind") == "log_root_cause_query"
            and (suppress_root_cause_card or saw_log_root_cause_query)
        ):
            logger.info(
                "IR copilot dropped duplicate log_root_cause_query "
                "(existing=%s declined=%s interview=%s saw=%s)",
                bool(existing_root_cause), root_cause_declined,
                root_cause_interview_started, saw_log_root_cause_query,
            )
            continue
        # Track a direct AI-emitted log_root_cause_query so a subsequent
        # close_incident rewrite in the same round drops instead of
        # duplicating the kick-off card.
        if (
            raw_type == "quick_reply"
            and raw_action.get("quick_reply_kind") == "log_root_cause_query"
        ):
            saw_log_root_cause_query = True
        if raw_type == "run_analysis" and canonical_analysis is None:
            logger.warning(
                "IR copilot dropped card %s: run_analysis without valid analysis_type=%r",
                card["id"], raw_analysis,
            )
            continue
        raw_field_name = raw_action.get("field_name")
        raw_field_value = raw_action.get("field_value")
        if raw_type == "set_field" and not _is_valid_set_field(raw_field_name, raw_field_value):
            logger.warning(
                "IR copilot dropped card %s: set_field with invalid field_name=%r value=%r",
                card["id"], raw_field_name, raw_field_value,
            )
            continue
        # Normalize enum field_value to lowercase so the route's exact-match
        # check passes even when the AI capitalizes it ("Behavioral").
        normalized_value = raw_field_value
        if (
            raw_type == "set_field"
            and isinstance(raw_field_name, str)
            and raw_field_name in IR_FIELD_VALUE_ENUMS
            and isinstance(raw_field_value, str)
        ):
            normalized_value = raw_field_value.strip().lower()
        card["action"]["type"] = raw_type
        card["action"]["analysis_type"] = canonical_analysis
        card["action"]["field_name"] = raw_field_name if isinstance(raw_field_name, str) else None
        card["action"]["field_value"] = normalized_value if isinstance(normalized_value, (str, type(None))) else None
        # _normalize_guidance_cards strips IR-only payload extensions
        # (choices, quick_reply_kind, target_field, etc.) because it
        # was built for the ER router and only knows the base action
        # schema. Without this re-attach an AI-emitted log_root_cause_query
        # card ends up with action.type='quick_reply' but no choices —
        # frontend falls through to Accept/Skip, sends no selected_value,
        # backend dispatcher returns "Pick an option to continue."
        if raw_type in {"quick_reply", "numeric_input", "text_input", "osha_emergency_alert"}:
            for ext_key in (
                "choices",
                "quick_reply_kind",
                "target_field",
                "pending_classification",
                "input_label",
                "input_min",
                "input_max",
                "prompt_text",
                "input_rows",
                "phone",
                "deadline",
            ):
                if ext_key in raw_action:
                    card["action"][ext_key] = raw_action[ext_key]
        filtered_cards.append(card)
    cards = filtered_cards

    # Summary cohesion: if a close_incident card got rewritten to the
    # root-cause kick-off, the AI's summary likely still says "ready to
    # close" — which contradicts the card the user actually sees. Prepend
    # a short note so the transcript reads consistently.
    if rewrote_close_to_root_cause and summary:
        summary = "Before closing, let's capture root cause. " + summary

    if not summary:
        # Minimal fallback — avoids returning empty payload.
        summary = "Review the incident and decide what to do next."
        if not cards and not open_questions:
            cards = [
                {
                    "id": "review_basics",
                    "title": "Review the incident details",
                    "recommendation": "Open the incident and confirm the description, location, and witnesses are filled in.",
                    "rationale": "AI couldn't generate guidance — usually means the incident has too little info.",
                    "priority": "medium",
                    "blockers": [],
                    "action": {
                        "type": "request_info",
                        "label": "Add details",
                        "tab": "overview",
                        "analysis_type": None,
                        "search_query": None,
                        "field_name": None,
                        "field_value": None,
                    },
                    "interview_questions": None,
                },
            ]
            # When the root-cause gate trips (safety / near_miss / high /
            # critical without logged or declined root cause), surface the
            # interview kick-off instead of fallback_close. The fallback
            # block runs AFTER the per-card filter loop, so close_incident
            # would otherwise bypass the gate that the filter applies to
            # AI-emitted close cards. Bug confirmed via transcript of
            # incident 0d4fc4d6 on 2026-05-19 — fallback fired on a
            # safety/high incident and surfaced close before root cause.
            if root_cause_required_before_close:
                from app.matcha.routes.ir_incidents._shared import build_log_root_cause_query_card
                cards.append(build_log_root_cause_query_card())
            else:
                cards.append({
                    "id": "fallback_close",
                    "title": "Close incident",
                    "recommendation": "Close this incident if everything is wrapped up.",
                    "rationale": "Use this once any remaining guidance has been addressed.",
                    "priority": "low",
                    "blockers": [],
                    "action": {
                        "type": "close_incident",
                        "label": "Close incident",
                        "tab": None,
                        "analysis_type": None,
                        "search_query": None,
                        "field_name": None,
                        "field_value": None,
                    },
                    "interview_questions": None,
                })

    return {
        "summary": summary,
        "open_questions": open_questions,
        "cards": cards,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": analyzer.model,
    }


async def append_message(
    conn,
    *,
    incident_id: UUID,
    role: str,
    message_type: str,
    content: str,
    metadata: Optional[dict] = None,
    created_by: Optional[UUID] = None,
) -> dict[str, Any]:
    """Insert a message row and return it as a dict."""
    # created_at is set explicitly to clock_timestamp() rather than leaning on
    # the column's NOW() default: NOW() is transaction_timestamp(), constant for
    # a whole transaction, so a round persisted inside one transaction (the
    # resume-after-info-request path) gave every row an identical timestamp.
    # Reads order by created_at, and _extract_current_cards resets its card list
    # on the assistant text row — with a tie, the cards could sort first and the
    # entire round's cards vanished from the panel. clock_timestamp() advances
    # within the transaction, so insertion order is recoverable.
    row = await conn.fetchrow(
        """
        INSERT INTO ir_incident_ai_messages
          (incident_id, role, message_type, content, metadata, created_by, created_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, clock_timestamp())
        RETURNING id, role, message_type, content, metadata, created_by, created_at
        """,
        incident_id, role, message_type, content,
        json.dumps(metadata) if metadata is not None else None,
        created_by,
    )
    out = dict(row)
    out["metadata"] = _coerce_metadata(out["metadata"])
    return out


_SUMMARY_DEDUPE_THRESHOLD = 0.75


def _normalize_summary(text: str) -> str:
    """Lowercase + collapse non-word chars to single spaces. Used by the
    similarity check so paraphrases compare equal under whitespace and
    punctuation noise."""
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def _summaries_too_similar(a: str, b: str, threshold: float = _SUMMARY_DEDUPE_THRESHOLD) -> bool:
    """True when one summary is mostly contained in the other (token overlap
    / smaller set size). The IR copilot regenerates a summary every guidance
    round; AI often restates the prior round when state hasn't changed, which
    clutters the transcript with near-duplicate assistant messages.

    Containment beats Jaccard here because a longer restatement that adds a
    bit of new framing still has high containment with the original, even
    when Jaccard drops below threshold from the added words."""
    na, nb = _normalize_summary(a), _normalize_summary(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    sa, sb = set(na.split()), set(nb.split())
    if not sa or not sb:
        return False
    smaller = min(len(sa), len(sb))
    if smaller == 0:
        return False
    return (len(sa & sb) / smaller) >= threshold


async def persist_assistant_round(
    conn,
    *,
    incident_id: UUID,
    user_id: Optional[UUID],
    user_message: Optional[str],
    guidance_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Persist a full guidance round: optional user message + assistant text +
    one card-row per recommendation. Returns the new messages in insertion order.

    Skips persisting the assistant text row when the new summary is a near-
    duplicate of the most recent persisted assistant text (Jaccard >= 0.75
    after lowercasing/punctuation strip). Cards still get persisted — the
    drop only suppresses the redundant prose."""
    inserted: list[dict[str, Any]] = []

    if user_message and user_message.strip():
        inserted.append(await append_message(
            conn,
            incident_id=incident_id,
            role="user",
            message_type="text",
            content=user_message.strip()[:4000],
            created_by=user_id,
        ))

    assistant_summary = guidance_payload.get("summary") or ""
    raw_cards = guidance_payload.get("cards") or []

    # A round that produced nothing is a failure, not a state transition.
    # generate_guidance swallows Gemini timeouts/parse errors into payload={},
    # which lands here as empty summary + no cards. Falling through would write
    # a blank assistant row AND run the supersede sweep below, silently wiping
    # every open recommendation the admin still had to act on. Persist the user's
    # message (it was really said) and leave the rest of the thread untouched.
    if not assistant_summary.strip() and not raw_cards and not (guidance_payload.get("open_questions") or []):
        logger.warning(
            "IR copilot round produced no summary/cards for incident %s — "
            "leaving existing cards intact", incident_id,
        )
        return inserted

    last_assistant_text = await conn.fetchval(
        """
        SELECT content FROM ir_incident_ai_messages
        WHERE incident_id = $1 AND role = 'assistant' AND message_type = 'text'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        incident_id,
    )
    if last_assistant_text and _summaries_too_similar(last_assistant_text, assistant_summary):
        logger.info(
            "IR copilot suppressed near-duplicate summary for incident %s", incident_id,
        )
    else:
        inserted.append(await append_message(
            conn,
            incident_id=incident_id,
            role="assistant",
            message_type="text",
            content=assistant_summary,
            metadata={
                "open_questions": guidance_payload.get("open_questions") or [],
                "model": guidance_payload.get("model"),
                "generated_at": guidance_payload.get("generated_at"),
            },
        ))

    # Dedupe within the new round: if the AI emits two cards with the same id
    # OR the same (action.type, field_name, field_value) signature, keep only
    # the first. Belt-and-suspenders against AI repeats.
    seen_ids: set[str] = set()
    seen_signatures: set[tuple] = set()
    deduped_cards: list[dict[str, Any]] = []
    for card in raw_cards:
        if not isinstance(card, dict):
            continue
        cid = card.get("id")
        action = card.get("action") or {}
        sig = (
            action.get("type"),
            action.get("field_name"),
            action.get("field_value"),
            action.get("analysis_type"),
        )
        if isinstance(cid, str) and cid in seen_ids:
            logger.info("IR copilot dedupe-within-round dropped card id=%s", cid)
            continue
        if any(sig) and sig in seen_signatures:
            logger.info("IR copilot dedupe-within-round dropped card sig=%s", sig)
            continue
        if isinstance(cid, str):
            seen_ids.add(cid)
        if any(sig):
            seen_signatures.add(sig)
        deduped_cards.append(card)

    # Supersede every prior unaccepted/non-skipped card row before persisting
    # the new round's cards. Without this, _extract_current_cards keeps
    # surfacing prior-round cards alongside the new ones whenever the
    # assistant-text suppression path fires (no fresh text → no reset point),
    # producing the "3× same card" bug.
    #
    # Deliberately NOT gated on the new round having cards. Gating it looks like
    # it would protect a summary-only round's predecessors, but it does not:
    # _extract_current_cards resets its accumulator on *any* assistant text row,
    # so those cards disappear from the panel regardless. Skipping the sweep only
    # leaves them un-superseded in the DB while invisible in the UI — and the
    # _close_incident_via_copilot idempotency probes then find those stale rows
    # and hand back a message_id for a card the user cannot see. The round that
    # genuinely must not clear anything (a failed/empty payload) is already
    # handled by the early return above, which writes no text row at all.
    await conn.execute(
        """
        UPDATE ir_incident_ai_messages
        SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{superseded}',
                'true'::jsonb,
                true
            )
        WHERE incident_id = $1
          AND role = 'assistant'
          AND message_type = 'card'
          AND COALESCE((metadata->>'accepted')::boolean, false) IS NOT TRUE
          AND COALESCE((metadata->>'superseded')::boolean, false) IS NOT TRUE
          AND COALESCE((metadata->>'skipped')::boolean, false) IS NOT TRUE
        """,
        incident_id,
    )

    for card in deduped_cards:
        inserted.append(await append_message(
            conn,
            incident_id=incident_id,
            role="assistant",
            message_type="card",
            content=card.get("title") or "Recommendation",
            metadata={
                "card": card,
                "accepted": False,
            },
        ))

    return inserted
