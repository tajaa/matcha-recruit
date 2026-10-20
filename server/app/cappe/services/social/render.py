"""Cut a dropped video to each network's shape with ffmpeg.

Every network we post video to takes a 1080x1920 vertical clip (Instagram
Reels, Facebook Reels; TikTok and YouTube Shorts later). A clip that is not
already 9:16 is fitted, never cropped: the frame is scaled to fit and the
bars are filled with a blurred, enlarged copy of itself. A landscape clip
also gets a 1920x1080 cut, which Facebook posts as a regular Page video.

This runs on the shared default worker (one slot, a 768 MB container), so
every step is bounded: clips are trimmed to `MAX_SECONDS`, x264 runs at
`veryfast` on two threads with a short lookahead, each ffmpeg has its own
timeout and is killed with its whole process group, and only one output
file exists on disk at a time. ffmpeg reads the original straight from S3
through a presigned URL, so the original never touches local disk.

The input is untrusted. Two ffmpeg options keep a hostile file from turning
the worker into a fetcher: `-protocol_whitelist` (https only, so a playlist
can't read `file:` paths) and `-format_whitelist` (MP4/MOV and Matroska/WebM
demuxers only, so a text playlist is never parsed as HLS).

Pure builders (`probe_facts`, `specs_for`, `encode_args`, `frame_args`) carry
the decisions and are tested without the binary.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# Facebook Reels take 3–90 s; Instagram Reels take longer, but one clip is
# cut once for every network.
MIN_SECONDS = 3.0
MAX_SECONDS = 90
MAX_RENDER_BYTES = 160 * 1024 * 1024
PROBE_TIMEOUT = 30
FRAME_TIMEOUT = 30
ENCODE_TIMEOUT = 240
FRAME_POINTS = (0.15, 0.5, 0.85)
FRAME_WIDTH = 720
# A landscape cut is only worth it for a clearly landscape clip.
LANDSCAPE_ASPECT = 1.2

_DEMUXERS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm"


class RenderError(RuntimeError):
    """The clip can't be prepared. The message is shown to the owner.
    `permanent` means the file itself is the problem (too short, no picture);
    otherwise it may be a passing failure worth one more try."""

    def __init__(self, message: str, *, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


@dataclass(frozen=True)
class VideoFacts:
    duration_ms: int
    width: int          # as displayed, rotation applied
    height: int
    has_audio: bool
    codec: str

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0

    @property
    def trimmed(self) -> bool:
        return self.duration_ms > MAX_SECONDS * 1000

    @property
    def output_seconds(self) -> float:
        return min(self.duration_ms / 1000, MAX_SECONDS)


@dataclass(frozen=True)
class RenderSpec:
    name: str
    width: int
    height: int

    @property
    def aspect(self) -> float:
        return self.width / self.height


VERTICAL = RenderSpec("vertical", 1080, 1920)
LANDSCAPE = RenderSpec("landscape", 1920, 1080)


# ── pure decisions ──────────────────────────────────────────────────────────

def _rotation(stream: dict[str, Any]) -> int:
    """Degrees a phone asked the player to rotate by: the display matrix in
    side data, or the old `rotate` tag."""
    for side in stream.get("side_data_list") or []:
        if isinstance(side, dict) and "rotation" in side:
            try:
                return int(float(side["rotation"])) % 360
            except (TypeError, ValueError):
                return 0
    try:
        return int((stream.get("tags") or {}).get("rotate") or 0) % 360
    except (TypeError, ValueError):
        return 0


def probe_facts(data: dict[str, Any]) -> VideoFacts:
    """What ffprobe's JSON says about a clip, or RenderError for one we
    can't post."""
    streams = [s for s in data.get("streams") or [] if isinstance(s, dict)]
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    if video is None:
        raise RenderError("That file has no video in it.", permanent=True)
    try:
        width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    except (TypeError, ValueError):
        width = height = 0
    if width < 16 or height < 16:
        raise RenderError("We couldn't read that video's size. Try exporting it as an MP4.", permanent=True)
    if _rotation(video) in (90, 270):
        width, height = height, width
    raw = (data.get("format") or {}).get("duration") or video.get("duration")
    try:
        duration = float(raw)
    except (TypeError, ValueError):
        raise RenderError("We couldn't tell how long that video is. Try exporting it as an MP4.", permanent=True) from None
    if duration < MIN_SECONDS:
        raise RenderError(f"Videos need to be at least {int(MIN_SECONDS)} seconds long.", permanent=True)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return VideoFacts(duration_ms=int(duration * 1000), width=width, height=height,
                      has_audio=has_audio, codec=str(video.get("codec_name") or ""))


def specs_for(facts: VideoFacts) -> list[RenderSpec]:
    """The vertical cut always; a landscape one for a clearly landscape clip."""
    return [VERTICAL, LANDSCAPE] if facts.aspect >= LANDSCAPE_ASPECT else [VERTICAL]


def input_args(source: str) -> list[str]:
    """The guards in front of every `-i`. A URL may only be fetched over
    https; a local path (tests, never production) only as a file."""
    protocols = "https,tls,tcp" if source.startswith("https://") else "file"
    return ["-protocol_whitelist", protocols, "-format_whitelist", _DEMUXERS]


