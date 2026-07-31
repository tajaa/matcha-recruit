#!/usr/bin/env python3
"""Extend the Sunset Smile Dental Group #Front Desk demo (see
seed_frontdesk_chat_demo.py) with a third day and the conversational half of
Huume: "@huume what happened with X?" recall questions, "@huume help", and a
few more LOG triggers — so the channel demos Huume as something the team
asks things, not just a stenographer.

Additive only — appends after the existing history, never touches or
re-runs day 0/1. Also backfills `avatar_url` on all five Front Desk members
(day-1 script left it null) so the channel reads like a populated
workspace, and adds Casey Nguyen as an `employee`-role member (the other
four are all `client`/business-admin) so the employee-redacted @huume
answer — no `behavioral` events, no severity/doc detail, see
services/ems/ask.py — has a real member to demo it live instead of only in
unit tests.

Runs LOG triggers through the real classify_event/persist_event seam (same
as day 1) and ASK/HELP triggers through the real
intent.classify_intent -> ask.fetch_channel_events/answer_question/help_text
path — the same fork channels_ws.py's _bg_ems_dispatch runs on a live
@huume mention. Live Gemini calls throughout.

Dev-only. Connects directly to the local dev Postgres container
(matcha-postgres:5432/matcha) — never point DATABASE_URL at this script.

Run (after seed_frontdesk_chat_demo.py has already been run once):
    cd server && ./venv/bin/python ../scripts/seed_frontdesk_chat_demo_day2.py

Undo (this script's additions only):
    DELETE FROM ems_events WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND created_at > '<run start>';
    DELETE FROM channel_messages WHERE channel_id = '3b98989c-708e-46c1-af66-235dd56b9fc6'
        AND created_at > '<run start>';
    DELETE FROM employees WHERE email = 'casey.nguyen@example.com';
    DELETE FROM users WHERE email = 'casey.nguyen@example.com';
    -- avatar_url backfill on the 4 pre-existing members is left in place;
    -- it's cosmetic and harmless to keep.
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

from app.core.services.auth import hash_password  # noqa: E402
from app.matcha.services.ems import ask as ems_ask  # noqa: E402
from app.matcha.services.ems.event_intake import (  # noqa: E402
    classify_event,
    gather_intake_context,
    persist_event,
    question_text,
)
from app.matcha.services.ems.intent import strip_mention  # noqa: E402

DATABASE_URL = "postgresql://matcha:matcha_dev@localhost:5432/matcha"

COMPANY_ID = UUID("287fffb5-ea50-40a2-bf07-6b5c2ca3c400")  # Sunset Smile Dental Group
CHANNEL_ID = UUID("3b98989c-708e-46c1-af66-235dd56b9fc6")  # Front Desk

MARIA = UUID("8e7614eb-7174-4802-8f6e-b44d065993e2")  # existing: Maria Chen (front desk)
OPS = UUID("05a86fd7-6f2c-47df-b4c4-bfc735d90025")  # existing: Ops Assistant

# DiceBear's avatar API is free, keyless, and deterministic per `seed` — the
# same name always renders the same face, so re-running this script doesn't
# reshuffle who looks like who.
AVATAR = "https://api.dicebear.com/9.x/notionists/svg?seed={seed}&backgroundColor=b6e3f4,c0aede,d1d4f9,ffd5dc,ffdfbf"

EXISTING_MEMBERS = {
    MARIA: "Maria Chen", OPS: "Ops Assistant",
}

NEW_USERS = {
    "priya": {"email": "priya.patel@example.com", "name": "Dr. Priya Patel", "job_title": "Owner / Dentist"},
    "jordan": {"email": "jordan.lee@example.com", "name": "Jordan Lee", "job_title": "Dental Hygienist"},
}

# Casey is `employee` role (not `client` like the other four) with a real
# `employees` row — the member this seed exists to add, so the
# employee-redacted @huume answer has someone real to demo, not just an
# assertion in test_ems_ask.py.
CASEY_EMAIL = "casey.nguyen@example.com"
CASEY_NAME = "Casey Nguyen"

# (hour, minute, sender_key, text, kind)
# kind in {"chat", "log", "ask", "help"}. Day anchor: the most recent day
# in CONVERSATION (day 1) + 1 — see main().
DAY2 = [
    (8, 40, "maria", "morning! anyone catch the score last night lol", "chat"),
    (8, 41, "jordan", "don't even get me started 😩", "chat"),
    (8, 55, "casey", "first day back at front desk after training, hi everyone!", "chat"),
    (8, 56, "maria", "welcome back Casey! let me know if anything looks unfamiliar", "chat"),
    (9, 0, "casey", "@huume help", "help"),
    (9, 10, "priya", "quick one before clinic opens — did we ever figure out that ceiling leak from a couple weeks back?", "chat"),
    (9, 11, "maria", "@huume what happened with the ceiling stains above reception?", "ask"),
    (9, 30, "casey", "hey does anyone know what's been going on with the autoclave, a patient asked if the tools are safe", "chat"),
    (9, 31, "casey", "@huume what's on file about the autoclave?", "ask"),
    (9, 45, "ops", "@huume the composite kit delivery came in short again, we ordered 12 and got 8, this is the second short shipment from this vendor this month", "log"),
    (10, 20, "jordan", "patient in chair 2 mentioned she felt a sharp pinch during the cleaning, nothing visible but wanted it on file just in case", "chat"),
    (10, 21, "jordan", "@huume patient in chair 2 said she felt a sharp pinch during her cleaning today, no visible injury but she wants it documented, I let her know we'd note it", "log"),
    (11, 5, "maria", "@huume front desk cash drawer was $40 short at close yesterday, second time in three weeks, not sure if it's a counting error or something else", "log"),
    (11, 40, "priya", "reminder the rep from the new imaging system is stopping by at 2 for a demo", "chat"),
    (12, 15, "casey", "@huume what happened last week that I should know about?", "ask"),
    (13, 0, "ops", "the reception chairs came back from the upholstery place, they look great", "chat"),
    (13, 30, "jordan", "@huume Dr. Patel asked me to redo a patient's x-rays and I pushed back in front of the patient because I felt the first set was fine, probably should've taken it outside", "log"),
    (14, 5, "priya", "demo went well, going to bring it to the team meeting Friday", "chat"),
    (14, 40, "maria", "@huume noticed the reception rug is fraying badly by the door, could be a trip hazard", "log"),
    (15, 10, "casey", "@huume what's logged in here today?", "ask"),
    (15, 45, "jordan", "restocked the sensitivity toothpaste samples up front", "chat"),
    (16, 0, "priya", "@huume what's on file about Jordan? want to make sure we're following up on everything", "ask"),
    (16, 20, "maria", "good first day Casey, you're a natural at the front desk already", "chat"),
    (16, 21, "casey", "thanks! this place is way more organized than my last job lol", "chat"),
]


async def ensure_user(conn, key: str) -> UUID:
    info = NEW_USERS[key]
    existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", info["email"])
    if existing:
        return existing
    user_id = await conn.fetchval(
        """
        INSERT INTO users (email, password_hash, role, is_active)
        VALUES ($1, $2, 'client', true) RETURNING id
        """,
        info["email"], hash_password("devpass123"),
    )
    await conn.execute(
        "INSERT INTO clients (user_id, company_id, name, job_title) VALUES ($1, $2, $3, $4)",
        user_id, COMPANY_ID, info["name"], info["job_title"],
    )
    print(f"  created user {info['name']} <{info['email']}> ({user_id})")
    return user_id


async def ensure_casey(conn) -> UUID:
    """Casey is `employee` role with a real `employees` row — see the
    module docstring for why this member exists."""
    existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", CASEY_EMAIL)
    if existing:
        return existing
    user_id = await conn.fetchval(
        """
        INSERT INTO users (email, password_hash, role, is_active)
        VALUES ($1, $2, 'employee', true) RETURNING id
        """,
        CASEY_EMAIL, hash_password("devpass123"),
    )
    first, last = CASEY_NAME.split(" ", 1)
    await conn.execute(
        """
        INSERT INTO employees (org_id, user_id, email, first_name, last_name, job_title, employment_type)
        VALUES ($1, $2, $3, $4, $5, 'Front Desk Coordinator', 'full_time')
        """,
        COMPANY_ID, user_id, CASEY_EMAIL, first, last,
    )
    print(f"  created employee {CASEY_NAME} <{CASEY_EMAIL}> ({user_id})")
    return user_id


async def ensure_member(conn, channel_id: UUID, user_id: UUID) -> None:
    await conn.execute(
        """
        INSERT INTO channel_members (channel_id, user_id, role)
        VALUES ($1, $2, 'member')
        ON CONFLICT (channel_id, user_id) DO NOTHING
        """,
        channel_id, user_id,
    )


async def backfill_avatar(conn, user_id: UUID, seed: str) -> None:
    # Only fill when empty — never clobber an avatar a real dev session set.
    await conn.execute(
        "UPDATE users SET avatar_url = $2 WHERE id = $1 AND avatar_url IS NULL",
        user_id, AVATAR.format(seed=seed),
    )


async def insert_system_message(conn, channel_id: UUID, content: str):
    return await conn.fetchrow(
        """
        INSERT INTO channel_messages (channel_id, sender_id, content, message_type)
        VALUES ($1, NULL, $2, 'system')
        RETURNING id, created_at
        """,
        channel_id, content,
    )


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

    # No first-time hint here — day 1 already logged events in this channel,
    # so the real dispatch path (_ems_first_time_hint) wouldn't fire one either.
    ask_followup = classified.get("needs_clarification") and classified.get("clarify_question")
    sys_text = (
        question_text(confirmation, classified["clarify_question"])
        if ask_followup else confirmation
    )
    sys_row = await insert_system_message(conn, CHANNEL_ID, sys_text)
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
    sys_row = await insert_system_message(conn, CHANNEL_ID, answer)
    await conn.execute(
        "UPDATE channel_messages SET created_at = $1 WHERE id = $2", ts + timedelta(seconds=5), sys_row["id"],
    )
    print(f"    -> answered ({'admin' if is_admin else 'employee'} view, {len(events)} events in scope)")


async def run_help(conn, *, role: str, ts) -> None:
    is_admin = ems_ask.is_admin_role(role)
    sys_row = await insert_system_message(conn, CHANNEL_ID, ems_ask.help_text(is_admin=is_admin))
    await conn.execute(
        "UPDATE channel_messages SET created_at = $1 WHERE id = $2", ts + timedelta(seconds=5), sys_row["id"],
    )
    print(f"    -> sent help ({'admin' if is_admin else 'employee'} view)")


async def main() -> None:
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
            print("No existing #Front Desk history found — run seed_frontdesk_chat_demo.py first.")
            return

        print("Ensuring channel members + avatars...")
        senders = {"maria": MARIA, "ops": OPS}
        senders["priya"] = await ensure_user(conn, "priya")
        senders["jordan"] = await ensure_user(conn, "jordan")
        senders["casey"] = await ensure_casey(conn)
        for key, uid in senders.items():
            await ensure_member(conn, CHANNEL_ID, uid)
            name = NEW_USERS.get(key, {}).get("name") or EXISTING_MEMBERS.get(uid) or CASEY_NAME
            await backfill_avatar(conn, uid, seed=name)

        roles = {
            key: await conn.fetchval("SELECT role FROM users WHERE id = $1", uid)
            for key, uid in senders.items()
        }

        # Anchor the new day to local midnight the day AFTER the last
        # existing message, so this always reads as "the next day" no
        # matter when the day-1 script was originally run.
        day2 = (last_msg_at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        print(f"Seeding {len(DAY2)} messages on day3 starting {day2.date()}...")
        for hour, minute, sender_key, text, kind in DAY2:
            ts = day2 + timedelta(hours=hour, minutes=minute)
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
            elif kind == "help":
                await run_help(conn, role=roles[sender_key], ts=ts)

        print(f"\nDone. {len(DAY2)} chat messages added to #Front Desk (day 3).")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
