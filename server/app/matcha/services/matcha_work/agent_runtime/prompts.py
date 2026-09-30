"""Questions the assistant asks in chat: `ask_user` and `confirm_action`.

They live in `mw_agent_card_prompts`, next to the agent-card questions, and
are posted as the same kind of message, so both apps render them with the
card they already have and a button press arrives as an ordinary threaded
reply. What differs is what an answer does:

  ask_user        any reply from the person who was asked is the answer, and
                  starts the next run (the conversation is replayed to it)
  confirm_action  yes runs the frozen action, exactly as it was shown; no
                  drops it. Anything else is not an answer.

Only the person who was asked can answer either.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from uuid import UUID

from app.database import decode_jsonb

from ..agent_card import chat_flow
from ..project_agent.chat import persist_espresso_message

logger = logging.getLogger(__name__)

ASK_USER = "ask_user"
CONFIRM_ACTION = "confirm_action"
KINDS = (ASK_USER, CONFIRM_ACTION)
ASK_TTL = timedelta(days=2)
CONFIRM_TTL = timedelta(hours=12)
YES_LABEL = "Yes, go ahead"
NO_LABEL = "No, cancel"
CONFIRM_HINT = "Reply yes to go ahead, or no to cancel."


_YES = frozenset({
    "yes", "y", "yep", "yeah", "yes please", "yes go ahead", "go ahead", "do it", "confirm",
    "confirmed", "send it", "book it", "ok go ahead", "okay go ahead", "please do",
})
_NO = frozenset({
    "no", "n", "nope", "no thanks", "no thank you", "cancel", "cancel it", "don t", "dont",
    "do not", "stop", "no cancel", "never mind", "nevermind",
})


def parse_confirmation(text: str) -> str | None:
    """"yes", "no", or None when the message is neither. A closed list on
    purpose: an action goes ahead on a clear yes and on nothing else, so a
    sentence that merely contains "yes" is not one."""
    if not isinstance(text, str) or len(text) > 40:
        return None
    normalized = " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())
    if normalized in _YES:
        return "yes"
    if normalized in _NO:
        return "no"
    return None


def ask_view(question: dict) -> dict:
    return {
        "question": question["question"],
        "buttons": [
            {"label": option, "reply": option, "style": "secondary", "detail": None}
            for option in question.get("options") or []
        ],
    }


def confirm_view(frozen: dict, ungrounded: list[str]) -> dict:
    preview = frozen.get("preview") or {}
    who = ", ".join(ungrounded)
    return {
        "question": (
            f"{preview.get('title') or 'Go ahead'}? You didn't mention {who}, so I'm checking first."
            if who else f"{preview.get('title') or 'Go ahead'}?"
        ),
        "action": {"title": preview.get("title"), "lines": preview.get("lines") or []},
        "buttons": [
            {"label": YES_LABEL, "reply": "yes", "style": "primary", "detail": None},
            {"label": NO_LABEL, "reply": "no", "style": "secondary", "detail": None},
        ],
    }


def metadata(prompt_id, kind: str, *, run_id, owner_user_id, expires_at, view: dict,
             project_id=None) -> dict:
    out = {
        "kind": chat_flow.PROMPT_METADATA_KIND,
        "prompt_id": str(prompt_id),
        "prompt_kind": kind,
        "run_id": str(run_id),
        "owner_user_id": str(owner_user_id),
        "expires_at": expires_at.isoformat(),
        "view": view,
    }
    if project_id is not None:
        out["project_id"] = str(project_id)
    return out


async def ask(conn, *, run: dict, kind: str, payload: dict, view: dict, content: str) -> dict | None:
    """Insert a question and its message on the caller's transaction. Returns
    the message to broadcast once that transaction has committed."""
    row = await conn.fetchrow(
        """INSERT INTO mw_agent_card_prompts
               (company_id, project_id, task_id, run_id, channel_id, kind,
                owner_user_id, payload, expires_at)
           VALUES ($1, $2, NULL, $3, $4, $5, $6, $7::jsonb, NOW() + $8::interval)
           RETURNING id, expires_at""",
        run["company_id"], run.get("project_id"), run["id"], run["channel_id"], kind,
        run["requested_by"], json.dumps(payload),
        CONFIRM_TTL if kind == CONFIRM_ACTION else ASK_TTL,
    )
    message = await persist_espresso_message(
        conn, run["company_id"], run["channel_id"], content,
        metadata=metadata(
            row["id"], kind, run_id=run["id"], owner_user_id=run["requested_by"],
            expires_at=row["expires_at"], view=view, project_id=run.get("project_id"),
        ),
    )
    if message:
        await conn.execute(
            "UPDATE mw_agent_card_prompts SET message_id = $2 WHERE id = $1",
            row["id"], UUID(message["id"]),
        )
    return message


def answer_text(kind: str, answer: str | None) -> str | None:
    if not answer:
        return None
    if kind == CONFIRM_ACTION:
        return "Went ahead" if answer == "yes" else "Cancelled"
    return "Answered"


def update_event(row, status: str, answer: str | None = None) -> dict:
    return {
        "type": chat_flow.PROMPT_UPDATED_EVENT,
        "channel_id": str(row["channel_id"]),
        "prompt_id": str(row["id"]),
        "status": status,
        "answer": answer,
        "answer_text": answer_text(row["kind"], answer),
    }


async def close_open(conn, *, channel_id: UUID, owner_user_id: UUID,
                     as_answered: bool = False) -> list[dict]:
    """Close the person's open questions in this conversation: a new message
    moved past them. An open `ask_user` was answered by that message; an open
    `confirm_action` was not, and lapses. Returns the socket events to send
    after the transaction commits."""
    rows = await conn.fetch(
        """UPDATE mw_agent_card_prompts
           SET status = CASE WHEN kind = 'ask_user' AND $3 THEN 'answered' ELSE 'superseded' END,
               answer = CASE WHEN kind = 'ask_user' AND $3 THEN 'text' ELSE answer END,
               answered_by = CASE WHEN kind = 'ask_user' AND $3 THEN $2 ELSE answered_by END,
               answered_at = CASE WHEN kind = 'ask_user' AND $3 THEN NOW() ELSE answered_at END
           WHERE channel_id = $1 AND owner_user_id = $2 AND status = 'open'
             AND kind IN ('ask_user', 'confirm_action')
           RETURNING id, channel_id, kind, status""",
        channel_id, owner_user_id, as_answered,
    )
    return [
        update_event(row, row["status"], "text" if row["status"] == "answered" else None)
        for row in rows
    ]


async def load(conn, *, prompt_id: UUID, channel_id: UUID) -> dict | None:
    row = await conn.fetchrow(
        """SELECT *, (status = 'open' AND expires_at > NOW()) AS live
           FROM mw_agent_card_prompts
           WHERE id = $1 AND channel_id = $2 AND kind IN ('ask_user', 'confirm_action')""",
        prompt_id, channel_id,
    )
    if not row:
        return None
    prompt = dict(row)
    prompt["payload"] = decode_jsonb(prompt.get("payload"), {}) or {}
    return prompt


async def open_confirmation(conn, *, channel_id: UUID, owner_user_id: UUID) -> dict | None:
    """The person's newest live confirmation here, for a plain "yes" or "no"."""
    row = await conn.fetchrow(
        """SELECT *, TRUE AS live FROM mw_agent_card_prompts
           WHERE channel_id = $1 AND owner_user_id = $2 AND kind = 'confirm_action'
             AND status = 'open' AND expires_at > NOW()
           ORDER BY created_at DESC LIMIT 1""",
        channel_id, owner_user_id,
    )
    if not row:
        return None
    prompt = dict(row)
    prompt["payload"] = decode_jsonb(prompt.get("payload"), {}) or {}
    return prompt


