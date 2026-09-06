"""Channel WebSocket handler for real-time group chat messaging."""

import asyncio
import json
import logging
import re
import time
from typing import Dict, Optional, Set
from uuid import UUID, uuid4

from cachetools import TTLCache
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from pydantic import BaseModel

from ...database import get_connection
from ...core.services.auth import decode_token
from ...core.services.redis_cache import get_redis_cache, check_rate_limit
from ...core.models.auth import CurrentUser
from ..services.channel_access import (
    ChannelCapability,
    ChannelScope,
    assert_channel_capability,
    channel_ops_automation_enabled,
    load_channel_access,
)

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


class _TokenBucket:
    """Per-socket send limiter: burst of 10, refill 1/s. Pure — caller
    supplies `now` (time.monotonic()) so tests need no clock patching.
    In-memory per worker: a reconnect resets the bucket, which is fine —
    the point is stopping a hot loop, not accounting."""
    __slots__ = ("burst", "refill", "tokens", "updated")

    def __init__(self, burst: int = 10, refill_per_sec: float = 1.0):
        self.burst = burst
        self.refill = refill_per_sec
        self.tokens = float(burst)
        self.updated: Optional[float] = None

    def allow(self, now: float) -> bool:
        if self.updated is not None:
            self.tokens = min(float(self.burst), self.tokens + (now - self.updated) * self.refill)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


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


# Channels that posted a schedule clarify pill recently (this process).
# Gates _bg_schedule_untargeted_reply's spawn so ordinary chat never costs a
# task + pooled connection + a schedule_chat_proposals scan — that table has
# no channel_id index, and without this gate the fallback's own query ran on
# every short (<=60 char) non-reply message in every company, schedule flag
# or not. A process restart empties the dict: the fallback goes dormant
# until the next clarify pill, which is acceptable for a best-effort
# convenience — threaded replies (the primary path) are unaffected.
_SCHEDULE_CLARIFY_TTL_SECONDS = 15 * 60
_recent_schedule_clarifies: Dict[str, float] = {}


def _note_schedule_clarify(channel_id_str: str) -> None:
    now = time.monotonic()
    stale = [k for k, deadline in _recent_schedule_clarifies.items() if deadline < now]
    for k in stale:
        _recent_schedule_clarifies.pop(k, None)
    _recent_schedule_clarifies[channel_id_str] = now + _SCHEDULE_CLARIFY_TTL_SECONDS


def _channel_recently_clarified(channel_id_str: str) -> bool:
    deadline = _recent_schedule_clarifies.get(channel_id_str)
    return deadline is not None and deadline >= time.monotonic()


# Channels that posted an event-draft pill recently (this process). Gates the
# _bg_ems_draft_untargeted_reply spawn below, same reasoning as
# _recent_schedule_clarifies: keep ordinary chat off the DB. A process
# restart empties the dict and the fallback goes dormant until the next
# pill — threaded replies (the primary path) are unaffected.
_EMS_DRAFT_TTL_SECONDS = 15 * 60
_recent_ems_drafts: Dict[str, float] = {}


def _note_ems_draft(channel_id_str: str) -> None:
    now = time.monotonic()
    stale = [k for k, deadline in _recent_ems_drafts.items() if deadline < now]
    for k in stale:
        _recent_ems_drafts.pop(k, None)
    _recent_ems_drafts[channel_id_str] = now + _EMS_DRAFT_TTL_SECONDS


def _channel_recently_ems_drafted(channel_id_str: str) -> bool:
    deadline = _recent_ems_drafts.get(channel_id_str)
    return deadline is not None and deadline >= time.monotonic()


def _autopr_context_reference(raw_metadata) -> Optional[dict]:
    """Return a validated Espresso AutoPR context pointer, if present."""
    if isinstance(raw_metadata, str):
        try:
            raw_metadata = json.loads(raw_metadata)
        except (TypeError, ValueError):
            return None
    if not isinstance(raw_metadata, dict) or raw_metadata.get("kind") != "autopr_context_request":
        return None
    try:
        project_id = UUID(str(raw_metadata.get("project_id")))
        task_id = UUID(str(raw_metadata.get("task_id")))
    except (TypeError, ValueError):
        return None
    expected = str(raw_metadata.get("expected_progress_note") or "").strip()
    if not expected:
        return None
    return {
        "project_id": project_id,
        "task_id": task_id,
        "expected_progress_note": expected,
    }


async def _bg_apply_autopr_context_reply(
    channel_id_str: str,
    user,
    content: str,
    reference: dict,
    attachments: Optional[list] = None,
) -> None:
    """Turn a direct reply to Espresso into decision-bound card evidence."""
    try:
        from app.matcha.services.matcha_work.project_agent.chat import post_as_espresso
        from app.matcha.services.matcha_work.project_task_service import (
            AutoPRReconsiderationConflict,
            request_autopr_reconsideration,
        )

        project_id = reference["project_id"]
        task_id = reference["task_id"]
        channel_id = UUID(channel_id_str)
        text = re.sub(
            r"(?i)(?:(?<=^)|(?<=\s))@espresso\b", "", content or "", count=1,
        ).strip()
        async with get_connection() as conn:
            project = await conn.fetchrow(
                """SELECT p.company_id,
                          EXISTS(
                            SELECT 1 FROM mw_project_collaborators pc
                            WHERE pc.project_id=p.id AND pc.user_id=$3
                              AND pc.status='active'
                          ) AS is_collaborator,
                          EXISTS(
                            SELECT 1 FROM clients c
                            WHERE c.user_id=$3 AND c.company_id=p.company_id
                          ) OR EXISTS(
                            SELECT 1 FROM employees e
                            WHERE e.user_id=$3 AND e.org_id=p.company_id
                          ) AS is_same_company
                   FROM mw_projects p
                   WHERE p.id=$1
                     AND p.project_data->>'discussion_channel_id'=$2""",
                project_id,
                channel_id_str,
                user.id,
            )
        if not project:
            return
        if not (
            project["is_collaborator"]
            or project["is_same_company"]
            or (getattr(user, "role", "") or "").lower() == "admin"
        ):
            await post_as_espresso(
                project["company_id"], channel_id,
                "I can only attach context from someone who can access this project.",
            )
            return
        if not text and not attachments:
            await post_as_espresso(
                project["company_id"], channel_id,
                "Please include the missing detail or a screenshot in your reply, or add it from the ticket.",
            )
            return
        attachment_ids = []
        if attachments:
            from app.matcha.services.matcha_work.project_file_service import (
                sync_channel_attachments_to_task,
            )
            async with get_connection() as conn:
                attachment_ids = await sync_channel_attachments_to_task(
                    conn, project_id, task_id, user.id, attachments,
                )
            if not attachment_ids and not text:
                await post_as_espresso(
                    project["company_id"], channel_id,
                    "I couldn't attach that screenshot to the ticket. Please upload it from the ticket and resend the context.",
                )
                return
        try:
            result = await request_autopr_reconsideration(
                project_id=project_id,
                task_id=task_id,
                actor_user_id=user.id,
                expected_progress_note=reference["expected_progress_note"],
                body=text or None,
                attachment_ids=attachment_ids or None,
            )
        except AutoPRReconsiderationConflict:
            await post_as_espresso(
                project["company_id"], channel_id,
                "That AutoPR decision changed before this reply arrived. Open the linked ticket to review its current state.",
            )
            return
        if result is None:
            return
        directives = set(result.get("autopr_directives") or [])
        directive_note = ""
        if "draft_pr" in directives:
            directive_note += " The draft-PR requirement is active."
        if "trust_still_broken" in directives:
            directive_note += " The still-broken assertion is active."
        if "extend_runtime" in directives:
            directive_note += " The 10-minute continuation is approved."
        await post_as_espresso(
            project["company_id"], channel_id,
            "Thanks — I attached your reply and any screenshots as escalated AutoPR context."
            + directive_note
            + " This ticket now goes ahead of routine rework in the next plan.",
        )
    except Exception:
        logger.warning("AutoPR context reply failed", exc_info=True)


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


async def _bg_dispatch_espresso_mention(
    channel_id_str: str,
    user,
    content: str,
    trigger_message_id: UUID,
) -> bool:
    """Queue one read-only repo question for a linked project discussion.

    Channel membership is not treated as repository authorization: same-tenant
    users or active project collaborators are re-checked before the process-
    global GitHub read token can be used. Returns whether a project discussion
    claimed the mention; raw ``@espresso`` text elsewhere stays ordinary chat.
    """
    claimed = False
    try:
        from app.core.feature_flags import merge_company_features
        from app.matcha.services.matcha_work.project_agent.chat import post_as_espresso
        from app.matcha.services.matcha_work.project_agent.guards import can_ask_project_agent
        from app.matcha.services.billing import token_budget_service
        from app.workers.tasks.project_agent import run_repo_question

        async with get_connection() as conn:
            project = await conn.fetchrow(
                """SELECT p.id, p.company_id, p.github_repo,
                          c.enabled_features, c.signup_source
                   FROM mw_projects p
                   JOIN companies c ON c.id=p.company_id
                   WHERE p.project_data->>'discussion_channel_id'=$1""",
                channel_id_str,
            )
            if not project:
                return False
            claimed = True
            company_id = project["company_id"]
            channel_id = UUID(channel_id_str)
            features = merge_company_features(
                project["enabled_features"], project["signup_source"],
            )
            if not features.get("matcha_work"):
                await post_as_espresso(
                    company_id, channel_id,
                    "Espresso repository questions aren't enabled for this workspace.",
                )
                return True

            collaborator_role = await conn.fetchval(
                """SELECT role FROM mw_project_collaborators
                   WHERE project_id=$1 AND user_id=$2 AND status='active'""",
                project["id"], user.id,
            )
            sender_role = (getattr(user, "role", "") or "").lower()
            sender_company_id = None
            if sender_role in ("client", "individual"):
                sender_company_id = await conn.fetchval(
                    "SELECT company_id FROM clients WHERE user_id=$1", user.id,
                )
            elif sender_role == "employee":
                sender_company_id = await conn.fetchval(
                    "SELECT org_id FROM employees WHERE user_id=$1", user.id,
                )
            if not can_ask_project_agent(
                sender_company_id=sender_company_id,
                project_company_id=company_id,
                collaborator_role=collaborator_role,
            ):
                await post_as_espresso(
                    company_id, channel_id,
                    "I can only inspect the repository for people who can access this project.",
                )
                return True
            if not project["github_repo"]:
                await post_as_espresso(
                    company_id, channel_id,
                    "Connect a GitHub repository in Elements before asking me about the app.",
                )
                return True

            # Strip the first virtual-agent mention before persisting the task;
            # keep every other character exactly as the user wrote it.
            question = re.sub(
                r"(?i)(?:(?<=^)|(?<=\s))@espresso\b", "", content or "", count=1,
            ).strip()
            if not question:
                await post_as_espresso(
                    company_id, channel_id,
                    "Ask me a question about how this project or its connected repository works.",
                )
                return True
            if sender_role != "admin":
                try:
                    await token_budget_service.check_token_budget(company_id)
                except HTTPException:
                    await post_as_espresso(
                        company_id, channel_id,
                        "This workspace has reached its Matcha Work AI token budget.",
                    )
                    return True
            try:
                await check_rate_limit(str(company_id), "espresso_repo_question", 20, 3600)
            except HTTPException:
                await post_as_espresso(
                    company_id, channel_id,
                    "Espresso has reached this workspace's hourly repo-question limit. Please try again later.",
                )
                return True

            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))", str(project["id"]),
                )
                live = await conn.fetchval(
                    """SELECT EXISTS(
                           SELECT 1 FROM mw_project_agent_runs
                           WHERE project_id=$1 AND kind='repo_question'
                             AND status IN ('queued','running')
                             AND COALESCE(started_at, created_at) > NOW() - INTERVAL '15 minutes'
                       )""",
                    project["id"],
                )
                if live:
                    await post_as_espresso(
                        company_id, channel_id,
                        "I'm already answering a repository question for this project. Ask me again when that answer lands.",
                    )
                    return True
                run_id = await conn.fetchval(
                    """INSERT INTO mw_project_agent_runs
                       (company_id, project_id, channel_id, requested_by,
                        trigger_message_id, agent_key, kind, prompt, status)
                       VALUES ($1,$2,$3,$4,$5,'espresso','repo_question',$6,'queued')
                       ON CONFLICT (trigger_message_id, agent_key) DO NOTHING
                       RETURNING id""",
                    company_id, project["id"], channel_id, user.id,
                    trigger_message_id, question,
                )
            if run_id is None:
                return True
            try:
                run_repo_question.delay(str(run_id))
            except Exception:
                logger.exception(
                    "Failed to enqueue Espresso project-agent run=%s", run_id,
                )
                failed_run_id = await conn.fetchval(
                    """UPDATE mw_project_agent_runs
                       SET status='failed', completed_at=NOW(),
                           error='Task enqueue failed before worker delivery.'
                       WHERE id=$1 AND status='queued'
                       RETURNING id""",
                    run_id,
                )
                if failed_run_id is not None:
                    await post_as_espresso(
                        company_id,
                        channel_id,
                        "I couldn't queue that repository question right now. Please try again.",
                    )
                    return True

        await post_as_espresso(
            company_id, channel_id,
            "I’m reading the connected repository now. I’ll post a source-linked answer here when the task finishes.",
        )
        return True
    except Exception:
        logger.warning("Espresso project-agent dispatch failed", exc_info=True)
        return claimed


async def _bg_maybe_dispatch_huume_code(channel_id_str: str, user, content: str, trigger_message_id) -> bool:
    """Queue one collab-chat code run and report whether it claimed the mention.

    A linked collab discussion channel belongs to Huume Code even when it must
    refuse the request (flag off, missing repo, or insufficient access). Other
    channels fall through to the existing EMS mention dispatcher.
    """
    claimed = False
    try:
        from app.core.feature_flags import merge_company_features
        from app.matcha.services.huume_code.chat import post_as_huume
        from app.matcha.services.huume_code.guards import can_dispatch_huume_code
        from app.core.services.redis_cache import check_rate_limit
        from app.workers.tasks.huume_code import run_huume_code

        async with get_connection() as conn:
            project = await conn.fetchrow(
                """SELECT p.id, p.company_id, p.github_repo, p.github_branch,
                          c.is_personal, c.enabled_features, c.signup_source
                   FROM mw_projects p JOIN companies c ON c.id=p.company_id
                   WHERE p.project_type='collab'
                     AND p.project_data->>'discussion_channel_id'=$1""",
                channel_id_str,
            )
            if not project:
                return False
            claimed = True
            company_id = project["company_id"]
            channel_id = UUID(channel_id_str)
            features = merge_company_features(project["enabled_features"], project["signup_source"])
            if project["is_personal"] or not (features.get("matcha_work") and features.get("huume_code")):
                await post_as_huume(company_id, channel_id, "Huume code isn't enabled for this workspace.")
                return True
            sender_role = (getattr(user, "role", "") or "").lower()
            if sender_role not in ("client", "admin"):
                await post_as_huume(company_id, channel_id, "Only a project editor who is a business admin can ask Huume to write code.")
                return True
            # Channel membership can cross company boundaries. Re-check both
            # company ownership and the project collaborator role here; a
            # client who happens to sit in another company's channel must not
            # gain its repo write capability through the global GitHub token.
            collaborator_role = await conn.fetchval(
                """SELECT role FROM mw_project_collaborators
                   WHERE project_id=$1 AND user_id=$2 AND status='active'""",
                project["id"], user.id,
            )
            sender_company_id = None
            if sender_role == "client":
                sender_company_id = await conn.fetchval(
                    "SELECT company_id FROM clients WHERE user_id=$1", user.id,
                )
                # A same-company business user is the project owner unless
                # explicitly added as a collaborator; match _verify_project_access.
                collaborator_role = collaborator_role or "owner"
            if not can_dispatch_huume_code(
                sender_role=sender_role,
                sender_company_id=sender_company_id,
                project_company_id=company_id,
                collaborator_role=collaborator_role,
            ):
                await post_as_huume(company_id, channel_id, "Only a project editor who is a business admin can ask Huume to write code.")
                return True
            if not project["github_repo"]:
                await post_as_huume(company_id, channel_id, "Connect a GitHub repo in Elements first.")
                return True
            try:
                await check_rate_limit(str(company_id), "huume_code_run", 10, 3600)
            except HTTPException:
                await post_as_huume(company_id, channel_id, "Huume has reached this company's hourly code-run limit. Please try again later.")
                return True
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(project["id"]))
                live = await conn.fetchval(
                    """SELECT EXISTS(SELECT 1 FROM huume_code_runs
                       WHERE project_id=$1 AND status IN ('queued','running')
                         AND COALESCE(started_at, created_at) > NOW() - INTERVAL '15 minutes')""",
                    project["id"],
                )
                if live:
                    await post_as_huume(company_id, channel_id, "Huume is already working on this project. I'll post the draft PR here when it's ready.")
                    return True
                run_id = await conn.fetchval(
                    """INSERT INTO huume_code_runs
                       (company_id, project_id, channel_id, requested_by, trigger_message_id, status)
                       VALUES ($1,$2,$3,$4,$5,'queued') RETURNING id""",
                    company_id, project["id"], channel_id, user.id, trigger_message_id,
                )
            run_huume_code.delay(str(run_id))
        await post_as_huume(company_id, channel_id, "Got it — I'll review the board and repository, then open a draft PR for review.")
        return True
    except Exception:
        logger.warning("Huume code dispatch failed", exc_info=True)
        return claimed


