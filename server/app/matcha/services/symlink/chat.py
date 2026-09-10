"""The sym-link "tunnel chat" engine — one bounded Gemini turn.

Same shape as `services/ir/ir_chat_intake.next_public_turn`: transcript +
known fields in, merged state out, never raises, never persists. The
difference is that the field schema is the link's *spec* (see kinds.py)
rather than a hard-coded incident shape.

Two invariants, both enforced here and not in the model:

  * Completion is deterministic — `is_complete` looks only at required fields
    and required attachment slots. The model proposes values and the next
    question; it never says "done".
  * A turn can only ADD or refine a known field, never blank one (`coerce_fields`
    mirrors `_coerce_public_chat_fields`).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH_LITE
from app.matcha.services._shared.gemini import genai_env_client
from app.matcha.services.ir.ir_voice_parser import _VOICE_PARSE_SAFETY_SETTINGS

logger = logging.getLogger(__name__)

CHAT_TURN_TIMEOUT = 20
MAX_TURNS = 20
# Transcript sent to the model is trimmed to this many trailing messages so a
# long resume never blows the prompt; known_fields carries the accumulated
# state, so nothing collected is lost by trimming.
MAX_PROMPT_MESSAGES = 30
FALLBACK_ERROR_MESSAGE = "Sorry, I'm having trouble right now. You can review what you have so far."


# ── deterministic pieces ───────────────────────────────────────────────────


def _field_map(spec: dict) -> dict[str, dict]:
    return {f["key"]: f for f in spec.get("fields", []) if isinstance(f, dict) and f.get("key")}


def _coerce_value(raw: Any, field: dict) -> Any | None:
    """One field's model-proposed value → stored value, or None to ignore."""
    ftype = field.get("type", "text")
    max_len = int(field.get("max_len") or 255)
    if raw is None:
        return None
    if ftype == "number":
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            return raw
        if isinstance(raw, str):
            text = raw.strip().replace(",", "")
            if not text:
                return None
            try:
                return int(text) if text.lstrip("-").isdigit() else float(text)
            except ValueError:
                return None
        return None
    if not isinstance(raw, str):
        return None
    cleaned = " ".join(raw.split()) if ftype != "long_text" else raw.strip()
    if not cleaned:
        return None
    if ftype == "choice":
        choices = field.get("choices") or []
        lowered = cleaned.lower()
        for choice in choices:
            if isinstance(choice, str) and choice.lower() == lowered:
                return choice
        # Tolerate a prefix / substring ("meets" → "Meets expectations").
        matches = [c for c in choices if isinstance(c, str) and (lowered in c.lower() or c.lower() in lowered)]
        return matches[0] if len(matches) == 1 else None
    return cleaned[:max_len]


def coerce_fields(raw: dict | None, known: dict | None, spec: dict) -> dict:
    """Merge model output over the known draft. Unknown keys are dropped; a
    known value is only replaced by a non-empty coerced value."""
    fields = _field_map(spec)
    merged: dict[str, Any] = {}
    known = known or {}
    raw = raw if isinstance(raw, dict) else {}
    for key, field in fields.items():
        current = _coerce_value(known.get(key), field)
        proposed = _coerce_value(raw.get(key), field)
        merged[key] = proposed if proposed is not None else current
    return merged


def coerce_submitted(raw: dict | None, spec: dict) -> dict:
    """The human review-form counterpart of `coerce_fields`: what the recipient
    sends IS the draft. A cleared input clears the field (the model may have
    extracted a wrong phone number and the person is correcting it), so
    nothing falls back to the previously known value. Required-ness is still
    enforced afterwards by `is_complete`."""
    fields = _field_map(spec)
    raw = raw if isinstance(raw, dict) else {}
    return {key: _coerce_value(raw.get(key), field) for key, field in fields.items()}


def missing_items(fields: dict | None, present_slots: Iterable[str], spec: dict) -> list[dict]:
    """Required fields / attachment slots still empty, in spec order."""
    fields = fields or {}
    present = set(present_slots or ())
    out: list[dict] = []
    for f in spec.get("fields", []):
        if f.get("required") and fields.get(f["key"]) in (None, ""):
            out.append({"kind": "field", "key": f["key"], "label": f.get("label") or f["key"]})
    for a in spec.get("attachments", []):
        if a.get("required") and a["slot"] not in present:
            out.append({"kind": "attachment", "key": a["slot"], "label": a.get("label") or a["slot"]})
    return out


def is_complete(fields: dict | None, present_slots: Iterable[str], spec: dict) -> bool:
    return not missing_items(fields, present_slots, spec)


# ── prompt ─────────────────────────────────────────────────────────────────


def _render_transcript(transcript: list[dict]) -> str:
    lines = []
    for entry in transcript[-MAX_PROMPT_MESSAGES:]:
        role = "Recipient" if entry.get("role") == "user" else "Assistant"
        content = str(entry.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) or "(no messages yet)"


