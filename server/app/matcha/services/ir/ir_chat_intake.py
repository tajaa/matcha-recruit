"""Conversational incident-intake — one Gemini flash-lite call per chat turn,
extracting the same create-form fields ir_voice_parser.py fills from audio.

Stateless: the caller (routes/ir_incidents/chat_intake.py) supplies the whole
transcript + the fields already known each turn; this module never persists
anything. Best-effort, never raises — a failed turn returns the known fields
unchanged with error=True so the UI can offer "finish in the form".
"""

import asyncio
import json
import logging
from typing import Literal, Optional

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH_LITE
from app.matcha.services._shared.gemini import genai_env_client
from app.matcha.services.ir.ir_voice_parser import _VOICE_PARSE_SAFETY_SETTINGS

logger = logging.getLogger(__name__)

# Live back-and-forth — the user is waiting on each reply, unlike voice
# parse's 90s single-shot budget. No retry either (see next_turn): a second
# ~20s wait mid-conversation is worse UX than a graceful failure message.
CHAT_TURN_TIMEOUT = 20
MAX_TURNS = 12
MAX_WITNESSES = 20
PublicIntakeKind = Literal["anonymous", "location"]

REQUIRED_FIELDS = ("reported_by_name", "occurred_at_text", "location_id", "description")


def _required_fields(location_options: list[dict]) -> tuple:
    """location_id isn't askable/answerable when the tenant has no locations on file."""
    if location_options:
        return REQUIRED_FIELDS
    return tuple(f for f in REQUIRED_FIELDS if f != "location_id")


def _is_complete(fields: dict, location_options: list[dict]) -> bool:
    return all(fields.get(k) for k in _required_fields(location_options))


def _normalized_witness_names(witnesses) -> list[str]:
    """Keep malformed client/model witness values out of prompt and merge paths."""
    names = []
    for witness in witnesses or []:
        if not isinstance(witness, dict):
            continue
        name = witness.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _render_known(known: dict) -> str:
    lines = []
    if known.get("reported_by_name"):
        lines.append(f"- reporter name: {known['reported_by_name']}")
    if known.get("occurred_at_text"):
        lines.append(f"- when: {known['occurred_at_text']}")
    if known.get("location_id"):
        lines.append(f"- location: already picked (id {known['location_id']})")
    if known.get("description"):
        lines.append(f"- what happened: {known['description']}")
    if known.get("witnesses"):
        names = _normalized_witness_names(known["witnesses"])
        if names:
            lines.append(f"- witnesses so far: {', '.join(names)}")
    return "\n".join(lines) or "(nothing yet)"


def _render_transcript(transcript: list[dict]) -> str:
    lines = []
    for m in transcript:
        speaker = "Assistant" if m.get("role") == "assistant" else "User"
        lines.append(f"{speaker}: {m.get('content', '')}")
    return "\n".join(lines) or "(no messages yet)"


def _build_turn_prompt(transcript: list[dict], known: dict, location_options: list[dict]) -> str:
    loc_lines = "\n".join(f"- {o['id']}: {o['label']}" for o in location_options) or "(none on file — do not ask about location)"
    required = _required_fields(location_options)
    return f"""You are a friendly intake assistant collecting a workplace incident report
through natural conversation — one short question at a time, like texting a
coworker. Never ask about a field already answered (see ALREADY KNOWN below).
If the user's last message answers multiple things at once, extract all of
them. Never invent facts not stated.

Required before you can stop asking: {", ".join(required)}.
witnesses is optional — ask about it once, but don't block on it.

ALREADY KNOWN:
{_render_known(known)}

LOCATIONS (return location_id as one of these ids, never a made-up id):
{loc_lines}

CONVERSATION SO FAR:
{_render_transcript(transcript)}

Return ONLY valid JSON with exactly these keys:
{{"assistant_message": "<your next short question, OR — if every required field
   above is now known — a brief closing line like 'Got it, let's review what
   I have'>",
 "reported_by_name": "<string or null>",
 "occurred_at_text": "<when it happened, in the words spoken, e.g. 'yesterday around 3pm', or null>",
 "location_id": "<the best-matching id from LOCATIONS, or null>",
 "description": "<what happened — grow/refine the ALREADY KNOWN description with new detail, don't discard it>",
 "witnesses": [{{"name": "<person other than the reporter who saw it>"}}]}}

Do not include markdown fences."""


