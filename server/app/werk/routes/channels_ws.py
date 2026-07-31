"""Channel WebSocket handler for real-time group chat messaging."""

import asyncio
import json
import logging
from typing import Dict, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from pydantic import BaseModel

from ...database import get_connection
from ...core.services.auth import decode_token
from ...core.services.redis_cache import get_redis_cache, check_rate_limit

logger = logging.getLogger(__name__)

# Cap on a single WS send so one slow/half-dead socket can't stall an entire
# room's fan-out (the Redis subscriber loop processes envelopes serially).
_WS_SEND_TIMEOUT_SECONDS = 5.0


def _room_key(channel_id) -> Optional[str]:
    """Canonical room key for a channel — always the lowercase-dashed str()
    of the UUID, never the raw client-supplied string. join_room/message-send
    used to key rooms on the raw `channel_id` string while EMS background
    broadcasts (_bg_ems_intake/_bg_ems_clarify) keyed on `str(ch_uuid)` — an
    uppercase/braced/urn:-form UUID (all accepted by UUID()) silently named
    two different rooms, so the Huume pill never fanned out live. Returns
    None on a malformed id."""
    try:
        return str(UUID(str(channel_id)))
    except (ValueError, TypeError):
        return None


async def _safe_send_text(ws: WebSocket, data: str) -> bool:
    """Send with a timeout. Returns False (caller treats the socket as dead)
    on any failure, including timeout.

    A failed/timed-out send only gets the socket discarded from
    active_connections by the caller — its receive loop stays alive, so the
    client's own ping/pong still succeeds and it never learns it's missing
    broadcasts. Close it here so the receive loop raises WebSocketDisconnect
    and the client's reconnect/backoff path actually kicks in.
    """
    try:
        await asyncio.wait_for(ws.send_text(data), timeout=_WS_SEND_TIMEOUT_SECONDS)
        return True
    except Exception:
        try:
            await asyncio.wait_for(ws.close(), timeout=2)
        except Exception:
            pass
        return False


# Background tasks spawned fire-and-forget from the WS handler. Held in a set so
# they aren't GC'd mid-flight (asyncio keeps only a weak ref to running tasks).
_bg_tasks: set = set()


def _spawn_bg(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _bg_sync_channel_attachments(channel_id_str: str, user_id, attachments: list) -> None:
    """Mirror a message's attachments into the linked collab project's Files,
    on its own connection and off the send hot path. The reverse JSONB lookup
    is unindexed, so this must not block broadcasting the message."""
    try:
        async with get_connection() as conn:
            proj_id = await conn.fetchval(
                "SELECT id FROM mw_projects WHERE project_data->>'discussion_channel_id' = $1",
                channel_id_str,
            )
            if proj_id:
                from app.matcha.services.matcha_work.project_file_service import (
                    sync_channel_attachments_to_project,
                )
                await sync_channel_attachments_to_project(
                    conn, proj_id, user_id, attachments,
                )
    except Exception:
        logger.warning("channel->project Files sync failed", exc_info=True)


def _system_message_payload(channel_id_str: str, sys_row) -> dict:
    """Broadcast payload for a persisted EMS/Huume system message — shared by
    _bg_ems_intake and _bg_ems_clarify so the 17-key WS message shape (every
    field a normal ChannelMessage carries, so the client's single dispatcher
    handles both identically) isn't duplicated."""
    return {
        "id": str(sys_row["id"]),
        "channel_id": channel_id_str,
        "sender_id": None,
        "sender_name": "Huume",
        "sender_avatar_url": None,
        "content": sys_row["content"],
        "attachments": [],
        "reply_to_id": None,
        "reply_preview": None,
        "reactions": [],
        "created_at": sys_row["created_at"].isoformat(),
        "edited_at": None,
        "mentioned_user_ids": [],
        "client_message_id": None,
        "message_type": sys_row["message_type"],
    }


async def _insert_system_message(conn, channel_id_str: str, content: str):
    """INSERT one message_type='system' channel_messages row. Shared by
    _bg_ems_intake and _bg_ems_clarify."""
    return await conn.fetchrow(
        """
        INSERT INTO channel_messages (channel_id, sender_id, content, message_type)
        VALUES ($1, NULL, $2, 'system')
        RETURNING id, channel_id, content, message_type, created_at
        """,
        UUID(channel_id_str), content,
    )


def _ems_row_allowed(row) -> bool:
    """Shared predicate for _ems_company_gate/_ems_flag_enabled: not a
    personal company AND the merged features carry `ems`. The merge itself
    is core's merge_company_features — this is the one place werk applies
    it, instead of each caller (and routes/ems.py's now-deleted private
    copy) re-deriving the overlay."""
    if not row or row["is_personal"]:
        return False
    from app.core.feature_flags import merge_company_features
    return bool(merge_company_features(row["enabled_features"], row["signup_source"]).get("ems"))


async def _ems_company_gate(conn, channel_id_str: str):
    """Company/is_personal/`ems`-flag lookup for _bg_ems_intake, keyed on the
    channel (that's all intake has). Returns the company_id UUID, or None if
    the caller should silently no-op (personal company, or `ems` not
    enabled)."""
    row = await conn.fetchrow(
        """
        SELECT ch.company_id, comp.is_personal, comp.enabled_features,
               comp.signup_source
        FROM channels ch
        JOIN companies comp ON comp.id = ch.company_id
        WHERE ch.id = $1
        """,
        UUID(channel_id_str),
    )
    return row["company_id"] if _ems_row_allowed(row) else None


async def _ems_flag_enabled(conn, company_id) -> bool:
    """Same is_personal/`ems`-flag check as _ems_company_gate, keyed on a
    company_id already in hand (_bg_ems_clarify has one from the claimed
    ems_events row — no need to re-derive it via a channel join). Re-checked
    at answer time in case the flag was toggled off between question and
    answer."""
    row = await conn.fetchrow(
        "SELECT is_personal, enabled_features, signup_source FROM companies WHERE id = $1",
        company_id,
    )
    return _ems_row_allowed(row)


async def _ems_first_time_hint(conn, channel_id_str: str) -> str:
    """`ask.FIRST_TIME_HINT` the FIRST time Huume logs something in a given
    channel, "" every time after — this is how people find out it does more
    than log (nothing else in the channel advertises it). Called after the
    INSERT, so the channel's own new event is included: count == 1 means
    this is it.

    Cheap enough to run per intake (indexed channel_id, one COUNT), and
    non-fatal — a failure here must not cost the confirmation."""
    from app.matcha.services.ems.ask import FIRST_TIME_HINT
    try:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM ems_events WHERE channel_id = $1", UUID(channel_id_str),
        )
        return FIRST_TIME_HINT if count == 1 else ""
    except Exception:
        logger.exception("EMS: first-time hint check failed for channel %s", channel_id_str)
        return ""


