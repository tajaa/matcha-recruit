"""Verbatim voice transcription for the schedule editor assistant.

Audio is an input transport only. This service does not interpret scheduling
intent or write anything; the transcript goes through the existing schedule
chat proposal flow.
"""

import asyncio
import io
import json
import logging
import struct
import wave
from typing import Optional

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH
from app.matcha.services._shared.gemini import genai_env_client

logger = logging.getLogger(__name__)

VOICE_TRANSCRIBE_TIMEOUT = 60
MAX_TRANSCRIPT_CHARS = 2_000
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_AUDIO_SECONDS = 50


def _build_prompt() -> str:
    return """Transcribe this spoken request to a workplace scheduling assistant VERBATIM.

Return ONLY valid JSON:
{"transcript": "<the spoken words, verbatim>"}

Rules:
- Preserve names, dates, times, quantities, corrections, and confirmation words exactly as spoken.
- Do not summarize, answer, interpret, or execute the request.
- Use an empty string for silence or entirely unintelligible audio.
- Do not include markdown fences."""


def _parse_model_json(text: str) -> object:
    value = (text or "").strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.startswith("json"):
            value = value[4:]
    return json.loads(value)


def _coerce_transcript(raw: object) -> Optional[str]:
    if not isinstance(raw, dict):
        return None
    transcript = raw.get("transcript")
    if not isinstance(transcript, str):
        return None
    transcript = transcript.strip()
    return transcript[:MAX_TRANSCRIPT_CHARS] if transcript else None


def validate_schedule_wav(audio_bytes: bytes) -> None:
    """Require the exact bounded PCM format emitted by useVoiceDictation."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            frame_rate = wav.getframerate()
            frames = wav.getnframes()
            compression = wav.getcomptype()
            frame_data_bytes = len(wav.readframes(frames))
    except (EOFError, struct.error, ValueError, wave.Error) as exc:
        raise ValueError("The voice recording is not a readable WAV file.") from exc

    if channels != 1 or sample_width != 2 or frame_rate != 16_000 or compression != "NONE":
        raise ValueError("Voice audio must be 16 kHz mono PCM WAV.")
    if frame_data_bytes != frames * channels * sample_width:
        raise ValueError("The voice recording is truncated or malformed.")
    if frames / frame_rate > MAX_AUDIO_SECONDS:
        raise ValueError(f"Voice requests must be {MAX_AUDIO_SECONDS} seconds or shorter.")


async def transcribe_schedule_request(audio_bytes: bytes, mime_type: str) -> dict:
    """Transcribe one WAV turn with one transient retry; never raises."""
    try:
        client = genai_env_client()
        audio = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        )
    except Exception as exc:
        logger.warning("schedule voice transcription could not initialize: %s", exc)
        return {"available": False, "transcript": None, "model": GEMINI_FLASH}

    payload: object = {}
    succeeded = False
    for attempt in range(1, 3):
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=GEMINI_FLASH,
                    contents=[_build_prompt(), audio],
                    config=config,
                ),
                timeout=VOICE_TRANSCRIBE_TIMEOUT,
            )
            payload = _parse_model_json(getattr(response, "text", None) or "")
            succeeded = True
            break
        except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                logger.warning("schedule voice transcription failed (attempt %d/2): %s", attempt, exc)
        except Exception as exc:
            logger.warning("schedule voice transcription failed: %s", exc)
            break

    return {
        "available": succeeded,
        "transcript": _coerce_transcript(payload),
        "model": GEMINI_FLASH,
    }