def _coerce_chat_fields(raw: dict, known: dict, valid_location_ids: set) -> dict:
    """Pure, unit-tested. Merges this turn's newly-extracted values over the
    already-confirmed `known` state. A turn can only ADD/refine a non-empty
    value — it must never blank an already-answered field back to null, since
    this call is one of many turns, not the only one (unlike voice parse's
    single-shot coerce)."""
    def _str(key):
        v = raw.get(key)
        return v.strip() if isinstance(v, str) and v.strip() else None

    merged = dict(known)

    for key in ("reported_by_name", "occurred_at_text", "description"):
        v = _str(key)
        if v:
            merged[key] = v

    loc = raw.get("location_id")
    if loc is not None and str(loc) in valid_location_ids:
        merged["location_id"] = str(loc)

    new_witnesses = []
    for w in (raw.get("witnesses") or []):
        name = None
        if isinstance(w, str):
            name = w.strip()
        elif isinstance(w, dict):
            n = w.get("name")
            name = n.strip() if isinstance(n, str) else None
        if name:
            new_witnesses.append(name)

    if new_witnesses:
        existing = [{"name": name} for name in _normalized_witness_names(known.get("witnesses"))]
        seen = {w["name"].lower() for w in existing}
        for name in new_witnesses:
            key = name.lower()
            if key not in seen:
                existing.append({"name": name})
                seen.add(key)
        merged["witnesses"] = existing[:MAX_WITNESSES]
    else:
        merged["witnesses"] = [
            {"name": name} for name in _normalized_witness_names(known.get("witnesses"))
        ]

    merged.setdefault("reported_by_name", None)
    merged.setdefault("occurred_at_text", None)
    merged.setdefault("location_id", None)
    merged.setdefault("description", None)
    return merged


async def next_turn(transcript: list[dict], known_fields: dict, *, location_options: list[dict]) -> dict:
    """One Gemini flash-lite call -> {assistant_message, fields, complete, error}.
    Never raises."""
    client = genai_env_client()
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
        safety_settings=_VOICE_PARSE_SAFETY_SETTINGS,
    )
    prompt = _build_turn_prompt(transcript, known_fields, location_options)

    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=GEMINI_FLASH_LITE, contents=[prompt], config=config,
            ),
            timeout=CHAT_TURN_TIMEOUT,
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        payload = json.loads(raw_text)
    except Exception as exc:
        logger.warning("IR chat intake turn failed: %s", exc)
        return {
            "assistant_message": "Sorry, having trouble right now — you can finish in the form below.",
            "fields": known_fields,
            "complete": False,
            "error": True,
        }

    valid_loc_ids = {str(o["id"]) for o in location_options}
    fields = _coerce_chat_fields(payload if isinstance(payload, dict) else {}, known_fields, valid_loc_ids)
    assistant_message = payload.get("assistant_message") if isinstance(payload, dict) else None
    assistant_message = assistant_message.strip() if isinstance(assistant_message, str) and assistant_message.strip() else "Got it."

    return {
        "assistant_message": assistant_message,
        "fields": fields,
        "complete": _is_complete(fields, location_options),
        "error": False,
    }


def _public_required_fields(intake_kind: PublicIntakeKind) -> tuple[str, ...]:
    return ("description",) if intake_kind == "anonymous" else ("reported_by_name", "description")


def _public_optional_fields(intake_kind: PublicIntakeKind) -> tuple[str, ...]:
    if intake_kind == "anonymous":
        return ("occurred_at_text", "location", "involved_parties", "contact_info")
    return ("occurred_at_text", "witnesses", "corrective_actions")