async def _bg_ems_ask(channel_id_str: str, asker_user_id_str: str, content: str, intent: str) -> None:
    """Answer an "@huume what's been logged in here?" (ASK) or "@huume help"
    (HELP) instead of logging an event. Same off-hot-path, top-level-except,
    never-affects-send-latency contract as _bg_ems_intake.

    Visibility is decided in `services/ems/ask`, not here — see that
    module's docstring for why a channel answer can't reuse the
    admin-only REST gate. This function only supplies the two inputs that
    decision needs: the company (via the same _ems_company_gate) and the
    asker's role.

    Rate-limited on its own `ems_ask` key rather than the `ems_event` one:
    logging is the documentation-critical path, and a chatty afternoon of
    questions must never exhaust the budget that lets a real event be
    written down.

    Two connection blocks, same reasoning as _bg_ems_intake — no pooled
    connection is held across the answer's Gemini call."""
    try:
        from app.matcha.services.ems import ask as ems_ask
        from app.matcha.services.ems.intent import HELP, strip_mention

        async with get_connection() as conn:
            company_id = await _ems_company_gate(conn, channel_id_str)
            if company_id is None:
                return
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(asker_user_id_str))
            is_admin = ems_ask.is_admin_role(role)

            if intent == HELP:
                text = ems_ask.help_text(is_admin=is_admin)
                sys_row = await _insert_system_message(conn, channel_id_str, text)
                await broadcast_system_message(
                    channel_id_str, _system_message_payload(channel_id_str, sys_row),
                )
                return

            try:
                await check_rate_limit(str(company_id), "ems_ask", 30, 3600)
            except HTTPException:
                return  # over the hourly limit: skip silently, same as intake

            events = await ems_ask.fetch_channel_events(
                conn, company_id=company_id, channel_id=UUID(channel_id_str),
                include_behavioral=is_admin,
            )
            if not events:
                # "Nothing you can see" and "nothing happened" must not read
                # as the same sentence — see ask.no_events_text.
                hidden = not is_admin and await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM ems_events
                        WHERE channel_id = $1 AND company_id = $2 AND status <> 'dismissed'
                    )
                    """,
                    UUID(channel_id_str), company_id,
                )
                text = ems_ask.no_events_text(filtered=bool(hidden))
                sys_row = await _insert_system_message(conn, channel_id_str, text)
                await broadcast_system_message(
                    channel_id_str, _system_message_payload(channel_id_str, sys_row),
                )
                return

        # No connection held across the Gemini call.
        answer = await ems_ask.answer_question(strip_mention(content), events, is_admin=is_admin)

        async with get_connection() as conn:
            sys_row = await _insert_system_message(conn, channel_id_str, answer)
        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
    except Exception:
        logger.exception("EMS ask failed in channel %s", channel_id_str)


async def _bg_ems_link(channel_id_str: str, asker_user_id_str: str) -> None:
    """Answer "@huume send the reporting link" — the company-wide anonymous
    IR `/report/:token` link (see services/ems/intent.LINK). Same
    off-hot-path/top-level-except/never-affects-send-latency contract as
    _bg_ems_intake, and no Gemini call at all — the whole reply is
    deterministic, so there's nothing to rate-limit here.

    Two gates stack, and they're deliberately different shapes:
    _ems_company_gate (the `ems` flag, merged) decides whether Huume
    responds in this channel AT ALL; report_link_allowed (raw
    `incidents`+`ir_magic_links`) decides whether THIS specific answer is
    something the company sells — a company can have `ems` on and IR off,
    in which case the honest reply is "that's not set up here", not a 404
    silence that reads as Huume ignoring the ask.

    Employees can ask for an EXISTING link (it's poster-grade public by
    design — anyone with the door poster's QR code already has it) but
    can't mint a new one: generating changes what the poster/prior link
    points at, an admin-only action everywhere else this token is touched
    (routes/ir_incidents/anonymous_reporting.py, require_admin_or_client)."""
    try:
        from app.matcha.services.ems import ask as ems_ask
        from app.matcha.services.ir.report_links import (
            fetch_report_token, generate_report_token, public_report_url, report_link_allowed,
        )

        async with get_connection() as conn:
            company_id = await _ems_company_gate(conn, channel_id_str)
            if company_id is None:
                return

            features = await conn.fetchval("SELECT enabled_features FROM companies WHERE id = $1", company_id)
            if isinstance(features, str):
                features = json.loads(features)
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(asker_user_id_str))
            is_admin = ems_ask.is_admin_role(role)

            if not report_link_allowed(features or {}):
                text = (
                    "\U0001F4CB Reporting links aren't set up for this company."
                    if is_admin else
                    "\U0001F4CB I don't have a reporting link for this company — an admin can "
                    "set one up in Incidents."
                )
            else:
                token = await fetch_report_token(conn, company_id)
                if token is None and is_admin:
                    token = await generate_report_token(conn, company_id)
                if token is None:
                    text = (
                        "\U0001F4CB There's no reporting link set up yet — an admin can create "
                        "one in Incidents → Magic Links."
                    )
                else:
                    text = (
                        f"\U0001F4CB Anyone can report something confidentially here — no login "
                        f"needed: {public_report_url(token)}\nIt's anonymous unless they choose "
                        f"to give their name."
                    )

            sys_row = await _insert_system_message(conn, channel_id_str, text)
        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
    except Exception:
        logger.exception("EMS link request failed in channel %s", channel_id_str)


async def _bg_ems_intake(
    channel_id_str: str, message_id_str: str, reporter_user_id_str: str, content: str,
) -> None:
    """EMS event intake for an "@huume ..." channel message. Off the send hot
    path, top-level except — must NEVER affect message-send latency or
    success. Excludes personal (is_personal) companies and companies without
    the `ems` flag; rate-limited per company.

    Deliberately uses TWO separate `get_connection()` blocks rather than one
    held open for the whole function: `classify_event` makes 1-3 Gemini
    calls (classify + best-effort IR categorize/severity, each with its own
    retry), and the pool is capped at 10 connections
    (app/database/pool.py). Holding a pooled connection across that would
    let a handful of concurrent @huume messages starve every other request
    in the backend, not just EMS.

    Conversational clarification: when the classifier flags
    needs_clarification, the confirmation message ALSO carries the follow-up
    question, and ems_events.clarify_message_id is stamped to that message's
    id — a reply to it is picked up by _bg_ems_clarify below."""
    try:
        # werk -> matcha.services: lazy in-function import per the
        # documented werk/matcha boundary rule (CLAUDE.md).
        from app.matcha.services.ems.event_intake import (
            classify_event, gather_intake_context, persist_event, question_text,
        )

        async with get_connection() as conn:
            company_id = await _ems_company_gate(conn, channel_id_str)
            if company_id is None:
                return
            try:
                await check_rate_limit(str(company_id), "ems_event", 30, 3600)
            except HTTPException:
                return  # over the hourly limit: skip silently, message already sent

            context = await gather_intake_context(
                conn, UUID(channel_id_str), UUID(message_id_str),
            )
        # No connection held across the Gemini calls.
        classified = await classify_event(content, context)

        async with get_connection() as conn:
            event_row, confirmation = await persist_event(
                conn,
                company_id=company_id,
                channel_id=UUID(channel_id_str),
                message_id=UUID(message_id_str),
                reporter_user_id=UUID(reporter_user_id_str),
                content=content,
                classified=classified,
            )
            if event_row is None:
                return  # dedupe hit (ON CONFLICT on message_id) — nothing to confirm

            ask = classified.get("needs_clarification") and classified.get("clarify_question")
            if ask:
                # The first-time hint is deliberately NOT appended here:
                # extract_question() recovers an armed question by stripping
                # the trailing _QUESTION_SUFFIX, so anything after it would
                # be read back as part of the question itself.
                message_text = question_text(confirmation, classified["clarify_question"])
            else:
                message_text = confirmation + await _ems_first_time_hint(conn, channel_id_str)
            sys_row = await _insert_system_message(conn, channel_id_str, message_text)
            if ask:
                # Arm the pending question: a reply to THIS system message
                # is the answer _bg_ems_clarify is waiting for.
                await conn.execute(
                    "UPDATE ems_events SET clarify_message_id = $1 WHERE id = $2",
                    sys_row["id"], event_row["id"],
                )
        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
    except Exception:
        logger.exception("EMS intake failed for message %s", message_id_str)


async def _bg_ems_clarify(
    channel_id_str: str, reply_to_id_str: str, answerer_user_id_str: str, content: str,
) -> bool:
    """Fold a reply-to-a-Huume-question into its EMS event. Off the send hot
    path, top-level except, fire-and-forget — same rules as _bg_ems_intake.
    Only invoked by _bg_ems_dispatch when the reply targets a Huume system
    message — it no longer runs an atomic-claim probe against every reply.

    Returns True iff the claim below matched (this reply IS an answer to a
    live question — the disarm below happened, whether or not anything
    downstream succeeds), False on a claim miss (stale/already-answered
    pill). _bg_ems_dispatch uses this: a claimed reply must never ALSO fall
    through to intake as a second, duplicate event.

    The claim UPDATE + fold_answer() run in ONE transaction: once it
    commits, the reporter's answer is durable narrative on the event even
    if everything after (rate limit, the Gemini reclassification call, a
    second connection, a process restart) fails. Previously the claim
    auto-committed alone and the narrative-append/rounds-increment only
    happened in a LATER apply_refinement() call, on the far side of a
    Gemini round-trip — any failure there silently dropped the answer with
    no way to re-arm the question. See event_intake.fold_answer /
    apply_reclassification.

    A second get_connection() block does the reclassification — never
    holds a pooled connection across the Gemini call, same reasoning as
    _bg_ems_intake."""
    claim_happened = False
    try:
        from app.matcha.services.ems.event_intake import (
            apply_reclassification, classify_event, compose_refinement_content,
            extract_question, fold_answer, gather_intake_context, question_text,
            should_ask_again, update_text,
        )

        reply_uuid = UUID(reply_to_id_str)

        async with get_connection() as conn:
            async with conn.transaction():
                # Atomic claim: first reply to this question wins. A claim
                # miss (stale pill, already answered) exits the transaction
                # normally with nothing changed.
                claimed = await conn.fetchrow(
                    """
                    UPDATE ems_events SET clarify_message_id = NULL
                    WHERE clarify_message_id = $1 AND status = 'logged'
                    RETURNING id, company_id, narrative, clarification_rounds
                    """,
                    reply_uuid,
                )
                if claimed is None:
                    return False
                claim_happened = True
                company_id = claimed["company_id"]

                if not await _ems_flag_enabled(conn, company_id):
                    return True  # ems disabled between question and answer — question stays dead, nothing to fold

                folded = await fold_answer(
                    conn, event_id=claimed["id"], company_id=company_id,
                    answer=content, answered_by=UUID(answerer_user_id_str),
                )
                if folded is None:
                    return True  # promote/dismiss race — claim still commits, nothing more to do

                question_row = await conn.fetchrow(
                    "SELECT content FROM channel_messages WHERE id = $1", reply_uuid,
                )
                # The question's own text isn't stored on a dedicated column —
                # it's recovered from the rendered system-message pill, which
                # also carries the confirmation preamble and the "reply to
                # this message" instruction. extract_question() strips both
                # so neither leaks into the refinement prompt as if the
                # reporter had said them.
                question = extract_question(question_row["content"]) if question_row else ""
                context = await gather_intake_context(conn, UUID(channel_id_str), reply_uuid)
        # -- the answer is durable from here on; only reclassification can still fail --

        try:
            await check_rate_limit(str(company_id), "ems_event", 30, 3600)
        except HTTPException:
            # Over the hourly limit: the answer is already folded above (no
            # Gemini, no new question) — post the deterministic pill.
            async with get_connection() as conn:
                sys_row = await _insert_system_message(
                    conn, channel_id_str, update_text(folded),
                )
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return True

        # No connection held across the Gemini call.
        refinement_content = compose_refinement_content(claimed["narrative"], question, content)
        classified = await classify_event(refinement_content, context)

        async with get_connection() as conn:
            reclassified = await apply_reclassification(
                conn, event_id=folded["id"], company_id=company_id, classified=classified,
            )
            display = reclassified or folded  # reclassify may no-op (not model_ok, or a promote/dismiss race)

            ask_again = should_ask_again(classified, claimed["clarification_rounds"])
            if ask_again:
                preamble = classified.get("ack") or "Got it, thanks."
                text = question_text(f"\U0001F4CB {preamble}", classified["clarify_question"])
            else:
                text = update_text(display, classified.get("ack"))
            sys_row = await _insert_system_message(conn, channel_id_str, text)
            if ask_again:
                await conn.execute(
                    "UPDATE ems_events SET clarify_message_id = $1 WHERE id = $2",
                    sys_row["id"], display["id"],
                )

        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        return True
    except Exception:
        logger.exception("EMS clarify failed for reply to message %s", reply_to_id_str)
        # If the claim already committed, the answer is folded — never let
        # _bg_ems_dispatch treat this as a miss and also fire intake.
        return claim_happened


def _ems_dispatch_decision(
    *, reply_target_type: Optional[str], has_huume_mention: bool,
) -> tuple[bool, bool]:
    """(spawn_task, reply_to_system) — pure, unit-tested in
    tests/ems/test_ems_dispatch.py. The send handler unpacks this to decide
    whether to spawn _bg_ems_dispatch at all; an ordinary reply to a normal
    user message (reply_target_type in (None, "user") and no @huume
    mention) spawns nothing — no task, no pooled connection, no ems_events
    probe for the overwhelmingly common case."""
    reply_to_system = reply_target_type == "system"
    return (reply_to_system or has_huume_mention, reply_to_system)


async def _bg_ems_dispatch(
    channel_id_str: str,
    message_id_str: str,
    reply_to_system_id_str: Optional[str],
    sender_user_id_str: str,
    content: str,
    *,
    has_huume_mention: bool,
) -> None:
    """Single EMS entry point off the send hot path, replacing the two
    independent _spawn_bg(...) call sites that used to fire in the same
    turn. Clarify wins over intake: a reply to a Huume question that ALSO
    @-mentions huume is the answer, not a second event — previously both
    _bg_ems_intake and _bg_ems_clarify fired independently and minted a
    duplicate. If the clarify claim misses (stale pill, already answered)
    an @huume mention still falls through to intake, so "@huume new thing"
    typed as a reply onto an old pill isn't swallowed.

    An @huume mention that is a QUESTION ("what happened last week?") or a
    capability probe ("help") is answered instead of logged — see
    services/ems/intent.classify_intent, which is deterministic and biased
    to LOG precisely because this is the fork where an event could be lost.
    The clarify path above still wins: a reply answering a live Huume
    question is folded into its event even when phrased as a question."""
    if reply_to_system_id_str is not None:
        claimed = await _bg_ems_clarify(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
    if has_huume_mention:
        from app.matcha.services.ems.intent import LINK, LOG, classify_intent

        intent = classify_intent(content)
        if intent == LOG:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
        elif intent == LINK:
            await _bg_ems_link(channel_id_str, sender_user_id_str)
        else:
            await _bg_ems_ask(channel_id_str, sender_user_id_str, content, intent)


async def _notify_channel_members(
    members: list, ch_name: Optional[str], sender_name: str, preview: str, channel_id_str: str,
) -> None:
    """In-app notification fan-out for a new channel message, as a single
    background task instead of one bare `create_task` per member — avoids
    N members opening N concurrent pool connections off one message send,
    and keeps a live reference so the tasks can't be GC'd mid-flight."""
    from app.matcha.services import notification_service as notif_svc
    for m in members:
        if not m["company_id"]:
            continue
        try:
            await notif_svc.create_notification(
                user_id=m["user_id"],
                company_id=m["company_id"],
                type="channel_message",
                title=f"#{ch_name}",
                body=f"{sender_name}: {preview}",
                link="/work",
                metadata={"channel_id": channel_id_str},
            )
        except Exception:
            logger.warning("channel_message notification failed for %s", m["user_id"], exc_info=True)

# Online presence — written on every WS receive (heartbeat), read by the
# mention_email Celery worker to skip emails for users who are still active.
# TTL is intentionally generous (60s) so a single dropped ping doesn't trigger
# a false-offline email; manager.disconnect explicitly clears the key when the
# last WS for a user closes.
_ONLINE_KEY_PREFIX = "channels_ws:online:"
_ONLINE_TTL_SECONDS = 60

# Redis pub/sub channel used to fan-out broadcasts across uvicorn workers.
# Production runs --workers 2, so an in-process broadcast on worker A would
# never reach a WS client connected to worker B. Each worker subscribes to
# this channel on startup and re-dispatches incoming envelopes to its own
# local sockets via _local_broadcast_to_room / _local_send_to_user.
_FANOUT_CHANNEL = "channels:fanout"
_SERVER_PING_INTERVAL_SECONDS = 25


async def _mark_online(user_id: UUID) -> None:
    redis = get_redis_cache()
    if redis is None:
        return
    try:
        await redis.setex(f"{_ONLINE_KEY_PREFIX}{user_id}", _ONLINE_TTL_SECONDS, "1")
    except Exception:
        pass


async def _mark_offline(user_id: UUID) -> None:
    redis = get_redis_cache()
    if redis is None:
        return
    try:
        await redis.delete(f"{_ONLINE_KEY_PREFIX}{user_id}")
    except Exception:
        pass

router = APIRouter()

# ---------------------------------------------------------------------------
# User identity model (resolved at connection time)
# ---------------------------------------------------------------------------

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"


class ChannelUser(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    company_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Connection Manager (adapted from chat/websocket.py)
# ---------------------------------------------------------------------------

class ChannelConnectionManager:
    """Manages WebSocket connections for channel chat."""

    def __init__(self):
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        self.room_members: Dict[str, Set[UUID]] = {}
        self.users: Dict[UUID, ChannelUser] = {}
        self.user_rooms: Dict[UUID, Set[str]] = {}
        self.lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, user: ChannelUser, subprotocol: Optional[str] = None
    ):
        await websocket.accept(subprotocol=subprotocol)
        async with self.lock:
            if user.id not in self.active_connections:
                self.active_connections[user.id] = set()
                self.user_rooms[user.id] = set()
            self.active_connections[user.id].add(websocket)
            self.users[user.id] = user

    async def disconnect(self, websocket: WebSocket, user_id: UUID):
        async with self.lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                    if user_id in self.user_rooms:
                        rooms_to_leave = list(self.user_rooms[user_id])
                        del self.user_rooms[user_id]
                        user = self.users.pop(user_id, None)
                        for room in rooms_to_leave:
                            if room in self.room_members:
                                self.room_members[room].discard(user_id)
                                if user:
                                    await self._broadcast_to_room(room, {
                                        "type": "user_left",
                                        "room": room,
                                        "user": user.model_dump(mode='json'),
                                    }, exclude_user=user_id)

    async def join_room(self, user_id: UUID, room_key: str):
        async with self.lock:
            if room_key not in self.room_members:
                self.room_members[room_key] = set()

            was_in_room = user_id in self.room_members[room_key]
            self.room_members[room_key].add(user_id)

            if user_id in self.user_rooms:
                self.user_rooms[user_id].add(room_key)

            if not was_in_room and user_id in self.users:
                await self._broadcast_to_room(room_key, {
                    "type": "user_joined",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                }, exclude_user=user_id)

    async def leave_room(self, user_id: UUID, room_key: str):
        async with self.lock:
            if room_key in self.room_members:
                self.room_members[room_key].discard(user_id)
            if user_id in self.user_rooms:
                self.user_rooms[user_id].discard(room_key)
            if user_id in self.users:
                await self._broadcast_to_room(room_key, {
                    "type": "user_left",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                })

    async def broadcast_message(self, room_key: str, message: dict):
        await self._broadcast_to_room(room_key, {
            "type": "message",
            "room": room_key,
            "message": message,
        })

    async def broadcast_typing(self, room_key: str, user: ChannelUser):
        await self._broadcast_to_room(room_key, {
            "type": "typing",
            "room": room_key,
            "user": user.model_dump(mode='json'),
        }, exclude_user=user.id)

    async def get_online_users(self, room_key: str) -> list:
        async with self.lock:
            if room_key not in self.room_members:
                return []
            return [
                self.users[uid].model_dump(mode='json')
                for uid in self.room_members[room_key]
                if uid in self.users
            ]

    async def send_to_user(self, user_id: UUID, message: dict):
        """Send a message to a specific user (all their connections, on any worker)."""
        redis = get_redis_cache()
        if redis is None:
            await self._local_send_to_user(user_id, message)
            return
        envelope = {
            "kind": "user",
            "user_id": str(user_id),
            "message": message,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in send_to_user; using local fallback")
            await self._local_send_to_user(user_id, message)

    async def _local_send_to_user(self, user_id: UUID, message: dict):
        """Direct write to this worker's local sockets for a user. Called by
        the subscriber loop when a fanout envelope targets this user, and as
        a fallback when Redis is unavailable."""
        async with self.lock:
            conns = set(self.active_connections.get(user_id, set()))
        if not conns:
            return
        data = json.dumps(message, default=str)
        # Fan out to this user's connections (usually one, but multi-tab/
        # multi-device is possible) concurrently instead of one at a time.
        results = await asyncio.gather(*(_safe_send_text(ws, data) for ws in conns))
        dead = [ws for ws, ok in zip(conns, results) if not ok]
        if dead:
            async with self.lock:
                for ws in dead:
                    self.active_connections.get(user_id, set()).discard(ws)

    async def _broadcast_to_room(self, room_key: str, message: dict, exclude_user: UUID = None):
        """Fan-out to every WS member of a room across all uvicorn workers.

        Publishes to Redis so other workers' subscribers can deliver to their
        own local sockets. If Redis is unavailable (e.g. dev without Redis),
        falls back to local-only fanout so single-process dev still works.
        """
        redis = get_redis_cache()
        if redis is None:
            await self._local_broadcast_to_room(room_key, message, exclude_user=exclude_user)
            return
        envelope = {
            "kind": "room",
            "room": room_key,
            "message": message,
            "exclude_user": str(exclude_user) if exclude_user else None,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in _broadcast_to_room; using local fallback")
            await self._local_broadcast_to_room(room_key, message, exclude_user=exclude_user)

    async def _local_broadcast_to_room(self, room_key: str, message: dict, exclude_user: UUID = None):
        """Direct write to this worker's local sockets for a room. Called by
        the subscriber loop and as a Redis-down fallback."""
        if room_key not in self.room_members:
            return
        data = json.dumps(message, default=str)
        targets: list[tuple[UUID, WebSocket]] = []
        for user_id in self.room_members[room_key]:
            if exclude_user and user_id == exclude_user:
                continue
            for ws in self.active_connections.get(user_id, set()):
                targets.append((user_id, ws))
        if not targets:
            return
        # Every socket in the room sent to concurrently — previously this
        # awaited sends one at a time, so a single slow/half-dead socket
        # delayed delivery to the rest of the room.
        results = await asyncio.gather(*(_safe_send_text(ws, data) for _, ws in targets))
        dead = [(uid, ws) for (uid, ws), ok in zip(targets, results) if not ok]
        if dead:
            async with self.lock:
                for uid, ws in dead:
                    self.active_connections.get(uid, set()).discard(ws)


manager = ChannelConnectionManager()


# ---------------------------------------------------------------------------
# Cross-worker pub/sub subscriber + server-side keepalive ping
# ---------------------------------------------------------------------------

_subscriber_task: Optional[asyncio.Task] = None
_server_ping_task: Optional[asyncio.Task] = None


async def _fanout_subscriber_loop() -> None:
    """Long-running per-worker task. Subscribes to the Redis fanout channel
    and dispatches incoming envelopes to this worker's local sockets.

    Self-healing: on any exception, sleeps 2s and re-subscribes. Cancellation
    exits cleanly.
    """
    while True:
        pubsub = None
        try:
            redis = get_redis_cache()
            if redis is None:
                # Dev without Redis — nothing to subscribe to; sleep then retry.
                await asyncio.sleep(5)
                continue
            pubsub = redis.pubsub()
            await pubsub.subscribe(_FANOUT_CHANNEL)
            logger.info("[Channels WS] Subscribed to %s", _FANOUT_CHANNEL)
            async for raw in pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                payload = raw.get("data")
                if not payload:
                    continue
                try:
                    envelope = json.loads(payload)
                except Exception:
                    logger.warning("[Channels WS] Malformed fanout envelope; dropping")
                    continue
                kind = envelope.get("kind")
                msg = envelope.get("message")
                if msg is None:
                    continue
                if kind == "room":
                    room_key = envelope.get("room")
                    if not room_key:
                        continue
                    exclude_raw = envelope.get("exclude_user")
                    exclude_user = None
                    if exclude_raw:
                        try:
                            exclude_user = UUID(exclude_raw)
                        except (ValueError, TypeError):
                            exclude_user = None
                    await manager._local_broadcast_to_room(
                        room_key, msg, exclude_user=exclude_user,
                    )
                elif kind == "user":
                    uid_raw = envelope.get("user_id")
                    if not uid_raw:
                        continue
                    try:
                        uid = UUID(uid_raw)
                    except (ValueError, TypeError):
                        continue
                    await manager._local_send_to_user(uid, msg)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("[Channels WS] Subscriber loop error; restarting in 2s")
            await asyncio.sleep(2)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(_FANOUT_CHANNEL)
                    await pubsub.aclose()
                except Exception:
                    pass


async def _server_ping_loop() -> None:
    """Periodic keepalive push from server to every connected WS. Prevents
    Nginx / intermediaries from silently killing idle connections and gives
    the server early detection of dead sockets (a failed send drops the WS
    from active_connections)."""
    while True:
        try:
            await asyncio.sleep(_SERVER_PING_INTERVAL_SECONDS)
            # Snapshot the per-user connection map under the lock so we don't
            # iterate while disconnect() mutates it.
            async with manager.lock:
                snapshot: list[tuple[UUID, list[WebSocket]]] = [
                    (uid, list(conns)) for uid, conns in manager.active_connections.items()
                ]
            ping_payload = json.dumps({"type": "server_ping"})
            # Ping every socket on this worker concurrently rather than one at
            # a time — sequential sends here would delay the next room's
            # pings behind a single slow/half-dead connection.
            targets: list[tuple[UUID, WebSocket]] = [
                (uid, ws) for uid, conns in snapshot for ws in conns
            ]
            if targets:
                results = await asyncio.gather(
                    *(_safe_send_text(ws, ping_payload) for _, ws in targets)
                )
                dead = [(uid, ws) for (uid, ws), ok in zip(targets, results) if not ok]
                if dead:
                    async with manager.lock:
                        for uid, ws in dead:
                            bucket = manager.active_connections.get(uid)
                            if bucket is not None:
                                bucket.discard(ws)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("[Channels WS] Server ping loop error; continuing")


def start_fanout_subscriber() -> None:
    """Start the per-worker Redis pub/sub subscriber. Idempotent."""
    global _subscriber_task
    if _subscriber_task and not _subscriber_task.done():
        return
    _subscriber_task = asyncio.create_task(_fanout_subscriber_loop())


def start_server_ping_loop() -> None:
    """Start the per-worker server-side ping loop. Idempotent."""
    global _server_ping_task
    if _server_ping_task and not _server_ping_task.done():
        return
    _server_ping_task = asyncio.create_task(_server_ping_loop())


async def stop_fanout_subscriber() -> None:
    """Cancel the subscriber task on shutdown."""
    global _subscriber_task
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except (asyncio.CancelledError, Exception):
            pass
        _subscriber_task = None


async def stop_server_ping_loop() -> None:
    global _server_ping_task
    if _server_ping_task is not None:
        _server_ping_task.cancel()
        try:
            await _server_ping_task
        except (asyncio.CancelledError, Exception):
            pass
        _server_ping_task = None


async def broadcast_message_deleted(
    channel_id: str,
    message_id: str,
    deleted_by: str,
) -> None:
    """Fan out a message_deleted event to all members currently connected
    to a channel room. Called by the REST DELETE handler in channels.py.
    """
    await manager._broadcast_to_room(
        channel_id,
        {
            "type": "message_deleted",
            "room": channel_id,
            "message_id": message_id,
            "deleted_by": deleted_by,
        },
    )


async def broadcast_message_edited(
    channel_id: str,
    message_id: str,
    content: str,
    edited_at: Optional[str] = None,
) -> None:
    """Fan out a message_edited event so connected members update the message
    text + 'edited' marker in place. Called by the REST PATCH handler."""
    await manager._broadcast_to_room(
        channel_id,
        {
            "type": "message_edited",
            "room": channel_id,
            "message_id": message_id,
            "content": content,
            "edited_at": edited_at,
        },
    )


async def broadcast_broadcast_started(
    channel_id: str,
    broadcast_id: str,
    started_by: str,
    started_at: str,
    title: Optional[str] = None,
) -> None:
    """Push broadcast.started to all connected members of a channel."""
    await manager._broadcast_to_room(channel_id, {
        "type": "broadcast.started",
        "channel_id": channel_id,
        "broadcast_id": broadcast_id,
        "started_by": started_by,
        "started_at": started_at,
        "title": title,
    })


async def broadcast_broadcast_ended(channel_id: str, broadcast_id: str) -> None:
    await manager._broadcast_to_room(channel_id, {
        "type": "broadcast.ended",
        "channel_id": channel_id,
        "broadcast_id": broadcast_id,
    })


async def broadcast_reaction_update(
    channel_id: str,
    message_id: str,
    reactions: list[dict],
) -> None:
    """Fan out a reaction_update event to all members currently connected
    to a channel room. Called by the REST react handler in channels.py.
    """
    await manager._broadcast_to_room(
        channel_id,
        {
            "type": "reaction_update",
            "room": channel_id,
            "message_id": message_id,
            "reactions": reactions,
        },
    )


async def broadcast_system_message(channel_id: str, message: dict) -> None:
    """Fan out a system (Huume/EMS) message to a channel room. Called from
    a background task, not a connected client — no WebSocket/user context
    required. Goes through manager.broadcast_message so the envelope
    matches every other message fan-out ({type, room, message}) — the
    client reads `data.message` and silently drops anything else shaped."""
    await manager.broadcast_message(channel_id, message)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _token_from_request(
    websocket: WebSocket, query_token: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Extract the JWT from the handshake. Sources, in preference order:

    1. ``Sec-WebSocket-Protocol: bearer, <token>`` — web clients; keeps the
       token out of the URL so it never lands in nginx/proxy access logs.
    2. ``?token=`` query param — legacy web clients / pre-deploy tabs.
    3. ``Authorization: Bearer`` header — native clients.

    Returns ``(token, subprotocol_to_echo)`` — when the token came in via
    subprotocol the accept() MUST echo ``"bearer"`` or browsers fail the
    handshake.
    """
    proto = websocket.headers.get("sec-websocket-protocol")
    if proto:
        parts = [p.strip() for p in proto.split(",")]
        if len(parts) >= 2 and parts[0] == "bearer" and parts[1]:
            return parts[1], "bearer"
    if query_token:
        return query_token, None
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:], None
    return None, None


