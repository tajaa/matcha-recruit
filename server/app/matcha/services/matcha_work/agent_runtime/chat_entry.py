"""A chat message, on its way to becoming a run.

Two doors lead here. In a person's private conversation every message is for
Espresso. In a project chat only an `@espresso` mention is, and only when it
is not a question about the code (the repository agent's) and not a shopping
errand (which becomes a card on the board, as it always has).

Whatever refuses a message, the refusal is posted in the chat and no run row
is written.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException

from app.database import get_connection

from ..agent_card import chat_create, chat_flow
from ..project_agent.chat import (
    broadcast_espresso_message,
    persist_espresso_message,
    post_as_espresso,
    strip_espresso_mention,
)
from . import chat_progress, enqueue, prompts

logger = logging.getLogger(__name__)

_MIN_WORDS = 3
NOTHING_TO_ASK = "What can I do for you?"
NOT_YOURS = "Only the person I asked can answer that."
CLOSED = "That question is closed. Ask me again if you still need it."
CANCELLED = "Okay, I won't."
ON_IT = "On it."


def assistant_request(text: str, *, repo_connected: bool) -> str | None:
    """The request when this `@espresso` mention in a project chat is for the
    assistant; None to leave it to the repository agent.

    Talk about the code always goes to the repository agent. With no
    repository connected there is nobody else to take it, so anything long
    enough to be a request comes here.
    """
    request = " ".join(strip_espresso_mention(text).split())
    if len(request.split()) < _MIN_WORDS:
        return None
    if chat_create._CODE_TALK.search(request):
        return None
    if repo_connected and not chat_create._ERRAND_START.search(request):
        # A repo-connected project's `@espresso` is the repository agent's by
        # default; only something phrased as an errand is ours.
        return None
    return request


def _reason(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        if code == "plan_required":
            return "The Espresso assistant needs the Pro plan."
        if code == "assistant_run_limit":
            return f"You've used all {detail.get('limit')} of today's requests. They reset at midnight UTC."
        if code == "feature_disabled":
            return str(detail.get("message"))
        if code == "token_budget_exhausted":
            return "This workspace has reached its AI token budget."
        detail = detail.get("message") or ""
    return str(detail or "Please try again in a moment.")


async def _flush(messages: list, events: list[dict]) -> None:
    for message in messages:
        await broadcast_espresso_message(message)
    await chat_flow.broadcast_prompt_updates(events)


async def _situation(user, company_id: UUID, channel_id: UUID, surface: str):
    from . import catalog, conversation, grants
    from ..gmail_service import GmailService

    async with get_connection() as conn:
        private = surface == "assistant" and await conversation.is_private_conversation(
            conn, channel_id=channel_id, user_id=user.id,
        )
        active = await grants.load_grants(conn, user.id) if private else {}
    connected, scopes = False, frozenset()
    if private and active:
        gmail = GmailService(user.id)
        await gmail.load_token()
        connected, scopes = gmail.is_configured, gmail.granted_scopes
    return catalog.Situation(
        private=private, grants=active, google_connected=connected, granted_scopes=scopes,
    )


async def ability_keys(user, company_id: UUID, channel_id: UUID, surface: str) -> list[str]:
    from . import catalog

    async def _no_fetch(_url: str):  # the catalog is only being listed
        return {}, set()

    situation = await _situation(user, company_id, channel_id, surface)
    return [a.key for a in catalog.abilities_for(catalog.build_catalog(fetch_page=_no_fetch), situation)]


async def start_run(
    *, channel_id: UUID, company_id: UUID, user, request: str, message_id: UUID,
    surface: str, project_id: UUID | None = None, resume_prompt_id: UUID | None = None,
) -> bool:
    """Gate, queue and acknowledge one run. False when it was refused (the
    reason is posted)."""
    try:
        await enqueue.preflight(user, company_id)
        keys = await ability_keys(user, company_id, channel_id, surface)
        queued = await enqueue.enqueue_assistant_run(
            user=user, company_id=company_id, channel_id=channel_id,
            trigger_message_id=message_id, project_id=project_id, surface=surface,
            prompt=request, abilities=keys, resume_prompt_id=resume_prompt_id,
            skip_preflight=True,
        )
    except HTTPException as exc:
        await post_as_espresso(company_id, channel_id, _reason(exc))
        return False
    if queued["run_id"] is None:
        return True
    await post_as_espresso(
        company_id, channel_id, ON_IT,
        metadata=chat_progress.progress_metadata(queued["run_id"]),
    )
    return True


async def _answer_prompt(*, prompt: dict, channel_id: UUID, company_id: UUID, user, content: str,
                         message_id: UUID, surface: str, project_id: UUID | None) -> bool:
    messages: list = []
    events: list[dict] = []
    resume: UUID | None = None
    next_request: str | None = None
    if (prompt["kind"] != prompts.ASK_USER and prompt["owner_user_id"] == user.id and prompt["live"]
            and prompts.parse_confirmation(content) == "yes"):
        # Refuse before the yes is recorded: a yes that cannot run must leave
        # the question open, not flip the card to "Went ahead".
        try:
            await enqueue.preflight(user, company_id)
        except HTTPException as exc:
            await post_as_espresso(company_id, channel_id, _reason(exc))
            return True
    async with get_connection() as conn, conn.transaction():

        async def say(text: str) -> None:
            messages.append(await persist_espresso_message(conn, company_id, channel_id, text))

        if prompt["owner_user_id"] != user.id:
            await say(NOT_YOURS)
        elif not prompt["live"]:
            await say(CLOSED)
        elif prompt["kind"] == prompts.ASK_USER:
            if await prompts.claim(conn, prompt, user.id, "text"):
                events.append(prompts.update_event(prompt, "answered", "text"))
                # In a project chat the answer may carry the mention it was sent with.
                next_request = " ".join(strip_espresso_mention(content).split()) or content
            else:
                await say(CLOSED)
        else:
            answer = prompts.parse_confirmation(content)
            if answer is None:
                await say(prompts.CONFIRM_HINT)
            elif not await prompts.claim(conn, prompt, user.id, answer):
                await say(CLOSED)
            else:
                events.append(prompts.update_event(prompt, "answered", answer))
                if answer == "yes":
                    resume = prompt["id"]
                else:
                    await say(CANCELLED)
    await _flush(messages, events)
    if resume is not None:
        started = await start_run(
            channel_id=channel_id, company_id=company_id, user=user,
            request="Yes, go ahead.", message_id=message_id, surface=surface,
            project_id=project_id, resume_prompt_id=resume,
        )
        if not started:
            async with get_connection() as conn:
                reopened = await prompts.reopen(conn, prompt, user.id)
            if reopened:
                await _flush([], [prompts.update_event(prompt, "open")])
    elif next_request is not None:
        await start_run(
            channel_id=channel_id, company_id=company_id, user=user, request=next_request,
            message_id=message_id, surface=surface, project_id=project_id,
        )
    return True


async def answer_loaded_prompt(*, prompt: dict, channel_id: UUID, user, content: str,
                               message_id: UUID | None = None) -> bool:
    """Apply a reply to one of the assistant's questions, already loaded."""
    async with get_connection() as conn:
        if message_id is None:
            message_id = await conn.fetchval(
                """SELECT id FROM channel_messages
                   WHERE channel_id = $1 AND sender_id = $2 AND reply_to_id = $3
                   ORDER BY created_at DESC LIMIT 1""",
                channel_id, user.id, prompt["message_id"],
            )
        surface = await conn.fetchval(
            "SELECT surface FROM mw_project_agent_runs WHERE id = $1", prompt["run_id"],
        ) or "assistant"
    if message_id is None:
        return True
    return await _answer_prompt(
        prompt=prompt, channel_id=channel_id, company_id=prompt["company_id"], user=user,
        content=content, message_id=message_id, surface=surface, project_id=prompt.get("project_id"),
    )


