"""Sym-link Celery tasks: weekly passcode rotation + the open-link sweep.

Both run on every worker restart (the hourly systemd timer) and are gated by
their `scheduler_settings` row (seeded disabled by migration symlink01).
Pool-free: each task opens its own asyncpg connection via `get_db_connection`.

  symlink_passcode_rotation
      Set-based: every `symlink_passcodes` row whose `next_rotation_at` has
      passed (and whose company has the flag on) gets a fresh code and a
      next_rotation_at a week out; then the new code is announced in the
      company's chosen channel when it has one AND `matcha_ops`. Unlock rows
      are never touched — an unlocked recipient keeps working.

  symlink_sweep
      (a) open links past `expires_at` → status 'expired' + unlock rows revoked;
      (b) one-shot reminder email to recipients of links still open 3 days
          after the latest send (a resend resets the clock and clears
          `reminder_sent_at`), claimed atomically on `reminder_sent_at`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from app.matcha.services._shared.public_links import public_link_from_settings
from app.matcha.services.symlink import passcode as pc
from app.matcha.services.symlink.links import LINK_COLS

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

REMINDER_AFTER = timedelta(days=3)
DEFAULT_MAX_PER_CYCLE = 200


def _features(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw or {}


# ── rotation ───────────────────────────────────────────────────────────────


async def _run_symlink_passcode_rotation() -> dict:
    from app.matcha.services.symlink.notify import announce_rotation

    conn = await get_db_connection()
    try:
        row = await scheduler_settings_row(conn, "symlink_passcode_rotation")
        if not row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not row["enabled"]:
            return {"skipped": True, "reason": "scheduler_disabled"}
        limit = int(row["max_per_cycle"] or 500)

        now = datetime.now(timezone.utc)
        due = await conn.fetch(
            """
            SELECT p.company_id, p.rotation_weekday, p.announce_channel_id, c.enabled_features
              FROM symlink_passcodes p
              JOIN companies c ON c.id = p.company_id
             WHERE p.next_rotation_at <= $1
               AND COALESCE((c.enabled_features->>'symlink')::boolean, false) = true
             ORDER BY p.next_rotation_at ASC
             LIMIT $2
            """,
            now, limit,
        )
        rotated = 0
        announced = 0
        for r in due:
            new_code = pc.generate_code()
            weekday = int(r["rotation_weekday"] if r["rotation_weekday"] is not None else pc.DEFAULT_ROTATION_WEEKDAY)
            updated = await conn.fetchrow(
                """UPDATE symlink_passcodes
                      SET code = $2, rotated_at = $3, next_rotation_at = $4, updated_at = NOW()
                    WHERE company_id = $1 AND next_rotation_at <= $3
                RETURNING company_id""",
                r["company_id"], new_code, now, pc.next_rotation(now, weekday),
            )
            if not updated:
                continue  # rotated concurrently (manual "Rotate now")
            rotated += 1
            if r["announce_channel_id"] and _features(r["enabled_features"]).get("matcha_ops"):
                try:
                    if await announce_rotation(
                        conn, company_id=r["company_id"], channel_id=r["announce_channel_id"], code=new_code,
                    ):
                        announced += 1
                except Exception:
                    logger.exception("[symlink] rotation announcement failed for %s", r["company_id"])
        return {"due": len(due), "rotated": rotated, "announced": announced}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_symlink_passcode_rotation(self) -> dict:
    """Rotate every due company passcode (+ announce in its Ops channel)."""
    print("[Sym-link] Running passcode rotation...")
    try:
        result = asyncio.run(_run_symlink_passcode_rotation())
        print(f"[Sym-link] Rotation completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        logger.exception("[Sym-link] Passcode rotation failed")
        raise self.retry(exc=exc, countdown=60)


# ── sweep ──────────────────────────────────────────────────────────────────


async def _expire_open_links(conn, now: datetime) -> int:
    expired = await conn.fetch(
        """UPDATE symlinks SET status = 'expired', updated_at = NOW()
            WHERE status IN ('pending', 'in_progress') AND expires_at <= $1
        RETURNING id""",
        now,
    )
    if expired:
        await conn.execute(
            """UPDATE symlink_unlocks SET revoked_at = NOW()
                WHERE revoked_at IS NULL AND symlink_id = ANY($1::uuid[])""",
            [r["id"] for r in expired],
        )
    return len(expired)


async def _send_reminders(conn, now: datetime, limit: int) -> dict:
    from app.core.services.email import get_email_service

    candidates = await conn.fetch(
        f"""
        SELECT {", ".join("s." + c.strip() for c in LINK_COLS.split(","))},
               c.name AS company_name, c.enabled_features
          FROM symlinks s
          JOIN companies c ON c.id = s.company_id
         WHERE s.status IN ('pending', 'in_progress')
           AND s.reminder_sent_at IS NULL
           AND s.sent_at IS NOT NULL
           AND COALESCE(s.last_sent_at, s.sent_at) <= $1
           AND s.expires_at > $2
           AND COALESCE((c.enabled_features->>'symlink')::boolean, false) = true
         ORDER BY COALESCE(s.last_sent_at, s.sent_at) ASC
         LIMIT $3
        """,
        now - REMINDER_AFTER, now, limit,
    )
    sent = 0
    skipped = 0
    email = get_email_service()
    for row in candidates:
        # Atomic slot claim — a concurrent worker restart can't double-send.
        claimed = await conn.fetchval(
            "UPDATE symlinks SET reminder_sent_at = NOW() WHERE id = $1 AND reminder_sent_at IS NULL RETURNING id",
            row["id"],
        )
        if not claimed:
            continue
        sender = await conn.fetchrow(
            "SELECT c.name FROM clients c WHERE c.user_id = $1", row["created_by"],
        ) if row["created_by"] else None
        requested_by = (sender["name"] if sender and sender["name"] else None) or "Your team"
        expires_text = "on " + row["expires_at"].strftime("%B %d, %Y") if row["expires_at"] else None
        try:
            ok = await email.send_symlink_invite_email(
                to_email=row["recipient_email"], to_name=row["recipient_name"],
                company_name=row["company_name"] or "Your company", requested_by_name=requested_by,
                title=row["title"], instructions=row["instructions"],
                link=public_link_from_settings(row["token"], "sym"), expires_text=expires_text, reminder=True,
            )
        except Exception:
            logger.exception("[symlink] reminder send failed for %s", row["id"])
            ok = False
        if ok:
            sent += 1
        else:
            # Release the slot so a transient mailer failure retries next cycle.
            await conn.execute("UPDATE symlinks SET reminder_sent_at = NULL WHERE id = $1", row["id"])
            skipped += 1
    return {"candidates": len(candidates), "sent": sent, "skipped": skipped}


async def _run_symlink_sweep() -> dict:
    conn = await get_db_connection()
    try:
        row = await scheduler_settings_row(conn, "symlink_sweep")
        if not row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not row["enabled"]:
            return {"skipped": True, "reason": "scheduler_disabled"}
        limit = int(row["max_per_cycle"] or DEFAULT_MAX_PER_CYCLE)
        now = datetime.now(timezone.utc)
        expired = await _expire_open_links(conn, now)
        reminders = await _send_reminders(conn, now, limit)
        return {"expired": expired, **reminders}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_symlink_sweep(self) -> dict:
    """Expire stale links and send the one-shot reminder."""
    print("[Sym-link] Running sweep...")
    try:
        result = asyncio.run(_run_symlink_sweep())
        print(f"[Sym-link] Sweep completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        logger.exception("[Sym-link] Sweep failed")
        raise self.retry(exc=exc, countdown=60)
