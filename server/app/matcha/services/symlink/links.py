"""symlinks / symlink_unlocks DB service.

Token lookups are RLS-free (the public side has no tenant context yet); every
write after that runs on a tenant-scoped connection the caller opens with the
company_id this module returned — the same two-step `/request-info` uses.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.matcha.services._shared.jsonio import safe_json_loads

LINK_COLS = (
    "id, company_id, token, kind, title, instructions, spec, recipient_name, recipient_email, "
    "employee_id, status, expires_at, created_by, created_at, sent_at, last_sent_at, "
    "first_unlocked_at, completed_at, reminder_sent_at, transcript, known_fields, turn_count, updated_at"
)

OPEN_STATUSES = ("pending", "in_progress")
CLOSED_MESSAGES = {
    "submitted": "This request has already been completed.",
    "applied": "This request has already been completed.",
    "rejected": "This request is closed.",
    "revoked": "This link has been revoked.",
    "expired": "This link has expired.",
}


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_unlock_token() -> str:
    return secrets.token_urlsafe(32)


def hash_unlock_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def effective_status(row: Any, now: Optional[datetime] = None) -> str:
    """Stored status, except an open link past its expiry reads as 'expired'
    (derived at read time; the sweep persists it later)."""
    status = row["status"]
    if status in OPEN_STATUSES:
        now = now or datetime.now(timezone.utc)
        expires_at = _aware(row["expires_at"])
        if expires_at and expires_at <= now:
            return "expired"
    return status


def is_open(row: Any, now: Optional[datetime] = None) -> bool:
    return effective_status(row, now) in OPEN_STATUSES


def transcript_of(row: Any) -> list[dict]:
    value = safe_json_loads(row["transcript"], [])
    return value if isinstance(value, list) else []


def known_fields_of(row: Any) -> dict:
    value = safe_json_loads(row["known_fields"], {})
    return value if isinstance(value, dict) else {}


def spec_of(row: Any) -> dict:
    value = safe_json_loads(row["spec"], {})
    return value if isinstance(value, dict) else {}


# ── reads ──────────────────────────────────────────────────────────────────


async def fetch_by_token(conn, token: str):
    """RLS-free lookup: link + the company's name and RAW enabled_features."""
    return await conn.fetchrow(
        f"""
        SELECT {", ".join("s." + c.strip() for c in LINK_COLS.split(","))},
               c.name AS company_name, c.enabled_features
          FROM symlinks s
          JOIN companies c ON c.id = s.company_id
         WHERE s.token = $1
        """,
        token,
    )


async def fetch_by_id(conn, link_id, company_id, *, for_update: bool = False):
    lock = " FOR UPDATE" if for_update else ""
    return await conn.fetchrow(
        f"SELECT {LINK_COLS} FROM symlinks WHERE id = $1 AND company_id = $2{lock}",
        link_id, company_id,
    )


async def list_links(conn, company_id, *, status: Optional[str] = None, limit: int = 200):
    if status:
        return await conn.fetch(
            f"""SELECT {LINK_COLS} FROM symlinks
                 WHERE company_id = $1 AND status = $2
                 ORDER BY created_at DESC LIMIT $3""",
            company_id, status, limit,
        )
    return await conn.fetch(
        f"SELECT {LINK_COLS} FROM symlinks WHERE company_id = $1 ORDER BY created_at DESC LIMIT $2",
        company_id, limit,
    )


async def list_attachments(conn, link_id):
    return await conn.fetch(
        """SELECT id, symlink_id, slot, storage_path, file_name, content_type, size_bytes, uploaded_at
             FROM symlink_attachments
            WHERE symlink_id = $1 AND discarded_at IS NULL
            ORDER BY uploaded_at""",
        link_id,
    )


async def present_slots(conn, link_id) -> set[str]:
    rows = await conn.fetch(
        "SELECT DISTINCT slot FROM symlink_attachments WHERE symlink_id = $1 AND discarded_at IS NULL",
        link_id,
    )
    return {r["slot"] for r in rows}


async def fetch_submission(conn, link_id):
    return await conn.fetchrow(
        """SELECT id, symlink_id, company_id, fields, attachment_ids, submitted_at, status,
                  reviewed_by, reviewed_at, review_note, applied_ref
             FROM symlink_submissions WHERE symlink_id = $1""",
        link_id,
    )


# ── writes ─────────────────────────────────────────────────────────────────


async def create_link(
    conn, *, company_id, kind: str, title: str, instructions: Optional[str], spec: dict,
    recipient_name: str, recipient_email: str, employee_id, expires_in_days: int, created_by,
):
    token = new_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    opening = spec.get("opening_message") or "Hi! Let's get started."
    transcript = [{"role": "assistant", "content": opening}]
    return await conn.fetchrow(
        f"""
        INSERT INTO symlinks
            (company_id, token, kind, title, instructions, spec, recipient_name, recipient_email,
             employee_id, expires_at, created_by, transcript)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12::jsonb)
        RETURNING {LINK_COLS}
        """,
        company_id, token, kind, title, instructions, json.dumps(spec), recipient_name,
        recipient_email, employee_id, expires_at, created_by, json.dumps(transcript),
    )


