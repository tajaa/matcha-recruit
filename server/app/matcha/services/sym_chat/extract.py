"""The sym-chat tunnel turn — one bounded flash-lite call per participant message.

Same engine shape as `services/symlink/chat.py`: transcript in, structured
state out, never raises, never persists. Two differences:

  * The stance is RE-DERIVED from the participant's whole transcript every
    turn (replace, not merge), so "actually 3pm no longer works" overrides the
    earlier availability. On a model failure the current stance is kept.
  * The model never decides consensus. It only reads one person's intent;
    `aggregate.compute_shape` is the deterministic roll-up.

`coerce_stance` is the trust boundary: whatever the model returns is clipped
to the kind's shape, the organizer's window, and the known option names.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH_LITE
from app.matcha.services._shared.gemini import genai_env_client
from app.matcha.services.ir.ir_voice_parser import _VOICE_PARSE_SAFETY_SETTINGS

from .kinds import clean_option, fmt_hhmm, parse_hhmm, stance_template

logger = logging.getLogger(__name__)

TURN_TIMEOUT = 20
MAX_PROMPT_MESSAGES = 60
MAX_WINDOWS = 20
MAX_PREFERRED = 10
MAX_NAMES = 20
MAX_REPLY_CHARS = 600
FALLBACK_REPLY = "Sorry, I'm having trouble right now — your earlier answers still count. Try again in a moment."


# ── coercion ───────────────────────────────────────────────────────────────


def _clip_windows(raw: Any, lo: int, hi: int) -> list[dict]:
    """[{start,end}] HH:MM → clipped to [lo, hi], empty/invalid dropped,
    sorted and merged so overlapping pieces become one window."""
    if not isinstance(raw, list):
        return []
    spans: list[tuple[int, int]] = []
    for item in raw[: MAX_WINDOWS * 2]:
        if not isinstance(item, dict):
            continue
        start, end = parse_hhmm(item.get("start")), parse_hhmm(item.get("end"))
        if start is None or end is None:
            continue
        start, end = max(start, lo), min(end, hi)
        if start < end:
            spans.append((start, end))
    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [{"start": fmt_hhmm(s), "end": fmt_hhmm(e)} for s, e in merged[:MAX_WINDOWS]]


def _coerce_schedule(raw: dict, config: dict) -> dict:
    lo = parse_hhmm(config.get("window_start")) or 0
    hi = parse_hhmm(config.get("window_end")) or 24 * 60
    preferred: list[str] = []
    for item in raw.get("preferred") or []:
        minutes = parse_hhmm(item)
        if minutes is not None and lo <= minutes < hi:
            text = fmt_hhmm(minutes)
            if text not in preferred:
                preferred.append(text)
    return {
        "available": _clip_windows(raw.get("available"), lo, hi),
        "unavailable": _clip_windows(raw.get("unavailable"), lo, hi),
        "preferred": preferred[:MAX_PREFERRED],
    }


def _canonical(name: str, known: dict[str, str]) -> str:
    return known.get(name.casefold(), name)


def _names(raw: Any, known: dict[str, str]) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = clean_option(item)
        if not name:
            continue
        name = _canonical(name, known)
        if name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out[:MAX_NAMES]


def _coerce_decide(raw: dict, known_options: list[str]) -> dict:
    known = {o.casefold(): o for o in known_options}
    vetoes = _names(raw.get("vetoes"), known)
    vetoed = {v.casefold() for v in vetoes}
    proposals = [n for n in _names(raw.get("proposals"), known) if n.casefold() not in vetoed]
    ok_with = [n for n in _names(raw.get("ok_with"), known) if n.casefold() not in vetoed]
    top = clean_option(raw.get("top_pick"))
    top = _canonical(top, known) if top else None
    if top and top.casefold() in vetoed:
        top = None
    return {"proposals": proposals, "ok_with": ok_with, "vetoes": vetoes, "top_pick": top}


def coerce_stance(kind: str, raw: Any, config: dict, known_options: list[str] | None = None) -> dict:
    """Model output → a stance of the kind's exact shape. Never raises."""
    raw = raw if isinstance(raw, dict) else {}
    if kind == "schedule":
        return _coerce_schedule(raw, config)
    if kind == "decide":
        return _coerce_decide(raw, known_options or [])
    return {}


def stance_has_content(kind: str, stance: dict | None) -> bool:
    """Has this participant actually told us anything the aggregate can use?
    Drives the "responded" count — a "hi" is not a response."""
    if not stance:
        return False
    if kind == "schedule":
        return bool(stance.get("available") or stance.get("unavailable"))
    if kind == "decide":
        return bool(
            stance.get("proposals") or stance.get("ok_with")
            or stance.get("vetoes") or stance.get("top_pick")
        )
    return False