async def _bg_dispatch_huume_mention(
    channel_id_str: str,
    message_id_str: str,
    reply_to_system_id_str: Optional[str],
    user,
    content: str,
) -> None:
    """Send an @huume mention to exactly one of code or EMS.

    A reply to an EMS system message preserves EMS's clarify-first behavior.
    Otherwise a linked collab discussion channel claims the mention for Huume
    Code; all other channels retain the established EMS behavior.
    """
    if reply_to_system_id_str is not None:
        await _bg_ems_dispatch(
            channel_id_str, message_id_str, reply_to_system_id_str, str(user.id), content,
            has_huume_mention=True,
        )
        return
    if await _bg_maybe_dispatch_huume_code(channel_id_str, user, content, UUID(message_id_str)):
        return
    await _bg_ems_dispatch(
        channel_id_str, message_id_str, None, str(user.id), content, has_huume_mention=True,
    )


def _row_metadata(sys_row) -> dict:
    """A system message's metadata, decoded.

    asyncpg hands JSONB back as a str — no set_type_codec('jsonb', …) is
    registered on the pool (app/database/pool.py:init_pool). The REST read
    path decodes explicitly (routes/channels.py:155); this one did not, so a
    live Huume pill reached the client with metadata as a raw JSON *string*,
    `msg.metadata?.action` was undefined, and the Confirm/Reject card only
    appeared after leaving and re-entering the channel (when the decoded REST
    snapshot replaced it). Applies to every card kind, not just event_draft —
    this is the shared payload builder for every broadcast_system_message
    call site."""
    raw = dict(sys_row).get("metadata")
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return raw or {}


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
        "metadata": _row_metadata(sys_row),
    }


async def _insert_system_message(
    conn,
    channel_id_str: str,
    content: str,
    *,
    metadata: Optional[dict] = None,
):
    """INSERT one message_type='system' channel_messages row. Shared by
    _bg_ems_intake and _bg_ems_clarify."""
    return await conn.fetchrow(
        """
        INSERT INTO channel_messages
            (channel_id, sender_id, content, message_type, metadata)
        VALUES ($1, NULL, $2, 'system', $3::jsonb)
        RETURNING id, channel_id, content, message_type, metadata, created_at
        """,
        UUID(channel_id_str), content, json.dumps(metadata or {}),
    )


def _ems_row_allowed(row) -> bool:
    """Shared predicate for _ems_company_gate/_ems_flag_enabled: not a
    personal company AND the merged features carry `ems`. The merge itself
    is core's merge_company_features — this is the one place werk applies
    it, instead of each caller (and routes/ems.py's now-deleted private
    copy) re-deriving the overlay."""
    if not row or row["is_personal"] or row.get("channel_scope") != ChannelScope.OPERATIONS.value:
        return False
    from app.core.feature_flags import merge_company_features
    features = merge_company_features(row["enabled_features"], row["signup_source"])
    return bool(features.get("matcha_ops") and features.get("ems"))


async def _ems_company_gate(conn, channel_id_str: str):
    """Company/is_personal/`ems`-flag lookup for _bg_ems_intake, keyed on the
    channel (that's all intake has). Returns the company_id UUID, or None if
    the caller should silently no-op (personal company, or `ems` not
    enabled)."""
    row = await conn.fetchrow(
        """
        SELECT ch.company_id, comp.is_personal, comp.enabled_features,
               COALESCE(ch.channel_scope, 'operations') AS channel_scope,
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
    if not row or row["is_personal"]:
        return False
    from app.core.feature_flags import merge_company_features
    features = merge_company_features(row["enabled_features"], row["signup_source"])
    return bool(features.get("matcha_ops") and features.get("ems"))


def _inventory_row_allowed(row) -> bool:
    """Same shape as _ems_row_allowed, keyed on the `inventory` flag."""
    if not row or row["is_personal"] or row.get("channel_scope") != ChannelScope.OPERATIONS.value:
        return False
    from app.core.feature_flags import merge_company_features
    features = merge_company_features(row["enabled_features"], row["signup_source"])
    return bool(features.get("matcha_ops") and features.get("inventory"))


async def _inventory_company_gate(conn, channel_id_str: str):
    row = await conn.fetchrow(
        """
        SELECT ch.company_id, comp.is_personal, comp.enabled_features,
               COALESCE(ch.channel_scope, 'operations') AS channel_scope,
               comp.signup_source
        FROM channels ch JOIN companies comp ON comp.id = ch.company_id
        WHERE ch.id = $1
        """,
        UUID(channel_id_str),
    )
    return row["company_id"] if _inventory_row_allowed(row) else None


async def _asker_is_company_admin(conn, asker_user_id_str: str, role: Optional[str], company_id) -> bool:
    """Whether an asker whose global role is admin-tier is actually an admin
    OF THIS CHANNEL'S COMPANY. `role='admin'` is a platform admin (blanket
    access, same as everywhere else in the app); `role='client'` is a
    per-company business admin and must be re-checked against the channel's
    own company_id — channel membership isn't company-bounded (an
    invite-code join at `channels.py`'s accept-invite path, or a
    cross-company `user_connections` add-members flow, can seat a company-A
    client in a company-B channel), so trusting the bare role would hand
    that asker company B's incidents/PTO/credentials/training data and the
    `stage_inventory_order` write tool via `channel_grounding`'s admin-only
    topics."""
    if role == "admin":
        return True
    if role != "client":
        return False
    client_company_id = await conn.fetchval(
        "SELECT company_id FROM clients WHERE user_id = $1", UUID(asker_user_id_str),
    )
    return client_company_id == company_id


async def _channel_location(conn, channel_id_str: str):
    """(location_id, location_name) when the channel is store-scoped to an
    ACTIVE store, (None, None) otherwise. Gates stay untouched — their
    company_id return is consumed at 6+ sites; this is a separate indexed
    lookup callers make only while already holding a conn.

    Deactivated store == unscoped here, not "keep dispatching to it": the
    binding itself is untouched on the channel row (a reactivation restores
    scoping with no re-pick needed), but ems/inventory stop stamping and
    resolving against a store nobody can act on anymore. Matches
    `schedule_chat_rules.apply_channel_default_location`, which falls
    through to the normal clarify path for the same stale-binding case —
    the two must agree on what "deactivated" means."""
    row = await conn.fetchrow(
        "SELECT bl.id AS location_id, bl.name AS location_name "
        "FROM channels ch LEFT JOIN business_locations bl "
        "ON bl.id = ch.location_id AND bl.is_active IS NOT FALSE "
        "WHERE ch.id = $1",
        UUID(channel_id_str),
    )
    if not row or row["location_id"] is None:
        return None, None
    return row["location_id"], row["location_name"]


async def _channel_bound_to_inactive_location(conn, channel_id_str: str) -> bool:
    """True when the channel is bound to a store that has since gone
    inactive. Inventory's WRITE path must block on this rather than treat
    it like an unscoped channel (which `_channel_location` does) — falling
    through to `location_id=None` there means `find_or_create_item`
    auto-creates a company-wide twin of an existing store item, permanently
    forking the stock ledger. schedule_chat's fallthrough is a clarify
    question, not a write, so it doesn't need this.

    `_bg_ems_ask`'s channel-grounding READ path needs it too, for the
    opposite reason: `_channel_location` returning `(None, None)` here would
    otherwise read as "unscoped", which for `channel_grounding.py`'s
    location-scoped topics (schedule/incidents/inventory) means "answer
    company-wide" — a real widening from one store's data to every store's,
    not the narrowing it is on the write paths above. A dead store must
    make those topics refuse, never expand."""
    row = await conn.fetchrow(
        "SELECT ch.location_id, bl.is_active FROM channels ch "
        "LEFT JOIN business_locations bl ON bl.id = ch.location_id "
        "WHERE ch.id = $1",
        UUID(channel_id_str),
    )
    return bool(row and row["location_id"] is not None and row["is_active"] is False)


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


async def _bg_ems_ask(
    channel_id_str: str, asker_user_id_str: str, content: str, intent: str,
    skip_rate_limit: bool = False,
) -> None:
    """Answer an "@huume what's been logged in here?" (ASK) or "@huume help"
    (HELP) instead of logging an event. Same off-hot-path, top-level-except,
    never-affects-send-latency contract as _bg_ems_intake.

    Visibility is decided in `services/ems/ask`, not here — see that
    module's docstring for why a channel answer can't reuse the
    admin-only REST gate. This function only supplies the two inputs that
    decision needs: the company (via the same _ems_company_gate) and the
    asker's role.

    Beyond ems_events, the answer is grounded on schedule/inventory/
    incidents/HR-ops data via `services/ems/channel_agent.py`'s bounded
    tool-calling loop, which decides FOR ITSELF (one topic per tool call,
    only the topics the question asks about) rather than being handed every
    topic this asker is merely allowed to see. `channel_grounding.py`
    remains the policy registry (which topics exist, admin/feature/location
    gates) — this function only resolves the two things that policy needs:
    the channel's store binding and whether that store is still active.

    Rate-limited on its own `ems_ask` key rather than the `ems_event` one:
    logging is the documentation-critical path, and a chatty afternoon of
    questions must never exhaust the budget that lets a real event be
    written down. `skip_rate_limit=True` is for the `_bg_ems_intake` model
    backstop, which already consumed one `ems_event` token to get here —
    charging `ems_ask` too would burn both budgets for a single message,
    defeating the reason they're split.

    Two connection blocks, same reasoning as _bg_ems_intake — no pooled
    connection is held across the loop's Gemini calls (channel_agent.py
    opens its own connection per tool call)."""
    try:
        from app.matcha.services.ems import ask as ems_ask
        from app.matcha.services.ems import channel_agent, channel_grounding
        from app.matcha.services.ems.intent import HELP, strip_mention

        sys_row = None
        events = None
        is_admin = False
        hidden = False
        recent_block = ""

        async with get_connection() as conn:
            company_id = await _ems_company_gate(conn, channel_id_str)
            if company_id is None:
                return
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(asker_user_id_str))
            is_admin = await _asker_is_company_admin(conn, asker_user_id_str, role, company_id)
            features = await _schedule_company_features(conn, company_id)
            loc_id, _loc_name = await _channel_location(conn, channel_id_str)
            location_unavailable = loc_id is None and await _channel_bound_to_inactive_location(
                conn, channel_id_str,
            )

            if intent == HELP:
                extra_lines = channel_grounding.help_lines(
                    features=features, is_admin=is_admin, location_unavailable=location_unavailable,
                )
                text = ems_ask.help_text(is_admin=is_admin, extra_lines=tuple(extra_lines))
                sys_row = await _insert_system_message(conn, channel_id_str, text)
            else:
                if not skip_rate_limit:
                    try:
                        await check_rate_limit(str(company_id), "ems_ask", 30, 3600)
                    except HTTPException:
                        return  # over the hourly limit: skip silently, same as intake

                events = await ems_ask.fetch_channel_events(
                    conn, company_id=company_id, channel_id=UUID(channel_id_str),
                    include_behavioral=is_admin,
                )
                reachable = channel_grounding.reachable_topics(
                    features=features, is_admin=is_admin, location_unavailable=location_unavailable,
                )
                stage_inventory_available = bool(features.get("inventory")) and not location_unavailable

                # "Nothing you can see" and "nothing happened" must not read
                # as the same sentence — see ask.no_events_text. This probe
                # runs whenever events are empty and the asker isn't an
                # admin, independent of whether the loop below even runs,
                # so a schedule/inventory-only answer still can't imply the
                # room's ems_events are clean when a behavioral one exists.
                if not events and not is_admin:
                    hidden = bool(await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM ems_events
                            WHERE channel_id = $1 AND company_id = $2 AND status <> 'dismissed'
                        )
                        """,
                        UUID(channel_id_str), company_id,
                    ))

                if not events and not reachable and not stage_inventory_available:
                    text = ems_ask.no_events_text(filtered=hidden)
                    sys_row = await _insert_system_message(conn, channel_id_str, text)
                elif is_admin and "schedule" in [t.topic for t in reachable]:
                    # Only fetched for the admin+schedule case that can
                    # actually use it (propose_schedule_change resolving
                    # anaphora) — an extra query on every plain ASK isn't
                    # worth it for the common case that never needs it.
                    recent_rows = await conn.fetch(
                        f"""
                        SELECT m.content, COALESCE({_USER_NAME_EXPR}, 'Huume') AS sender_name
                        FROM channel_messages m
                        LEFT JOIN users u ON u.id = m.sender_id
                        LEFT JOIN clients c ON c.user_id = u.id
                        LEFT JOIN employees e ON e.user_id = u.id
                        LEFT JOIN admins a ON a.user_id = u.id
                        WHERE m.channel_id = $1 AND m.deleted_at IS NULL
                          AND m.message_type IS DISTINCT FROM 'system'
                        ORDER BY m.created_at DESC LIMIT 12
                        """,
                        UUID(channel_id_str),
                    )
                    recent_block = "\n".join(
                        f"{r['sender_name']}: {(r['content'] or '')[:200]}"
                        for r in reversed(recent_rows)
                    )

        # Broadcast AFTER the connection releases in every branch above —
        # holding a pooled connection across the fan-out isn't needed and
        # (the events==None loop path below) must never happen.
        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return

        # No connection held across the loop's Gemini calls.
        result = await channel_agent.answer_channel_question(
            question=strip_mention(content), events=events, is_admin=is_admin, filtered=hidden,
            company_id=company_id, channel_id=UUID(channel_id_str), asker_user_id=UUID(asker_user_id_str),
            asker_role=role, features=features, location_id=loc_id, location_unavailable=location_unavailable,
            recent_block=recent_block,
        )

        async with get_connection() as conn:
            sys_row = await _insert_system_message(conn, channel_id_str, result["message"])
            if result.get("pending_order_id"):
                await conn.execute(
                    "UPDATE inventory_orders SET confirm_message_id = $1 WHERE id = $2",
                    sys_row["id"], result["pending_order_id"],
                )
            elif result.get("pending_proposal_id"):
                # Stamped exactly like a deterministic-fork proposal — the
                # existing _bg_schedule_reply claim handles confirm/cancel/
                # clarify from here, no new reply-handling code needed.
                await conn.execute(
                    "UPDATE schedule_chat_proposals SET confirm_message_id = $1 WHERE id = $2",
                    sys_row["id"], result["pending_proposal_id"],
                )
                _note_schedule_clarify(channel_id_str)  # this build may be a clarify
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


