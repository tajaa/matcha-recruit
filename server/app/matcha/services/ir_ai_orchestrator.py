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
IR_ACTION_TYPES = {
    "run_analysis",
    "set_field",
    "request_info",
    "escalate",
    "close_incident",
}


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
        "field_name": "category" | "severity" | "status" | "root_cause" | "corrective_actions" | null,
        "field_value": "string or null"
      }}
    }}
  ]
}}

ACTION RULES:
- run_analysis: pick analysis_type from IR's valid set. Don't recommend an
  analysis that's already in CACHED ANALYSES unless re-running adds value.
- set_field: when you can confidently propose a value (e.g. category from
  description), pre-fill field_name + field_value. The user clicks accept and
  the system writes it.
- request_info: use sparingly — open_questions cover this; only add as a card
  when the missing info is high-stakes.
- escalate: recommend when severity is high/critical OR when an investigation
  would benefit from ER Copilot case management.
- close_incident: recommend when status is action_required and a corrective
  action plan exists.

QUALITY RULES:
- 1-4 cards. Don't pad. Skip cards if nothing useful applies.
- Sort cards by priority (high first).
- summary always present, even when no cards.
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
        "FROM ir_incident_ai_messages WHERE incident_id = $1 ORDER BY created_at",
        incident_id,
    )
    return dict(incident), [dict(a) for a in analyses], [dict(m) for m in messages]


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
    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("ir_analysis", "ir_copilot")

    conversation_text, latest_user_message = _serialize_conversation(messages)
    prompt = PROMPT_TEMPLATE.format(
        incident_core=_serialize_incident_core(incident),
        cached_analyses=_serialize_analyses(analyses),
        conversation=conversation_text,
        latest_user_message=latest_user_message,
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
    filtered_cards: list[dict[str, Any]] = []
    for card in cards:
        raw = raw_cards_by_id.get(card["id"]) or {}
        raw_action = raw.get("action") or {}
        raw_type = raw_action.get("type")
        raw_analysis = raw_action.get("analysis_type")
        canonical_analysis = _canonical_analysis_type(raw_analysis)
        if raw_type not in IR_ACTION_TYPES:
            logger.warning(
                "IR copilot dropped card %s: unsupported action_type=%r",
                card["id"], raw_type,
            )
            continue
        if raw_type == "run_analysis" and canonical_analysis is None:
            logger.warning(
                "IR copilot dropped card %s: run_analysis without valid analysis_type=%r",
                card["id"], raw_analysis,
            )
            continue
        card["action"]["type"] = raw_type
        card["action"]["analysis_type"] = canonical_analysis
        card["action"]["field_name"] = raw_action.get("field_name") if isinstance(raw_action.get("field_name"), str) else None
        card["action"]["field_value"] = raw_action.get("field_value") if isinstance(raw_action.get("field_value"), (str, type(None))) else None
        filtered_cards.append(card)
    cards = filtered_cards

    if not summary:
        # Minimal fallback — avoids returning empty payload.
        summary = "Review the incident and decide what to do next."
        if not cards and not open_questions:
            cards = [{
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
            }]

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
    row = await conn.fetchrow(
        """
        INSERT INTO ir_incident_ai_messages
          (incident_id, role, message_type, content, metadata, created_by)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        RETURNING id, role, message_type, content, metadata, created_by, created_at
        """,
        incident_id, role, message_type, content,
        json.dumps(metadata) if metadata is not None else None,
        created_by,
    )
    out = dict(row)
    out["metadata"] = _coerce_metadata(out["metadata"])
    return out


async def persist_assistant_round(
    conn,
    *,
    incident_id: UUID,
    user_id: Optional[UUID],
    user_message: Optional[str],
    guidance_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Persist a full guidance round: optional user message + assistant text +
    one card-row per recommendation. Returns the new messages in insertion order."""
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

    for card in guidance_payload.get("cards") or []:
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