def _field_line(f: dict) -> str:
    bits = [f"- {f['key']}: {f.get('label') or f['key']} ({f.get('type', 'text')}"]
    if f.get("type") == "choice" and f.get("choices"):
        bits.append("; one of: " + " | ".join(str(c) for c in f["choices"]))
    bits.append(")")
    if f.get("hint"):
        bits.append(f" — {f['hint']}")
    return "".join(bits)


def build_prompt(spec: dict, transcript: list[dict], known: dict | None,
                 present_slots: Iterable[str], *, company_name: str | None = None,
                 instructions: str | None = None) -> str:
    known = known or {}
    present = set(present_slots or ())
    required = [f for f in spec.get("fields", []) if f.get("required")]
    optional = [f for f in spec.get("fields", []) if not f.get("required")]
    missing = missing_items(known, present, spec)

    known_lines = [f"- {k}: {v}" for k, v in known.items() if v not in (None, "")] or ["(nothing yet)"]
    attach_lines = []
    for a in spec.get("attachments", []):
        state = "UPLOADED" if a["slot"] in present else "not yet uploaded"
        need = "required" if a.get("required") else "optional"
        attach_lines.append(f"- {a['slot']}: {a.get('label') or a['slot']} ({need}) — {state}")
    attach_text = "\n".join(attach_lines) or "(none)"
    missing_text = "\n".join(f"- {m['label']} ({m['kind']})" for m in missing) or "(nothing — everything required is collected)"

    schema_keys = ", ".join(f'"{f["key"]}": <value or null>' for f in spec.get("fields", []))
    company = f" on behalf of {company_name}" if company_name else ""
    extra = f"\nSENDER INSTRUCTIONS (verbatim from the person who sent this link):\n{instructions.strip()}\n" if instructions and instructions.strip() else ""

    return f"""You are a friendly assistant{company} helping one person complete a small, bounded task
through a short text conversation. Ask ONE short question at a time. Never invent facts,
never give legal or medical advice, never discuss anything outside this task, and never say
the task has been submitted — a separate review step does that.

TASK GOAL:
{spec.get('goal') or '(see the field list)'}
{extra}
REQUIRED FIELDS (must all be collected):
{chr(10).join(_field_line(f) for f in required) or '(none)'}

OPTIONAL FIELDS (ask about each at most once; skipping is fine):
{chr(10).join(_field_line(f) for f in optional) or '(none)'}

ATTACHMENTS (the recipient uploads these with the paperclip button — you cannot receive files
in chat; when one is missing, ask them to tap the upload button for it):
{attach_text}

KNOWN FIELDS SO FAR:
{chr(10).join(known_lines)}

STILL MISSING:
{missing_text}

CONVERSATION SO FAR:
{_render_transcript(transcript)}

Rules: extract any field values the recipient just gave (keep their wording, don't embellish);
never ask for a field already known; when nothing required is missing, say so briefly and
invite them to review and send. Keep assistant_message under 60 words.

Return ONLY valid JSON with exactly these keys:
{{"assistant_message": "<next short question or wrap-up>", {schema_keys}}}
Do not include markdown fences."""


# ── the turn ───────────────────────────────────────────────────────────────


async def next_turn(
    transcript: list[dict],
    known_fields: dict | None,
    spec: dict,
    present_slots: Iterable[str] = (),
    *,
    company_name: str | None = None,
    instructions: str | None = None,
) -> dict:
    """One bounded Gemini turn. Never raises; never persists."""
    present = set(present_slots or ())
    known_fields = coerce_fields({}, known_fields, spec)
    client = genai_env_client()
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
        safety_settings=_VOICE_PARSE_SAFETY_SETTINGS,
    )
    prompt = build_prompt(
        spec, transcript, known_fields, present,
        company_name=company_name, instructions=instructions,
    )
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=GEMINI_FLASH_LITE, contents=[prompt], config=config,
            ),
            timeout=CHAT_TURN_TIMEOUT,
        )
        payload = json.loads((getattr(response, "text", None) or "").strip())
    except Exception as exc:
        logger.warning("Sym-link chat turn failed: %s", exc)
        return {
            "assistant_message": FALLBACK_ERROR_MESSAGE,
            "fields": known_fields,
            "complete": is_complete(known_fields, present, spec),
            "error": True,
        }

    fields = coerce_fields(payload if isinstance(payload, dict) else {}, known_fields, spec)
    message = payload.get("assistant_message") if isinstance(payload, dict) else None
    message = message.strip() if isinstance(message, str) and message.strip() else "Got it."
    return {
        "assistant_message": message[:600],
        "fields": fields,
        "complete": is_complete(fields, present, spec),
        "error": False,
    }
