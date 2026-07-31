#!/usr/bin/env python3
"""Extend the Sunset Smile Dental Group #Front Desk demo (see
seed_frontdesk_chat_demo.py + _day2.py) with a fourth day demoing the
newest Huume surface: the LINK intent ("@huume send the reporting link"),
plus a few more LOG triggers so the casual model-written `ack` voice
(services/ems/event_intake.py's classify prompt) shows up on a fresh
variety of categories rather than just the day-1/day-2 examples.

Additive only — appends after day 3's history, never touches or re-runs
anything earlier.

Runs LOG through the real classify_event/persist_event seam, ASK/HELP
through services/ems/ask, and LINK through the real
werk.routes.channels_ws._bg_ems_link — the exact function a live @huume
mention dispatches to (see intent.LINK / that module's _bg_ems_dispatch).
Reusing it here (rather than re-deriving the report_links calls) means this
script exercises the identical company/role gating, not a re-implementation
of it. Live Gemini calls for LOG/ASK; LINK is deterministic (no Gemini).

Dev-only. Connects directly to the local dev Postgres container
(matcha-postgres:5432/matcha) — never point DATABASE_URL at this script.

Run (after seed_frontdesk_chat_demo.py and _day2.py have already been run):
    cd server && ./venv/bin/python ../scripts/seed_frontdesk_chat_demo_day3.py

Undo (this script's additions only):
    DELETE FROM ems_events WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND created_at > '<run start>';
    DELETE FROM channel_messages WHERE channel_id = '3b98989c-708e-46c1-af66-235dd56b9fc6'
        AND created_at > '<run start>';
"""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import asyncpg  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()  # event_intake._get_client() calls get_settings(), which raises unless this runs first

from app.database.pool import close_pool, init_pool  # noqa: E402
from app.matcha.services.ems import ask as ems_ask  # noqa: E402
from app.matcha.services.ems.event_intake import (  # noqa: E402
    classify_event,
    gather_intake_context,
    persist_event,
    question_text,
)
from app.matcha.services.ems.intent import strip_mention  # noqa: E402
from app.werk.routes.channels_ws import _bg_ems_link  # noqa: E402

DATABASE_URL = "postgresql://matcha:matcha_dev@localhost:5432/matcha"

COMPANY_ID = UUID("287fffb5-ea50-40a2-bf07-6b5c2ca3c400")  # Sunset Smile Dental Group
CHANNEL_ID = UUID("3b98989c-708e-46c1-af66-235dd56b9fc6")  # Front Desk

MARIA = UUID("8e7614eb-7174-4802-8f6e-b44d065993e2")  # existing: Maria Chen (front desk)
OPS = UUID("05a86fd7-6f2c-47df-b4c4-bfc735d90025")  # existing: Ops Assistant

# (hour, minute, sender_key, text, kind)
# kind in {"chat", "log", "ask", "link"}. Day anchor: the day after the
# latest existing message — see main().
DAY4 = [
    (8, 30, "priya", "morning team, a new hire is starting at the front desk next week and asked how patients report concerns confidentially", "chat"),
    (8, 31, "priya", "@huume send the reporting link, want to add it to the new-hire packet", "link"),
    (8, 45, "casey", "good question to have on hand honestly, patients ask sometimes", "chat"),
    (8, 46, "casey", "@huume can you share the reporting link too, want to bookmark it", "link"),
    (9, 20, "jordan", "@huume the nitrous tank in room 1 is reading low, we swapped in the backup but ordering a replacement", "log"),
    (10, 5, "maria", "@huume a guest called upset that we charged a $35 no-show fee she says she wasn't told about at booking, I waived it this time but flagging the policy gap", "log"),
    (10, 40, "ops", "reminder the shredding company comes tomorrow, bins are out back", "chat"),
    (11, 15, "casey", "@huume noticed the break room fridge has a weird smell, might be something forgotten in there from before I started", "log"),
    (11, 50, "priya", "@huume what's on file about the no-show fee thing? want to see if this is a pattern before we change policy", "ask"),
    (13, 0, "jordan", "@huume patient asked us to email his x-rays to a new dentist and front desk wasn't sure about the release process, walked him through it but flagging so we tighten the SOP", "log"),
    (14, 10, "maria", "slow afternoon, caught up on filing finally", "chat"),
    (14, 30, "ops", "@huume what happened with the nitrous tank earlier?", "ask"),
    (15, 45, "casey", "loving the front desk job so far, feels like a real team here", "chat"),
    (16, 0, "priya", "agreed, great week everyone", "chat"),
]


async def run_log(conn, *, sender_id: UUID, message_id: UUID, text: str, ts) -> None:
    context = await gather_intake_context(conn, CHANNEL_ID, message_id)
    classified = await classify_event(text, context)
    event_row, confirmation = await persist_event(
        conn, company_id=COMPANY_ID, channel_id=CHANNEL_ID,
        message_id=message_id, reporter_user_id=sender_id,
        content=text, classified=classified,
    )
    if event_row is None:
        print("    (dedupe hit, skipped)")
        return
    ask_followup = classified.get("needs_clarification") and classified.get("clarify_question")
    sys_text = (
        question_text(confirmation, classified["clarify_question"])
        if ask_followup else confirmation
    )
    sys_row = await conn.fetchrow(
        """
        INSERT INTO channel_messages (channel_id, sender_id, content, message_type)
        VALUES ($1, NULL, $2, 'system')
        RETURNING id, created_at
        """,
        CHANNEL_ID, sys_text,
    )
    await conn.execute(
        "UPDATE channel_messages SET created_at = $1 WHERE id = $2", ts + timedelta(seconds=5), sys_row["id"],
    )
    if ask_followup:
        await conn.execute(
            "UPDATE ems_events SET clarify_message_id = $1 WHERE id = $2", sys_row["id"], event_row["id"],
        )
    print(f"    -> logged {event_row['category']}/{event_row['severity_hint']}: {event_row['title']}")


