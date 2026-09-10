"""Company-wide weekly sym-link passcode.

The passcode is a low-entropy shared secret that proves "insider" status on
top of the per-task link token (the real credential). It rotates weekly; the
grace rule decided with the product owner is:

  * verification accepts the CURRENT code only;
  * an already-unlocked session (symlink_unlocks row) is untouched by a
    rotation — the recipient keeps working;
  * coming back after a rotation means entering the NEW code.

Pure helpers (generate / normalize / verify / rotation math) are DB-free so
they unit-test without a database; the `ensure_passcode` / `rotate_passcode`
coroutines take an asyncpg connection.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# No 0/O/1/I — the code is read aloud and typed from a wall poster.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
ROTATION_HOUR_UTC = 6
DEFAULT_ROTATION_WEEKDAY = 0  # Monday (datetime.weekday convention)


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def format_code(code: str) -> str:
    """Display form: ``ABC-234``. Storage stays unformatted."""
    code = normalize(code)
    if len(code) == 6:
        return f"{code[:3]}-{code[3:]}"
    return code


def normalize(entered: str | None) -> str:
    """Case-, whitespace- and dash-insensitive: ``' abc-234 '`` → ``'ABC234'``."""
    if not entered:
        return ""
    return "".join(ch for ch in entered.upper() if ch.isalnum())


def verify(entered: str | None, stored: str | None) -> bool:
    """Constant-time compare of a normalized entry against the stored code."""
    if not stored:
        return False
    candidate = normalize(entered)
    expected = normalize(stored)
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate.encode(), expected.encode())


def next_rotation(now: datetime, weekday: int = DEFAULT_ROTATION_WEEKDAY) -> datetime:
    """The next ``weekday`` at ROTATION_HOUR_UTC strictly after ``now``."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    weekday = weekday % 7
    days_ahead = (weekday - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=ROTATION_HOUR_UTC, minute=0, second=0, microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def due_for_rotation(next_rotation_at: datetime | None, now: datetime) -> bool:
    if next_rotation_at is None:
        return True
    if next_rotation_at.tzinfo is None:
        next_rotation_at = next_rotation_at.replace(tzinfo=timezone.utc)
    return next_rotation_at <= now


# ── DB ─────────────────────────────────────────────────────────────────────

_COLS = "id, company_id, code, rotated_at, next_rotation_at, rotation_weekday, announce_channel_id"


async def fetch_passcode(conn, company_id) -> Optional[Any]:
    return await conn.fetchrow(
        f"SELECT {_COLS} FROM symlink_passcodes WHERE company_id = $1", company_id,
    )


async def ensure_passcode(conn, company_id):
    """The company's passcode row, creating it on first use.

    Racing creators are resolved by the UNIQUE(company_id) + ON CONFLICT: the
    loser reads the winner's row.
    """
    row = await fetch_passcode(conn, company_id)
    if row:
        return row
    now = datetime.now(timezone.utc)
    await conn.execute(
        """
        INSERT INTO symlink_passcodes (company_id, code, rotated_at, next_rotation_at, rotation_weekday)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (company_id) DO NOTHING
        """,
        company_id, generate_code(), now, next_rotation(now), DEFAULT_ROTATION_WEEKDAY,
    )
    return await fetch_passcode(conn, company_id)


async def rotate_passcode(conn, company_id, *, now: datetime | None = None):
    """Issue a fresh code now and push next_rotation_at a week out.

    Returns the updated row. Unlock rows are deliberately untouched.
    """
    now = now or datetime.now(timezone.utc)
    row = await ensure_passcode(conn, company_id)
    weekday = int(row["rotation_weekday"] if row and row["rotation_weekday"] is not None else DEFAULT_ROTATION_WEEKDAY)
    return await conn.fetchrow(
        f"""
        UPDATE symlink_passcodes
           SET code = $2, rotated_at = $3, next_rotation_at = $4, updated_at = NOW()
         WHERE company_id = $1
        RETURNING {_COLS}
        """,
        company_id, generate_code(), now, next_rotation(now, weekday),
    )