async def claim(conn, prompt: dict, user_id: UUID, answer: str) -> bool:
    """Answered once: the first claim wins, a second finds it closed."""
    return bool(await conn.fetchval(
        """UPDATE mw_agent_card_prompts
           SET status = 'answered', answer = $2, answered_by = $3, answered_at = NOW()
           WHERE id = $1 AND status = 'open' AND expires_at > NOW()
           RETURNING TRUE""",
        prompt["id"], answer, user_id,
    ))


async def reopen(conn, prompt: dict, user_id: UUID) -> bool:
    """Undo a yes whose run could not be queued (a cap, a rate limit, a run
    already live), so the frozen action is not lost and can be approved again
    once whatever refused it clears. Only while it would still be claimable."""
    return bool(await conn.fetchval(
        """UPDATE mw_agent_card_prompts
           SET status = 'open', answer = NULL, answered_by = NULL, answered_at = NULL
           WHERE id = $1 AND status = 'answered' AND answer = 'yes' AND answered_by = $2
             AND expires_at > NOW()
           RETURNING TRUE""",
        prompt["id"], user_id,
    ))


async def overlay_statuses(conn, messages, *, channel_id: UUID) -> list:
    """`chat_flow.overlay_prompt_statuses` words every answer the agent-card
    way; restamp the assistant's own questions with their own wording."""
    out = []
    for message in messages:
        meta = decode_jsonb(message.get("metadata"), {}) or {}
        if (
            isinstance(meta, dict)
            and meta.get("kind") == chat_flow.PROMPT_METADATA_KIND
            and meta.get("prompt_kind") in KINDS
            and "prompt_status" in meta
        ):
            message = dict(message)
            message["metadata"] = {**meta, "answer_text": answer_text(meta["prompt_kind"], meta.get("answer"))}
        out.append(message)
    return out
