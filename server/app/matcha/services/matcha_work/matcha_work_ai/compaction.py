"""Conversation compaction: the summarization prompt, its thresholds, and the
compact_conversation entry point the turn pipeline schedules in the background.
"""
import asyncio
import logging
from typing import Optional
from google import genai
from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH


logger = logging.getLogger(__name__)


COMPACTION_PROMPT = (
    "Summarize this conversation history into a concise context block (max 200 words). "
    "Include: key decisions made, document type, specific values/names/dates mentioned, "
    "user preferences expressed, and current state of the work. "
    "Do NOT include greetings or filler. Return ONLY the summary text, no JSON."
)


COMPACTION_MODEL = GEMINI_FLASH


COMPACTION_THRESHOLD = 30


# Cap how many "older" messages we feed into one compaction call. Without this,
# a thread with 5000 messages would send all 4985 older ones to the summarizer
# every refresh cycle, blowing up cost + latency + hitting input limits.
COMPACTION_INPUT_MESSAGE_CAP = 200


async def compact_conversation(
    messages: list[dict],
    client: genai.Client,
    prior_summary: Optional[str] = None,
) -> Optional[str]:
    """Summarize older messages into a short context block using a fast model.

    If prior_summary is provided, the new summary builds on it iteratively so
    older context is preserved without re-summarizing the entire history each
    cycle. Older raw messages are also capped at COMPACTION_INPUT_MESSAGE_CAP
    to bound cost and latency on long threads.
    """
    if len(messages) < COMPACTION_THRESHOLD:
        return None

    # Summarize all but the most recent 15 messages, capped to avoid blowup
    older = messages[:-15][-COMPACTION_INPUT_MESSAGE_CAP:]
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in older
    )
    if prior_summary:
        conversation_text = (
            f"PRIOR SUMMARY (preserve key facts from this):\n{prior_summary}\n\n"
            f"NEW MESSAGES:\n{conversation_text}"
        )

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=COMPACTION_MODEL,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=conversation_text)],
                )],
                config=types.GenerateContentConfig(
                    system_instruction=COMPACTION_PROMPT,
                    temperature=0.1,
                ),
            ),
            timeout=30,
        )
        summary = (response.text or "").strip()
        if summary:
            return summary
    except Exception:
        logger.warning("Conversation compaction failed", exc_info=True)

    return None