async def _schedule_company_features(conn, company_id) -> dict:
    """Merged features for a company, `{}` for a personal company (never
    reached in practice — schedule pills only ever originate from a real
    tenant channel, but the guard mirrors `_ems_row_allowed`)."""
    from app.core.feature_flags import merge_company_features

    row = await conn.fetchrow(
        "SELECT is_personal, enabled_features, signup_source FROM companies WHERE id = $1",
        company_id,
    )
    if not row or row["is_personal"]:
        return {}
    features = merge_company_features(row["enabled_features"], row["signup_source"])
    if not features.get("matcha_ops"):
        features["employee_schedule"] = False
        features["schedule_intelligence"] = False
    return features


async def _bg_schedule_request(
    channel_id_str: str, message_id_str: str, sender_user_id_str: str, content: str,
) -> None:
    """"@huume I need an opener and a closer for our La Jolla store next
    week" — SCHEDULE-classified channel message. Same off-hot-path,
    top-level-except, never-affects-send-latency contract as _bg_ems_intake.

    Two connection blocks: the Gemini parse call (services/scheduling/
    schedule_chat.py:parse_schedule_request) must not run with a pooled
    connection held (same reasoning as _bg_ems_ask/_bg_ems_intake — the pool
    is capped at 10).

    Bias-to-LOG survives a SCHEDULE misroute: a parse that comes back
    non-actionable (Gemini outage, or the intent regex matched something
    that isn't really a staffing request) falls back to _bg_ems_intake so
    the message is still documented rather than silently dropped."""
    try:
        from datetime import date as _date

        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.scheduling import schedule_chat
        from app.matcha.services.scheduling.schedule_chat_rules import evaluate_schedule_proposal

        sys_row = None

        async with get_connection() as conn:
            channel_row = await conn.fetchrow(
                """
                SELECT ch.company_id, COALESCE(ch.channel_scope, 'operations') AS channel_scope,
                       comp.is_personal, comp.enabled_features, comp.signup_source
                  FROM channels ch
                  JOIN companies comp ON comp.id = ch.company_id
                 WHERE ch.id = $1
                """,
                UUID(channel_id_str),
            )
            if not channel_row or channel_row["is_personal"] or channel_row["channel_scope"] != "operations":
                return
            from app.core.feature_flags import merge_company_features
            channel_features = merge_company_features(
                channel_row["enabled_features"], channel_row["signup_source"]
            )
            company_id = channel_row["company_id"]
            if not channel_features.get("matcha_ops"):
                return

            # Rate-limit BEFORE any write: previously the authz-refusal pill
            # below was written+broadcast unconditionally, giving an
            # unbounded write/fan-out path to anyone retrying an unauthorized
            # request. Checking first bounds both the refusal pill and the
            # real flow on the same per-company budget.
            try:
                await check_rate_limit(str(company_id), "ems_schedule", 20, 3600)
            except HTTPException:
                return  # over the hourly limit: skip silently, same as ems_ask/ems_event

            features = await _schedule_company_features(conn, company_id)
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(sender_user_id_str))
            verdict = evaluate_schedule_proposal(role=role, features=features, stage="propose")
            if not verdict.ok:
                sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return

        # No connection held across the Gemini parse call.
        parsed = await schedule_chat.parse_schedule_request(strip_mention(content), _date.today())
        if parsed is None:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
            return
        action = parsed.get("action", "create")
        if action == "edit":
            if not parsed.get("edit_requests"):
                await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
                return
        elif not parsed.get("shift_requests"):
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
            return

        async with get_connection() as conn:
            if action == "edit":
                build = await schedule_chat.build_edit_proposal(
                    conn, company_id=company_id, channel_id=UUID(channel_id_str),
                    source_message_id=UUID(message_id_str), created_by=UUID(sender_user_id_str),
                    parsed=parsed, today=_date.today(), original_content=strip_mention(content),
                )
            else:
                build = await schedule_chat.build_proposal(
                    conn, company_id=company_id, channel_id=UUID(channel_id_str),
                    source_message_id=UUID(message_id_str), created_by=UUID(sender_user_id_str),
                    parsed=parsed, today=_date.today(), original_content=strip_mention(content),
                )
            sys_row = await _insert_system_message(conn, channel_id_str, build.pill_text)
            await conn.execute(
                "UPDATE schedule_chat_proposals SET confirm_message_id = $1, updated_at = NOW() WHERE id = $2",
                sys_row["id"], build.proposal_id,
            )
            if build.kind == "clarify":
                _note_schedule_clarify(channel_id_str)
        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
    except Exception:
        logger.exception("schedule chat request failed for message %s", message_id_str)


async def _bg_inventory_request(
    channel_id_str: str, message_id_str: str, sender_user_id_str: str, content: str,
) -> None:
    """"@huume we gifted some cookies to Elizabeth" / "@huume we ran out of
    salads again" — INVENTORY-classified channel message. Same off-hot-path
    contract as _bg_schedule_request. Two connection blocks: the Gemini
    extraction call must not run with a pooled connection held."""
    try:
        from app.matcha.services.ems.event_intake import fallback_classification
        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.inventory import movements as movements_service
        from app.matcha.services.inventory import orders as orders_service
        from app.matcha.services.inventory import pills
        from app.matcha.services.inventory import receipts as receipts_service
        from app.matcha.services.inventory.extraction import extract_inventory
        from app.matcha.services.inventory.reorder import suggest_order
        from app.matcha.services.inventory.rules import evaluate_inventory_action
        from app.matcha.services.inventory.waste import reasons

        sys_row = None
        item_rows = []
        osha_dual_write = False
        location_id = None
        stripped = strip_mention(content)

        async with get_connection() as conn:
            company_id = await _inventory_company_gate(conn, channel_id_str)
            if company_id is None:
                ems_company_id = await _ems_company_gate(conn, channel_id_str)
                delegate = ems_company_id is not None
            else:
                delegate = False
                try:
                    await check_rate_limit(str(company_id), "inventory_event", 30, 3600)
                except HTTPException:
                    return

                if fallback_classification(content).get("urgency") == "osha":
                    osha_dual_write = True

                location_id, _ = await _channel_location(conn, channel_id_str)
                features = await _schedule_company_features(conn, company_id)
                role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(sender_user_id_str))
                verdict = evaluate_inventory_action(role=role, features=features, stage="movement")
                if not verdict.ok:
                    sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)
                elif location_id is None and await _channel_bound_to_inactive_location(conn, channel_id_str):
                    sys_row = await _insert_system_message(
                        conn, channel_id_str,
                        "\U0001F4E6 This channel's store is deactivated, so inventory tracking is paused here. "
                        "Ask an admin to reactivate the store or rebind this channel.",
                    )
                elif sys_row is None:
                    item_rows = await movements_service.list_item_names(conn, company_id, location_id)

        if delegate:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
            return

        if company_id is None:
            return

        if osha_dual_write:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return

        item_names = [r["name"] for r in item_rows]
        extracted = await extract_inventory(stripped, item_names)

        if not extracted.get("actionable"):
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
            return

        kind = extracted.get("kind", "movement")
        lines = extracted.get("lines") or []

        async with get_connection() as conn:
            if kind == "movement":
                resolved_lines = []
                for line in lines:
                    item = await movements_service.find_or_create_item(
                        conn, company_id, line.get("item_name", ""),
                        created_by=UUID(sender_user_id_str), location_id=location_id,
                    )
                    qty = line.get("quantity")
                    estimated = qty is None
                    resolved_lines.append({
                        "item_id": item["id"], "quantity": 1 if estimated else qty, "estimated": estimated,
                    })
                inserted = await movements_service.record_movements(
                    conn, company_id=company_id, channel_id=UUID(channel_id_str),
                    source_message_id=UUID(message_id_str), recorded_by=UUID(sender_user_id_str),
                    kind="out", lines=resolved_lines, narrative=stripped,
                    note=extracted.get("recipient_note"),
                )
                if not inserted:
                    return
                first = inserted[0]
                item_row = await conn.fetchrow(
                    "SELECT name, current_quantity FROM inventory_items WHERE id = $1", first["item_id"],
                )
                pill_text = pills.movement_pill(
                    item_row["name"], first["quantity"], item_row["current_quantity"],
                    extracted.get("recipient_note"), first["quantity_estimated"],
                )
                single_unknown = len(inserted) == 1 and inserted[0]["quantity_estimated"]
                if single_unknown:
                    pill_text = pills.quantity_question(pill_text)
                sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                if single_unknown:
                    await conn.execute(
                        "UPDATE inventory_movements SET clarify_message_id = $1 WHERE id = $2",
                        sys_row["id"], inserted[0]["id"],
                    )

            elif kind == "waste":
                waste_verdict = evaluate_inventory_action(role=role, features=features, stage="waste")
                if not waste_verdict.ok:
                    sys_row = await _insert_system_message(conn, channel_id_str, waste_verdict.reason)
                else:
                    # Same provenance invariant as `return`: waste is a
                    # first-hand observed LOSS, never a fabrication, so
                    # free-form chat needs no confirm step — but it also
                    # never auto-creates an item, matching `return`'s bar
                    # (mint the catalog row on the page, not from a chat
                    # aside about throwing something away).
                    raw_reason = extracted.get("waste_reason")
                    reason = reasons.coerce_chat_reason(raw_reason)
                    reason_coerced = raw_reason != reason
                    resolved_lines = []
                    unmatched_names = []
                    for line in lines:
                        raw_name = line.get("item_name", "")
                        item = await movements_service.find_item(
                            conn, company_id, raw_name, location_id, existing=item_rows,
                        )
                        if item is None:
                            unmatched_names.append(raw_name)
                            continue
                        qty = line.get("quantity")
                        estimated = qty is None
                        resolved_lines.append({
                            "item_id": item["id"], "quantity": 1 if estimated else qty,
                            "estimated": estimated, "waste_reason": reason,
                        })
                    if not resolved_lines:
                        pill_text = pills.waste_unmatched_pill(unmatched_names[0] if unmatched_names else None)
                        sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                    else:
                        inserted = await movements_service.record_movements(
                            conn, company_id=company_id, channel_id=UUID(channel_id_str),
                            source_message_id=UUID(message_id_str), recorded_by=UUID(sender_user_id_str),
                            kind="waste", lines=resolved_lines, narrative=stripped,
                            note=extracted.get("recipient_note"),
                        )
                        if inserted:
                            first = inserted[0]
                            item_row = await conn.fetchrow(
                                "SELECT name, current_quantity FROM inventory_items WHERE id = $1", first["item_id"],
                            )
                            pill_text = pills.waste_pill(
                                item_row["name"], first["quantity"], item_row["current_quantity"],
                                reason, first["quantity_estimated"], reason_coerced=reason_coerced,
                            )
                            single_unknown = len(inserted) == 1 and inserted[0]["quantity_estimated"]
                            if single_unknown:
                                pill_text = pills.quantity_question(pill_text)
                            sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                            if single_unknown:
                                await conn.execute(
                                    "UPDATE inventory_movements SET clarify_message_id = $1 WHERE id = $2",
                                    sys_row["id"], inserted[0]["id"],
                                )

            elif kind == "receipt":
                # Provenance invariant (services/inventory/CLAUDE.md): a
                # delivery reported in chat is NEVER auto-created or booked as
                # a bare `in` movement — it only checks in against an item's
                # own open order. No clarify-arm here (that machinery is
                # out-only now); an unmatched line just steers toward a real
                # audit trail (Receive Delivery / an invoice).
                result = await receipts_service.receive_channel_lines(
                    conn, company_id=company_id, location_id=location_id,
                    user_id=UUID(sender_user_id_str), source_message_id=UUID(message_id_str),
                    note=extracted.get("recipient_note"),
                    lines=[{"item_name": l.get("item_name", ""), "quantity": l.get("quantity")} for l in lines],
                )
                pill_text = pills.channel_receipt_pill(result["received"], result["unmatched"])
                sys_row = await _insert_system_message(conn, channel_id_str, pill_text)

            elif kind == "return":
                # Chat-only ADDITION exception (services/inventory/CLAUDE.md
                # provenance invariant): a return needs no invoice/receipt/
                # CSV, unlike every other addition — but it still never
                # AUTO-CREATES an item the way movement/stockout do, since
                # returning stock the company never tracked would otherwise
                # mint a catalog row from an unreviewed chat claim.
                resolved_lines = []
                unmatched_names = []
                for line in lines:
                    raw_name = line.get("item_name", "")
                    item = await movements_service.find_item(
                        conn, company_id, raw_name, location_id, existing=item_rows,
                    )
                    if item is None:
                        unmatched_names.append(raw_name)
                        continue
                    qty = line.get("quantity")
                    estimated = qty is None
                    resolved_lines.append({
                        "item_id": item["id"], "quantity": 1 if estimated else qty, "estimated": estimated,
                    })
                if not resolved_lines:
                    pill_text = pills.return_unmatched_pill(unmatched_names[0] if unmatched_names else None)
                    sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                else:
                    inserted = await movements_service.record_movements(
                        conn, company_id=company_id, channel_id=UUID(channel_id_str),
                        source_message_id=UUID(message_id_str), recorded_by=UUID(sender_user_id_str),
                        kind="in", lines=resolved_lines, narrative=stripped,
                        # A chat return is the one addition kind that skips
                        # invoice/receipt/order provenance (CLAUDE.md
                        # invariant) — the fallback note is what still lets
                        # an auditor tell it apart from a delivery-backed
                        # `in` row when the reporter added no aside.
                        note=extracted.get("recipient_note") or "Customer return (chat)",
                    )
                    if inserted:
                        first = inserted[0]
                        item_row = await conn.fetchrow(
                            "SELECT name, current_quantity FROM inventory_items WHERE id = $1", first["item_id"],
                        )
                        pill_text = pills.return_pill(
                            item_row["name"], first["quantity"], item_row["current_quantity"],
                            first["quantity_estimated"], unmatched_names,
                        )
                        single_unknown = len(inserted) == 1 and inserted[0]["quantity_estimated"]
                        if single_unknown:
                            pill_text = pills.quantity_question(pill_text)
                        sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                        if single_unknown:
                            await conn.execute(
                                "UPDATE inventory_movements SET clarify_message_id = $1 WHERE id = $2",
                                sys_row["id"], inserted[0]["id"],
                            )

            else:  # stockout / order_request
                item_name = lines[0].get("item_name") if lines else stripped
                item = await movements_service.find_or_create_item(
                    conn, company_id, item_name,
                    created_by=UUID(sender_user_id_str), location_id=location_id,
                )
                if kind == "stockout":
                    await movements_service.record_movements(
                        conn, company_id=company_id, channel_id=UUID(channel_id_str),
                        source_message_id=UUID(message_id_str), recorded_by=UUID(sender_user_id_str),
                        kind="stockout", lines=[{"item_id": item["id"], "quantity": None, "estimated": False}],
                        narrative=stripped, note=None,
                    )
                history_rows = await conn.fetch(
                    "SELECT kind, quantity, quantity_delta, created_at FROM inventory_movements "
                    "WHERE item_id = $1 ORDER BY created_at ASC",
                    item["id"],
                )
                from datetime import datetime, timezone
                suggestion = suggest_order([dict(r) for r in history_rows], datetime.now(timezone.utc))
                order_qty = suggestion.get("suggested_quantity") if suggestion else None

                order = await orders_service.stage_order(
                    conn, company_id=company_id, item_id=item["id"], channel_id=UUID(channel_id_str),
                    source_message_id=UUID(message_id_str), created_by=UUID(sender_user_id_str),
                    suggestion=suggestion,
                )
                pill_text = (
                    pills.stockout_pill(item["name"], suggestion, order_qty) if kind == "stockout"
                    else pills.reorder_pill(item["name"], suggestion, order_qty)
                )
                sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                await conn.execute(
                    "UPDATE inventory_orders SET confirm_message_id = $1 WHERE id = $2",
                    sys_row["id"], order["id"],
                )

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))

        # Returns and waste are both reportable operational events, not just
        # ledger corrections. Preserve the channel narrative in Ops while the
        # inventory movement records the quantity and reason. OSHA reports
        # already took this path above, so do not create a duplicate event.
        if kind in {"return", "waste"} and not osha_dual_write:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
    except Exception:
        logger.exception("inventory chat request failed for message %s", message_id_str)