async def run_ask(conn, *, role: str, text: str, ts) -> None:
    is_admin = ems_ask.is_admin_role(role)
    events = await ems_ask.fetch_channel_events(
        conn, company_id=COMPANY_ID, channel_id=CHANNEL_ID, include_behavioral=is_admin,
    )
    if events:
        answer = await ems_ask.answer_question(strip_mention(text), events, is_admin=is_admin)
    else:
        answer = ems_ask.no_events_text(filtered=False)
    sys_row = await conn.fetchrow(
        """
        INSERT INTO channel_messages (channel_id, sender_id, content, message_type)
        VALUES ($1, NULL, $2, 'system')
        RETURNING id
        """,
        CHANNEL_ID, answer,
    )
    await conn.execute(
        "UPDATE channel_messages SET created_at = $1 WHERE id = $2", ts + timedelta(seconds=5), sys_row["id"],
    )
    print(f"    -> answered ({'admin' if is_admin else 'employee'} view, {len(events)} events in scope)")


async def main() -> None:
    await init_pool(DATABASE_URL)  # _bg_ems_link runs its own get_connection() blocks
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        features = await conn.fetchval("SELECT enabled_features FROM companies WHERE id = $1", COMPANY_ID)
        features = json.loads(features) if isinstance(features, str) else (features or {})
        if not features.get("ems"):
            print("Company doesn't have `ems` enabled — aborting so nothing silently no-ops.")
            return

        last_msg_at = await conn.fetchval(
            "SELECT MAX(created_at) FROM channel_messages WHERE channel_id = $1", CHANNEL_ID,
        )
        if last_msg_at is None:
            print("No existing #Front Desk history found — run the day 1/2 seed scripts first.")
            return

        senders = {
            "maria": MARIA, "ops": OPS,
            "priya": await conn.fetchval("SELECT id FROM users WHERE email = 'priya.patel@example.com'"),
            "jordan": await conn.fetchval("SELECT id FROM users WHERE email = 'jordan.lee@example.com'"),
            "casey": await conn.fetchval("SELECT id FROM users WHERE email = 'casey.nguyen@example.com'"),
        }
        if not all(senders.values()):
            print("Front Desk day-2 members not found — run seed_frontdesk_chat_demo_day2.py first.")
            return
        roles = {key: await conn.fetchval("SELECT role FROM users WHERE id = $1", uid) for key, uid in senders.items()}

        day4 = (last_msg_at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        # See seed_frontdesk_chat_demo_day2.py's matching comment — a
        # future-dated row outranks every live message in GET /channels/{id}
        # (ORDER BY created_at DESC LIMIT 50), silently dropping anything
        # typed live in the channel on the next refetch. Clamp the NEW
        # anchor into the past instead of rewinding existing rows — this
        # script is additive-only, and a blanket
        # `created_at = created_at - shift` over the whole channel silently
        # back-dates every prior message (seeded AND live) and breaks every
        # earlier script's documented `created_at > '<run start>'` undo.
        yesterday = (await conn.fetchval("SELECT NOW()")).replace(
            hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        if day4 > yesterday:
            day4 = yesterday
        if day4 <= last_msg_at:
            print(
                "Existing #Front Desk history is already at or past yesterday — "
                "no safe past slot left for a new day without overlapping it. "
                "Aborting without changing anything."
            )
            return

        print(f"Seeding {len(DAY4)} messages on day4 starting {day4.date()}...")

        for hour, minute, sender_key, text, kind in DAY4:
            ts = day4 + timedelta(hours=hour, minutes=minute)
            sender_id = senders[sender_key]
            row = await conn.fetchrow(
                """
                INSERT INTO channel_messages (channel_id, sender_id, content, message_type, created_at)
                VALUES ($1, $2, $3, 'user', $4)
                RETURNING id
                """,
                CHANNEL_ID, sender_id, text, ts,
            )
            message_id = row["id"]

            if kind == "chat":
                continue

            print(f"  [{kind}] {sender_key}: {text[:70]}...")
            if kind == "log":
                await run_log(conn, sender_id=sender_id, message_id=message_id, text=text, ts=ts)
            elif kind == "ask":
                await run_ask(conn, role=roles[sender_key], text=text, ts=ts)
            elif kind == "link":
                # _bg_ems_link opens its own connections via get_connection()
                # (init_pool above) — it never touches this script's `conn`,
                # and it inserts its reply with a real-`now()` created_at
                # (there's no ts param on the real dispatch path). Backdate
                # it to this narrative slot afterward, same as the other
                # kinds, or it sorts into "today" instead of "day 4" in the
                # actual channel UI.
                #
                # Snapshot the DB's own real `now()` — NOT MAX(created_at) —
                # as the "before" marker: every earlier seed script anchors
                # its fake history to a day AFTER whatever "today" was when
                # it ran, so the existing max is already in the future
                # relative to the real timestamp _bg_ems_link is about to
                # insert. Comparing against that future max would match zero
                # rows and silently leave the reply un-backdated (as it did
                # on the first run of this script).
                before = await conn.fetchval("SELECT NOW()")
                await _bg_ems_link(str(CHANNEL_ID), str(sender_id))
                await conn.execute(
                    """
                    UPDATE channel_messages SET created_at = $1
                    WHERE channel_id = $2 AND message_type = 'system' AND created_at >= $3
                    """,
                    ts + timedelta(seconds=5), CHANNEL_ID, before,
                )
                print("    -> sent link reply")

        print(f"\nDone. {len(DAY4)} chat messages added to #Front Desk (day 4).")
    finally:
        await conn.close()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
