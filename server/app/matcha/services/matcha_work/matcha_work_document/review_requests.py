"""Anonymous review request lifecycle — send/list/sync/public submit."""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.database import get_connection
from app.config import get_settings
from app.core.services.email import EmailService

from ._coerce import (
    _parse_jsonb,
    normalize_recipient_emails,
    _coerce_state_recipient_emails,
    _row_to_review_request_status,
    _build_review_request_state_update,
)
from ._email_html import _render_review_request_email_html
from .versions import apply_update
from .messages import add_message

logger = logging.getLogger(__name__)


async def _list_review_requests_for_thread(thread_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT recipient_email, status, sent_at, submitted_at, last_error
            FROM mw_review_requests
            WHERE thread_id=$1
            ORDER BY recipient_email ASC
            """,
            thread_id,
        )
    return [_row_to_review_request_status(dict(row)) for row in rows]


async def list_review_requests(thread_id: UUID, company_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        thread_exists = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1
                FROM mw_threads
                WHERE id=$1 AND company_id=$2
            )
            """,
            thread_id,
            company_id,
        )
    if not thread_exists:
        raise ValueError("Thread not found")
    return await _list_review_requests_for_thread(thread_id)


async def sync_review_request_state(thread_id: UUID) -> dict:
    status_rows = await _list_review_requests_for_thread(thread_id)
    updates = _build_review_request_state_update(status_rows)
    update_keys = set(updates.keys())

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT current_state, version
            FROM mw_threads
            WHERE id=$1
            """,
            thread_id,
        )
    if row is None:
        raise ValueError("Thread not found")

    current_state = _parse_jsonb(row["current_state"])
    unchanged = True
    for key in update_keys:
        if current_state.get(key) != updates.get(key):
            unchanged = False
            break
    if unchanged:
        return {"version": row["version"], "current_state": current_state}

    return await apply_update(
        thread_id,
        updates,
        diff_summary="Updated review request tracking",
    )


async def send_review_requests(
    thread_id: UUID,
    company_id: UUID,
    recipient_emails: list[str],
    custom_message: Optional[str] = None,
) -> dict:
    async with get_connection() as conn:
        thread_row = await conn.fetchrow(
            """
            SELECT title, status, current_state, c.name AS company_name
            FROM mw_threads t
            JOIN companies c ON c.id = t.company_id
            WHERE t.id=$1 AND t.company_id=$2
            """,
            thread_id,
            company_id,
        )
    if thread_row is None:
        raise ValueError("Thread not found")

    if thread_row["status"] == "archived":
        raise ValueError("Cannot send review requests for an archived thread")

    state = _parse_jsonb(thread_row["current_state"])
    normalized_recipients = normalize_recipient_emails(recipient_emails)
    if not normalized_recipients:
        normalized_recipients = _coerce_state_recipient_emails(state)
    if not normalized_recipients:
        raise ValueError("At least one valid recipient email is required")
    if len(normalized_recipients) > 100:
        raise ValueError("A maximum of 100 recipient emails is supported per send")

    review_title = (
        state.get("review_title")
        or state.get("review_subject")
        or thread_row["title"]
        or "Anonymous Performance Review"
    )
    company_name = thread_row["company_name"] or "Your HR Team"
    settings = get_settings()
    app_base_url = (settings.app_base_url or "").rstrip("/")
    if not app_base_url:
        raise ValueError("APP_BASE_URL is required to send review request links")

    pending_requests: list[dict] = []
    async with get_connection() as conn:
        async with conn.transaction():
            existing_rows = await conn.fetch(
                """
                SELECT recipient_email, status
                FROM mw_review_requests
                WHERE thread_id=$1
                  AND recipient_email = ANY($2::text[])
                FOR UPDATE
                """,
                thread_id,
                normalized_recipients,
            )
            existing_status_by_email = {
                str(row["recipient_email"]).strip().lower(): str(row["status"] or "pending")
                for row in existing_rows
            }
            await conn.execute(
                """
                DELETE FROM mw_review_requests
                WHERE thread_id=$1
                  AND status != 'submitted'
                  AND NOT (recipient_email = ANY($2::text[]))
                """,
                thread_id,
                normalized_recipients,
            )
            for email in normalized_recipients:
                if existing_status_by_email.get(email) == "submitted":
                    continue
                token = secrets.token_urlsafe(24)
                row = await conn.fetchrow(
                    """
                    INSERT INTO mw_review_requests(
                        thread_id, company_id, recipient_email, token, status
                    )
                    VALUES($1, $2, $3, $4, 'pending')
                    ON CONFLICT(thread_id, recipient_email) DO UPDATE
                    SET token=EXCLUDED.token,
                        status='pending',
                        sent_at=NULL,
                        submitted_at=NULL,
                        last_error=NULL,
                        feedback=NULL,
                        rating=NULL,
                        updated_at=NOW()
                    RETURNING recipient_email, token
                    """,
                    thread_id,
                    company_id,
                    email,
                    token,
                )
                pending_requests.append(dict(row))

    email_service = EmailService()
    sent_count = 0
    failed_count = 0

    async with get_connection() as conn:
        for request_row in pending_requests:
            recipient_email = request_row["recipient_email"]
            token = request_row["token"]
            response_url = f"{app_base_url}/review-request/{token}"
            subject = f"Anonymous review request: {review_title}"
            html_content = _render_review_request_email_html(
                review_title=review_title,
                company_name=company_name,
                response_url=response_url,
                custom_message=custom_message,
            )

            status_value = "failed"
            sent_at = None
            last_error = None
            if not email_service.is_configured():
                last_error = "email_service_not_configured"
            else:
                try:
                    sent = await email_service.send_email(
                        to_email=recipient_email,
                        to_name=None,
                        subject=subject,
                        html_content=html_content,
                    )
                    if sent:
                        status_value = "sent"
                        sent_at = datetime.now(timezone.utc)
                    else:
                        last_error = "send_failed"
                except Exception as e:
                    logger.warning(
                        "Failed to send Matcha Work review request email to %s: %s",
                        recipient_email,
                        e,
                    )
                    last_error = "send_exception"

            if status_value == "sent":
                sent_count += 1
            else:
                failed_count += 1

            await conn.execute(
                """
                UPDATE mw_review_requests
                SET status=$1,
                    sent_at=$2,
                    last_error=$3,
                    updated_at=NOW()
                WHERE thread_id=$4 AND recipient_email=$5
                """,
                status_value,
                sent_at,
                last_error,
                thread_id,
                recipient_email,
            )

    state_sync = await sync_review_request_state(thread_id)
    status_rows = await _list_review_requests_for_thread(thread_id)
    expected_responses = len(status_rows)
    received_responses = sum(1 for row in status_rows if row["status"] == "submitted")
    pending_responses = max(expected_responses - received_responses, 0)

    await add_message(
        thread_id,
        "system",
        (
            f"Review requests sent to {expected_responses} recipient(s): "
            f"{sent_count} sent, {failed_count} failed. "
            f"Received {received_responses}/{expected_responses} response(s)."
        ),
        version_created=state_sync["version"],
    )

    return {
        "thread_id": thread_id,
        "expected_responses": expected_responses,
        "received_responses": received_responses,
        "pending_responses": pending_responses,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "recipients": status_rows,
    }


async def get_public_review_request(token: str) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                r.recipient_email,
                r.status,
                r.submitted_at,
                t.title,
                t.current_state
            FROM mw_review_requests r
            JOIN mw_threads t ON t.id = r.thread_id
            WHERE r.token=$1
            """,
            token,
        )
    if row is None:
        return None

    state = _parse_jsonb(row["current_state"])
    review_title = (
        state.get("review_title")
        or state.get("review_subject")
        or row["title"]
        or "Anonymous Performance Review"
    )

    return {
        "token": token,
        "review_title": review_title,
        "recipient_email": row["recipient_email"],
        "status": row["status"],
        "submitted_at": row["submitted_at"],
    }


async def submit_public_review_request(
    token: str,
    feedback: str,
    rating: Optional[int] = None,
) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                """
                SELECT id, thread_id, recipient_email, status
                FROM mw_review_requests
                WHERE token=$1
                FOR UPDATE
                """,
                token,
            )
            if existing is None:
                raise ValueError("Review request not found")
            if existing["status"] == "submitted":
                raise ValueError("Review response already submitted")

            updated = await conn.fetchrow(
                """
                UPDATE mw_review_requests
                SET status='submitted',
                    feedback=$1,
                    rating=$2,
                    submitted_at=NOW(),
                    last_error=NULL,
                    updated_at=NOW()
                WHERE id=$3
                RETURNING thread_id, submitted_at
                """,
                feedback.strip(),
                rating,
                existing["id"],
            )

    thread_id = updated["thread_id"]
    state_sync = await sync_review_request_state(thread_id)
    await add_message(
        thread_id,
        "system",
        "A review response was submitted from one of the requested recipients.",
        version_created=state_sync["version"],
    )

    return {
        "status": "submitted",
        "submitted_at": updated["submitted_at"],
    }