async def _bg_inventory_reply(
    channel_id_str: str, reply_to_id_str: str, sender_user_id_str: str, content: str,
) -> bool:
    """Fold a reply-to-an-inventory-pill into its order or clarify-armed
    movement. Same claim-then-act, exception-safe contract as
    _bg_schedule_reply — returns True iff a claim matched (order OR
    movement), so _bg_ems_dispatch knows whether to still try the mention
    fork. No Gemini call anywhere in this path."""
    claim_happened = False
    try:
        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.inventory import movements as movements_service
        from app.matcha.services.inventory import orders as orders_service
        from app.matcha.services.inventory import pills
        from app.matcha.services.inventory.rules import evaluate_inventory_action, parse_quantity_reply
        from app.matcha.services.scheduling.schedule_chat_rules import parse_confirm_reply

        reply_uuid = UUID(reply_to_id_str)
        sender_uuid = UUID(sender_user_id_str)
        stripped = strip_mention(content)
        sys_row = None

        async with get_connection() as conn:
            if not await channel_ops_automation_enabled(
                conn, channel_id=UUID(channel_id_str), feature="inventory"
            ):
                return False
            async with conn.transaction():
                claimed_order = await conn.fetchrow(
                    """
                    UPDATE inventory_orders SET confirm_message_id = NULL, updated_at = NOW()
                    WHERE confirm_message_id = $1 AND channel_id = $2 AND status = 'queued'
                      AND created_at > NOW() - INTERVAL '7 days'
                    RETURNING id, company_id, item_id, suggested_quantity, quantity, suggestion
                    """,
                    reply_uuid, UUID(channel_id_str),
                )
                if claimed_order is not None:
                    claim_happened = True
                    item = await conn.fetchrow(
                        "SELECT name FROM inventory_items WHERE id = $1", claimed_order["item_id"],
                    )
                    features = await _schedule_company_features(conn, claimed_order["company_id"])
                    role = await conn.fetchval("SELECT role FROM users WHERE id = $1", sender_uuid)
                    verdict = evaluate_inventory_action(role=role, features=features, stage="approve_order")
                    if not verdict.ok:
                        await conn.execute(
                            "UPDATE inventory_orders SET confirm_message_id = $1 WHERE id = $2",
                            reply_uuid, claimed_order["id"],
                        )
                        sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)
                    else:
                        action = parse_confirm_reply(stripped)
                        if action == "confirm":
                            row = await orders_service.approve_order(
                                conn, order_id=claimed_order["id"], company_id=claimed_order["company_id"],
                                user_id=sender_uuid, quantity=claimed_order["quantity"],
                            )
                            if row is None:
                                sys_row = await _insert_system_message(
                                    conn, channel_id_str,
                                    "\U0001F4E6 That order was already handled — check the Inventory page.",
                                )
                            else:
                                sys_row = await _insert_system_message(
                                    conn, channel_id_str, pills.order_confirmed_pill(item["name"], row["quantity"]),
                                )
                        elif action == "cancel":
                            await orders_service.cancel_order(
                                conn, order_id=claimed_order["id"], company_id=claimed_order["company_id"],
                                user_id=sender_uuid,
                            )
                            sys_row = await _insert_system_message(
                                conn, channel_id_str, pills.order_cancelled_pill(item["name"]),
                            )
                        else:
                            new_qty = parse_quantity_reply(stripped)
                            if new_qty is not None:
                                await conn.execute(
                                    "UPDATE inventory_orders SET quantity = $1 WHERE id = $2",
                                    new_qty, claimed_order["id"],
                                )
                                # Neutral pill — origin (stockout vs a plain
                                # order_request) isn't stored on
                                # inventory_orders, so stockout_pill here
                                # used to claim "marked out of stock" even
                                # for a reorder that was never a stockout.
                                pill_text = pills.order_updated_pill(item["name"], new_qty)
                            else:
                                pill_text = pills.rearm_pill()
                            sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                            await conn.execute(
                                "UPDATE inventory_orders SET confirm_message_id = $1 WHERE id = $2",
                                sys_row["id"], claimed_order["id"],
                            )

                else:
                    claimed_movement = await conn.fetchrow(
                        """
                        UPDATE inventory_movements SET clarify_message_id = NULL
                        WHERE clarify_message_id = $1 AND channel_id = $2
                          AND created_at > NOW() - INTERVAL '7 days'
                        RETURNING id, company_id, item_id, clarify_rounds, kind
                        """,
                        reply_uuid, UUID(channel_id_str),
                    )
                    if claimed_movement is not None:
                        claim_happened = True
                        item = await conn.fetchrow(
                            "SELECT name, current_quantity FROM inventory_items WHERE id = $1",
                            claimed_movement["item_id"],
                        )
                        qty = parse_quantity_reply(stripped)
                        if qty is not None:
                            await movements_service.amend_movement_quantity(
                                conn, movement_id=claimed_movement["id"], quantity=qty, user_id=sender_uuid,
                            )
                            new_item = await conn.fetchrow(
                                "SELECT current_quantity FROM inventory_items WHERE id = $1",
                                claimed_movement["item_id"],
                            )
                            pill_text = (
                                pills.return_pill(item["name"], qty, new_item["current_quantity"], False)
                                if claimed_movement["kind"] == "in"
                                else pills.movement_pill(item["name"], qty, new_item["current_quantity"], None, False)
                            )
                            sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                        elif claimed_movement["clarify_rounds"] < 2:
                            await conn.execute(
                                "UPDATE inventory_movements SET clarify_rounds = clarify_rounds + 1 WHERE id = $1",
                                claimed_movement["id"],
                            )
                            pill_text = pills.quantity_question(pills.rearm_pill())
                            sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                            await conn.execute(
                                "UPDATE inventory_movements SET clarify_message_id = $1 WHERE id = $2",
                                sys_row["id"], claimed_movement["id"],
                            )
                        else:
                            sys_row = await _insert_system_message(
                                conn, channel_id_str,
                                f"\U0001F4E6 Couldn't pin down the count for {item['name']} — set it on the Inventory page.",
                            )

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        return claim_happened
    except Exception:
        logger.exception("inventory chat reply failed for %s", reply_to_id_str)
        return claim_happened


# ── Channel receipt/invoice ingest (attachment-driven) ──────────────────
#
# "@huume here's the delivery invoice" + a dropped CSV/PDF/photo. A CSV or
# PDF attachment is unambiguously a document, so it's tried regardless of
# wording; a photo is ambiguous (could be an incident photo), so it's only
# tried when the text itself reads as a delivery/invoice mention
# (_RECEIPT_TEXT_RE). STRICT provenance, same invariant as the deterministic
# INVENTORY "receipt" fork: only lines that resolve against an item's own
# open order actually check in (`receipts.receive_channel_lines`) — nothing
# is auto-created from an unreviewed chat attachment. The staged draft lives
# in `inventory_receipt_drafts` (migration `receiptdraft01`) between the
# review pill and the confirm reply, the same `confirm_message_id`
# atomic-claim idiom as `schedule_chat_proposals`/`inventory_orders`.

_RECEIPT_TEXT_RE = re.compile(
    r"\b(invoice|receipt|packing slip|delivery|shipment|order (?:came|arrived|is here)|restock)\b",
    re.IGNORECASE,
)
_RECEIPT_DOC_EXTS = (".csv", ".pdf")
_RECEIPT_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_RECEIPT_MAX_BYTES = 15 * 1024 * 1024  # same cap as routes/inventory.py's REST /receipts/parse


def _pick_receipt_attachment(attachments: Optional[list], content: str) -> Optional[dict]:
    """Most-recent-first (mirrors huume/inventory_skill.py's attachment
    order rule). Returns None when nothing here reads as a receipt — the
    caller falls through to the normal intent fork untouched.

    A doc attachment (.csv/.pdf) requires the SAME wording opt-in as an
    image one, unless the message is a bare mention with nothing else said
    — "@huume attaching the incident report from this morning" + a PDF must
    still reach `classify_intent`/LOG (and the OSHA dual-write), not get
    silently swallowed here just because it happens to carry a PDF."""
    if not attachments:
        return None
    from app.matcha.services.ems.intent import strip_mention

    text_hints_receipt = bool(_RECEIPT_TEXT_RE.search(content or ""))
    bare_mention = not strip_mention(content).strip()
    for att in reversed(attachments):
        filename = (att.get("filename") or "").lower()
        size = att.get("size") or 0
        if size > _RECEIPT_MAX_BYTES:
            continue
        if filename.endswith(_RECEIPT_DOC_EXTS) and (text_hints_receipt or bare_mention):
            return att
        if filename.endswith(_RECEIPT_IMAGE_EXTS) and text_hints_receipt:
            return att
    return None


async def _bg_inventory_receipt(
    channel_id_str: str, message_id_str: str, sender_user_id_str: str, content: str,
    attachments: Optional[list],
) -> bool:
    """Claim-style: True iff a receipt-shaped attachment was found and
    handled (a pill was always posted in that case — refusal included), so
    the mention fork is never ALSO tried for the same message. False means
    "nothing here looked like a receipt", the normal fork proceeds
    untouched. Two connection blocks: the Gemini parse call (PDF/image
    branch of `receipts.parse_receipt`) must not run with a pooled
    connection held, same rule as every other Gemini-calling dispatch here."""
    att = _pick_receipt_attachment(attachments, content)
    if att is None:
        return False
    try:
        from app.core.services.storage import get_storage
        from app.matcha.services.inventory import pills
        from app.matcha.services.inventory import receipts as receipts_service
        from app.matcha.services.inventory.rules import evaluate_inventory_action

        sys_row = None
        async with get_connection() as conn:
            company_id = await _inventory_company_gate(conn, channel_id_str)
            if company_id is None:
                return False  # inventory off here — let the normal fork's own gate answer
            try:
                await check_rate_limit(str(company_id), "inventory_event", 30, 3600)
            except HTTPException:
                return True  # over budget — claimed, but silently skip like every other rate-limited path
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(sender_user_id_str))
            features = await _schedule_company_features(conn, company_id)
            # approve_order bar (client/admin), not the any-role movement bar —
            # committing a receive is the same authority level as approving an
            # order, matching the REST /receipts/commit route's gate.
            verdict = evaluate_inventory_action(role=role, features=features, stage="approve_order")
            if not verdict.ok:
                sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)
            else:
                location_id, _ = await _channel_location(conn, channel_id_str)
                if location_id is None and await _channel_bound_to_inactive_location(conn, channel_id_str):
                    sys_row = await _insert_system_message(
                        conn, channel_id_str,
                        "\U0001F4E6 This channel's store is deactivated, so inventory tracking is paused here.",
                    )
        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return True

        # No connection held — download + parse (parse's PDF/image branch is Gemini).
        storage = get_storage()
        if not storage.is_supported_storage_path(att.get("url")):
            async with get_connection() as conn:
                sys_row = await _insert_system_message(
                    conn, channel_id_str, "\U0001F4E6 Couldn't read that attachment.")
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return True
        file_bytes = await storage.download_file(att["url"])
        receipt = await receipts_service.parse_receipt(
            file_bytes, att.get("content_type") or "", att.get("filename") or "")

        async with get_connection() as conn:
            if not receipt["available"] or not receipt["lines"]:
                sys_row = await _insert_system_message(
                    conn, channel_id_str,
                    "\U0001F4E6 Couldn't read any line items off that file — try Receive Delivery "
                    "on the Inventory page instead.",
                )
            else:
                location_id, _ = await _channel_location(conn, channel_id_str)
                preview = await receipts_service.resolve_lines(
                    conn, company_id=company_id, location_id=location_id, lines=receipt["lines"])
                draft_id = await conn.fetchval(
                    """
                    INSERT INTO inventory_receipt_drafts
                        (company_id, channel_id, location_id, source_message_id, created_by,
                         vendor, invoice_number, lines)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)
                    RETURNING id
                    """,
                    company_id, UUID(channel_id_str), location_id, UUID(message_id_str),
                    UUID(sender_user_id_str), receipt.get("vendor"), receipt.get("invoice_number"),
                    json.dumps(receipt["lines"]),
                )
                pill_text = pills.receipt_draft_pill(
                    vendor=receipt.get("vendor"), invoice_number=receipt.get("invoice_number"),
                    preview=preview,
                )
                sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                await conn.execute(
                    "UPDATE inventory_receipt_drafts SET confirm_message_id = $1 WHERE id = $2",
                    sys_row["id"], draft_id,
                )
        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        return True
    except Exception:
        logger.exception("inventory receipt ingest failed for message %s", message_id_str)
        return True  # we found a receipt-shaped attachment; a crash must not fall through to double-dispatch


async def _bg_receipt_reply(
    channel_id_str: str, reply_to_id_str: str, sender_user_id_str: str, content: str,
) -> bool:
    """Fold a reply-to-a-receipt-draft-pill into confirm/cancel. Same
    claim-then-act contract as `_bg_inventory_reply` — returns True iff the
    atomic claim below matched, and (also mirroring `_bg_inventory_reply`)
    re-runs the `approve_order` authz bar on the REPLIER once claimed —
    staging is not confirming, so a non-admin/employee reply or a
    since-disabled `inventory` flag re-arms the pill instead of committing.
    Lines are RE-resolved fresh at confirm time (`receive_channel_lines`
    calls `resolve_lines` internally) rather than trusting the stage-time
    preview — an order may have been queued or claimed by something else in
    the meantime, same "current state, not proposal time" posture as the
    schedule-edit executor."""
    claim_happened = False
    try:
        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.inventory import pills
        from app.matcha.services.inventory import receipts as receipts_service
        from app.matcha.services.inventory.rules import evaluate_inventory_action
        from app.matcha.services.scheduling.schedule_chat_rules import parse_confirm_reply

        reply_uuid = UUID(reply_to_id_str)
        sender_uuid = UUID(sender_user_id_str)
        sys_row = None

        async with get_connection() as conn:
            if not await channel_ops_automation_enabled(
                conn, channel_id=UUID(channel_id_str), feature="inventory"
            ):
                return False
            claimed = await conn.fetchrow(
                """
                UPDATE inventory_receipt_drafts SET confirm_message_id = NULL, updated_at = NOW()
                WHERE confirm_message_id = $1 AND channel_id = $2 AND status = 'staged'
                  AND created_at > NOW() - INTERVAL '7 days'
                RETURNING id, company_id, location_id, vendor, invoice_number, lines
                """,
                reply_uuid, UUID(channel_id_str),
            )
            if claimed is None:
                return False
            claim_happened = True

            # Same approve_order bar `_bg_inventory_reply` re-checks on ITS
            # replier — committing a receive is at least that authority
            # level, and it must be re-verified on the REPLIER, not just
            # whoever staged the draft (an admin can stage, then anyone in
            # the channel could otherwise reply "confirm"), and it must be
            # re-verified fresh in case `inventory` was turned off since.
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", sender_uuid)
            features = await _schedule_company_features(conn, claimed["company_id"])
            verdict = evaluate_inventory_action(role=role, features=features, stage="approve_order")
            if not verdict.ok:
                await conn.execute(
                    "UPDATE inventory_receipt_drafts SET confirm_message_id = $1 WHERE id = $2",
                    reply_uuid, claimed["id"],
                )
                sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)
                await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
                return True

            action = parse_confirm_reply(strip_mention(content))

            if action == "cancel":
                await conn.execute(
                    "UPDATE inventory_receipt_drafts SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
                    claimed["id"],
                )
                sys_row = await _insert_system_message(conn, channel_id_str, pills.receipt_draft_cancelled_pill())
            elif action == "confirm":
                lines = claimed["lines"]
                if isinstance(lines, str):
                    lines = json.loads(lines)
                note = " ".join(filter(None, [
                    claimed["vendor"],
                    f"invoice {claimed['invoice_number']}" if claimed["invoice_number"] else None,
                ])) or None
                result = await receipts_service.receive_channel_lines(
                    conn, company_id=claimed["company_id"], location_id=claimed["location_id"],
                    user_id=sender_uuid, source_message_id=reply_uuid, note=note, lines=lines,
                )
                await conn.execute(
                    "UPDATE inventory_receipt_drafts SET status = 'committed', committed_by = $1, "
                    "committed_at = NOW(), updated_at = NOW() WHERE id = $2",
                    sender_uuid, claimed["id"],
                )
                sys_row = await _insert_system_message(
                    conn, channel_id_str, pills.channel_receipt_pill(result["received"], result["unmatched"]))
            else:
                pill_text = pills.rearm_pill()
                sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                await conn.execute(
                    "UPDATE inventory_receipt_drafts SET confirm_message_id = $1 WHERE id = $2",
                    sys_row["id"], claimed["id"],
                )

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        return claim_happened
    except Exception:
        logger.exception("receipt draft reply failed for %s", reply_to_id_str)
        return claim_happened