async def _authenticate(token: str) -> Optional[ChannelUser]:
    """Authenticate a WebSocket connection using the main app JWT."""
    payload = decode_token(token, expected_type="access")
    if not payload:
        return None

    user_id = UUID(payload.sub)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT u.id, u.email, u.role, u.avatar_url,
                   {_USER_NAME_EXPR} AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = $1 AND u.is_active = true
            """,
            user_id,
        )
        if not row:
            return None

        # Resolve company_id
        company_id = None
        if row["role"] in ("client", "individual"):
            company_id = await conn.fetchval(
                "SELECT company_id FROM clients WHERE user_id = $1", user_id
            )
        elif row["role"] == "employee":
            company_id = await conn.fetchval(
                "SELECT org_id FROM employees WHERE user_id = $1", user_id
            )
        elif row["role"] == "admin":
            # Admin can access any company — resolved per room join
            company_id = None

        return ChannelUser(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            role=row["role"],
            avatar_url=row["avatar_url"],
            company_id=company_id,
        )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("")
async def channel_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """WebSocket endpoint for real-time channel messaging."""
    auth_token, subprotocol = _token_from_request(websocket, token)
    if not auth_token:
        await websocket.close(code=4001, reason="Missing token")
        return
    user = await _authenticate(auth_token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user, subprotocol=subprotocol)
    await _mark_online(user.id)

    try:
        while True:
            data = await websocket.receive_json()
            await _mark_online(user.id)
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "join_room":
                channel_id = data.get("channel_id")
                if channel_id:
                    try:
                        ch_uuid = UUID(channel_id)
                    except (ValueError, TypeError):
                        await websocket.send_json({"type": "error", "message": "Invalid channel ID"})
                        continue
                    async with get_connection() as conn:
                        # Verify membership (allows cross-tenant memberships; REST uses the same rule)
                        ok = await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2 AND removed_for_inactivity IS NOT TRUE)",
                            ch_uuid, user.id,
                        )

                        if ok:
                            # Canonical key (str(ch_uuid), not the raw client
                            # string) — must match the key EMS background
                            # broadcasts use, or a non-canonical UUID form
                            # silently joins a different room than the pill
                            # is fanned out to.
                            room_key = str(ch_uuid)
                            await manager.join_room(user.id, room_key)
                            online = await manager.get_online_users(room_key)
                            await websocket.send_json({
                                "type": "online_users",
                                "room": room_key,
                                "users": online,
                            })
                            # Emit live broadcast state so late-joiners see "Live now"
                            bc = await conn.fetchrow(
                                "SELECT id, started_by, started_at, title FROM channel_broadcasts WHERE channel_id = $1 AND ended_at IS NULL",
                                ch_uuid,
                            )
                            if bc:
                                await websocket.send_json({
                                    "type": "broadcast.started",
                                    "channel_id": room_key,
                                    "broadcast_id": str(bc["id"]),
                                    "started_by": str(bc["started_by"]),
                                    "started_at": bc["started_at"].isoformat(),
                                    "title": bc["title"],
                                })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Channel not found or not a member",
                            })

            elif msg_type == "leave_room":
                channel_id = data.get("channel_id")
                if channel_id:
                    rk = _room_key(channel_id)
                    if rk:
                        await manager.leave_room(user.id, rk)

            elif msg_type == "message":
                channel_id = data.get("channel_id")
                content = (data.get("content") or "").strip()
                attachments = data.get("attachments") or []
                reply_to_id = data.get("reply_to_id")
                # Client-generated correlation ID for optimistic UI reconciliation.
                # Clients append a pending message locally with this ID; on echo,
                # they replace the pending entry instead of duplicating it.
                client_message_id = data.get("client_message_id")
                # Parse cmid to UUID for server-side idempotency. Bad/missing
                # cmid -> None -> INSERT skips the partial unique index and
                # proceeds as a fresh row (legacy behavior).
                cmid_uuid: Optional[UUID] = None
                if client_message_id:
                    try:
                        cmid_uuid = UUID(str(client_message_id))
                    except (ValueError, TypeError):
                        cmid_uuid = None
                if channel_id and (content or attachments) and len(content) <= 4000:
                    try:
                        ch_uuid = UUID(channel_id)
                    except (ValueError, TypeError):
                        continue
                    reply_uuid = None
                    if reply_to_id:
                        try:
                            reply_uuid = UUID(reply_to_id)
                        except (ValueError, TypeError):
                            pass
                    # Canonical key (str(ch_uuid), not the raw client
                    # string) — see _room_key's docstring; must match what
                    # join_room and the EMS background broadcasts use.
                    room_key = str(ch_uuid)
                    import json as _json
                    attachments_json = _json.dumps(attachments) if attachments else "[]"
                    reply_target_type: Optional[str] = None
                    async with get_connection() as conn:
                        # Verify membership (exclude removed members)
                        is_member = await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2 AND removed_for_inactivity IS NOT TRUE)",
                            ch_uuid, user.id,
                        )
                        if is_member:
                            if reply_uuid:
                                # Cross-channel/bogus reply targets are dropped
                                # silently rather than trusted: without this, a
                                # crafted payload could quote any message UUID in
                                # any tenant (the rp preview query below is
                                # unscoped, so its content would leak into this
                                # broadcast), and a nonexistent UUID would hit the
                                # reply_to_id FK and raise past this except-free
                                # INSERT, killing the WS receive loop. Runs only
                                # on the is_member path — a non-member's send is
                                # dropped below without touching the DB again.
                                #
                                # Also carries message_type: the EMS dispatch
                                # decision below needs to know whether this
                                # reply targets a Huume system-message pill
                                # (a possible clarify answer) without a
                                # second query.
                                reply_target_type = await conn.fetchval(
                                    "SELECT message_type FROM channel_messages WHERE id = $1 AND channel_id = $2",
                                    reply_uuid, ch_uuid,
                                )
                                if reply_target_type is None:
                                    reply_uuid = None
                            # ON CONFLICT path makes the INSERT idempotent on
                            # (sender_id, client_message_id) so a retried send
                            # returns the original row instead of inserting a
                            # second one. The unique index is partial (only
                            # rows with non-null cmid), so the conflict target
                            # `WHERE client_message_id IS NOT NULL` matches it
                            # for inference. DO UPDATE SET id = id is a no-op
                            # that makes RETURNING return the existing row.
                            row = await conn.fetchrow(
                                """
                                INSERT INTO channel_messages
                                    (channel_id, sender_id, content, attachments, reply_to_id, client_message_id)
                                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                                ON CONFLICT (sender_id, client_message_id)
                                    WHERE client_message_id IS NOT NULL
                                    DO UPDATE SET id = channel_messages.id
                                RETURNING id, channel_id, sender_id, content, attachments,
                                          reply_to_id, client_message_id, created_at, edited_at,
                                          message_type,
                                          -- xmax = 0 iff this row was just inserted (no conflict).
                                          -- Lets us skip duplicate side-effects (mention email,
                                          -- in-app notification, activity-timestamp updates) when
                                          -- a retried send hits the ON CONFLICT branch.
                                          (xmax = 0) AS inserted
                                """,
                                ch_uuid, user.id, content or "", attachments_json, reply_uuid, cmid_uuid,
                            )
                            is_new_message = bool(row["inserted"])
                            # Update channel + member activity timestamps only
                            # on the fresh-insert path. A retried duplicate
                            # send shouldn't bump activity (otherwise a flaky
                            # client could keep a channel appearing "active"
                            # via repeated cmid retries).
                            if is_new_message:
                                await conn.execute(
                                    "UPDATE channels SET updated_at = NOW() WHERE id = $1",
                                    ch_uuid,
                                )
                                await conn.execute(
                                    "UPDATE channel_members SET last_contributed_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                                    ch_uuid, user.id,
                                )

                            broadcast_attachments = _json.loads(row["attachments"]) if row["attachments"] else []

                            # Mirror chat media into the linked collab project's
                            # Files (root) — fire-and-forget on its own connection
                            # so the unindexed reverse lookup never adds latency to
                            # the send. Fresh inserts only (no re-mirror on retry).
                            if is_new_message and broadcast_attachments:
                                _spawn_bg(_bg_sync_channel_attachments(
                                    str(ch_uuid), user.id, list(broadcast_attachments),
                                ))
                            # Build reply preview for broadcast
                            reply_preview = None
                            if reply_uuid:
                                rp = await conn.fetchrow(
                                    """
                                    SELECT m.content, m.attachments, m.deleted_at,
                                           COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email, 'Huume') AS sender_name
                                    FROM channel_messages m
                                    LEFT JOIN users u ON u.id = m.sender_id
                                    LEFT JOIN clients c ON c.user_id = u.id
                                    LEFT JOIN employees e ON e.user_id = u.id
                                    LEFT JOIN admins a ON a.user_id = u.id
                                    WHERE m.id = $1
                                    """,
                                    reply_uuid,
                                )
                                if rp:
                                    rp_atts = []
                                    if not rp["deleted_at"]:
                                        raw = rp["attachments"]
                                        rp_atts = _json.loads(raw) if isinstance(raw, str) else (raw or [])
                                    reply_preview = {
                                        "id": str(reply_uuid),
                                        "sender_name": rp["sender_name"],
                                        "content": "" if rp["deleted_at"] else rp["content"],
                                        "attachments": rp_atts,
                                    }

                            # Parse + resolve @mentions BEFORE broadcasting so the
                            # payload carries the resolved IDs for client-side chip
                            # rendering. Email enqueue happens below; emails are
                            # rate-limited and only send to offline users.
                            from app.matcha.services.matcha_work.mentions import (
                                parse_mentions, resolve_mentions,
                            )
                            mention_handles = parse_mentions(row["content"])
                            mentioned_users = await resolve_mentions(
                                conn, ch_uuid, mention_handles, exclude_user_id=user.id,
                            ) if mention_handles else []
                            mentioned_user_ids = [str(m["id"]) for m in mentioned_users]

                            # EMS: ONE dispatch task, routed by
                            # _ems_dispatch_decision. Gated on is_new_message
                            # — an ON CONFLICT cmid-retry replay must not
                            # double-log (unique(message_id) on ems_events is
                            # the DB-side belt). Uses row["reply_to_id"]
                            # (post channel-scope validation above), not the
                            # raw parsed reply_uuid, so a dropped bogus/
                            # cross-channel target can't trigger clarify.
                            # resolve_mentions drops the unresolved "huume"
                            # handle (no huume channel_members row), so no
                            # mention email/notification noise from the
                            # trigger itself. Spawns nothing for an ordinary
                            # reply to a normal user message with no @huume
                            # mention — no task, no pooled connection, no
                            # ems_events probe for the common case.
                            spawn_ems, reply_to_system = _ems_dispatch_decision(
                                reply_target_type=reply_target_type if row["reply_to_id"] else None,
                                has_huume_mention="huume" in mention_handles,
                            )
                            if is_new_message and spawn_ems:
                                _spawn_bg(_bg_ems_dispatch(
                                    str(ch_uuid), str(row["id"]),
                                    str(row["reply_to_id"]) if reply_to_system else None,
                                    str(user.id), row["content"],
                                    has_huume_mention="huume" in mention_handles,
                                ))

                            await manager.broadcast_message(room_key, {
                                "id": str(row["id"]),
                                "channel_id": str(row["channel_id"]),
                                "sender_id": str(row["sender_id"]) if row["sender_id"] else None,
                                "sender_name": user.name,
                                "sender_avatar_url": user.avatar_url,
                                "content": row["content"],
                                "attachments": broadcast_attachments,
                                "reply_to_id": str(reply_uuid) if reply_uuid else None,
                                "reply_preview": reply_preview,
                                "reactions": [],
                                "created_at": row["created_at"].isoformat(),
                                "edited_at": None,
                                "mentioned_user_ids": mentioned_user_ids,
                                "client_message_id": client_message_id,
                                "message_type": row["message_type"],
                            })

                            # Off-load offline-email check to Celery so the WS
                            # hot path stays fast. Worker re-checks online state
                            # via Redis before sending. Gated on is_new_message
                            # so a retry doesn't queue a second mention email.
                            if mentioned_user_ids and is_new_message:
                                try:
                                    from app.workers.tasks.mention_email import send_mention_email
                                    send_mention_email.delay(
                                        message_id=str(row["id"]),
                                        channel_id=str(row["channel_id"]),
                                        sender_id=str(user.id),
                                        sender_name=user.name,
                                        content=row["content"] or "",
                                        mentioned_user_ids=mentioned_user_ids,
                                    )
                                except Exception:
                                    logger.exception("Failed to enqueue mention_email")

                            # In-app notifications for non-sender members.
                            # Skip on duplicate retry to avoid double-notify.
                            if is_new_message:
                                try:
                                    _ch_name = await conn.fetchval(
                                        "SELECT name FROM channels WHERE id = $1", ch_uuid
                                    )
                                    _members = await conn.fetch(
                                        """
                                        SELECT cm.user_id, COALESCE(c.company_id, e.org_id) AS company_id
                                        FROM channel_members cm
                                        JOIN users u ON u.id = cm.user_id
                                        LEFT JOIN clients c ON c.user_id = u.id
                                        LEFT JOIN employees e ON e.user_id = u.id
                                        WHERE cm.channel_id = $1 AND cm.user_id != $2
                                          AND cm.removed_for_inactivity IS NOT TRUE
                                        """,
                                        ch_uuid, user.id,
                                    )
                                    _preview = (row["content"] or "")[:80]
                                    _spawn_bg(_notify_channel_members(
                                        list(_members), _ch_name, user.name, _preview, str(ch_uuid),
                                    ))
                                except Exception:
                                    pass
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Not a member of this channel",
                            })

            elif msg_type == "typing":
                channel_id = data.get("channel_id")
                if channel_id:
                    room_key = _room_key(channel_id)
                    if room_key:
                        async with manager.lock:
                            is_room_member = user.id in manager.room_members.get(room_key, set())
                        if is_room_member:
                            await manager.broadcast_typing(room_key, user)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[Channel WS] Error: {e}")
    finally:
        await manager.disconnect(websocket, user.id)
        # Only clear the online key if this was the user's last active WS.
        # manager.active_connections drops the user_id when the set goes empty.
        if user.id not in manager.active_connections:
            await _mark_offline(user.id)
