"""Deterministic validation and metadata extraction for release masters."""

import json
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal


ACCEPTED_CODECS = {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "flac"}


class AudioMetaError(ValueError):
    """A user-facing master-file validation error."""


@dataclass(frozen=True)
class AudioMeta:
    duration_seconds: Decimal
    sample_rate: int
    bit_depth: int | None
    channels: int
    audio_format: Literal["wav", "flac"]


def _bit_depth(stream: dict, codec: str) -> int | None:
    if stream.get("bits_per_raw_sample"):
        return int(stream["bits_per_raw_sample"])
    if stream.get("bits_per_sample"):
        return int(stream["bits_per_sample"])
    if codec == "pcm_f32le":
        return 32
    if codec == "flac":
        return None
    return None


def extract(path: Path, *, ffprobe: str = "ffprobe") -> AudioMeta:
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise AudioMetaError("Could not read the audio master. Upload a valid WAV or FLAC file.") from exc

    stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not stream:
        raise AudioMetaError("The master does not contain an audio stream.")
    codec = str(stream.get("codec_name", "")).lower()
    if codec not in ACCEPTED_CODECS:
        raise AudioMetaError(f"Not a WAV/FLAC master: detected {codec or 'unknown codec'}")
    try:
        sample_rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
        duration = stream.get("duration") or payload.get("format", {}).get("duration")
        if duration is None:
            raise ValueError("duration missing")
        seconds = Decimal(str(duration)).quantize(Decimal("0.001"))
    except (KeyError, TypeError, ValueError) as exc:
        raise AudioMetaError("The master is missing readable audio metadata.") from exc
    return AudioMeta(
        duration_seconds=seconds,
        sample_rate=sample_rate,
        bit_depth=_bit_depth(stream, codec),
        channels=channels,
        audio_format="flac" if codec == "flac" else "wav",
    )
