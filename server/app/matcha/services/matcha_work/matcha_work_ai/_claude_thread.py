"""A thread turn on Claude, laid out for prompt caching.

Messages caches by prefix, in render order `system` → `messages`; any byte
that changes ends the reusable prefix there. So the request is ordered from
most to least stable, with a breakpoint after each stable part:

    system A   the instructions: the skill-engine template with no date and no
               company data. Identical for every thread on the platform.   [1h]
    system B   the thread's context: company profile, project files, the
               recruiting roster, the HR-Pilot action vocabulary, the thread's
               mode contexts, the conversation summary. Changes when a mode is
               toggled, a file is uploaded, a candidate moves, or the thread is
               compacted.                                                    [1h]
    messages   the history from the checkpoint (`claude_history_start`),
               append-only, attached-file text inside the message that carried
               it; the latest user message carries the third breakpoint.    [1h]
    tail       one `role: "system"` TURN CONTEXT message: today's date, the
               document (`current_state`), valid fields, per-message
               regulations, the slide being edited. Never stored, so it can
               change every turn without touching anything cached.

1h TTL: people often answer a thread minutes later, and a turn only writes
what it appended, so the 2x write rate is paid on small amounts.

Gemini keeps its own two-string prompt; both are built from `_parts`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from google.genai import types

from ._fields import SUPPORTED_AI_MODES, SUPPORTED_AI_OPERATIONS, SUPPORTED_AI_SKILLS
from ._parts import HR_PILOT_ACTIONS, recruiting_update, slide_lock, summary_block
from ._prompts import (
    MATCHA_WORK_BLOG_DYNAMIC_PROMPT,
    MATCHA_WORK_BLOG_STATIC_PROMPT,
    MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE,
    MATCHA_WORK_STATIC_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)

CACHE_CONTROL = {"type": "ephemeral", "ttl": "1h"}
TODAY_REF = "given in TURN CONTEXT at the end of the conversation"

# The checkpoint after a compaction keeps this many recent messages verbatim
# (the same 15 `compaction.compact_conversation` leaves out of its summary).
KEEP_RECENT = 15
# Without a usable summary the window still has to end somewhere: past this
# many messages it starts at a multiple of STEP instead, so it moves rarely.
MAX_WINDOW = 60
STEP = 20

# Skills whose turns write documents: they think harder, as Gemini's
# `classify_thinking_level` already has them do.
_DOCUMENT_SKILLS = frozenset({
    "offer_letter", "review", "workbook", "handbook", "policy", "presentation", "project", "onboarding",
})

_REASONING_STEP = {
    "type": "object",
    "properties": {
        "step": {"type": "integer"},
        "question": {"type": "string"},
        "answer": {"type": "string"},
        "conclusion": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["step", "question", "answer", "conclusion", "sources"],
    "additionalProperties": False,
}

# The engine's reply contract as a schema. Free-form `updates` cannot be
# expressed (every object must close its properties), so it travels as a
# JSON string and `engine_reply_text` turns it back into the object the
# shared parser expects. `reply` comes early so it streams before the
# document edits.
ENGINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": sorted(SUPPORTED_AI_MODES)},
        "skill": {"type": "string", "enum": sorted(SUPPORTED_AI_SKILLS)},
        "operation": {"type": "string", "enum": sorted(SUPPORTED_AI_OPERATIONS)},
        "confidence": {"type": "number"},
        "reply": {"type": "string"},
        "updates_json": {"type": "string"},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "compliance_reasoning": {"type": "array", "items": _REASONING_STEP},
        "referenced_categories": {"type": "array", "items": {"type": "string"}},
        "referenced_locations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "mode", "skill", "operation", "confidence", "reply", "updates_json", "missing_fields",
        "compliance_reasoning", "referenced_categories", "referenced_locations",
    ],
    "additionalProperties": False,
}

_OUTPUT_NOTE = (
    "\n\nHow your answer is delivered: it is one JSON object in the shape described above, except that "
    "`updates` is carried as `updates_json`, a string holding the updates object as JSON (\"{}\" when "
    "nothing changes). Write `reply` before you write the updates. Dates and the thread's live state "
    "(current_skill, current_state, valid_update_fields) are in the TURN CONTEXT message at the end of "
    "the conversation; the company and mode context is in THREAD CONTEXT below."
)
_JSON_ONLY = (
    "\n\nRespond with exactly one JSON object in the shape described above and nothing else: no prose "
    "before or after it, and no Markdown code fences."
)


def claude_history_start(message_count: int, summary_at_count: Optional[int]) -> int:
    """Where a Claude thread's history window starts, as an absolute message
    index. It moves only at a compaction (or every STEP messages when there is
    none to anchor on), so the history in between is append-only and cached."""
    start = max(0, (summary_at_count or 0) - KEEP_RECENT) if summary_at_count else 0
    if message_count - start > MAX_WINDOW:
        start = max(start, ((message_count - (MAX_WINDOW - STEP)) // STEP) * STEP)
    return min(start, max(0, message_count - 1))


def thread_effort(*, current_skill: str, grounded: bool) -> str:
    """One effort per thread shape, never per message: an effort change
    invalidates the cached conversation. Adaptive thinking still decides how
    much to think on each turn, down to not at all on "thanks"."""
    return "high" if grounded or current_skill in _DOCUMENT_SKILLS else "medium"


def instructions(blog: bool, structured: bool) -> str:
    """System block A."""
    template = MATCHA_WORK_BLOG_STATIC_PROMPT if blog else MATCHA_WORK_STATIC_PROMPT_TEMPLATE
    text = template.format(today=TODAY_REF, company_context="").rstrip()
    return text + (_OUTPUT_NOTE if structured else _JSON_ONLY)


def thread_context(*, company_context: str, stable_context: str, summary: Optional[str],
                   hr_pilot_mode: bool) -> str:
    """System block B, or "" when the thread has none."""
    parts = []
    if company_context.strip():
        parts.append(company_context.strip())
    if hr_pilot_mode:
        parts.append(HR_PILOT_ACTIONS.strip())
    if stable_context.strip():
        parts.append(stable_context.strip())
    summary_text = summary_block(summary).strip()
    if summary_text:
        parts.append(summary_text)
    if not parts:
        return ""
    return "THREAD CONTEXT\n\n" + "\n\n".join(parts)


def turn_context(*, today: str, current_skill: str, current_state: dict, valid_fields: list[str],
                 per_message_context: str = "", blog_state: Optional[str] = None,
                 slide_index: Optional[int] = None, slide_context: str = "") -> str:
    """The trailing TURN CONTEXT message."""
    lines = ["TURN CONTEXT (this turn only; it is not part of the conversation)", f"Today's date: {today}"]
    if blog_state is not None:
        lines.append(MATCHA_WORK_BLOG_DYNAMIC_PROMPT.format(blog_state=blog_state).strip())
        lines.append(f"- valid_update_fields: {', '.join(valid_fields)}")
    else:
        lines.append(MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE.format(
            current_skill=current_skill,
            current_state=json.dumps(current_state, default=str, separators=(",", ":"), sort_keys=True),
            valid_fields=", ".join(valid_fields),
        ).strip())
    for extra in (
        per_message_context,
        recruiting_update(current_skill, current_state),
        slide_lock(slide_index, current_skill, current_state),
        slide_context,
    ):
        if extra and extra.strip():
            lines.append(extra.strip())
    return "\n\n".join(lines)


def history_contents(messages: list[dict]) -> list[types.Content]:
    """The window as Gemini-shaped contents, ready for the shared image
    normalizer and translator. A user turn is its images, then the text of
    files attached to it, then what the person wrote, before any per-turn
    rewrite (the slide being edited rides in TURN CONTEXT instead, so the
    stored history and the sent history never differ)."""
    contents: list[types.Content] = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        parts: list[types.Part] = []
        if role == "user":
            for image_bytes, mime in (msg.get("claude_image_parts", msg.get("image_parts")) or []):
                if image_bytes:
                    parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
            for filename, text in (msg.get("files") or []):
                if text:
                    parts.append(types.Part(text=f"[Attached file: {filename or 'file'}]\n{text}"))
        text = msg.get("original_content", msg.get("content")) or ""
        if text or not parts:
            parts.append(types.Part(text=text))
        contents.append(types.Content(role=role, parts=parts))
    return contents


@dataclass
class ThreadRequest:
    """Everything one call needs except the model and its settings."""

    blog: bool
    context: str  # system block B ("" for none)
    history: list[dict]  # Messages turns, breakpoint already on the last user block
    turn_context: str
    valid_fields: list[str] = field(default_factory=list)
    skill: str = "chat"

    def system(self, *, structured: bool) -> list[dict]:
        return build_system(blog=self.blog, structured=structured, context=self.context)

    def messages(self, *, system_role: bool) -> list[dict]:
        """The history plus the turn context: as a trailing `role: "system"`
        message, or (on a model without it) as a text block at the end of the
        latest user message, after its breakpoint."""
        if system_role:
            return [*self.history, {"role": "system", "content": self.turn_context}]
        history = [dict(m) for m in self.history]
        last = history[-1]
        last["content"] = [*last["content"], {"type": "text", "text": f"<turn_context>\n{self.turn_context}\n</turn_context>"}]
        return history


def build_system(*, blog: bool, structured: bool, context: str) -> list[dict]:
    blocks = [{"type": "text", "text": instructions(blog, structured), "cache_control": dict(CACHE_CONTROL)}]
    if context:
        blocks.append({"type": "text", "text": context, "cache_control": dict(CACHE_CONTROL)})
    return blocks


def mark_latest_user_turn(messages: list[dict]) -> list[dict]:
    """Put the conversation breakpoint on the last block of the last user
    turn. Content becomes a block list where it was a string."""
    out = [dict(m) for m in messages]
    for msg in reversed(out):
        if msg["role"] != "user":
            continue
        content = msg["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else [dict(b) for b in content]
        if blocks:
            blocks[-1] = {**blocks[-1], "cache_control": dict(CACHE_CONTROL)}
        msg["content"] = blocks
        break
    return out


def engine_reply_text(raw: str) -> str:
    """The schema's JSON → the engine's reply JSON (`updates_json` back to an
    `updates` object) for `provider._parse_engine_reply`. Anything that is not
    the schema's object passes through for the parser's own salvage."""
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if not isinstance(parsed, dict) or "updates_json" not in parsed:
        return raw
    encoded = parsed.pop("updates_json")
    updates: Any = {}
    if isinstance(encoded, str) and encoded.strip():
        try:
            updates = json.loads(encoded)
        except ValueError:
            logger.warning("Claude returned invalid updates_json; ignoring document updates")
            updates = {}
    parsed["updates"] = updates if isinstance(updates, dict) else {}
    return json.dumps(parsed)
