"""Sym-chat persistence + the turn orchestration.

`run_turn` is the one write path that involves the model, and it never holds a
pooled connection across the model call:

  1. short read/insert: load the chat, my membership, my transcript and the
     known options; store my message; release the connection.
  2. `extract.next_turn` — one Luna call (up to 30 s, never raises).
  3. one transaction: `SELECT … FOR UPDATE` the chat row, store my new stance,
     recompute the shape from every participant's stance, append my
     per-person feed line (when my stance changed) and the group line (when
     `narrate.describe_change` says the change is material), flip to
     `resolved` on consensus, store the assistant reply, then post the
     coordinator's message into every tunnel that needs one: "could you make
     the candidate work?" to anyone it doesn't fit yet, or "it's confirmed"
     to everyone on consensus. Nobody coordinates with anybody else.
  4. after commit: invites (only when THIS turn resolved — the row lock plus
     the `status='open'` check make that happen exactly once) and a
     `sym_chat.updated` WS nudge to every participant.

Errors a route should surface are raised as `SymChatError(status, detail)`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.database import decode_jsonb, get_connection
from app.matcha.services import notification_service

from . import aggregate, extract, narrate
from .kinds import KINDS, materialize_config

logger = logging.getLogger(__name__)

MAX_PARTICIPANTS = 20
MAX_TURNS_PER_PARTICIPANT = 40
LIST_LIMIT = 100
UPDATE_EVENT = "sym_chat.updated"


class SymChatError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def chat_link(chat_id: UUID | str) -> str:
    return f"/work/sym-chat/{chat_id}"


_NAME_SQL = "COALESCE(NULLIF(TRIM(c.name), ''), u.email)"


# ── reads ──────────────────────────────────────────────────────────────────


async def search_people(company_id: UUID, user_id: UUID, q: str | None, limit: int = 20) -> list[dict]:
    """Active client users in the same company, excluding the caller."""
    term = (q or "").strip()
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT u.id, u.email, {_NAME_SQL} AS name
              FROM clients c
              JOIN users u ON u.id = c.user_id
             WHERE c.company_id = $1
               AND u.id <> $2
               AND u.is_active IS NOT FALSE
               AND ($3 = '' OR c.name ILIKE $4 ESCAPE '\\' OR u.email ILIKE $4 ESCAPE '\\')
             ORDER BY name
             LIMIT $5
            """,
            company_id, user_id, term, pattern, limit,
        )
    return [{"id": str(r["id"]), "name": r["name"], "email": r["email"]} for r in rows]