async def handle_prompt_reply(*, channel_id: UUID, user, content: str, prompt_id: UUID,
                              message_id: UUID | None = None) -> bool | None:
    """A threaded reply to one of Espresso's questions. None when the question
    is not one of the assistant's (an agent-card question), so the caller goes
    on to handle it as it always has."""
    async with get_connection() as conn:
        prompt = await prompts.load(conn, prompt_id=prompt_id, channel_id=channel_id)
    if prompt is None:
        return None
    return await answer_loaded_prompt(
        prompt=prompt, channel_id=channel_id, user=user, content=content, message_id=message_id,
    )


async def handle_message(
    *, channel_id: UUID, company_id: UUID, user, content: str, message_id: UUID,
    surface: str, reply_prompt_id: UUID | None = None, project_id: UUID | None = None,
) -> bool:
    """One message addressed to Espresso. Returns whether it was handled."""
    try:
        if reply_prompt_id is not None:
            handled = await handle_prompt_reply(
                channel_id=channel_id, user=user, content=content,
                prompt_id=reply_prompt_id, message_id=message_id,
            )
            if handled is not None:
                return handled
        request = " ".join(strip_espresso_mention(content).split())
        if not request:
            await post_as_espresso(company_id, channel_id, NOTHING_TO_ASK)
            return True
        events: list[dict] = []
        pending = None
        # The lookup's connection is released before anything below takes its
        # own: holding one while waiting on the pool for another is how a
        # burst of messages starves the pool.
        async with get_connection() as conn:
            if prompts.parse_confirmation(request) is not None:
                pending = await prompts.open_confirmation(
                    conn, channel_id=channel_id, owner_user_id=user.id,
                )
            if pending is None:
                # A new request moves past whatever was still open: a question
                # is answered by it, a confirmation lapses.
                async with conn.transaction():
                    events = await prompts.close_open(
                        conn, channel_id=channel_id, owner_user_id=user.id, as_answered=True,
                    )
        if pending is not None:
            return await _answer_prompt(
                prompt=pending, channel_id=channel_id, company_id=company_id, user=user,
                content=request, message_id=message_id, surface=surface, project_id=project_id,
            )
        await chat_flow.broadcast_prompt_updates(events)
        await start_run(
            channel_id=channel_id, company_id=company_id, user=user, request=request,
            message_id=message_id, surface=surface, project_id=project_id,
        )
        # Handled either way: a refusal was posted in the chat.
        return True
    except Exception:
        logger.exception("assistant message failed channel=%s", channel_id)
        try:
            await post_as_espresso(company_id, channel_id, "Something went wrong starting that. Please try again.")
        except Exception:
            logger.warning("assistant failure notice could not be posted", exc_info=True)
        return True