async def _bg_schedule_reply(
    channel_id_str: str, reply_to_id_str: str, sender_user_id_str: str, content: str,
) -> bool:
    """Fold a reply-to-a-schedule-pill into its proposal. Same
    off-hot-path/top-level-except/claim-then-act contract as
    _bg_ems_clarify: returns True iff the atomic claim below matched (this
    reply IS aimed at a live proposal), False on a claim miss (stale/
    already-resolved pill) — _bg_ems_dispatch uses this to decide whether an
    @huume mention on the same message should still fall through to the
    normal intent fork.

    The claim mirrors `ems_events.clarify_message_id` (migration `ems01`):
    first reply to a pill wins (partial unique index on
    `confirm_message_id`), and the 7-day age guard IS the expiry — no
    sweeper, a stale pill simply never claims again.

    Confirm/cancel/re-arm never call Gemini and run entirely in the first
    connection block. Only the clarify-answer path needs a second call to
    `schedule_chat.parse_schedule_request` — that branch closes the first
    connection before making it, then opens a fresh one, same two-block
    shape as `_bg_ems_clarify`.

    Every branch below sets `sys_row` and falls through to a single
    broadcast after its connection releases, rather than broadcasting while
    still holding the pooled connection. A confirm whose `execute_proposal`
    write itself raises is caught explicitly: the claim above already
    cleared `confirm_message_id` on the original pill, so letting the
    exception propagate to the top-level handler would leave the proposal
    row unclaimable forever (still 'proposed', nothing to reply to) with no
    feedback in the channel — instead it re-arms on a fresh pill so a later
    confirm can retry."""
    claim_happened = False
    try:
        from datetime import date as _date

        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.scheduling import schedule_chat
        from app.matcha.services.scheduling.schedule_chat_rules import (
            evaluate_schedule_proposal, parse_confirm_reply, resolve_clarify_answer,
            snapped_to_option,
        )

        reply_uuid = UUID(reply_to_id_str)
        sender_uuid = UUID(sender_user_id_str)
        need_reparse = False
        composed: Optional[str] = None
        proposal: Optional[dict] = None
        claimed: Optional[dict] = None
        stored_parse: Optional[dict] = None
        snapped: Optional[str] = None
        clarify_options: list = []
        sys_row = None

        async with get_connection() as conn:
            if not await channel_ops_automation_enabled(
                conn, channel_id=UUID(channel_id_str), feature="employee_schedule"
            ):
                return False
            claimed_row = await conn.fetchrow(
                """
                UPDATE schedule_chat_proposals
                SET confirm_message_id = NULL, updated_at = NOW()
                WHERE confirm_message_id = $1
                  AND status IN ('proposed', 'clarifying')
                  AND created_at > NOW() - INTERVAL '7 days'
                RETURNING id, company_id, channel_id, source_message_id, status,
                          proposal, parse, clarify_rounds, created_by
                """,
                reply_uuid,
            )
            if claimed_row is None:
                return False
            claim_happened = True
            claimed = dict(claimed_row)
            proposal = claimed["proposal"]
            if isinstance(proposal, str):
                proposal = json.loads(proposal)
            stored_parse = claimed.get("parse")
            if isinstance(stored_parse, str):
                stored_parse = json.loads(stored_parse)

            # Re-assert role + features on the REPLIER — any admin/client may
            # confirm a proposal, not only the manager who started it, and a
            # flag/role change between propose and confirm must be caught.
            features = await _schedule_company_features(conn, claimed["company_id"])
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", sender_uuid)
            verdict = evaluate_schedule_proposal(
                role=role, features=features, stage="confirm", proposal_status=claimed["status"],
            )
            if not verdict.ok:
                # Refused (e.g. an employee replying to a manager's pill) —
                # re-arm on the ORIGINAL pill so the manager's later confirm
                # still claims it. We hold the claim, so this can't race.
                await conn.execute(
                    "UPDATE schedule_chat_proposals SET confirm_message_id = $1 WHERE id = $2",
                    reply_uuid, claimed["id"],
                )
                sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)

            else:
                action = parse_confirm_reply(strip_mention(content))

                if action == "cancel":
                    await conn.execute(
                        "UPDATE schedule_chat_proposals SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
                        claimed["id"],
                    )
                    sys_row = await _insert_system_message(conn, channel_id_str, schedule_chat.CANCELLED_TEXT)

                elif claimed["status"] == "proposed" and action == "confirm":
                    executor = (
                        schedule_chat.execute_edit_proposal
                        if proposal.get("kind") == "edit"
                        else schedule_chat.execute_proposal
                    )
                    try:
                        text = await executor(
                            conn, proposal_row={**claimed, "proposal": proposal},
                            confirmed_by=sender_uuid, features=features,
                        )
                    except Exception:
                        logger.exception(
                            "schedule chat execute_proposal failed for proposal %s", claimed["id"],
                        )
                        sys_row = await _insert_system_message(
                            conn, channel_id_str, schedule_chat.EXECUTE_FAILED_TEXT,
                        )
                        await conn.execute(
                            "UPDATE schedule_chat_proposals SET confirm_message_id = $1 WHERE id = $2",
                            sys_row["id"], claimed["id"],
                        )
                    else:
                        sys_row = await _insert_system_message(conn, channel_id_str, text)

                elif claimed["status"] == "proposed":  # action == 'other'
                    sys_row = await _insert_system_message(conn, channel_id_str, schedule_chat.REARM_TEXT)
                    await conn.execute(
                        "UPDATE schedule_chat_proposals SET confirm_message_id = $1 WHERE id = $2",
                        sys_row["id"], claimed["id"],
                    )

                elif claimed["clarify_rounds"] >= schedule_chat.CLARIFY_ROUND_CAP:
                    # status == 'clarifying', past the round cap.
                    await conn.execute(
                        "UPDATE schedule_chat_proposals SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
                        claimed["id"],
                    )
                    sys_row = await _insert_system_message(conn, channel_id_str, schedule_chat.CLARIFY_BAIL_TEXT)

                else:
                    # status == 'clarifying' — this reply is the answer to the
                    # outstanding question and needs a fresh Gemini parse,
                    # which must not run with this connection held.
                    need_reparse = True
                    clarify_options = proposal.get("clarify_options") or []
                    snapped = resolve_clarify_answer(strip_mention(content), clarify_options)
                    composed = schedule_chat.compose_clarify_followup(proposal, snapped)

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return True

        if not need_reparse or composed is None:
            return True

        # The location question is OUR OWN multiple-choice offer
        # (build_proposal's own options list). `location_question` is true
        # whenever THIS clarify round is that offer — independent of
        # whether the reply actually snapped onto one of the options —
        # because a reply that DIDN'T snap ("the one over on Wilshire
        # Blvd") still needs to be force-fed into location_hint below:
        # apply_channel_default_location's "an explicit hint always wins"
        # rule silently loses to the channel's default store otherwise.
        # `location_answer` (snapped cleanly) additionally unlocks the
        # deterministic resume path, skipping a Gemini call entirely.
        location_question = proposal.get("clarify_question") == schedule_chat.LOCATION_CLARIFY_QUESTION
        location_answer = location_question and snapped_to_option(snapped, clarify_options)

        if location_answer and stored_parse is not None:
            parsed = dict(stored_parse)
            parsed["location_hint"] = snapped
        else:
            # No connection held across the Gemini re-parse call.
            parsed = await schedule_chat.parse_schedule_request(composed, _date.today())
            if parsed is None and location_question and stored_parse is not None:
                # The re-parse came back non-actionable even though we
                # already have a successfully-parsed original request AND
                # this clarify round has a slot (location_hint) to inject
                # the answer into below — resume from it rather than
                # cancelling outright. Restricted to the location question:
                # any OTHER clarify's answer has no slot to inject into, so
                # resuming from stored_parse (which by construction lacks
                # the answer) would just re-ask the identical question
                # until the round cap — two wasted Gemini calls to reach
                # the same bail the un-resumed path gives immediately.
                parsed = dict(stored_parse)
            if (
                parsed is not None and location_question
                and not (parsed.get("location_hint") or "").strip()
            ):
                # Force the reply through even when it didn't snap onto an
                # offered option — resolve_clarify_answer returns the RAW
                # reply in that case, which is still a real answer to this
                # question (a fuzzy store name, say) and must win over the
                # channel's default location, not silently lose to it.
                parsed["location_hint"] = snapped

        async with get_connection() as conn2:
            if parsed is None:
                await conn2.execute(
                    "UPDATE schedule_chat_proposals SET status = 'cancelled', updated_at = NOW() WHERE id = $1",
                    claimed["id"],
                )
                sys_row = await _insert_system_message(conn2, channel_id_str, schedule_chat.CLARIFY_BAIL_TEXT)
            else:
                history = list(proposal.get("clarify_history") or []) + [
                    {"q": proposal.get("clarify_question"), "a": content}
                ]
                # Dispatch on the ORIGINAL proposal's kind (set once by
                # build_edit_proposal's own _clarify), not the fresh
                # re-parse's guess — an edit clarify round must stay an
                # edit proposal even if the composed follow-up text reads
                # ambiguously to the model.
                builder = (
                    schedule_chat.build_edit_proposal
                    if proposal.get("kind") == "edit"
                    else schedule_chat.build_proposal
                )
                build = await builder(
                    conn2, company_id=claimed["company_id"], channel_id=claimed.get("channel_id"),
                    source_message_id=claimed.get("source_message_id"), created_by=claimed["created_by"],
                    parsed=parsed, today=_date.today(), original_content=proposal.get("original_content", ""),
                    clarify_history=history, existing_proposal_id=claimed["id"],
                )
                sys_row = await _insert_system_message(conn2, channel_id_str, build.pill_text)
                await conn2.execute(
                    "UPDATE schedule_chat_proposals SET confirm_message_id = $1 WHERE id = $2",
                    sys_row["id"], build.proposal_id,
                )
                if build.kind == "clarify":
                    _note_schedule_clarify(channel_id_str)

        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        return True
    except Exception:
        logger.exception("schedule chat reply failed for %s", reply_to_id_str)
        return claim_happened


# Start time as printed by schedule_chat's clarify option lines
# ("Shift — Fri Aug 7 08:00–16:00 · Aisha Kim") — plain hyphen tolerated.
_OPTION_START_RE = re.compile(r"\b(\d{2}:\d{2})\s*[–-]")
# Mirrors schedule_chat_rules._OPTION_CITY_SUFFIX — kept as a local copy
# rather than importing an underscore-prefixed name across modules.
_LOCATION_OPTION_CITY_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


