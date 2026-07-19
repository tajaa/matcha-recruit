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


async def create_hr_pilot_escalation(
    company_id: UUID,
    thread_id: UUID,
    user_message_id: UUID | None,
    assistant_message_id: UUID,
    category: str | None,
    user_query: str,
    notice: str,
    matched_terms: tuple[str, ...],
) -> dict:
    """Insert an HR Pilot hard-stop trip into the same human-review queue as
    low-confidence AI escalations (mw_escalated_queries) — no separate table
    or admin UI needed. Every hard-stop is severity=high by construction: the
    gate's own posture is that a category match is a live legal-exposure
    event, not something to grade."""
    title = f"HR Pilot escalation: {category or 'policy'}"
    missing = json.dumps(list(matched_terms)) if matched_terms else None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mw_escalated_queries
                   (company_id, thread_id, message_id, user_message_id,
                    severity, title, user_query, ai_reply, ai_mode, missing_fields)
               VALUES ($1, $2, $3, $4, 'high', $5, $6, $7, 'hr_pilot_hard_stop', $8::jsonb)
               RETURNING *""",
            company_id,
            thread_id,
            assistant_message_id,
            user_message_id,
            title,
            user_query,
            notice,
            missing,
        )

    logger.info(
        "HR Pilot escalation %s (category=%s) for company %s",
        row["id"], category, company_id,
    )
    return dict(row)


async def create_hr_pilot_compliance_escalation(
    company_id: UUID,
    thread_id: UUID,
    user_message_id: UUID | None,
    assistant_message_id: UUID,
    user_query: str,
    notice: str,
    blocks: list[dict],
) -> dict:
    """Log an HR Pilot discipline-compliance BLOCK into the same review queue
    (mw_escalated_queries). Distinct `ai_mode` so a reviewer can tell a
    statutory discipline block apart from a keyword hard-stop. Severity is
    always high — a protected-leave block is a live legal-exposure event."""
    statutes = ", ".join(sorted({
        str(b.get("statute")) for b in (blocks or []) if b.get("statute")
    })) or "protected leave"
    title = f"HR Pilot blocked discipline ({statutes})"
    codes = [b.get("code") for b in (blocks or []) if b.get("code")]
    missing = json.dumps(codes) if codes else None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mw_escalated_queries
                   (company_id, thread_id, message_id, user_message_id,
                    severity, title, user_query, ai_reply, ai_mode, missing_fields)
               VALUES ($1, $2, $3, $4, 'high', $5, $6, $7, 'hr_pilot_compliance_block', $8::jsonb)
               RETURNING *""",
            company_id,
            thread_id,
            assistant_message_id,
            user_message_id,
            title,
            user_query,
            notice,
            missing,
        )

    logger.info("HR Pilot compliance block %s for company %s", row["id"], company_id)
    return dict(row)


# Friendly, content-free labels for the hard-stop notification email.
_HARD_STOP_CATEGORY_LABELS = {
    "harassment_discrimination": "a harassment or discrimination concern",
    "workplace_safety": "a workplace safety or injury concern",
    "leave_and_medical": "a leave or medical matter",
    "termination_or_legal": "a termination or legal matter",
}


async def send_hr_pilot_hard_stop_notifications(
    *,
    company_id: UUID,
    category: str | None,
    thread_id: UUID,
    thread_title: str | None = None,
) -> None:
    """Email the company's business admins that a supervisor question tripped a
    hard-stop and was routed to corporate HR. **Content-free by design** —
    category + a link only, never the supervisor's raw (sensitive) message. The
    caller is responsible for the first-occurrence dedupe (see messaging.py)."""
    from app.core.services.email import get_email_service

    email_service = get_email_service()
    if not email_service.is_configured():
        return

    async with get_connection() as conn:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        contacts = await conn.fetch(
            """SELECT DISTINCT u.email,
                      COALESCE(NULLIF(c.name, ''), split_part(u.email, '@', 1)) AS name
               FROM clients c JOIN users u ON u.id = c.user_id
               WHERE c.company_id = $1 AND u.is_active = true AND u.email IS NOT NULL
               ORDER BY u.email""",
            company_id,
        )
    if not contacts:
        return

    company_name = (company["name"] if company else None) or "Your company"
    label = _HARD_STOP_CATEGORY_LABELS.get(category or "", "a sensitive HR matter")
    subject = f"[{company_name}] A supervisor question was routed to HR"
    link = "https://hey-matcha.com/dashboard"
    html = (
        f"<p>An on-site supervisor raised something HR Pilot classified as "
        f"<strong>{label}</strong>, so it was routed to corporate HR instead of being "
        f"handled on-site.</p>"
        f"<p>Review it in the escalation queue: <a href=\"{link}\">{link}</a></p>"
        f"<p>This message intentionally omits the details — open the queue to review.</p>"
    )

    import asyncio
    await asyncio.gather(
        *[
            email_service.send_email_with_fallback(
                to_email=c["email"], to_name=c["name"], subject=subject, html_content=html,
            )
            for c in contacts
        ],
        return_exceptions=True,
    )