def video_graph(spec: RenderSpec, facts: VideoFacts) -> str:
    """Fit the clip into the spec's frame. When the shapes already match it
    is a plain scale; otherwise the frame sits on a blurred copy of itself.
    The blur runs at a quarter size and is scaled up, which is most of the
    cost saved."""
    w, h = spec.width, spec.height
    tail = "setsar=1,fps=30,format=yuv420p[v]"
    if abs(facts.aspect - spec.aspect) < 0.01:
        return f"[0:v]scale={w}:{h},{tail}"
    sw, sh = w // 4, h // 4
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},boxblur=10:1,scale={w}:{h}[bgb];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,{tail}"
    )


def encode_args(source: str, spec: RenderSpec, facts: VideoFacts, out_path: str) -> list[str]:
    """H.264 High / AAC 48 kHz stereo MP4 with the index up front — what Meta
    asks for. A 2 s closed GOP keeps Facebook's Reels check happy. A clip
    with no sound gets a silent track: Reels without audio are refused."""
    args = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *input_args(source), "-i", source]
    if not facts.has_audio:
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    args += [
        "-filter_complex", video_graph(spec, facts),
        "-map", "[v]", "-map", "0:a:0" if facts.has_audio else "1:a:0",
        "-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast", "-crf", "23",
        "-maxrate", "6M", "-bufsize", "12M", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
        "-x264-params", "rc-lookahead=10", "-threads", "2", "-filter_complex_threads", "1",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
    ]
    if not facts.has_audio:
        args.append("-shortest")
    args += ["-t", str(MAX_SECONDS), "-movflags", "+faststart", "-fs", str(MAX_RENDER_BYTES), out_path]
    return args


def frame_points_ms(facts: VideoFacts) -> list[int]:
    seconds = facts.output_seconds
    return [round(seconds * p * 1000) for p in FRAME_POINTS]


def frame_args(source: str, at_ms: int, out_path: str) -> list[str]:
    """One poster frame, seeked before the input so only a little is read."""
    return [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{at_ms / 1000:.3f}",
            *input_args(source), "-i", source, "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH}:-2",
            "-q:v", "4", "-f", "image2", out_path]


def probe_args(source: str) -> list[str]:
    return [FFPROBE, "-v", "error", *input_args(source), "-print_format", "json",
            "-show_streams", "-show_format", source]


def check_output(data: dict[str, Any], spec: RenderSpec, facts: VideoFacts) -> None:
    """The cut is what we meant to make: H.264 at the spec's size, about as
    long as the clip (or the trim), with sound."""
    streams = [s for s in data.get("streams") or [] if isinstance(s, dict)]
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None or video.get("codec_name") != "h264" or audio is None:
        raise RenderError("The prepared video came out wrong. Try uploading it again.")
    if (int(video.get("width") or 0), int(video.get("height") or 0)) != (spec.width, spec.height):
        raise RenderError("The prepared video came out the wrong size. Try uploading it again.")
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if abs(duration - facts.output_seconds) > 1.5:
        raise RenderError("The prepared video came out too short. Try uploading it again.")


# ── running ffmpeg ──────────────────────────────────────────────────────────

async def run(args: list[str], *, timeout: float) -> bytes:
    """Run one ffmpeg/ffprobe. It gets its own process group, so a timeout —
    or the task being cancelled — kills it and anything it started."""
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True,
    )
    try:
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            raise RenderError("Preparing the video took too long. Try a shorter clip.") from None
        if process.returncode:
            logger.warning("cappe social render: %s exited %s: %s", args[0], process.returncode,
                           (err or b"")[-2000:].decode("utf-8", "replace"))
            raise RenderError("We couldn't read that video. Try exporting it as an MP4 and uploading again.")
        return out
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()


async def probe(source: str) -> VideoFacts:
    out = await run(probe_args(source), timeout=PROBE_TIMEOUT)
    try:
        data = json.loads(out or b"{}")
    except ValueError:
        raise RenderError("We couldn't read that video. Try exporting it as an MP4 and uploading again.") from None
    return probe_facts(data)


async def extract_frame(source: str, at_ms: int, workdir: Path, index: int) -> Path:
    path = workdir / f"frame-{index}.jpg"
    await run(frame_args(source, at_ms, str(path)), timeout=FRAME_TIMEOUT)
    if not path.exists() or path.stat().st_size == 0:
        raise RenderError("We couldn't take a picture from that video. Try uploading it again.")
    return path


async def encode(source: str, spec: RenderSpec, facts: VideoFacts, workdir: Path) -> Path:
    """Cut one render and check it before it is uploaded."""
    path = workdir / f"cut-{spec.name}.mp4"
    await run(encode_args(source, spec, facts, str(path)), timeout=ENCODE_TIMEOUT)
    if not path.exists() or path.stat().st_size == 0:
        raise RenderError("The prepared video came out empty. Try uploading it again.")
    out = await run(probe_args(str(path)), timeout=PROBE_TIMEOUT)
    check_output(json.loads(out or b"{}"), spec, facts)
    return path


__all__ = [
    "MIN_SECONDS", "MAX_SECONDS", "RenderError", "VideoFacts", "RenderSpec", "VERTICAL", "LANDSCAPE",
    "probe_facts", "specs_for", "input_args", "video_graph", "encode_args", "frame_points_ms", "frame_args",
    "probe_args", "check_output", "run", "probe", "extract_frame", "encode",
]
