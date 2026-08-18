"""Safety-meeting summary — one Gemini text call over the full assembled
transcript when the manager taps "End meeting". Produces the structured draft
(summary paragraph, topics covered, action items, attendees mentioned) that the
manager REVIEWS and edits before signing. Best-effort, never raises: on failure
the meeting still moves to review with an empty draft the manager types
themselves.
"""

import asyncio
import json
import logging
from typing import Optional

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH
from app.matcha.services._shared.gemini import genai_env_client

logger = logging.getLogger(__name__)

SUMMARY_TIMEOUT = 60
MAX_TOPICS = 20
MAX_ACTION_ITEMS = 30
MAX_ATTENDEES_MENTIONED = 100
MAX_SUMMARY_CHARS = 20000
MAX_INPUT_CHARS = 120000  # ~2h of speech; longer transcripts are truncated at the tail


def _build_prompt(*, title: str, topic: Optional[str], location_name: Optional[str],
                  attendee_names: list[str], transcript: str) -> str:
    context_lines = [f"Meeting title: {title}"]
    if topic:
        context_lines.append(f"Planned topic: {topic}")
    if location_name:
        context_lines.append(f"Location: {location_name}")
    if attendee_names:
        context_lines.append(f"Expected attendees: {', '.join(attendee_names)}")
    context = "\n".join(context_lines)
    return f"""You are compiling the official record of a workplace safety meeting (a toolbox talk) from its transcript. A safety manager will review your draft for accuracy before signing it.

{context}

Transcript:
\"\"\"
{transcript}
\"\"\"

Return ONLY valid JSON with exactly these keys:
{{"summary": "<a factual 1-3 paragraph narrative of what was covered and discussed, third person, suitable for a compliance record>",
  "topics": ["<a distinct safety topic actually covered>", ...],
  "action_items": [{{"description": "<a follow-up action agreed or assigned>", "owner": "<the person responsible if named, else null>"}}, ...],
  "attendees_mentioned": ["<names of people identified as present or speaking>", ...]}}

Rules:
- Never invent content not present in the transcript. If the transcript is empty or unintelligible, return empty values.
- Topics are short labels (e.g. "Ladder safety", "Heat illness prevention"), not sentences.
- Action items must be things actually agreed or assigned in the meeting, not generic best practices.
- Do not include markdown fences."""


def _str_or_none(value, max_chars: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:max_chars] if value else None


def _str_list(value, *, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split())[:max_chars]
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        out.append(cleaned)
        if len(out) >= max_items:
            break
    return out


def _coerce_summary(raw: dict) -> dict:
    """Validate/clamp the model output into the safe draft shape. PURE
    (unit-tested). Never raises; always returns the full canonical dict."""
    if not isinstance(raw, dict):
        raw = {}
    action_items = []
    raw_action_items = raw.get("action_items")
    if not isinstance(raw_action_items, list):
        raw_action_items = []
    for entry in raw_action_items[:MAX_ACTION_ITEMS]:
        if isinstance(entry, str):
            description, owner = entry.strip(), None
        elif isinstance(entry, dict):
            description = entry.get("description")
            description = description.strip() if isinstance(description, str) else ""
            owner = entry.get("owner")
            owner = owner.strip()[:120] if isinstance(owner, str) and owner.strip() else None
        else:
            continue
        if description:
            action_items.append({"description": description[:500], "owner": owner})

    return {
        "summary": _str_or_none(raw.get("summary"), MAX_SUMMARY_CHARS),
        "topics": _str_list(raw.get("topics"), max_items=MAX_TOPICS, max_chars=200),
        "action_items": action_items,
        "attendees_mentioned": _str_list(
            raw.get("attendees_mentioned"), max_items=MAX_ATTENDEES_MENTIONED, max_chars=120),
    }


def _parse_model_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


async def summarize_meeting(*, title: str, topic: Optional[str], location_name: Optional[str],
                            attendee_names: list[str], transcript: str) -> dict:
    """Gemini compiles the structured draft from the full transcript, with one
    retry (fresh timeout) on a transient timeout or unparsable JSON. Never
    raises. ``available`` is False only when Gemini never returned a usable
    response (an empty-but-clean draft still counts as available)."""
    client = genai_env_client()
    prompt = _build_prompt(
        title=title, topic=topic, location_name=location_name,
        attendee_names=attendee_names, transcript=transcript[-MAX_INPUT_CHARS:],
    )
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
    )

    payload: dict = {}
    succeeded = False
    for attempt in range(1, 3):  # one retry on timeout / bad JSON
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=GEMINI_FLASH, contents=prompt, config=config,
                ),
                timeout=SUMMARY_TIMEOUT,
            )
            raw = (getattr(response, "text", None) or "").strip()
            payload = _parse_model_json(raw)
            succeeded = True
            break
        except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                logger.warning("safety-meeting summary failed (attempt %d/2): %s", attempt, exc)
        except Exception as exc:  # never-raises contract — anything else, no retry
            logger.warning("safety-meeting summary failed (attempt %d/2): %s", attempt, exc)
            break

    result = _coerce_summary(payload)
    result["available"] = succeeded
    result["model"] = GEMINI_FLASH
    return result
