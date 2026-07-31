#!/usr/bin/env python3
"""Seed the Sunset Smile Dental Group #Front Desk channel with realistic
two-day chat history — ordinary front-desk chatter interspersed with six
"@huume ..." triggers, one per EMS category (behavioral/safety/operational/
equipment/property/guest_experience). Each trigger runs through the REAL
classify pipeline (services/ems/event_intake.create_event_from_message —
same seam channels_ws.py's _bg_ems_intake uses, just off the WS hot path),
so it makes a live Gemini call and writes a real ems_events row + a
message_type='system' confirmation, exactly like a live @huume mention
would.

Dev-only. Connects directly to the local dev Postgres container
(matcha-postgres:5432/matcha) — never point DATABASE_URL at this script.

Adds two more channel members for sender variety (the channel only had 2):
Dr. Priya Patel (owner) and Jordan Lee (hygienist), both @example.com,
password devpass123 — matching the anonymized-dev-refresh convention.

Run:
    cd server && ./venv/bin/python ../scripts/seed_frontdesk_chat_demo.py

Idempotent-ish: re-running inserts a second copy of the chat (channel_messages
has no natural key to dedupe on) — undo by deleting messages/events tagged
below.

Undo:
    DELETE FROM ems_events WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND created_at > '<run start>';
    DELETE FROM channel_messages WHERE channel_id = '3b98989c-708e-46c1-af66-235dd56b9fc6'
        AND created_at > '<run start>';
    DELETE FROM users WHERE email IN ('priya.patel@example.com', 'jordan.lee@example.com');
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
from app.matcha.services.ems.event_intake import (  # noqa: E402
    classify_event,
    gather_intake_context,
    persist_event,
    question_text,
)

DATABASE_URL = "postgresql://matcha:matcha_dev@localhost:5432/matcha"

COMPANY_ID = UUID("287fffb5-ea50-40a2-bf07-6b5c2ca3c400")  # Sunset Smile Dental Group
CHANNEL_ID = UUID("3b98989c-708e-46c1-af66-235dd56b9fc6")  # Front Desk

MARIA = UUID("8e7614eb-7174-4802-8f6e-b44d065993e2")  # existing: Maria Chen (front desk)
OPS = UUID("05a86fd7-6f2c-47df-b4c4-bfc735d90025")  # existing: Ops Assistant

NEW_USERS = {
    "priya": {"email": "priya.patel@example.com", "name": "Dr. Priya Patel", "job_title": "Owner / Dentist"},
    "jordan": {"email": "jordan.lee@example.com", "name": "Jordan Lee", "job_title": "Dental Hygienist"},
}

# (day, hour, minute, sender_key, text, is_huume_trigger)
# sender_key in {"maria", "ops", "priya", "jordan"}; day 0 = Monday, day 1 = Tuesday.
CONVERSATION = [
    (0, 8, 45, "maria", "morning everyone ☀️ AC feels a little warm in here, anyone else notice?", False),
    (0, 8, 47, "jordan", "yeah it's been off since yesterday, I think ops turned it down for the weekend", False),
    (0, 8, 50, "ops", "my bad, bumping it back up now", False),
    (0, 9, 15, "maria", "8am pt Sanders is running late, pushing Dr. Patel's first slot by 15", False),
    (0, 9, 16, "priya", "no worries, I'll use the time to prep for the crown seat at 9:30", False),
    (0, 9, 40, "maria", "@huume Jordan raised her voice at me in front of a patient this morning when the schedule got mixed up, the patient looked uncomfortable. This is the second time this month.", True),
    (0, 10, 5, "jordan", "sorry about that, wasn't my best moment. I'll be more careful, especially with patients around", False),
    (0, 10, 7, "maria", "all good, let's just keep patients out of it going forward", False),
    (0, 10, 30, "ops", "sterilization room 2 autoclave is beeping an error code again", False),
    (0, 10, 32, "priya", "is it the same E4 code as last time?", False),
    (0, 10, 33, "ops", "yep", False),
    (0, 10, 34, "ops", "@huume autoclave in sterilization room 2 is throwing an E4 error code again, third time this month, we had to reschedule the 10:45 cleaning appt", True),
    (0, 11, 0, "maria", "lunch order for the team - usual sandwich place?", False),
    (0, 11, 2, "jordan", "yes please, turkey club", False),
    (0, 11, 3, "priya", "same as always for me thanks", False),
    (0, 12, 15, "maria", "just restocked the composite kits, we were almost out", False),
    (0, 12, 40, "ops", "@huume patient in the waiting room slipped near the front entrance where the wet floor mats were bunched up, no injury but she grabbed the counter to catch herself", True),
    (0, 13, 10, "maria", "front desk printer jammed again mid fax, I think the roller needs replacing", False),
    (0, 13, 15, "ops", "adding it to the supply order", False),
    (0, 14, 0, "priya", "reminder team meeting is moved to 4:30 today not 4", False),
    (0, 14, 5, "maria", "got it", False),
    (0, 15, 20, "jordan", "does anyone know the wifi password for the guest network? patient asked", False),
    (0, 15, 22, "maria", "it's on the sticky note by the register, I'll relabel it properly", False),
    (0, 16, 0, "ops", "@huume noticed water stains spreading across the ceiling tile above the reception desk again, looks like the upstairs unit's AC condensate line might be leaking", True),
    (0, 16, 30, "priya", "great first day back for Jordan on the new patient scripts, went smoothly", False),
    (0, 16, 31, "jordan", "thanks! still getting the insurance verification flow down but feeling more confident", False),
    (0, 17, 5, "maria", "closing up, locking the supply closet, see everyone tomorrow", False),
    (1, 8, 50, "maria", "morning! quick heads up the online booking system double booked two patients at 9am", False),
    (1, 8, 52, "ops", "ugh, I'll call the one further out and reschedule", False),
    (1, 9, 5, "maria", "@huume the new online scheduling widget double-booked two patients into the same 9am slot again, this is the third double-book this week, might be a timezone bug in the widget settings", True),
    (1, 9, 30, "priya", "morning huddle - reminder that we're piloting the new whitening kit inventory this week", False),
    (1, 9, 32, "jordan", "on it, I'll track usage on the sheet", False),
    (1, 10, 15, "maria", "a patient just called asking if we do Saturday hours, said their old dentist did", False),
    (1, 10, 16, "priya", "not yet but worth revisiting for Q3", False),
    (1, 11, 0, "jordan", "@huume patient in chair 3 got upset when we told her the whitening treatment wasn't covered by insurance, she raised her voice and said she'd leave a bad review, front desk offered a payment plan and she calmed down some but left frustrated", True),
    (1, 11, 45, "maria", "does anyone have the UPS tracking number for the impression material order?", False),
    (1, 12, 0, "ops", "checking my email now", False),
    (1, 12, 30, "priya", "great case today, the crown fit was perfect first try", False),
    (1, 13, 0, "maria", "reminder we're closing 30 min early Friday for the team lunch", False),
    (1, 13, 45, "jordan", "restocked the kids' toy box in the waiting room, ran low on stickers", False),
    (1, 14, 20, "ops", "the shred bin is full again, did we skip a pickup?", False),
    (1, 14, 22, "maria", "checking the schedule, I think it's every other Tuesday, should've been yesterday", False),
    (1, 15, 0, "priya", "nice work everyone this week, patient satisfaction survey scores came back strong", False),
    (1, 15, 30, "maria", "on that note, anyone want to grab the survey feedback and post the highlights in here later", False),
    (1, 16, 0, "jordan", "will do after my last patient", False),
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
        """
        INSERT INTO clients (user_id, company_id, name, job_title)
        VALUES ($1, $2, $3, $4)
        """,
        user_id, COMPANY_ID, info["name"], info["job_title"],
    )
    print(f"  created user {info['name']} <{info['email']}> ({user_id})")
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


async def insert_system_message(conn, channel_id: UUID, content: str):
    return await conn.fetchrow(
        """
        INSERT INTO channel_messages (channel_id, sender_id, content, message_type)
        VALUES ($1, NULL, $2, 'system')
        RETURNING id, created_at
        """,
        channel_id, content,
    )


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        features = await conn.fetchval("SELECT enabled_features FROM companies WHERE id = $1", COMPANY_ID)
        features = json.loads(features) if isinstance(features, str) else (features or {})
        if not features.get("ems"):
            print("Company doesn't have `ems` enabled — aborting so nothing silently no-ops.")
            return

        print("Ensuring channel members...")
        senders = {"maria": MARIA, "ops": OPS}
        senders["priya"] = await ensure_user(conn, "priya")
        senders["jordan"] = await ensure_user(conn, "jordan")
        for uid in senders.values():
            await ensure_member(conn, CHANNEL_ID, uid)

        base = (await conn.fetchval("SELECT now()")).replace(hour=0, minute=0, second=0, microsecond=0)
        # Anchor day 0 to the most recent Monday-shaped weekday two days back
        # from "now" so the seeded history reads as recent, never future.
        day0 = base - timedelta(days=2)

        print(f"Seeding {len(CONVERSATION)} messages across 2 days starting {day0.date()}...")
        trigger_count = 0
        for day, hour, minute, sender_key, text, is_trigger in CONVERSATION:
            ts = day0 + timedelta(days=day, hours=hour, minutes=minute)
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

            if not is_trigger:
                continue

            trigger_count += 1
            print(f"  [{trigger_count}/6] classifying: {text[:70]}...")
            context = await gather_intake_context(conn, CHANNEL_ID, message_id)
            classified = await classify_event(text, context)
            event_row, confirmation = await persist_event(
                conn, company_id=COMPANY_ID, channel_id=CHANNEL_ID,
                message_id=message_id, reporter_user_id=sender_id,
                content=text, classified=classified,
            )
            if event_row is None:
                print("    (dedupe hit, skipped)")
                continue

            ask = classified.get("needs_clarification") and classified.get("clarify_question")
            sys_text = question_text(confirmation, classified["clarify_question"]) if ask else confirmation
            sys_row = await insert_system_message(conn, CHANNEL_ID, sys_text)
            await conn.execute(
                "UPDATE channel_messages SET created_at = $1 WHERE id = $2",
                ts + timedelta(seconds=5), sys_row["id"],
            )
            if ask:
                await conn.execute(
                    "UPDATE ems_events SET clarify_message_id = $1 WHERE id = $2",
                    sys_row["id"], event_row["id"],
                )
            print(f"    -> {event_row['category']}/{event_row['severity_hint']}: {event_row['title']}")

        print(f"\nDone. {len(CONVERSATION)} chat messages, {trigger_count} EMS events logged in #Front Desk.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
