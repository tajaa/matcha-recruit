"""The spoken words of a clip, with their timings, for burned-in captions.

Claude doesn't take audio, so this is Google's speech model,
`gemini-3.5-transcribe`, asked for word-level timestamps
(`AudioTranscriptionConfig(word_timestamp=True)`). ffmpeg pulls the sound
out as 16 kHz mono FLAC (three minutes is about 4 MB), which goes inline;
the words come back on the response's audio part as
`audio_transcription.words[]`, each `{word, start_offset: "1.2s",
end_offset}` with its punctuation attached ("week."). Checked against the
live API on 2026-10-20. Google notes word timings can cost a little
accuracy; captions are for reading along, so that's the trade.

Calls count in the `gemini` rate-limit bucket. A full bucket or a server
with no key means "not now" (`TranscribeUnavailable`, and the worker tries
again later); a reply with no timed words means the clip gets no captions,
with a note saying so.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.core.services.genai_client import get_genai_client

from . import render
from .subtitles import Word

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-transcribe"
SERVICE = "cappe_social"
ENDPOINT = "transcribe"
MIME = "audio/flac"
AUDIO_TIMEOUT = 120
CALL_TIMEOUT = 150
# A request is capped at 20 MB; three minutes of 16 kHz mono FLAC is ~4 MB.
MAX_AUDIO_BYTES = 19 * 1024 * 1024
MAX_TEXT = 20_000

_OFFSET = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(ms|s)?\s*")


class TranscribeUnavailable(RuntimeError):
    """No key on this server, or the bucket is full: try again later."""


class TranscribeError(RuntimeError):
    """The audio couldn't be read or the reply had nothing usable."""


@dataclass(frozen=True)
class Transcript:
    words: list[Word]
    text: str
    language: Optional[str] = None


def audio_args(source: str, out_path: str, *, max_seconds: float) -> list[str]:
    """The first audio track, as 16 kHz mono FLAC, trimmed like the cut."""
    return [render.FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *render.input_args(source),
            "-i", source, "-vn", "-map", "0:a:0", "-t", f"{max_seconds:g}", "-ac", "1", "-ar", "16000",
            "-c:a", "flac", "-compression_level", "5", "-f", "flac", out_path]


async def extract_audio(source: str, workdir: Path, *, max_seconds: float) -> bytes:
    path = workdir / "speech.flac"
    try:
        await render.run(audio_args(source, str(path), max_seconds=max_seconds), timeout=AUDIO_TIMEOUT)
    except render.RenderError as exc:
        raise TranscribeError(str(exc)) from None
    data = path.read_bytes() if path.exists() else b""
    path.unlink(missing_ok=True)
    if not data:
        raise TranscribeError("That video's sound couldn't be read.")
    if len(data) > MAX_AUDIO_BYTES:
        raise TranscribeError("That video's sound is too long to caption.")
    return data


def offset_ms(value: Any) -> Optional[int]:
    """"1.200s", "3s", "1200ms", 1.2 (seconds) or {"seconds", "nanos"} → ms."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, round(value * 1000))
    if isinstance(value, dict):
        try:
            return max(0, round(float(value.get("seconds") or 0) * 1000 + float(value.get("nanos") or 0) / 1e6))
        except (TypeError, ValueError):
            return None
    m = _OFFSET.fullmatch(str(value))
    if not m:
        return None
    number = float(m.group(1))
    return max(0, round(number if m.group(2) == "ms" else number * 1000))


def _get(obj: Any, *names: str) -> Any:
    for name in names:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if value is not None:
            return value
    return None


def words_from(transcriptions: list[Any]) -> list[Word]:
    """Timed words from the response's transcription objects (SDK models or
    plain dicts), skipping any without both offsets."""
    out: list[Word] = []
    for t in transcriptions:
        for raw in _get(t, "words") or []:
            text = str(_get(raw, "word", "text") or "").strip()
            start = offset_ms(_get(raw, "start_offset", "startOffset"))
            end = offset_ms(_get(raw, "end_offset", "endOffset"))
            if text and start is not None and end is not None:
                out.append(Word(text, start, max(start, end)))
    return out


def _transcriptions(response: Any) -> list[Any]:
    found = []
    for candidate in _get(response, "candidates") or []:
        content = _get(candidate, "content")
        for part in (_get(content, "parts") or []) if content is not None else []:
            t = _get(part, "audio_transcription")
            if t is not None:
                found.append(t)
    return found


async def _limit() -> None:
    from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter

    try:
        await get_rate_limiter("gemini").check_and_record(SERVICE, ENDPOINT)
    except RateLimitExceeded as exc:
        raise TranscribeUnavailable(f"Gemini is busy right now ({exc})") from None
    except Exception:  # noqa: BLE001 — a broken limiter never blocks captions
        logger.warning("cappe social transcribe: rate-limit check failed; allowing", exc_info=True)


async def transcribe(audio: bytes) -> Transcript:
    """The words in `audio` (FLAC). Raises TranscribeUnavailable or
    TranscribeError."""
    settings = get_settings()
    if not (settings.gemini_api_key or getattr(settings, "use_vertex_ai", False)):
        raise TranscribeUnavailable("Captions need a Gemini key on this server")
    await _limit()
    from google.genai import types

    client = get_genai_client()
    try:
        response = await asyncio.wait_for(client.aio.models.generate_content(
            model=MODEL,
            contents=[types.Part.from_bytes(data=audio, mime_type=MIME)],
            config=types.GenerateContentConfig(
                audio_transcription_config=types.AudioTranscriptionConfig(word_timestamp=True, mode="VERBATIM"),
            ),
        ), timeout=CALL_TIMEOUT)
    except asyncio.TimeoutError:
        raise TranscribeError("Listening to the video took too long.") from None
    except Exception as exc:  # noqa: BLE001 — the SDK raises many shapes
        logger.warning("cappe social transcribe failed: %s", exc)
        raise TranscribeError("We couldn't listen to that video just now.") from None
    found = _transcriptions(response)
    words = words_from(found)
    text = " ".join(str(_get(t, "text") or "").strip() for t in found).strip() or str(_get(response, "text") or "")
    language = next((str(_get(t, "language_code")) for t in found if _get(t, "language_code")), None)
    return Transcript(words=words, text=text[:MAX_TEXT], language=language)


__all__ = [
    "MODEL", "TranscribeUnavailable", "TranscribeError", "Transcript", "audio_args", "extract_audio", "offset_ms",
    "words_from", "transcribe",
]
