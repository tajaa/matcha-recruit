"""Safety-meeting chunk transcription — one Gemini multimodal call per ~1-minute
WAV segment while the meeting runs. Best-effort, never raises: an unusable
response returns available=False and the meeting keeps recording (the audio is
still stored, so the gap is recoverable by hand).

Mirrors ir_voice_parser.py's audio-part/JSON-mode/retry wrapper, minus field
extraction — a meeting chunk is transcribed VERBATIM, structuring happens once
at the end (summary.py) over the full transcript. Audio arrives as WAV from
the browser's PCM worklet (Gemini rejects MediaRecorder's webm/opus).
"""

import asyncio
import json
import logging
from typing import Optional

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH
from app.matcha.services._shared.gemini import genai_env_client

logger = logging.getLogger(__name__)

TRANSCRIBE_TIMEOUT = 90
MAX_TRANSCRIPT_CHARS = 20000  # one minute of speech is ~1.5k chars; this is generous

# Toolbox talks legitimately discuss injuries, hazards, and fatalities — the
# same reason ir_voice_parser disables blocking for a bounded extraction call.
_SAFETY_SETTINGS = [
    types.SafetySetting(category=category, threshold="BLOCK_NONE")
    for category in (
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    )
]


def _build_prompt(context: str) -> str:
    return f"""You are transcribing one segment of a workplace safety meeting (a toolbox talk), recorded on a phone or laptop microphone. There may be multiple speakers and background noise.

Meeting context: {context}

Transcribe the audio VERBATIM. Return ONLY valid JSON:
{{"transcript": "<the spoken words, verbatim>"}}

Rules:
- Transcribe exactly what is said; do not summarize, editorialize, or invent speech.
- Use "" if the segment is silence or entirely unintelligible.
- Do not include markdown fences."""


def _coerce_transcript(raw: dict) -> Optional[str]:
    """Validate/clamp the model output. PURE (unit-tested). Never raises."""
    if not isinstance(raw, dict):
        return None
    text = raw.get("transcript")
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    return text[:MAX_TRANSCRIPT_CHARS]


def _parse_model_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


async def transcribe_meeting_chunk(audio_bytes: bytes, mime_type: str, *, context: str) -> dict:
    """Gemini transcribes one meeting segment, with one retry (fresh timeout) on
    a transient timeout or unparsable JSON. Never raises. ``available`` is False
    only when Gemini never returned a usable response; a clean transcription of
    a silent segment is available=True with transcript=None (the UI tells
    "couldn't hear" apart from "nothing said" that way)."""
    client = genai_env_client()
    part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    prompt = _build_prompt(context or "(no context provided)")
    config = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json",
        safety_settings=_SAFETY_SETTINGS,
    )

    payload: dict = {}
    succeeded = False
    for attempt in range(1, 3):  # one retry on timeout / bad JSON
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=GEMINI_FLASH, contents=[prompt, part], config=config,
                ),
                timeout=TRANSCRIBE_TIMEOUT,
            )
            raw = (getattr(response, "text", None) or "").strip()
            payload = _parse_model_json(raw)
            succeeded = True
            break
        except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                logger.warning("safety-meeting transcribe failed (attempt %d/2): %s", attempt, exc)
        except Exception as exc:  # never-raises contract — anything else, no retry
            logger.warning("safety-meeting transcribe failed (attempt %d/2): %s", attempt, exc)
            break

    return {
        "transcript": _coerce_transcript(payload),
        "available": succeeded,
        "model": GEMINI_FLASH,
    }
