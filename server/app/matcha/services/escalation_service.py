"""Low-confidence escalation service for Matcha Work queries."""

import json
import logging
from uuid import UUID

from ...database import get_connection
from .matcha_work_ai import AIResponse

logger = logging.getLogger(__name__)


def should_escalate(ai_resp: AIResponse) -> bool:
    """Return True if the AI response should be escalated for human review."""
    mode = ai_resp.mode
    conf = ai_resp.confidence

    if mode == "refuse":
        return True
    if mode == "general" and conf < 0.4:
        return True
    if mode == "clarify" and conf < 0.5:
        return True
    if mode == "skill" and conf < 0.65 and ai_resp.missing_fields:
        return True
    return False


def compute_severity(ai_resp: AIResponse) -> str:
    """Map an AI response to an escalation severity level."""
    mode = ai_resp.mode
    conf = ai_resp.confidence

    if mode == "refuse":
        return "high"
    if mode == "general" and conf < 0.4:
        return "high"
    # Everything else that triggers escalation is medium
    return "medium"


def _build_title(user_query: str, ai_resp: AIResponse) -> str:
    """Generate a short title for the escalation row."""
    if ai_resp.mode == "refuse":
        return "AI refused to answer"
    if ai_resp.mode == "clarify":
        return "AI needed clarification"
    # Truncate user query for title
    q = user_query.strip()
    if len(q) > 80:
        q = q[:77] + "..."
    return q


async def create_escalation(
    company_id: UUID,
    thread_id: UUID,
    user_message_id: UUID | None,
    assistant_message_id: UUID,
    user_query: str,
    ai_resp: AIResponse,
) -> dict:
    """Insert an escalation row and return it."""
    severity = compute_severity(ai_resp)
    title = _build_title(user_query, ai_resp)
    missing = json.dumps(ai_resp.missing_fields) if ai_resp.missing_fields else None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mw_escalated_queries
                   (company_id, thread_id, message_id, user_message_id,
                    severity, title, user_query, ai_reply, ai_mode,
                    ai_confidence, missing_fields)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
               RETURNING *""",
            company_id,
            thread_id,
            assistant_message_id,
            user_message_id,
            severity,
            title,
            user_query,
            ai_resp.assistant_reply,
            ai_resp.mode,
            ai_resp.confidence,
            missing,
        )

    logger.info(
        "Escalated query %s (severity=%s, mode=%s, confidence=%.2f) for company %s",
        row["id"], severity, ai_resp.mode, ai_resp.confidence, company_id,
    )
    return dict(row)
