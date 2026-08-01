"""Auto-title a matcha-work thread from its first exchange — Gemini Flash
Lite condenses the opening user/assistant turn into a short title.

Self-contained Gemini call (mirrors task_summary_service / ticket_draft_service
/ commit_scan_service) rather than the entangled matcha_work_ai.generate()
chat pipeline. Fire-and-forget, dispatched from messaging.py's turn pipeline.
"""

import logging
import re
from typing import Optional
from uuid import UUID

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH_LITE
from app.database import get_connection
from app.matcha.services._shared.gemini import genai_env_client as _get_client

logger = logging.getLogger(__name__)

# Flash-lite: cheapest/fastest tier — a title is a one-shot, throwaway read.
FLASH_LITE_MODEL = GEMINI_FLASH_LITE

_DEFAULT_TITLE = "New Chat"
_MAX_TITLE_LEN = 80
_MAX_SNIPPET_LEN = 1500


def _build_title_prompt(user_text: str, assistant_text: str) -> str:
    return (
        "Write a short title for this chat, 3-6 words, Title Case, a noun "
        "phrase describing what it's about. No quotes, no markdown, no "
        "trailing punctuation, no preamble — just the title.\n\n"
        f"USER: {user_text}\n\nASSISTANT: {assistant_text}\n\nTitle:"
    )


def _clean_title(raw: str) -> Optional[str]:
    """Strip quotes/markdown/newlines the model might add; cap length;
    reject an effectively-empty result."""
    if not raw:
        return None
    title = raw.strip()
    title = re.sub(r"^[\"'`*_\s]+|[\"'`*_\s.]+$", "", title)
    title = " ".join(title.split())
    if not title:
        return None
    if len(title) > _MAX_TITLE_LEN:
        title = title[:_MAX_TITLE_LEN].rstrip()
    return title or None


async def maybe_autotitle_thread(thread_id: UUID) -> None:
    """No-ops unless the thread's title is still the default 'New Chat' — a
    user rename always wins, even one that happens mid-flight (the final
    UPDATE is guarded on the same condition). Never raises: a flaky Gemini
    call, or a thread with no assistant reply yet, must not surface anywhere
    — this runs detached from the request/response cycle.
    """
    try:
        async with get_connection() as conn:
            thread_row = await conn.fetchrow(
                "SELECT title FROM mw_threads WHERE id=$1", thread_id
            )
            # Espresso (desktop) seeds new threads as "New Chat <dateStr>"
            # rather than the web client's bare "New Chat" — both are the
            # placeholder title and are eligible for autotitling.
            if thread_row is None or not thread_row["title"].startswith(_DEFAULT_TITLE):
                return
            original_title = thread_row["title"]

            messages = await conn.fetch(
                """
                SELECT role, content FROM mw_messages
                WHERE thread_id=$1
                ORDER BY created_at ASC
                LIMIT 4
                """,
                thread_id,
            )

        user_msg = next((m for m in messages if m["role"] == "user"), None)
        assistant_msg = next((m for m in messages if m["role"] == "assistant"), None)
        if user_msg is None or assistant_msg is None:
            return

        user_text = (user_msg["content"] or "")[:_MAX_SNIPPET_LEN]
        assistant_text = (assistant_msg["content"] or "")[:_MAX_SNIPPET_LEN]
        if not user_text.strip():
            return

        prompt = _build_title_prompt(user_text, assistant_text)

        try:
            resp = await _get_client().aio.models.generate_content(
                model=FLASH_LITE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=60,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as e:  # noqa: BLE001 — soft-fail, never surface
            logger.warning("thread autotitle: Gemini failed thread=%s: %s", thread_id, e)
            return

        title = _clean_title(resp.text or "")
        if not title:
            logger.warning(
                "thread autotitle: empty response thread=%s finish_reason=%s",
                thread_id,
                getattr(resp.candidates[0], "finish_reason", None) if resp.candidates else None,
            )
            return

        async with get_connection() as conn:
            updated = await conn.fetchrow(
                """
                UPDATE mw_threads
                SET title=$1, updated_at=NOW()
                WHERE id=$2 AND title=$3
                RETURNING id
                """,
                title,
                thread_id,
                original_title,
            )
        if updated is not None:
            from app.matcha.services.matcha_work import matcha_work_document as doc_svc
            await doc_svc.sync_element_record(thread_id)
    except Exception as e:  # noqa: BLE001 — background task, must never raise
        logger.warning("thread autotitle: unexpected failure thread=%s: %s", thread_id, e)