async def _bg_schedule_untargeted_reply(
    channel_id_str: str, sender_user_id_str: str, content: str,
) -> bool:
    """Narrow fallback for a clarify answer typed as a plain new message
    rather than a threaded reply-to-the-pill. A real transcript showed a
    bare "Willshire" (no @huume mention, no reply_to) go through with zero
    response — _ems_dispatch_decision spawns nothing without one of those
    two signals, so nothing ever looked at it.

    Claims ONLY on one of three exact-ish matches — full option echo,
    unique location resolution for the location question specifically, or a
    clock time matching exactly one option's own printed start time.
    Deliberately NOT resolve_clarify_answer's plain containment: against
    options ending "· Aisha Kim" / "· unstaffed", substrings like "Kim",
    "unstaffed", or "ed" all satisfied containment and hijacked ordinary
    chatter — those must stay plain messages here (a THREADED reply still
    uses the looser resolve_clarify_answer path in _bg_schedule_reply,
    where a reply-to is an explicit signal this fallback doesn't have).

    Sender must be client/admin, checked BEFORE any match: an employee's
    ordinary chatter must never surface evaluate_schedule_proposal's "Only a
    business admin can…" refusal into the channel unprompted.

    Short-content only (clarify answers are short) and gated by the caller
    on _channel_recently_clarified (see that helper) so this whole function,
    including its query, never runs against a channel with no live clarify
    — schedule_chat_proposals has no channel_id index. Purely a targeting
    shim once a match is found: the real resolution/re-parse/build logic is
    _bg_schedule_reply's, reached via the SAME confirm_message_id claim a
    threaded reply would use, so it can't race a genuine threaded answer to
    the same pill. Top-level try/except, unlike its sibling _bg_* functions
    only in that most of them are entered from a context that already
    wraps one — this one is spawned directly via _spawn_bg, so a bare
    exception here would otherwise surface only as an unretrieved-task
    warning with no channel/content context."""
    try:
        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.scheduling import schedule_chat
        from app.matcha.services.scheduling.schedule_chat_rules import match_location, parse_time_hint

        text = strip_mention(content).strip()
        if not text or len(text) > 60:
            return False

        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT company_id, confirm_message_id, proposal
                FROM schedule_chat_proposals
                WHERE channel_id = $1 AND status = 'clarifying'
                  AND confirm_message_id IS NOT NULL
                  AND created_at > NOW() - INTERVAL '15 minutes'
                ORDER BY created_at DESC LIMIT 1
                """,
                UUID(channel_id_str),
            )
            if row is None or row["confirm_message_id"] is None:
                return False

            # Role gate BEFORE any match — an employee's plain chatter must
            # never claim the pill just to be told they can't confirm it.
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(sender_user_id_str))
            if role not in ("client", "admin"):
                return False

            proposal = row["proposal"]
            if isinstance(proposal, str):
                proposal = json.loads(proposal)
            options: list = proposal.get("clarify_options") or []
            low = text.lower()

            # (a) full option echo, with or without the "(City)" suffix
            looks_like_answer = any(
                low == opt.lower() or low == _LOCATION_OPTION_CITY_SUFFIX_RE.sub("", opt).strip().lower()
                for opt in options
            )

            # (b) location question -> unique store resolution. match_location's
            # fuzzy tier (0.9 threshold, digit-guarded) is the SAME resolver
            # _bg_schedule_reply's re-parse path would eventually land on —
            # checking it directly here is what makes a typo'd store name
            # ("Willshire" for "Wilshire") reachable from a plain reply.
            if not looks_like_answer and proposal.get("clarify_question") == schedule_chat.LOCATION_CLARIFY_QUESTION:
                location_rows = await conn.fetch(
                    "SELECT id, name, address, city, state, zipcode FROM business_locations "
                    "WHERE company_id = $1 AND is_active IS NOT FALSE",
                    row["company_id"],
                )
                looks_like_answer = len(match_location(text, [dict(r) for r in location_rows])) == 1

            # (c) a clock time matching exactly ONE option's own printed
            # start time. A bare "2026" parses as 20:26 (colonless-clock
            # normalization) but claims nothing unless a listed shift
            # genuinely starts then — this is what keeps that parse from
            # becoming a false claim on ordinary numeric chatter.
            if not looks_like_answer and options:
                t = parse_time_hint(text)
                if t is not None:
                    hhmm = f"{t.hour:02d}:{t.minute:02d}"
                    hits = [
                        m for opt in options
                        if (m := _OPTION_START_RE.search(opt)) and m.group(1) == hhmm
                    ]
                    looks_like_answer = len(hits) == 1

        if not looks_like_answer:
            return False

        return await _bg_schedule_reply(
            channel_id_str, str(row["confirm_message_id"]), sender_user_id_str, content,
        )
    except Exception:
        logger.exception("schedule untargeted-reply fallback failed for channel %s", channel_id_str)
        return False


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
            classify_event, fallback_classification, gather_intake_context,
            persist_event, question_text,
        )
        from app.matcha.services.ems.protocols import (
            fetch_protocol, mentions_incident, protocol_prompt_excerpt,
        )

        rate_limited = False
        async with get_connection() as conn:
            company_id = await _ems_company_gate(conn, channel_id_str)
            if company_id is None:
                return
            try:
                await check_rate_limit(str(company_id), "ems_event", 30, 3600)
            except HTTPException:
                # Over the hourly limit. The limit bounds Gemini spend/pill
                # spam — an OSHA-regex hit costs zero Gemini, and an
                # over-budget hour must not lose a fatality report, so those
                # persist via the deterministic fallback below. Everything
                # else skips silently as before (message already sent).
                if fallback_classification(content)["urgency"] != "osha":
                    return
                rate_limited = True

            protocol_text = None
            if not rate_limited and mentions_incident(content):
                protocol_row = await fetch_protocol(conn, company_id)
                protocol_text = protocol_prompt_excerpt(protocol_row)

            context = await gather_intake_context(
                conn, UUID(channel_id_str), UUID(message_id_str),
            )
            location_id, location_name = await _channel_location(conn, channel_id_str)
        # No connection held across the Gemini calls.
        if rate_limited:
            classified = fallback_classification(content)  # zero Gemini calls
        else:
            classified = await classify_event(
                content, context, protocol_text=protocol_text, location_name=location_name,
            )

        # Model-side backstop for the deterministic classify_intent gate:
        # the regex layer routed this to LOG, but the model itself read the
        # message as a question/request with nothing to document (e.g. a
        # recap phrasing the regex didn't catch). Reroute to the same
        # answer path a correctly-classified ASK would take instead of
        # logging a junk event — the misread becomes a visible wrong
        # answer, not a silent bad log row. See _intake_disposition.
        #
        # A wrong `not_an_event=True` on a genuine report has no DB trail
        # otherwise (no ems_events row to hang an audit-log entry off of),
        # so this is logged here — the only forensic record if someone
        # later asks "where did my report go?".
        if _intake_disposition(classified) == "reroute_ask":
            from app.matcha.services.ems.intent import ASK
            logger.warning(
                "EMS: model backstop rerouted message %s (channel %s) from LOG to ASK "
                "(classify_event returned not_an_event=True) — content=%r",
                message_id_str, channel_id_str, content[:200],
            )
            # skip_rate_limit=True: the ems_event check above already gated
            # this call; charging ems_ask too would burn both budgets for
            # one message (see _bg_ems_ask's docstring).
            await _bg_ems_ask(channel_id_str, reporter_user_id_str, content, ASK, skip_rate_limit=True)
            return

        async with get_connection() as conn:
            # Non-urgent reports are drafts until the reporter or a reviewer
            # explicitly confirms them. Urgent reports retain the immediate
            # logging path below so OSHA/severe documentation is never lost.
            if classified.get("urgency") not in ("osha", "severe"):
                from app.matcha.services.ems.event_drafts import create_event_draft, set_confirmation_message

                async with conn.transaction():
                    draft = await create_event_draft(
                        conn,
                        company_id=company_id,
                        channel_id=UUID(channel_id_str),
                        source_message_id=UUID(message_id_str),
                        reporter_user_id=UUID(reporter_user_id_str),
                        narrative=content,
                        classified=classified,
                        location_id=location_id,
                    )
                    if draft is None:
                        return
                    message_text = _event_draft_confirmation_text(classified)
                    sys_row = await _insert_system_message(
                        conn,
                        channel_id_str,
                        message_text,
                        metadata={
                            "action": {
                                "kind": "event_draft",
                                "id": str(draft["id"]),
                                "status": "pending",
                            }
                        },
                    )
                    linked = await set_confirmation_message(
                        conn,
                        draft_id=draft["id"],
                        company_id=company_id,
                        confirmation_message_id=sys_row["id"],
                    )
                    if linked is None:
                        raise RuntimeError("Could not link event draft confirmation message")
                await broadcast_system_message(
                    channel_id_str, _system_message_payload(channel_id_str, sys_row)
                )
                _note_ems_draft(channel_id_str)
                return

            event_row, confirmation = await persist_event(
                conn,
                company_id=company_id,
                channel_id=UUID(channel_id_str),
                message_id=UUID(message_id_str),
                reporter_user_id=UUID(reporter_user_id_str),
                content=content,
                classified=classified,
                location_id=location_id,
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
        # not_an_event: the model still judged this a non-report (question,
        # recap, etc.) despite the OSHA-keyword override in
        # _intake_disposition forcing it to persist — document it, but don't
        # page leadership over what the model itself flagged as not a real
        # event (e.g. "did the guest hospitalized last month get a refund?").
        if event_row.get("urgency") and not classified.get("not_an_event"):
            await _maybe_notify_urgent(str(company_id), event_row, bypassed_budget=rate_limited)
    except Exception:
        logger.exception("EMS intake failed for message %s", message_id_str)


# Small, separate budget for the urgent-notify EMAIL fan-out specifically —
# distinct from the "ems_event" budget that bounds Gemini spend. The OSHA
# regex override in _bg_ems_intake/_bg_ems_clarify deliberately bypasses
# ems_event once it's exhausted (a fatality report must still be logged),
# but that bypass has no bound of its own: a burst of OSHA-keyword messages
# during an over-budget hour would each fire an unbounded admin-email
# fan-out (send_urgent_event_notifications emails every designated/admin
# contact). Gate the FAN-OUT ONLY — the event itself always persists.
_OSHA_NOTIFY_BYPASS_LIMIT = 10
_OSHA_NOTIFY_BYPASS_WINDOW_SECONDS = 3600


async def _maybe_notify_urgent(company_id_str: str, event_row: dict, *, bypassed_budget: bool) -> None:
    """Spawn the urgent-notify fan-out, unless this event only reached
    urgency via a rate-limit bypass path AND the separate, smaller
    notify-fan-out budget is also exhausted."""
    if bypassed_budget:
        try:
            await check_rate_limit(company_id_str, "ems_urgent_notify_bypass",
                                    _OSHA_NOTIFY_BYPASS_LIMIT, _OSHA_NOTIFY_BYPASS_WINDOW_SECONDS)
        except HTTPException:
            logger.warning(
                "EMS: urgent-notify bypass budget exhausted for company %s — "
                "event %s logged, admin email fan-out skipped",
                company_id_str, event_row.get("id"),
            )
            return
    _spawn_bg(_bg_ems_urgent_notify(company_id_str, dict(event_row)))


async def _bg_ems_urgent_notify(company_id_str: str, event_row: dict) -> None:
    """Urgent-event fan-out off the pill path — a notify failure must never
    cost the confirmation. Lazy import per the werk→matcha boundary rule."""
    try:
        from app.matcha.services.ems.urgent_notify import send_urgent_event_notifications
        await send_urgent_event_notifications(
            company_id=UUID(company_id_str), event_row=event_row,
        )
    except Exception:
        logger.exception("EMS urgent notify failed for event %s", event_row.get("id"))


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
            _pill_emoji, apply_reclassification, classify_event, compose_refinement_content,
            extract_question, fold_answer, gather_intake_context, question_text,
            should_ask_again, update_text,
        )
        from app.matcha.services.ems.protocols import (
            fetch_protocol, mentions_incident, protocol_prompt_excerpt,
        )

        reply_uuid = UUID(reply_to_id_str)

        async with get_connection() as conn:
            if not await channel_ops_automation_enabled(
                conn, channel_id=UUID(channel_id_str), feature="ems"
            ):
                return False
            async with conn.transaction():
                # Atomic claim: first reply to this question wins. A claim
                # miss (stale pill, already answered) exits the transaction
                # normally with nothing changed.
                claimed = await conn.fetchrow(
                    """
                    UPDATE ems_events SET clarify_message_id = NULL
                    WHERE clarify_message_id = $1 AND status = 'logged'
                    RETURNING id, company_id, narrative, clarification_rounds, urgency
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
                _, location_name = await _channel_location(conn, channel_id_str)

                protocol_text = None
                if mentions_incident(claimed["narrative"]) or mentions_incident(content):
                    protocol_row = await fetch_protocol(conn, company_id)
                    protocol_text = protocol_prompt_excerpt(protocol_row)
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
            if folded.get("urgency") and folded.get("urgency") != claimed["urgency"]:
                await _maybe_notify_urgent(str(company_id), folded, bypassed_budget=True)
            return True

        # No connection held across the Gemini call.
        refinement_content = compose_refinement_content(claimed["narrative"], question, content)
        classified = await classify_event(
            refinement_content, context, protocol_text=protocol_text, location_name=location_name,
        )

        async with get_connection() as conn:
            reclassified = await apply_reclassification(
                conn, event_id=folded["id"], company_id=company_id, classified=classified,
            )
            display = reclassified or folded  # reclassify may no-op (not model_ok, or a promote/dismiss race)

            ask_again = should_ask_again(classified, claimed["clarification_rounds"])
            if ask_again:
                preamble = classified.get("ack") or "Got it, thanks."
                text = question_text(f"{_pill_emoji(display)} {preamble}", classified["clarify_question"])
            else:
                text = update_text(display, classified.get("ack"))
            sys_row = await _insert_system_message(conn, channel_id_str, text)
            if ask_again:
                await conn.execute(
                    "UPDATE ems_events SET clarify_message_id = $1 WHERE id = $2",
                    sys_row["id"], display["id"],
                )

        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        if display.get("urgency") and display.get("urgency") != claimed["urgency"]:
            await _maybe_notify_urgent(str(company_id), display, bypassed_budget=False)
        return True
    except Exception:
        logger.exception("EMS clarify failed for reply to message %s", reply_to_id_str)
        # If the claim already committed, the answer is folded — never let
        # _bg_ems_dispatch treat this as a miss and also fire intake.
        return claim_happened


def _intake_disposition(classified: dict) -> str:
    """"persist" (log the event, the default) or "reroute_ask" (the
    classifier's model-side backstop: the message reached intake as a LOG
    per intent.classify_intent's deterministic bias, but the model itself
    flagged it as a question/request with nothing to document — e.g. a
    recap phrasing the regex layer didn't catch). Pure so the branch is
    unit-testable without DB/Gemini — see _bg_ems_intake's use of it.

    A Gemini outage's fallback shape carries not_an_event=False (see
    event_intake._FALLBACK_CLASSIFICATION), so this always persists during
    an outage — the "documentation survives everything" invariant is
    untouched.

    OSHA overrides the reroute: a message carrying an OSHA keyword that the
    model misread as a question must still be documented — rerouting to
    the ask path leaves no DB row at all, the exact loss this pipeline
    exists to prevent."""
    if classified.get("urgency") == "osha":
        return "persist"
    return "reroute_ask" if classified.get("not_an_event") else "persist"


def _event_draft_confirmation_text(classified: dict) -> str:
    """Render a stable, reply-compatible confirmation prompt."""

    category = str(classified.get("category") or "uncategorized").replace("_", " ")
    title = str(classified.get("title") or "this report").strip()
    return (
        f"Huume thinks this may be a {category} event: **{title}**. "
        "Add it to Events? Reply **confirm** or **not an event**."
    )


def _draft_reply_decision(content: str) -> Optional[str]:
    """Parse only unambiguous confirmation replies."""

    normalized = re.sub(r"[^a-z0-9 ]+", " ", content.lower()).strip()
    if normalized in {"confirm", "confirmed", "yes", "add", "add it", "log", "log it"}:
        return "confirm"
    if normalized in {
        "no", "nope", "cancel", "cancel it", "skip", "not an event",
        "dont add", "do not add", "don't add", "don t add",
    }:
        return "reject"
    return None


async def _bg_ems_draft_reply(
    channel_id_str: str,
    reply_to_id_str: str,
    actor_user_id_str: str,
    content: str,
) -> bool:
    """Resolve a reply to an event-draft confirmation system message."""

    decision = _draft_reply_decision(content)
    # Preserve the existing mention dispatch fallback for a stale system
    # reply such as "@huume new thing". It is a new intake, not an ambiguous
    # answer to an event-draft card.
    if decision is None and "@huume" in content.lower():
        return False
    try:
        from app.matcha.services.ems.event_drafts import (
            confirm_event_draft,
            may_decide_event_draft,
            reject_event_draft,
        )

        async with get_connection() as conn:
            if not await channel_ops_automation_enabled(
                conn, channel_id=UUID(channel_id_str), feature="ems"
            ):
                return False
            draft_row = await conn.fetchrow(
                """
                SELECT id, company_id
                  FROM ems_event_drafts
                 WHERE confirmation_message_id = $1
                   AND channel_id = $2
                   AND status = 'pending'
                """,
                UUID(reply_to_id_str),
                UUID(channel_id_str),
            )
            if not draft_row:
                return False
            user_row = await conn.fetchrow(
                "SELECT id, email, role FROM users WHERE id = $1",
                UUID(actor_user_id_str),
            )
            if not user_row:
                return True
            actor = CurrentUser(
                id=user_row["id"],
                email=user_row["email"],
                role=user_row["role"],
            )
            from app.matcha.services.ops.permissions import resolve_ops_access

            access = await resolve_ops_access(
                conn, user=actor, company_id=draft_row["company_id"]
            )
            draft = await conn.fetchrow(
                "SELECT reporter_user_id FROM ems_event_drafts WHERE id = $1",
                draft_row["id"],
            )
            if not draft or not may_decide_event_draft(
                reporter_user_id=draft["reporter_user_id"],
                actor_user_id=actor.id,
                access=access,
            ):
                return True
            if decision is None:
                sys_row = await _insert_system_message(
                    conn,
                    channel_id_str,
                    "Please reply **confirm** to add this to Events or **not an event** to leave it out.",
                    metadata={
                        "action": {
                            "kind": "event_draft",
                            "id": str(draft_row["id"]),
                            "status": "pending",
                        }
                    },
                )
                await broadcast_system_message(
                    channel_id_str, _system_message_payload(channel_id_str, sys_row)
                )
                _note_ems_draft(channel_id_str)
                return True
            async with conn.transaction():
                if decision == "confirm":
                    result = await confirm_event_draft(
                        conn,
                        draft_id=draft_row["id"],
                        actor_user_id=actor.id,
                        access=access,
                    )
                    text = "Added to Events. A reviewer can now complete it or mark it no action."
                    status = "confirmed"
                else:
                    result = await reject_event_draft(
                        conn,
                        draft_id=draft_row["id"],
                        actor_user_id=actor.id,
                        access=access,
                        reason="Rejected in channel",
                    )
                    text = "Okay — I left it out of Events."
                    status = "rejected"
                sys_row = await _insert_system_message(
                    conn,
                    channel_id_str,
                    text,
                    metadata={
                        "action": {
                            "kind": "event_draft",
                            "id": str(draft_row["id"]),
                            "status": status,
                        }
                    },
                )
        await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        await broadcast_channel_action_updated(
            channel_id_str,
            {"kind": "event_draft", "id": str(draft_row["id"]), "status": status},
        )
        return True
    except Exception:
        logger.exception("EMS event-draft reply failed for channel %s", channel_id_str)
        # A probe failure must not swallow the existing clarify/schedule
        # reply dispatch paths. The source message is already durable; a
        # later retry can resolve the draft once the database is available.
        return False