def _build_public_turn_prompt(
    transcript: list[dict], known: dict, *, intake_kind: PublicIntakeKind,
) -> str:
    required = _public_required_fields(intake_kind)
    optional = _public_optional_fields(intake_kind)
    if intake_kind == "anonymous":
        context = (
            "This is an anonymous report. Do not ask for the reporter's name. "
            "Location, involved parties, and follow-up contact are optional."
        )
    else:
        context = (
            "This report link is already locked to its location. Do not ask where it happened, "
            "do not mention location identifiers, and never return a location_id."
        )
    known_lines = []
    for key in (
        "reported_by_name", "occurred_at_text", "location", "description",
        "witnesses", "involved_parties", "contact_info", "corrective_actions",
    ):
        value = known.get(key)
        if value:
            known_lines.append(f"- {key}: {value}")
    known_text = "\n".join(known_lines) or "(nothing yet)"
    return f"""You are a friendly assistant collecting a workplace incident report through a
short, private conversation. Ask one short question at a time. Never invent facts,
never give legal advice, and never say that a report has been submitted.

{context}
Required before review: {", ".join(required)}.
Optional fields: {", ".join(optional)}. Ask about each optional field at most once,
but do not block review when it is skipped. Never ask for an already-known field.

KNOWN FIELDS:
{known_text}

CONVERSATION SO FAR:
{_render_transcript(transcript)}

Return ONLY valid JSON with exactly these keys:
{{"assistant_message": "<next short question, or a short review prompt>",
  "reported_by_name": "<string or null>",
  "occurred_at_text": "<string or null>",
  "location": "<string or null>",
  "description": "<string or null>",
  "witnesses": [{{"name": "<string>"}}],
  "involved_parties": "<string or null>",
  "contact_info": "<string or null>",
  "corrective_actions": "<string or null>"}}
Do not include markdown fences."""


def _coerce_public_chat_fields(raw: dict, known: dict, *, intake_kind: PublicIntakeKind) -> dict:
    """Merge model output over a public draft without accepting irrelevant fields."""
    limits = {
        "reported_by_name": 255,
        "occurred_at_text": 255,
        "location": 255,
        "description": 10_000,
        "involved_parties": 2_000,
        "contact_info": 255,
        "corrective_actions": 10_000,
    }
    allowed = set(_public_required_fields(intake_kind)) | set(_public_optional_fields(intake_kind))
    merged = dict(known)
    for key, limit in limits.items():
        if key not in allowed:
            merged[key] = None
            continue
        value = raw.get(key)
        if isinstance(value, str) and (cleaned := value.strip()):
            merged[key] = cleaned[:limit]
        else:
            merged.setdefault(key, None)

    if "witnesses" in allowed:
        existing = [{"name": name} for name in _normalized_witness_names(known.get("witnesses"))]
        seen = {w["name"].lower() for w in existing}
        for witness in raw.get("witnesses") or []:
            name = witness.get("name") if isinstance(witness, dict) else witness
            if not isinstance(name, str) or not (cleaned := name.strip()[:255]):
                continue
            if cleaned.lower() not in seen:
                existing.append({"name": cleaned})
                seen.add(cleaned.lower())
        merged["witnesses"] = existing[:50]
    else:
        merged["witnesses"] = []
    return merged


def _public_chat_is_complete(fields: dict, *, intake_kind: PublicIntakeKind) -> bool:
    return all(fields.get(key) for key in _public_required_fields(intake_kind))


async def next_public_turn(
    transcript: list[dict], known_fields: dict, *, intake_kind: PublicIntakeKind,
) -> dict:
    """One bounded Gemini turn for a public token intake; never persists data."""
    client = genai_env_client()
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
        safety_settings=_VOICE_PARSE_SAFETY_SETTINGS,
    )
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=GEMINI_FLASH_LITE,
                contents=[_build_public_turn_prompt(transcript, known_fields, intake_kind=intake_kind)],
                config=config,
            ),
            timeout=CHAT_TURN_TIMEOUT,
        )
        payload = json.loads((getattr(response, "text", None) or "").strip())
    except Exception as exc:
        logger.warning("Public IR chat intake turn failed: %s", exc)
        return {
            "assistant_message": "Sorry, having trouble right now. You can review what you have.",
            "fields": known_fields,
            "complete": False,
            "error": True,
        }

    fields = _coerce_public_chat_fields(
        payload if isinstance(payload, dict) else {}, known_fields, intake_kind=intake_kind,
    )
    assistant_message = payload.get("assistant_message") if isinstance(payload, dict) else None
    assistant_message = (
        assistant_message.strip() if isinstance(assistant_message, str) and assistant_message.strip()
        else "Got it."
    )
    return {
        "assistant_message": assistant_message[:600],
        "fields": fields,
        "complete": _public_chat_is_complete(fields, intake_kind=intake_kind),
        "error": False,
    }