async def mark_sent(conn, link_id, company_id):
    return await conn.fetchrow(
        f"""UPDATE symlinks
               SET sent_at = COALESCE(sent_at, NOW()), last_sent_at = NOW(), updated_at = NOW()
             WHERE id = $1 AND company_id = $2
         RETURNING {LINK_COLS}""",
        link_id, company_id,
    )


async def rotate_token(conn, link_id, company_id, *, token: str, expires_in_days: int):
    """Persist a pre-generated token + fresh expiry; only while the link is still
    open. Callers generate the token first, send the email WITHOUT a connection
    held, and call this only after the send succeeded (info_requests.py pattern)."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    return await conn.fetchrow(
        f"""UPDATE symlinks
               SET token = $3, expires_at = $4, last_sent_at = NOW(), sent_at = COALESCE(sent_at, NOW()),
                   status = CASE WHEN status = 'expired' THEN 'pending' ELSE status END,
                   updated_at = NOW()
             WHERE id = $1 AND company_id = $2 AND status IN ('pending', 'in_progress', 'expired')
         RETURNING {LINK_COLS}""",
        link_id, company_id, token, expires_at,
    )


async def set_status(conn, link_id, company_id, status: str, *, completed: bool = False):
    completed_sql = ", completed_at = NOW()" if completed else ""
    return await conn.fetchrow(
        f"""UPDATE symlinks SET status = $3, updated_at = NOW(){completed_sql}
             WHERE id = $1 AND company_id = $2
         RETURNING {LINK_COLS}""",
        link_id, company_id, status,
    )


async def revoke(conn, link_id, company_id):
    row = await conn.fetchrow(
        f"""UPDATE symlinks SET status = 'revoked', updated_at = NOW()
             WHERE id = $1 AND company_id = $2 AND status IN ('pending', 'in_progress', 'expired')
         RETURNING {LINK_COLS}""",
        link_id, company_id,
    )
    if row:
        await revoke_unlocks(conn, link_id)
    return row


async def revoke_unlocks(conn, link_id):
    await conn.execute(
        "UPDATE symlink_unlocks SET revoked_at = NOW() WHERE symlink_id = $1 AND revoked_at IS NULL",
        link_id,
    )


async def record_unlock(conn, link_id, company_id, *, ip: Optional[str]) -> str:
    """Insert an unlock row and return the plaintext token (hash is what's stored)."""
    token = new_unlock_token()
    await conn.execute(
        """INSERT INTO symlink_unlocks (symlink_id, company_id, unlock_token_hash, ip)
           VALUES ($1, $2, $3, $4)""",
        link_id, company_id, hash_unlock_token(token), ip,
    )
    await conn.execute(
        """UPDATE symlinks
              SET first_unlocked_at = COALESCE(first_unlocked_at, NOW()),
                  status = CASE WHEN status = 'pending' THEN 'in_progress' ELSE status END,
                  updated_at = NOW()
            WHERE id = $1""",
        link_id,
    )
    return token


async def verify_unlock(conn, link_id, unlock_token: Optional[str]) -> bool:
    """True when the header token matches a live unlock row for this link.
    Passcode rotations never touch unlock rows (decided grace rule)."""
    if not unlock_token:
        return False
    row = await conn.fetchrow(
        """UPDATE symlink_unlocks SET last_seen_at = NOW()
            WHERE symlink_id = $1 AND unlock_token_hash = $2 AND revoked_at IS NULL
        RETURNING id""",
        link_id, hash_unlock_token(unlock_token),
    )
    return row is not None


async def save_turn(conn, link_id, *, transcript: list[dict], known_fields: dict, turn_count: int):
    await conn.execute(
        """UPDATE symlinks
              SET transcript = $2::jsonb, known_fields = $3::jsonb, turn_count = $4, updated_at = NOW()
            WHERE id = $1""",
        link_id, json.dumps(transcript), json.dumps(known_fields), turn_count,
    )


async def log_audit(
    conn, link_id, company_id, user_id, action: str, *,
    entity_type: Optional[str] = None, entity_id: Optional[str] = None,
    details: Optional[dict] = None, ip_address: Optional[str] = None,
) -> None:
    await conn.execute(
        """INSERT INTO symlink_audit_log
               (symlink_id, company_id, user_id, action, entity_type, entity_id, details, ip_address)
           VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)""",
        link_id, company_id, user_id, action, entity_type, entity_id,
        json.dumps(details) if details else None, ip_address,
    )