# ── prompt ─────────────────────────────────────────────────────────────────


def _render_transcript(transcript: list[dict], participant_name: str) -> str:
    lines = []
    for entry in transcript[-MAX_PROMPT_MESSAGES:]:
        role = participant_name if entry.get("role") == "user" else "Assistant"
        content = str(entry.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) or "(no messages yet)"


def _kind_brief(kind: str, config: dict, known_options: list[str]) -> tuple[str, str]:
    """(what the task is + the stance rules, the JSON stance schema)."""
    if kind == "schedule":
        brief = f"""TASK: find a {config.get('duration_min')}-minute meeting slot on {config.get('date')}
between {config.get('window_start')} and {config.get('window_end')} ({config.get('timezone')} time).

STANCE RULES (times are 24-hour HH:MM, inside the window):
- available: windows this person said they CAN make. "Anytime" / "I'm free all day" means the whole window.
- unavailable: windows they said they CANNOT make.
- preferred: specific start times they said they'd prefer (may be empty).
- If they changed their mind, the LATEST statement wins — drop what they took back."""
        schema = '"available": [{"start": "HH:MM", "end": "HH:MM"}], "unavailable": [{"start": "HH:MM", "end": "HH:MM"}], "preferred": ["HH:MM"]'
        return brief, schema
    options = ", ".join(known_options) or "(none yet — people propose their own)"
    brief = f"""TASK: the group is choosing ONE option.
OPTIONS SO FAR: {options}

STANCE RULES (use an option's exact spelling from OPTIONS SO FAR when they mean it):
- proposals: new options this person suggested.
- ok_with: options this person said they're fine with (include their own proposals and top pick).
- vetoes: options this person said they will NOT do.
- top_pick: their single favourite, or null.
- If they changed their mind, the LATEST statement wins — drop what they took back."""
    schema = '"proposals": ["..."], "ok_with": ["..."], "vetoes": ["..."], "top_pick": "..." or null'
    return brief, schema


def build_prompt(
    kind: str,
    objective: str,
    config: dict,
    transcript: list[dict],
    current_stance: dict | None,
    known_options: list[str],
    participant_name: str,
) -> str:
    brief, schema = _kind_brief(kind, config, known_options)
    current = json.dumps(current_stance or stance_template(kind))
    goal = objective.strip() if objective and objective.strip() else "(no extra detail)"
    return f"""You are a private assistant helping {participant_name} tell a small group what works
for them. Only {participant_name} sees this conversation — never claim to have told anyone
anything, never reveal or guess what other people said, and never say a decision has been
made. Stay on this one task; ask at most ONE short question when their answer is unclear.

ORGANIZER'S OBJECTIVE: {goal}

{brief}

THEIR STANCE AS LAST RECORDED (re-derive it from the whole conversation below; it may be wrong):
{current}

CONVERSATION:
{_render_transcript(transcript, participant_name)}

Return ONLY valid JSON with exactly these keys:
{{"reply": "<short acknowledgement or one clarifying question, under 50 words>", "stance": {{{schema}}}}}
Do not include markdown fences."""


# ── the turn ───────────────────────────────────────────────────────────────


async def next_turn(
    kind: str,
    objective: str,
    config: dict,
    transcript: list[dict],
    current_stance: dict | None,
    known_options: list[str],
    participant_name: str,
) -> dict:
    """One bounded Gemini turn → {reply, stance, error}. Never raises; never persists."""
    kept = coerce_stance(kind, current_stance or {}, config, known_options)
    prompt = build_prompt(kind, objective, config, transcript, kept, known_options, participant_name)
    try:
        client = genai_env_client()
        gen_config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            safety_settings=_VOICE_PARSE_SAFETY_SETTINGS,
        )
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=GEMINI_FLASH_LITE, contents=[prompt], config=gen_config,
            ),
            timeout=TURN_TIMEOUT,
        )
        payload = json.loads((getattr(response, "text", None) or "").strip())
        if not isinstance(payload, dict):
            raise ValueError("model returned non-object JSON")
    except Exception as exc:
        logger.warning("Sym-chat turn failed: %s", exc)
        return {"reply": FALLBACK_REPLY, "stance": kept, "error": True}

    stance = coerce_stance(kind, payload.get("stance"), config, known_options)
    reply = payload.get("reply")
    reply = reply.strip() if isinstance(reply, str) and reply.strip() else "Got it."
    return {"reply": reply[:MAX_REPLY_CHARS], "stance": stance, "error": False}