async def list_for_user(company_id: UUID, user_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.kind, s.title, s.status, s.shape, s.resolution, s.created_by,
                   s.created_at, s.updated_at, s.resolved_at,
                   (SELECT COUNT(*) FROM mw_sym_chat_participants p2 WHERE p2.sym_chat_id = s.id) AS participant_count,
                   (me.responded_at IS NOT NULL) AS i_responded
              FROM mw_sym_chats s
              JOIN mw_sym_chat_participants me ON me.sym_chat_id = s.id AND me.user_id = $2
             WHERE s.company_id = $1
             ORDER BY s.created_at DESC
             LIMIT $3
            """,
            company_id, user_id, LIST_LIMIT,
        )
    out = []
    for r in rows:
        shape = decode_jsonb(r["shape"], {}) or {}
        out.append({
            "id": str(r["id"]),
            "kind": r["kind"],
            "title": r["title"],
            "status": r["status"],
            "summary": narrate.describe_shape(r["kind"], shape) if shape else None,
            "resolution": decode_jsonb(r["resolution"]),
            "is_organizer": r["created_by"] == user_id,
            "participant_count": int(r["participant_count"] or 0),
            "responded_count": int(shape.get("responded") or 0),
            "i_responded": bool(r["i_responded"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        })
    return out


async def get_detail(chat_id: UUID, company_id: UUID, user_id: UUID) -> dict:
    """The chat as `user_id` sees it: shared shape + feed + participant roll
    call, and ONLY their own tunnel. Other people's stances and transcripts are
    never returned."""
    async with get_connection() as conn:
        chat = await conn.fetchrow(
            """
            SELECT s.*, (SELECT 1 FROM mw_sym_chat_participants p
                          WHERE p.sym_chat_id = s.id AND p.user_id = $3) AS is_member
              FROM mw_sym_chats s
             WHERE s.id = $1 AND s.company_id = $2
            """,
            chat_id, company_id, user_id,
        )
        if not chat or not chat["is_member"]:
            raise SymChatError(404, "Sym-chat not found")
        participants = await conn.fetch(
            f"""
            SELECT p.user_id, p.responded_at, p.stance, {_NAME_SQL} AS name
              FROM mw_sym_chat_participants p
              JOIN users u ON u.id = p.user_id
              LEFT JOIN clients c ON c.user_id = p.user_id
             WHERE p.sym_chat_id = $1
             ORDER BY p.created_at, p.id
            """,
            chat_id,
        )
        updates = await conn.fetch(
            "SELECT seq, content, created_at FROM mw_sym_chat_updates WHERE sym_chat_id = $1 ORDER BY seq",
            chat_id,
        )
        messages = await conn.fetch(
            """
            SELECT id, role, content, created_at FROM mw_sym_chat_messages
             WHERE sym_chat_id = $1 AND user_id = $2
             ORDER BY created_at, id
            """,
            chat_id, user_id,
        )

    my_stance = None
    roll = []
    for p in participants:
        if p["user_id"] == user_id:
            my_stance = decode_jsonb(p["stance"])
        roll.append({
            "user_id": str(p["user_id"]),
            "name": p["name"],
            "responded": p["responded_at"] is not None,
            "is_organizer": p["user_id"] == chat["created_by"],
            "is_me": p["user_id"] == user_id,
        })
    return {
        "id": str(chat["id"]),
        "kind": chat["kind"],
        "title": chat["title"],
        "objective": chat["objective"],
        "config": decode_jsonb(chat["config"], {}) or {},
        "status": chat["status"],
        "shape": decode_jsonb(chat["shape"], {}) or {},
        "resolution": decode_jsonb(chat["resolution"]),
        "resolved_at": chat["resolved_at"].isoformat() if chat["resolved_at"] else None,
        "is_organizer": chat["created_by"] == user_id,
        "created_at": chat["created_at"].isoformat() if chat["created_at"] else None,
        "participants": roll,
        "updates": [
            {"seq": u["seq"], "content": u["content"],
             "created_at": u["created_at"].isoformat() if u["created_at"] else None}
            for u in updates
        ],
        "messages": [
            {"id": str(m["id"]), "role": m["role"], "content": m["content"],
             "created_at": m["created_at"].isoformat() if m["created_at"] else None}
            for m in messages
        ],
        "my_stance": my_stance,
    }


# ── writes ─────────────────────────────────────────────────────────────────


async def _insert_update(conn, chat_id: UUID, content: str, shape: dict) -> int:
    seq = await conn.fetchval(
        "SELECT COALESCE(MAX(seq), 0) + 1 FROM mw_sym_chat_updates WHERE sym_chat_id = $1",
        chat_id,
    )
    await conn.execute(
        "INSERT INTO mw_sym_chat_updates (sym_chat_id, seq, content, shape) VALUES ($1, $2, $3, $4::jsonb)",
        chat_id, seq, content, json.dumps(shape),
    )
    return seq


async def _insert_assistant(conn, chat_id: UUID, user_id: UUID, content: str) -> None:
    # clock_timestamp(), not the NOW() default: NOW() is the TRANSACTION start,
    # so a reply and the coordinator message written after it in the same
    # transaction would tie and the tunnel would order them by random uuid.
    await conn.execute(
        """
        INSERT INTO mw_sym_chat_messages (sym_chat_id, user_id, role, content, created_at)
        VALUES ($1, $2, 'assistant', $3, clock_timestamp())
        """,
        chat_id, user_id, content,
    )


def coordinator_messages(kind: str, shape: dict, resolution: dict | None,
                         stances: dict, last_assistant: dict) -> dict:
    """user_id → the coordinator message their tunnel should get now.

    On consensus everyone hears it's confirmed. Otherwise anyone the current
    candidate doesn't fit yet is asked about it (responders: "could you make
    it?"; silent people: "does it work?"). Someone whose last assistant
    message already asked about this same candidate is skipped — only a new
    candidate re-asks, not a headcount tick."""
    out: dict = {}
    candidate = narrate.candidate_text(kind, shape)
    for user_id, stance in stances.items():
        last = last_assistant.get(user_id) or ""
        if resolution:
            text = narrate.confirmed_text(resolution)
            if last == text:
                continue
        elif aggregate.fits_candidate(kind, stance, shape):
            continue
        else:
            text = narrate.nudge_text(kind, shape, responded=extract.stance_has_content(kind, stance))
            if narrate.is_nudge_about(last, candidate):
                continue
        if text:
            out[user_id] = text
    return out


async def create_sym_chat(
    *,
    company_id: UUID,
    user_id: UUID,
    kind: str,
    title: str,
    objective: str,
    participant_ids: list[UUID],
    raw_config: dict | None,
) -> dict:
    if kind not in KINDS:
        raise SymChatError(400, f"Unknown sym-chat kind: {kind}")
    try:
        config = materialize_config(kind, raw_config)
    except ValueError as exc:
        raise SymChatError(400, str(exc))
    title = " ".join((title or "").split())[:120]
    if not title:
        raise SymChatError(400, "title is required")

    others = list(dict.fromkeys(pid for pid in participant_ids if pid != user_id))
    if not others:
        raise SymChatError(400, "Add at least one other person")
    if len(others) + 1 > MAX_PARTICIPANTS:
        raise SymChatError(400, f"At most {MAX_PARTICIPANTS} people per sym-chat")

    async with get_connection() as conn:
        valid = await conn.fetch(
            """
            SELECT u.id FROM clients c JOIN users u ON u.id = c.user_id
             WHERE c.company_id = $1 AND u.id = ANY($2::uuid[]) AND u.is_active IS NOT FALSE
            """,
            company_id, others,
        )
        if {r["id"] for r in valid} != set(others):
            raise SymChatError(400, "Everyone must be an active member of your company")
        organizer_name = await conn.fetchval(
            f"SELECT {_NAME_SQL} FROM users u LEFT JOIN clients c ON c.user_id = u.id WHERE u.id = $1",
            user_id,
        )
        members = [user_id, *others]
        shape = aggregate.compute_shape(kind, config, [{"stance": None} for _ in members])
        async with conn.transaction():
            chat_id = await conn.fetchval(
                """
                INSERT INTO mw_sym_chats (company_id, created_by, kind, title, objective, config, shape)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)
                RETURNING id
                """,
                company_id, user_id, kind, title, (objective or "").strip()[:500],
                json.dumps(config), json.dumps(shape),
            )
            # Insert one by one, organizer first: created_at ties are broken by
            # this order in every "join order" read.
            for member in members:
                await conn.execute(
                    "INSERT INTO mw_sym_chat_participants (sym_chat_id, user_id) VALUES ($1, $2)",
                    chat_id, member,
                )
            await _insert_update(
                conn, chat_id,
                f"{organizer_name or 'The organizer'} started this. {narrate.describe_shape(kind, shape)}",
                shape,
            )
            kickoff = narrate.kickoff_text(kind, config, organizer_name or "The organizer", objective)
            for member in members:
                await _insert_assistant(conn, chat_id, member, kickoff)

    for member in others:
        try:
            await notification_service.create_notification(
                user_id=member,
                company_id=company_id,
                type="sym_chat_invited",
                title=f"{organizer_name or 'A teammate'} added you to “{title}”",
                body=(objective or "").strip()[:200] or KINDS[kind]["description"],
                link=chat_link(chat_id),
                metadata={"sym_chat_id": str(chat_id)},
                send_email=True,
            )
        except Exception:
            logger.warning("sym-chat invite notification failed for %s", member, exc_info=True)

    return await get_detail(chat_id, company_id, user_id)


async def cancel(chat_id: UUID, company_id: UUID, user_id: UUID) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            chat = await conn.fetchrow(
                "SELECT created_by, status, shape FROM mw_sym_chats WHERE id = $1 AND company_id = $2 FOR UPDATE",
                chat_id, company_id,
            )
            if not chat:
                raise SymChatError(404, "Sym-chat not found")
            if chat["created_by"] != user_id:
                raise SymChatError(403, "Only the organizer can cancel this sym-chat")
            if chat["status"] != "open":
                raise SymChatError(409, f"This sym-chat is already {chat['status']}")
            await conn.execute(
                "UPDATE mw_sym_chats SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
                chat_id,
            )
            await _insert_update(conn, chat_id, "The organizer cancelled this sym-chat.",
                                 decode_jsonb(chat["shape"], {}) or {})
            member_ids = [r["user_id"] for r in await conn.fetch(
                "SELECT user_id FROM mw_sym_chat_participants WHERE sym_chat_id = $1", chat_id,
            )]
    await notification_service.push_to_users(
        member_ids, {"type": UPDATE_EVENT, "sym_chat_id": str(chat_id), "status": "cancelled"},
    )
    return await get_detail(chat_id, company_id, user_id)


def inbox_invite_text(title: str, resolution: dict, chat_id: UUID | str) -> str:
    outcome = narrate.outcome_text(resolution)
    what = "Meeting" if resolution.get("kind") == "schedule" else "Decision"
    return (
        f"**Invite: {title}**\n\n{what}: **{outcome}**\n\n"
        f"Everyone agreed in sym-chat — nothing else to do. [Open the sym-chat]({chat_link(chat_id)})"
    )


async def post_inbox_invite(
    conn, *, chat_id: UUID, title: str, organizer_id: UUID, member_ids: list[UUID], resolution: dict,
) -> UUID:
    """One group inbox conversation holding the invite, sent as the organizer.

    Same direct-insert shape as the project-invite inbox message
    (project_service/collaborators.py). The organizer is the sender, so their
    own copy starts read; everyone else sees it unread in /work/inbox."""
    content = inbox_invite_text(title, resolution, chat_id)
    async with conn.transaction():
        conv_id = await conn.fetchval(
            """
            INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
            VALUES ($1, true, $2, NOW(), $3)
            RETURNING id
            """,
            f"Invite: {title}"[:255], organizer_id,
            f"Invite: {title} — {narrate.outcome_text(resolution)}"[:100],
        )
        for member in dict.fromkeys([organizer_id, *member_ids]):
            await conn.execute(
                "INSERT INTO inbox_participants (conversation_id, user_id, last_read_at) VALUES ($1, $2, $3)",
                conv_id, member, datetime.now(timezone.utc) if member == organizer_id else None,
            )
        await conn.execute(
            "INSERT INTO inbox_messages (conversation_id, sender_id, content) VALUES ($1, $2, $3)",
            conv_id, organizer_id, content,
        )
    return conv_id


async def send_invites(
    *, chat_id: UUID, company_id: UUID, title: str, resolution: dict, member_ids: list[UUID],
    organizer_id: UUID | None = None,
) -> None:
    """The invite, three ways, each best effort: a group message in the Matcha
    inbox (from the organizer), plus a bell notification + email per person."""
    if organizer_id:
        try:
            async with get_connection() as conn:
                await post_inbox_invite(
                    conn, chat_id=chat_id, title=title, organizer_id=organizer_id,
                    member_ids=member_ids, resolution=resolution,
                )
        except Exception:
            logger.warning("sym-chat inbox invite failed for %s", chat_id, exc_info=True)
    outcome = narrate.outcome_text(resolution)
    for member in member_ids:
        try:
            await notification_service.create_notification(
                user_id=member,
                company_id=company_id,
                type="sym_chat_resolved",
                title=f"“{title}” is settled: {outcome}",
                body=f"Everyone agreed on {outcome}.",
                link=chat_link(chat_id),
                metadata={"sym_chat_id": str(chat_id), "resolution": resolution},
                send_email=True,
                email_subject=f"Settled: {title} — {outcome}",
            )
        except Exception:
            logger.warning("sym-chat resolved notification failed for %s", member, exc_info=True)


async def run_turn(chat_id: UUID, company_id: UUID, user_id: UUID, content: str) -> dict:
    content = (content or "").strip()
    if not content:
        raise SymChatError(400, "Message is empty")

    # 1 — load + store my message; no connection is held past this block.
    async with get_connection() as conn:
        chat = await conn.fetchrow(
            "SELECT id, kind, title, objective, config, status, created_by FROM mw_sym_chats WHERE id = $1 AND company_id = $2",
            chat_id, company_id,
        )
        me = await conn.fetchrow(
            f"""
            SELECT p.stance, {_NAME_SQL} AS name
              FROM mw_sym_chat_participants p
              JOIN users u ON u.id = p.user_id
              LEFT JOIN clients c ON c.user_id = p.user_id
             WHERE p.sym_chat_id = $1 AND p.user_id = $2
            """,
            chat_id, user_id,
        ) if chat else None
        if not chat or not me:
            raise SymChatError(404, "Sym-chat not found")
        if chat["status"] != "open":
            raise SymChatError(409, f"This sym-chat is {chat['status']}")
        turns = await conn.fetchval(
            "SELECT COUNT(*) FROM mw_sym_chat_messages WHERE sym_chat_id = $1 AND user_id = $2 AND role = 'user'",
            chat_id, user_id,
        )
        if int(turns or 0) >= MAX_TURNS_PER_PARTICIPANT:
            raise SymChatError(429, "You've reached the message limit for this sym-chat")
        kind = chat["kind"]
        config = decode_jsonb(chat["config"], {}) or {}
        known_options = list(config.get("options") or [])
        if kind == "decide":
            for row in await conn.fetch(
                "SELECT stance FROM mw_sym_chat_participants WHERE sym_chat_id = $1 ORDER BY created_at, id",
                chat_id,
            ):
                for name in (decode_jsonb(row["stance"], {}) or {}).get("proposals") or []:
                    if isinstance(name, str) and name.casefold() not in {o.casefold() for o in known_options}:
                        known_options.append(name)
        await conn.execute(
            "INSERT INTO mw_sym_chat_messages (sym_chat_id, user_id, role, content) VALUES ($1, $2, 'user', $3)",
            chat_id, user_id, content,
        )
        transcript = [
            {"role": r["role"], "content": r["content"]}
            for r in await conn.fetch(
                """
                SELECT role, content FROM mw_sym_chat_messages
                 WHERE sym_chat_id = $1 AND user_id = $2
                 ORDER BY created_at, id
                """,
                chat_id, user_id,
            )
        ]

    # 2 — the model call, with no pooled connection held.
    turn = await extract.next_turn(
        kind, chat["objective"] or "", config, transcript,
        decode_jsonb(me["stance"]), known_options, me["name"] or "Participant",
    )
    stance = turn["stance"]
    has_content = extract.stance_has_content(kind, stance)

    # 3 — one locked transaction for stance → shape → feed → resolution.
    resolved_now = False
    changed = False
    resolution = None
    nudges: dict = {}
    async with get_connection() as conn:
        async with conn.transaction():
            locked = await conn.fetchrow(
                "SELECT status, shape FROM mw_sym_chats WHERE id = $1 FOR UPDATE",
                chat_id,
            )
            status = locked["status"]
            shape = decode_jsonb(locked["shape"], {}) or {}
            if status == "open":
                before = await conn.fetch(
                    f"""
                    SELECT p.user_id, p.stance, {_NAME_SQL} AS name
                      FROM mw_sym_chat_participants p
                      JOIN users u ON u.id = p.user_id
                      LEFT JOIN clients c ON c.user_id = p.user_id
                     WHERE p.sym_chat_id = $1
                     ORDER BY p.created_at, p.id
                    """,
                    chat_id,
                )
                await conn.execute(
                    """
                    UPDATE mw_sym_chat_participants
                       SET stance = $3::jsonb,
                           responded_at = CASE WHEN $4 THEN COALESCE(responded_at, NOW()) ELSE NULL END
                     WHERE sym_chat_id = $1 AND user_id = $2
                    """,
                    chat_id, user_id, json.dumps(stance), has_content,
                )
                member_ids = [r["user_id"] for r in before]
                stances = {
                    r["user_id"]: (stance if r["user_id"] == user_id else decode_jsonb(r["stance"]))
                    for r in before
                }
                old_mine = next((decode_jsonb(r["stance"]) for r in before if r["user_id"] == user_id), None)
                new_shape = aggregate.compute_shape(kind, config, [{"stance": stances[m]} for m in member_ids])

                # Shared feed: my structured answer (never my words), then the group line.
                if has_content and stance != old_mine:
                    person = narrate.describe_stance(kind, me["name"] or "Someone", stance)
                    if person:
                        await _insert_update(conn, chat_id, person, new_shape)
                        changed = True
                line = narrate.describe_change(kind, shape, new_shape)
                if line:
                    await _insert_update(conn, chat_id, line, new_shape)
                    changed = True

                resolution = aggregate.resolution_for(kind, config, new_shape)
                if resolution:
                    await conn.execute(
                        """
                        UPDATE mw_sym_chats
                           SET shape = $2::jsonb, status = 'resolved', resolution = $3::jsonb,
                               resolved_at = NOW(), updated_at = NOW()
                         WHERE id = $1
                        """,
                        chat_id, json.dumps(new_shape), json.dumps(resolution),
                    )
                    resolved_now = changed = True
                    status = "resolved"
                else:
                    await conn.execute(
                        "UPDATE mw_sym_chats SET shape = $2::jsonb, updated_at = NOW() WHERE id = $1",
                        chat_id, json.dumps(new_shape),
                    )
                shape = new_shape

                last_assistant = {
                    r["user_id"]: r["content"]
                    for r in await conn.fetch(
                        """
                        SELECT DISTINCT ON (user_id) user_id, content
                          FROM mw_sym_chat_messages
                         WHERE sym_chat_id = $1 AND role = 'assistant'
                         ORDER BY user_id, created_at DESC, id DESC
                        """,
                        chat_id,
                    )
                }
                nudges = coordinator_messages(kind, new_shape, resolution, stances, last_assistant)
            await _insert_assistant(conn, chat_id, user_id, turn["reply"])
            # Coordinator messages land after my reply, so in my own tunnel the
            # acknowledgement comes first and the follow-up question second.
            for member, text in nudges.items():
                await _insert_assistant(conn, chat_id, member, text)
                changed = True

    # 4 — side effects after commit.
    if resolved_now:
        await send_invites(
            chat_id=chat_id, company_id=company_id, title=chat["title"],
            resolution=resolution, member_ids=member_ids, organizer_id=chat["created_by"],
        )
    if changed:
        await notification_service.push_to_users(
            member_ids, {"type": UPDATE_EVENT, "sym_chat_id": str(chat_id), "status": status},
        )

    return {
        "reply": turn["reply"],
        "error": bool(turn["error"]),
        "status": status,
        "shape": shape,
        "resolved": resolved_now,
    }