async def _bg_ems_draft_untargeted_reply(
    channel_id_str: str,
    sender_user_id_str: str,
    content: str,
) -> bool:
    """Narrow fallback for a decision typed as a plain new message rather
    than a threaded reply to the pill — the event-draft twin of
    _bg_schedule_untargeted_reply, for the same root cause: without a
    reply_to or an @huume mention _ems_dispatch_decision spawns nothing, so
    a bare "confirm" answering a live pill was never looked at. With a
    mention it was worse — classify_intent has no confirm/reject case and
    bias-to-LOG returned LOG, so "@huume confirm" minted a *second* event
    draft titled "confirm" instead of resolving the first.

    Claims only on _draft_reply_decision's exact literal set (checked BEFORE
    any query, so ordinary chat costs nothing), and only when the channel
    has a live pending draft. The mention is stripped before delegating:
    _bg_ems_draft_reply deliberately refuses mention-bearing content whose
    decision is None (see its "@huume new thing" guard above), so
    "@huume confirm" must arrive there as "confirm".

    Purely a targeting shim — resolution, permissions (may_decide_event_draft)
    and idempotency stay in _bg_ems_draft_reply, reached through the SAME
    confirmation_message_id a threaded reply would use, so this cannot race
    or double-resolve against a genuine threaded answer to the same pill."""
    try:
        from app.matcha.services.ems.intent import strip_mention

        text = strip_mention(content).strip()
        if _draft_reply_decision(text) is None:
            return False

        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT confirmation_message_id
                  FROM ems_event_drafts
                 WHERE channel_id = $1
                   AND status = 'pending'
                   AND confirmation_message_id IS NOT NULL
                   AND created_at > NOW() - INTERVAL '15 minutes'
                 ORDER BY created_at DESC
                 LIMIT 1
                """,
                UUID(channel_id_str),
            )
        if row is None:
            return False

        return await _bg_ems_draft_reply(
            channel_id_str, str(row["confirmation_message_id"]), sender_user_id_str, text,
        )
    except Exception:
        logger.exception(
            "EMS event-draft untargeted-reply fallback failed for channel %s", channel_id_str,
        )
        return False


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
    attachments: Optional[list] = None,
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
    question is folded into its event even when phrased as a question.

    A reply that misses the EMS clarify claim is next offered to the
    schedule-proposal claim (`_bg_schedule_reply`) — a reply aimed at a
    live "@huume I need an opener…" pill is its confirm/cancel/clarify
    answer, not a new mention-fork dispatch. A miss there too still falls
    through to the mention fork below, so "@huume new thing" typed as a
    reply onto a stale schedule pill isn't swallowed, same reasoning as
    EMS."""
    if reply_to_system_id_str is not None:
        claimed = await _bg_ems_draft_reply(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
        claimed = await _bg_ems_clarify(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
        claimed = await _bg_schedule_reply(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
        claimed = await _bg_inventory_reply(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
        claimed = await _bg_receipt_reply(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
    if has_huume_mention:
        # A bare decision word answering a live pill is never a new report,
        # a receipt, or a question — claim it before classify_intent's
        # bias-to-LOG default mints a duplicate draft titled "confirm".
        if await _bg_ems_draft_untargeted_reply(channel_id_str, sender_user_id_str, content):
            return
        from app.matcha.services.ems.intent import INVENTORY, LINK, LOG, SCHEDULE, classify_intent

        # A receipt-shaped attachment is tried before intent classification —
        # "@huume here's the invoice" with a CSV/PDF attached should ingest it
        # even if the wording alone wouldn't trip the INVENTORY regex. But a
        # doc attachment still needs receipt wording (or a bare mention) per
        # `_pick_receipt_attachment` — "@huume attaching the incident report"
        # + a PDF must fall through to LOG, not get claimed here.
        if await _bg_inventory_receipt(channel_id_str, message_id_str, sender_user_id_str, content, attachments):
            return
        intent = classify_intent(content)
        if intent == LOG:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
        elif intent == LINK:
            await _bg_ems_link(channel_id_str, sender_user_id_str)
        elif intent == SCHEDULE:
            await _bg_schedule_request(channel_id_str, message_id_str, sender_user_id_str, content)
        elif intent == INVENTORY:
            await _bg_inventory_request(channel_id_str, message_id_str, sender_user_id_str, content)
        else:
            await _bg_ems_ask(channel_id_str, sender_user_id_str, content, intent)


async def _notify_channel_members(
    members: list, ch_name: Optional[str], sender_name: str, preview: str, channel_id_str: str,
) -> None:
    """Bell fan-out for a new channel message — ONE batched call (see
    notification_service.create_notifications_bulk) instead of a sequential
    per-member loop that cost ~2 pool acquires + ~2 Redis RTs per member. A
    200-member channel used to be ~400 remote round-trips per message."""
    from app.matcha.services import notification_service as notif_svc
    targets = [(m["user_id"], m["company_id"]) for m in members if m["company_id"]]
    if not targets:
        return
    try:
        await notif_svc.create_notifications_bulk(
            user_ids=[t[0] for t in targets],
            company_ids=[t[1] for t in targets],
            type="channel_message",
            title=f"#{ch_name}",
            body=f"{sender_name}: {preview}",
            link="/work",
            metadata={"channel_id": channel_id_str},
        )
    except Exception:
        logger.warning("bulk channel_message notification failed", exc_info=True)


_channel_name_cache: "TTLCache" = TTLCache(maxsize=2048, ttl=60)


async def _get_channel_name(conn, ch_uuid: UUID) -> Optional[str]:
    """60s-cached channel name — was a per-message SELECT on the send path."""
    key = str(ch_uuid)
    if key in _channel_name_cache:
        return _channel_name_cache[key]
    name = await conn.fetchval("SELECT name FROM channels WHERE id = $1", ch_uuid)
    # Don't cache a miss/NULL for the full TTL — a transient lookup failure
    # would otherwise show "#None" in bell titles for up to 60s.
    if name is not None:
        _channel_name_cache[key] = name
    return name

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
# Typing is the highest-frequency event class; it rides its own pub/sub
# channel so a typing storm can't head-of-line-block message delivery in the
# (serial, per-worker) fanout subscriber loop.
_TYPING_CHANNEL = "channels:typing:fanout"
_SERVER_PING_INTERVAL_SECONDS = 25
# A healthy client touches at least every 25-30s (its own ping, or its pong
# reply to server_ping). 90s = 3 missed cycles ⇒ the socket is a zombie the
# 5s send timeout can't see (TCP buffer still accepting writes).
_LIVENESS_DEADLINE_SECONDS = 90

# Identifies THIS worker's envelopes on the fanout channel. Local delivery
# now happens synchronously at publish time (local-first), so the subscriber
# must skip envelopes this worker published or every local socket gets
# doubles.
_WORKER_ID = uuid4().hex


def _should_process_envelope(envelope: dict, worker_id: str) -> bool:
    """Pure: process an envelope unless this worker published it. Envelopes
    from pre-deploy workers carry no 'origin' — process those (worst case a
    brief double-delivery during a rolling restart; client dedups by id)."""
    return envelope.get("origin") != worker_id


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

# NULLIF+BTRIM wrap: Postgres CONCAT() ignores NULLs, so with no matching
# `employees` row CONCAT(NULL, ' ', NULL) is ' ' (non-NULL) and COALESCE
# stops there instead of falling through to a.name/u.email — see the same
# fix + comment on channels.py's _USER_NAME_EXPR.
_USER_NAME_EXPR = "COALESCE(c.name, NULLIF(BTRIM(CONCAT(e.first_name, ' ', e.last_name)), ''), a.name, u.email)"


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
        # Liveness tracking (touch() called on every inbound frame + on
        # connect). Plain dict — single event loop, no await between reads
        # and writes, so no lock needed. See _server_ping_loop's reaper.
        self.last_seen: Dict[WebSocket, float] = {}

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
            self.last_seen[websocket] = time.monotonic()

    def touch(self, websocket: WebSocket) -> None:
        """Stamp last-activity for the liveness reaper."""
        self.last_seen[websocket] = time.monotonic()

    async def disconnect(self, websocket: WebSocket, user_id: UUID):
        # Collect broadcasts under the lock, send after release — the lock is
        # non-reentrant and _local_broadcast_to_room re-acquires it for dead-
        # socket cleanup, so awaiting a broadcast while holding it deadlocks
        # the whole manager the moment Redis is down AND a socket is dead.
        to_broadcast: list[tuple[str, dict]] = []
        async with self.lock:
            self.last_seen.pop(websocket, None)
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
                                if not self.room_members[room]:
                                    # Never deleted before — slow leak, one
                                    # entry per channel ever joined.
                                    del self.room_members[room]
                                if user:
                                    to_broadcast.append((room, {
                                        "type": "user_left",
                                        "room": room,
                                        "user": user.model_dump(mode='json'),
                                    }))
        for room, payload in to_broadcast:
            await self._broadcast_to_room(room, payload, exclude_user=user_id)

    async def join_room(self, user_id: UUID, room_key: str):
        payload = None
        async with self.lock:
            if room_key not in self.room_members:
                self.room_members[room_key] = set()

            was_in_room = user_id in self.room_members[room_key]
            self.room_members[room_key].add(user_id)

            if user_id in self.user_rooms:
                self.user_rooms[user_id].add(room_key)

            if not was_in_room and user_id in self.users:
                payload = {
                    "type": "user_joined",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                }
        if payload:
            await self._broadcast_to_room(room_key, payload, exclude_user=user_id)

    async def leave_room(self, user_id: UUID, room_key: str):
        payload = None
        async with self.lock:
            if room_key in self.room_members:
                self.room_members[room_key].discard(user_id)
                if not self.room_members[room_key]:
                    del self.room_members[room_key]
            if user_id in self.user_rooms:
                self.user_rooms[user_id].discard(room_key)
            if user_id in self.users:
                payload = {
                    "type": "user_left",
                    "room": room_key,
                    "user": self.users[user_id].model_dump(mode='json'),
                }
        if payload:
            await self._broadcast_to_room(room_key, payload)

    async def broadcast_message(self, room_key: str, message: dict):
        await self._broadcast_to_room(room_key, {
            "type": "message",
            "room": room_key,
            "message": message,
        })

    async def broadcast_typing(self, room_key: str, user: ChannelUser):
        # Rides its own pub/sub channel — see _TYPING_CHANNEL's comment.
        await self._broadcast_to_room(room_key, {
            "type": "typing",
            "room": room_key,
            "user": user.model_dump(mode='json'),
        }, exclude_user=user.id, channel=_TYPING_CHANNEL)

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
        """Send to a user's connections on every worker. Local sockets are
        written directly (survives a Redis/subscriber outage); the Redis
        publish only exists to reach the OTHER worker's sockets."""
        await self._local_send_to_user(user_id, message)
        redis = get_redis_cache()
        if redis is None:
            return
        envelope = {
            "kind": "user",
            "user_id": str(user_id),
            "message": message,
            "origin": _WORKER_ID,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in send_to_user (local delivery already done)")

    async def send_to_users(self, payloads: "Dict[UUID, dict]") -> None:
        """Multicast: per-user payloads in ONE fanout envelope. Local sockets
        are written directly; one Redis publish covers the other worker
        (subscriber kind 'users'). Used by the batched notification fanout
        (create_notifications_bulk) instead of N separate send_to_user calls."""
        if not payloads:
            return
        # Concurrent, not serial: a 200-recipient batch awaited one at a time
        # would block the caller (and, via the fanout envelope below, the
        # message-delivery subscriber on the OTHER worker — see the
        # _process_envelope 'users' branch) for as long as the single
        # slowest socket in the batch takes, reintroducing exactly the
        # head-of-line blocking the typing/message channel split exists to
        # avoid.
        await asyncio.gather(
            *(self._local_send_to_user(uid, message) for uid, message in payloads.items()),
            return_exceptions=True,
        )
        redis = get_redis_cache()
        if redis is None:
            return
        envelope = {
            "kind": "users",
            "messages": {str(uid): m for uid, m in payloads.items()},
            "origin": _WORKER_ID,
        }
        try:
            await redis.publish(_FANOUT_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in send_to_users (local delivery already done)")

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

    async def _broadcast_to_room(
        self, room_key: str, message: dict, exclude_user: UUID = None,
        channel: str = _FANOUT_CHANNEL,
    ):
        """Fan-out to every WS member of a room across all uvicorn workers.

        Local-first: this worker's sockets are written directly, then one
        Redis publish reaches the other worker. `channel` lets high-frequency
        event classes (typing) ride their own pub/sub channel so they can't
        head-of-line-block message delivery in the serial subscriber.
        """
        await self._local_broadcast_to_room(room_key, message, exclude_user=exclude_user)
        redis = get_redis_cache()
        if redis is None:
            return
        envelope = {
            "kind": "room",
            "room": room_key,
            "message": message,
            "exclude_user": str(exclude_user) if exclude_user else None,
            "origin": _WORKER_ID,
        }
        try:
            await redis.publish(channel, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Redis publish failed in _broadcast_to_room (local delivery already done)")

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
_typing_subscriber_task: Optional[asyncio.Task] = None
_server_ping_task: Optional[asyncio.Task] = None


async def _process_envelope(envelope: dict) -> None:
    """Dispatch one decoded fanout envelope to this worker's local sockets.
    Shared by the message-fanout and typing-fanout subscriber loops."""
    if not _should_process_envelope(envelope, _WORKER_ID):
        return
    kind = envelope.get("kind")
    msg = envelope.get("message")
    if msg is None and kind != "users":
        return
    if kind == "room":
        room_key = envelope.get("room")
        if not room_key:
            return
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
            return
        try:
            uid = UUID(uid_raw)
        except (ValueError, TypeError):
            return
        await manager._local_send_to_user(uid, msg)
    elif kind == "users":
        # Multicast: one envelope, many recipients (bulk notify). Concurrent
        # for the same reason as send_to_users above — this runs on the
        # single serial fanout subscriber, so one slow socket serially
        # awaited here stalls every other message this worker is about to
        # dispatch, not just the rest of this batch.
        msgs = envelope.get("messages") or {}
        targets = []
        for uid_raw, m in msgs.items():
            try:
                targets.append((UUID(uid_raw), m))
            except (ValueError, TypeError):
                continue
        if targets:
            await asyncio.gather(
                *(manager._local_send_to_user(uid, m) for uid, m in targets),
                return_exceptions=True,
            )


async def _subscriber_loop(channel: str, label: str) -> None:
    """Long-running per-worker task. Subscribes to a Redis fanout channel and
    dispatches incoming envelopes to this worker's local sockets via
    _process_envelope. Parametrized by channel so message and typing traffic
    ride independent pub/sub channels (see _TYPING_CHANNEL) and can't head-
    of-line-block each other.

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
            await pubsub.subscribe(channel)
            logger.info("[Channels WS] Subscribed to %s (%s)", channel, label)
            async for raw in pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                payload = raw.get("data")
                if not payload:
                    continue
                try:
                    envelope = json.loads(payload)
                except Exception:
                    logger.warning("[Channels WS] Malformed fanout envelope on %s; dropping", label)
                    continue
                await _process_envelope(envelope)
            # listen() ended without raising (connection closed cleanly) —
            # don't spin through resubscribe at full speed.
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("[Channels WS] Subscriber loop error (%s); restarting in 2s", label)
            await asyncio.sleep(2)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except Exception:
                    pass


async def _fanout_subscriber_loop() -> None:
    await _subscriber_loop(_FANOUT_CHANNEL, "messages")


async def _typing_subscriber_loop() -> None:
    await _subscriber_loop(_TYPING_CHANNEL, "typing")


async def _server_ping_loop() -> None:
    """Periodic keepalive push from server to every connected WS. Prevents
    Nginx / intermediaries from silently killing idle connections and gives
    the server early detection of dead sockets (a failed send drops the WS
    from active_connections). Also reaps zombie sockets — a half-open
    connection can pass the 5s send timeout indefinitely (kernel buffer
    still accepting writes) while never actually reaching the peer; a client
    that hasn't touched the connection (ping or pong) in
    _LIVENESS_DEADLINE_SECONDS is closed outright."""
    while True:
        try:
            await asyncio.sleep(_SERVER_PING_INTERVAL_SECONDS)
            # Snapshot the per-user connection map under the lock so we don't
            # iterate while disconnect() mutates it.
            async with manager.lock:
                snapshot: list[tuple[UUID, list[WebSocket]]] = [
                    (uid, list(conns)) for uid, conns in manager.active_connections.items()
                ]
            targets: list[tuple[UUID, WebSocket]] = [
                (uid, ws) for uid, conns in snapshot for ws in conns
            ]

            now = time.monotonic()
            stale = [
                (uid, ws) for uid, ws in targets
                if now - manager.last_seen.get(ws, now) > _LIVENESS_DEADLINE_SECONDS
            ]
            if stale:
                # Concurrent, not serial: this runs BEFORE the keepalive
                # gather below, so a batch of zombies (a NAT rebind, an LB
                # event) closed one at a time could burn up to
                # len(stale) * 2s here before a single server_ping goes out —
                # cascading a partial outage into healthy clients getting
                # dropped by intermediaries for missing the very keepalive
                # this loop exists to send.
                async def _close(ws: WebSocket) -> None:
                    try:
                        await asyncio.wait_for(ws.close(), timeout=2)
                    except Exception:
                        pass
                await asyncio.gather(*(_close(ws) for _, ws in stale), return_exceptions=True)
                stale_set = {id(ws) for _, ws in stale}
                targets = [(uid, ws) for uid, ws in targets if id(ws) not in stale_set]

            ping_payload = json.dumps({"type": "server_ping"})
            # Ping every socket on this worker concurrently rather than one at
            # a time — sequential sends here would delay the next room's
            # pings behind a single slow/half-dead connection.
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
    """Start the per-worker Redis pub/sub subscribers (message + typing).
    Idempotent."""
    global _subscriber_task, _typing_subscriber_task
    if not _subscriber_task or _subscriber_task.done():
        _subscriber_task = asyncio.create_task(_fanout_subscriber_loop())
    if not _typing_subscriber_task or _typing_subscriber_task.done():
        _typing_subscriber_task = asyncio.create_task(_typing_subscriber_loop())


def start_server_ping_loop() -> None:
    """Start the per-worker server-side ping loop. Idempotent."""
    global _server_ping_task
    if _server_ping_task and not _server_ping_task.done():
        return
    _server_ping_task = asyncio.create_task(_server_ping_loop())


async def stop_fanout_subscriber() -> None:
    """Cancel both subscriber tasks on shutdown."""
    global _subscriber_task, _typing_subscriber_task
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except (asyncio.CancelledError, Exception):
            pass
        _subscriber_task = None
    if _typing_subscriber_task is not None:
        _typing_subscriber_task.cancel()
        try:
            await _typing_subscriber_task
        except (asyncio.CancelledError, Exception):
            pass
        _typing_subscriber_task = None


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


async def push_channel_read(channel_id: str, user_id: str) -> None:
    """Zero the unread badge on a user's OTHER devices — read state is
    per-user, not per-device, so a read on one device must clear all of
    them. Called by the WS mark_read handler and by REST GET /channels/{id}
    (channels.py), which also flips last_read_at."""
    await manager.send_to_user(UUID(user_id), {
        "type": "channel_read",
        "channel_id": channel_id,
        "user_id": user_id,
    })


async def broadcast_system_message(channel_id: str, message: dict) -> None:
    """Fan out a system (Huume/EMS) message to a channel room. Called from
    a background task, not a connected client — no WebSocket/user context
    required. Goes through manager.broadcast_message so the envelope
    matches every other message fan-out ({type, room, message}) — the
    client reads `data.message` and silently drops anything else shaped."""
    await manager.broadcast_message(channel_id, message)


async def broadcast_channel_action_updated(channel_id: str, action: dict) -> None:
    """Fan out an authoritative action-state change to channel clients."""
    await manager._broadcast_to_room(channel_id, {
        "type": "channel_action_updated",
        "channel_id": channel_id,
        "action": action,
    })


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
    # Per-socket send limiter — one loose/abusive client must never be able
    # to loop `type: message` sends as fast as the DB round-trips allow, each
    # triggering a full room + notification fanout.
    rate = _TokenBucket()
    # mark_read had no rate check at all (unlike `message`, which does
    # strictly more work) and no membership check — a buggy or hostile
    # client looping it acquires a pool connection per frame and can exhaust
    # the pool, taking down HTTP request handling for the whole worker, not
    # just channels. Separate, more permissive bucket: the legitimate client
    # already self-debounces to ~1/5s, this only needs to catch a loop.
    mark_read_rate = _TokenBucket(burst=5, refill_per_sec=0.5)
    mark_read_last_written: Dict[str, float] = {}

    try:
        while True:
            data = await websocket.receive_json()
            manager.touch(websocket)
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
                        await websocket.send_json({
                            "type": "error", "message": "Invalid channel ID", "channel_id": channel_id,
                        })
                        continue
                    async with get_connection() as conn:
                        try:
                            access = await load_channel_access(
                                conn,
                                channel_id=ch_uuid,
                                user_id=user.id,
                                user_role=user.role,
                            )
                            assert_channel_capability(access, ChannelCapability.CHAT)
                        except (HTTPException, PermissionError):
                            await websocket.send_json({
                                "type": "error",
                                "message": "Channel unavailable for this account",
                                "channel_id": str(ch_uuid),
                            })
                            continue
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
                                "channel_id": str(ch_uuid),
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
                if not rate.allow(time.monotonic()):
                    # Never kill the socket over rate — error frame + drop.
                    # Client-side onServerError removes the pending row and
                    # toasts (scoped by client_message_id).
                    await websocket.send_json({
                        "type": "error",
                        "code": "rate_limited",
                        "message": "You're sending messages too quickly — give it a moment.",
                        "channel_id": channel_id,
                        "client_message_id": client_message_id,
                    })
                    continue
                if channel_id and (content or attachments) and len(content) > 4000:
                    # Previously a bare `if ... and len(content) <= 4000:`
                    # with no else — an oversize send fell through to the
                    # next receive_json() with no error frame, leaving the
                    # client's optimistic pending row stuck forever.
                    await websocket.send_json({
                        "type": "error",
                        "message": "Message too long (max 4000 characters)",
                        "channel_id": channel_id,
                        "client_message_id": client_message_id,
                    })
                    continue
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
                    reply_target_metadata: dict = {}
                    async with get_connection() as conn:
                        try:
                            access = await load_channel_access(
                                conn,
                                channel_id=ch_uuid,
                                user_id=user.id,
                                user_role=user.role,
                            )
                            assert_channel_capability(access, ChannelCapability.CHAT)
                        except (HTTPException, PermissionError):
                            await websocket.send_json({
                                "type": "error",
                                "message": "Channel unavailable for this account",
                                "channel_id": channel_id,
                                "client_message_id": client_message_id,
                            })
                            continue
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
                                reply_target = await conn.fetchrow(
                                    "SELECT message_type, metadata FROM channel_messages WHERE id = $1 AND channel_id = $2",
                                    reply_uuid, ch_uuid,
                                )
                                if reply_target is None:
                                    reply_uuid = None
                                else:
                                    reply_target_type = reply_target["message_type"]
                                    raw_reply_metadata = reply_target["metadata"]
                                    if isinstance(raw_reply_metadata, str):
                                        try:
                                            raw_reply_metadata = _json.loads(raw_reply_metadata)
                                        except (TypeError, ValueError):
                                            raw_reply_metadata = {}
                                    if isinstance(raw_reply_metadata, dict):
                                        reply_target_metadata = raw_reply_metadata
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
                            # Everything between the committed INSERT and the
                            # broadcast below is best-effort: a failure here
                            # must degrade the payload (no preview / no
                            # mentions), never strand a persisted row
                            # unbroadcast and kill the sender's socket via the
                            # endpoint's catch-all.
                            broadcast_attachments: list = []
                            reply_preview = None
                            mention_handles: list = []
                            mentioned_user_ids: list = []

                            try:
                                # Update channel + member activity timestamps
                                # only on the fresh-insert path. A retried
                                # duplicate send shouldn't bump activity
                                # (otherwise a flaky client could keep a
                                # channel appearing "active" via repeated
                                # cmid retries).
                                if is_new_message:
                                    await conn.execute(
                                        "UPDATE channels SET updated_at = NOW() WHERE id = $1",
                                        ch_uuid,
                                    )
                                    await conn.execute(
                                        "UPDATE channel_members SET last_contributed_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                                        ch_uuid, user.id,
                                    )
                            except Exception:
                                logger.warning("[Channel WS] activity bump failed", exc_info=True)

                            try:
                                broadcast_attachments = _json.loads(row["attachments"]) if row["attachments"] else []
                            except Exception:
                                logger.warning("[Channel WS] attachments parse failed", exc_info=True)

                            # Mirror chat media into the linked collab project's
                            # Files (root) — fire-and-forget on its own connection
                            # so the unindexed reverse lookup never adds latency to
                            # the send. Fresh inserts only (no re-mirror on retry).
                            if is_new_message and broadcast_attachments:
                                _spawn_bg(_bg_sync_channel_attachments(
                                    str(ch_uuid), user.id, list(broadcast_attachments),
                                ))

                            try:
                                # Build reply preview for broadcast
                                if reply_uuid:
                                    rp = await conn.fetchrow(
                                        """
                                        SELECT m.content, m.attachments, m.deleted_at,
                                               COALESCE(c.name, NULLIF(BTRIM(CONCAT(e.first_name, ' ', e.last_name)), ''), a.name, u.email, 'Huume') AS sender_name
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
                            except Exception:
                                logger.warning("[Channel WS] reply preview failed", exc_info=True)

                            try:
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
                            except Exception:
                                logger.warning("[Channel WS] mention resolve failed", exc_info=True)

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
                            # A coding-capable collab discussion channel claims an
                            # @huume mention before EMS sees it. This preserves the
                            # existing clarify-first path for replies to EMS system
                            # messages, while preventing two Huume workflows from
                            # responding to one code request.
                            # Espresso is an independent read-only project agent;
                            # unlike Huume it never enters the EMS dispatch tree.
                            autopr_context_ref = _autopr_context_reference(reply_target_metadata)
                            if is_new_message and autopr_context_ref is not None:
                                # A direct reply to Espresso's decision-bound
                                # request is card evidence, even without an
                                # @espresso mention. Do not also send it to the
                                # generic read-only repository-question agent.
                                _spawn_bg(_bg_apply_autopr_context_reply(
                                    str(ch_uuid), user, row["content"], autopr_context_ref,
                                    broadcast_attachments,
                                ))
                            if (
                                is_new_message
                                and "espresso" in mention_handles
                                and autopr_context_ref is None
                            ):
                                _spawn_bg(_bg_dispatch_espresso_mention(
                                    str(ch_uuid), user, row["content"], row["id"],
                                ))
                            if is_new_message and "huume" in mention_handles:
                                _spawn_bg(_bg_dispatch_huume_mention(
                                    str(ch_uuid), str(row["id"]),
                                    str(row["reply_to_id"]) if reply_to_system else None,
                                    user, row["content"],
                                ))
                            elif is_new_message and spawn_ems:
                                _spawn_bg(_bg_ems_dispatch(
                                    str(ch_uuid), str(row["id"]),
                                    str(row["reply_to_id"]) if reply_to_system else None,
                                    str(user.id), row["content"],
                                    has_huume_mention="huume" in mention_handles,
                                    attachments=list(broadcast_attachments) if broadcast_attachments else None,
                                ))
                            elif (
                                is_new_message and not row["reply_to_id"]
                                and _channel_recently_ems_drafted(room_key)
                                and _draft_reply_decision(row["content"]) is not None
                            ):
                                # A plain "confirm"/"not an event" answering a
                                # live event-draft pill. _draft_reply_decision
                                # is a pure set-membership test, so ordering
                                # this arm ahead of the schedule one below
                                # costs nothing and cannot steal from it: a
                                # schedule answer ("Wilshire", a clock time)
                                # fails this guard synchronously and falls
                                # through.
                                _spawn_bg(_bg_ems_draft_untargeted_reply(
                                    str(ch_uuid), str(user.id), row["content"],
                                ))
                            elif (
                                is_new_message and not row["reply_to_id"]
                                and len(row["content"]) <= 60
                                and _channel_recently_clarified(room_key)
                            ):
                                # Neither threaded-reply nor @huume-mention —
                                # _ems_dispatch_decision spawns nothing for
                                # this message. Still worth one cheap check:
                                # is this a clarify answer typed as a plain
                                # message? See _bg_schedule_untargeted_reply.
                                # _channel_recently_clarified is an in-memory
                                # dict lookup (no DB) — it's what keeps this
                                # branch off the hot path for the overwhelming
                                # common case of a channel with no live
                                # schedule clarify at all.
                                _spawn_bg(_bg_schedule_untargeted_reply(
                                    str(ch_uuid), str(user.id), row["content"],
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
                                "metadata": {},
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
                                    _ch_name = await _get_channel_name(conn, ch_uuid)
                                    _members = await conn.fetch(
                                        """
                                        SELECT cm.user_id, cm.is_muted,
                                               COALESCE(c.company_id, e.org_id) AS company_id
                                        FROM channel_members cm
                                        JOIN users u ON u.id = cm.user_id
                                        LEFT JOIN clients c ON c.user_id = u.id
                                        LEFT JOIN employees e ON e.user_id = u.id
                                        -- INNER join on companies: mw_notifications.company_id is a
                                        -- NOT NULL FK, and create_notifications_bulk is one INSERT for
                                        -- every recipient — one member with an unresolvable company_id
                                        -- (e.g. a stale employees.org_id) would fail the whole
                                        -- statement and silently zero the bell for the entire channel.
                                        JOIN companies co ON co.id = COALESCE(c.company_id, e.org_id)
                                        WHERE cm.channel_id = $1 AND cm.user_id != $2
                                          AND cm.removed_for_inactivity IS NOT TRUE
                                        """,
                                        ch_uuid, user.id,
                                    )
                                    # Mute silences the bell EXCEPT direct
                                    # @mentions (Slack semantics) — the live
                                    # in-channel message frame above is
                                    # unaffected by mute either way.
                                    _notify_targets = [
                                        m for m in _members
                                        if not m["is_muted"] or str(m["user_id"]) in mentioned_user_ids
                                    ]
                                    _preview = (row["content"] or "")[:80]
                                    _spawn_bg(_notify_channel_members(
                                        list(_notify_targets), _ch_name, user.name, _preview, str(ch_uuid),
                                    ))
                                except Exception:
                                    logger.warning("[Channel WS] notify fanout setup failed", exc_info=True)
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Not a member of this channel",
                                "channel_id": str(ch_uuid),
                                "client_message_id": client_message_id,
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

            elif msg_type == "mark_read":
                # Client sends this (debounced) while sitting in a visible
                # channel as messages arrive — otherwise last_read_at only
                # advances on GET /channels/{id} and phantom unread piles up.
                if not mark_read_rate.allow(time.monotonic()):
                    continue
                channel_id = data.get("channel_id")
                rk = _room_key(channel_id) if channel_id else None
                # Per-socket coalesce on top of the bucket: skip a redundant
                # write for a channel already marked read in the last 2s
                # (matches the client's own debounce floor) rather than
                # spending a pool connection on it.
                now_mono = time.monotonic()
                if rk and now_mono - mark_read_last_written.get(rk, 0) < 2:
                    continue
                if rk:
                    try:
                        async with get_connection() as conn:
                            await conn.execute(
                                "UPDATE channel_members SET last_read_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                                UUID(rk), user.id,
                            )
                        mark_read_last_written[rk] = now_mono
                        # Zero the badge on this user's OTHER devices too.
                        await push_channel_read(rk, str(user.id))
                    except Exception:
                        logger.warning("[Channel WS] mark_read failed", exc_info=True)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("[Channel WS] Error: %s", e, exc_info=True)
    finally:
        await manager.disconnect(websocket, user.id)
        # Only clear the online key if this was the user's last active WS.
        # manager.active_connections drops the user_id when the set goes empty.
        if user.id not in manager.active_connections:
            await _mark_offline(user.id)
