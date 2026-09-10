"""Sym-link notifications: recipient invite, sender completion notice, and the
weekly passcode announcement in an Ops channel.

Emails go through the shared EmailService (which hard-blocks RFC 2606 test
domains). The channel announcement is a persisted `message_type='system'`
`channel_messages` row with `sender_id NULL` — the same shape EMS uses
(`services/ems/event_assignments.py`). It runs from the worker, so there is
no live WebSocket fan-out; members see it on their next history load.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.services.email import get_email_service
from app.matcha.services.symlink.passcode import format_code

logger = logging.getLogger(__name__)


def _expires_text(expires_at: Optional[datetime]) -> Optional[str]:
    if not expires_at:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return "on " + expires_at.strftime("%B %d, %Y")


async def send_invite(link_row: Any, *, url: str, company_name: str, requested_by_name: str,
                      reminder: bool = False) -> bool:
    try:
        return await get_email_service().send_symlink_invite_email(
            to_email=link_row["recipient_email"],
            to_name=link_row["recipient_name"],
            company_name=company_name,
            requested_by_name=requested_by_name,
            title=link_row["title"],
            instructions=link_row["instructions"],
            link=url,
            expires_text=_expires_text(link_row["expires_at"]),
            reminder=reminder,
        )
    except Exception as exc:
        logger.warning("[symlink] invite email failed for %s: %s", link_row["id"], exc)
        return False


async def send_submitted(*, to_email: str, to_name: Optional[str], company_name: str,
                         recipient_name: str, title: str, review_link: str) -> bool:
    try:
        return await get_email_service().send_symlink_submitted_email(
            to_email=to_email, to_name=to_name, company_name=company_name,
            recipient_name=recipient_name, title=title, review_link=review_link,
        )
    except Exception as exc:
        logger.warning("[symlink] submitted email failed: %s", exc)
        return False


async def sender_contact(conn, created_by, company_id) -> tuple[Optional[str], Optional[str]]:
    """(email, display name) for the user who minted a link, falling back to the
    company's oldest client contact so a completion notice always has a home."""
    if created_by:
        row = await conn.fetchrow(
            """SELECT u.email, c.name
                 FROM users u LEFT JOIN clients c ON c.user_id = u.id
                WHERE u.id = $1""",
            created_by,
        )
        if row and row["email"]:
            return row["email"], row["name"] or row["email"].split("@")[0]
    row = await conn.fetchrow(
        """SELECT u.email, c.name
             FROM clients c JOIN users u ON u.id = c.user_id
            WHERE c.company_id = $1
            ORDER BY c.created_at ASC, u.email ASC
            LIMIT 1""",
        company_id,
    )
    if row and row["email"]:
        return row["email"], row["name"] or row["email"].split("@")[0]
    return None, None


async def requester_display_name(conn, current_user) -> str:
    row = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", current_user.id)
    if row and row["name"]:
        return row["name"]
    return current_user.email.split("@")[0]


async def announce_rotation(conn, *, company_id, channel_id, code: str) -> bool:
    """Post the new passcode into the company's chosen channel as a system
    message. The channel must belong to the company (re-checked here so a stale
    settings row can never leak a code cross-tenant)."""
    if not channel_id:
        return False
    channel = await conn.fetchrow(
        "SELECT id FROM channels WHERE id = $1 AND company_id = $2 AND COALESCE(is_archived, false) = false",
        channel_id, company_id,
    )
    if not channel:
        return False
    content = (
        f"🔑 This week's sym-link passcode is **{format_code(code)}**. "
        "Anyone opening a task link from us will be asked for it. It rotates weekly."
    )
    metadata = {"action": {"kind": "symlink_passcode", "status": "rotated"}}
    await conn.execute(
        """INSERT INTO channel_messages (channel_id, sender_id, content, message_type, metadata)
           VALUES ($1, NULL, $2, 'system', $3::jsonb)""",
        channel_id, content, json.dumps(metadata),
    )
    return True
