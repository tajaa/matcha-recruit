"""Isolated local scene renderer and bounded FFmpeg assembly, media worker only."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time
import zipfile
from pathlib import Path

from app.config import get_settings

from . import storage
from app.matcha.models.matcha_work.recaps import Manifest
from .settings import OUTPUT_BYTES, SCRATCH_BYTES


async def command(args: list[str], *, timeout=180) -> bytes:
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
    try:
        out, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        if process.returncode:
            raise RuntimeError("media_process_failed")
        return out
    finally:
        if process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()


def scratch_budget(directory: Path):
    if sum(path.stat().st_size for path in directory.rglob("*") if path.is_file()) > SCRATCH_BYTES:
        raise ValueError("scratch_size_limit")


def unpack_frames(archive: Path, directory: Path) -> list[dict]:
    # Never extract archive paths. Only numbered JPEG members plus a tiny
    # timing index produced by our own capture adapter are admitted.
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if len(members) > 66 or sum(m.file_size for m in members) > 16 * 1024 * 1024:
            raise ValueError("capture_package_limit")
        index = package.read("frames.json")
        if len(index) > 16_384:
            raise ValueError("capture_index_limit")
        frames = json.loads(index)
        if not isinstance(frames, list) or not 1 <= len(frames) <= 64:
            raise ValueError("capture_frame_count")
        previous = -1.0
        for n, frame in enumerate(frames):
            if frame.get("file") != f"{n:03d}.jpg" or not isinstance(frame.get("at"), (int, float)) or not previous <= frame["at"] <= 8:
                raise ValueError("capture_frame_index")
            previous = frame["at"]
            data = package.read(frame["file"])
            if len(data) > 256 * 1024:
                raise ValueError("capture_frame_size")
            (directory / frame["file"]).write_bytes(data)
    return frames


async def render(manifest: Manifest, directory: Path) -> dict:
    from playwright.async_api import async_playwright

    bundle = Path(get_settings().espresso_recaps_render_bundle).resolve()
    if not (bundle / "index.html").is_file():
        raise RuntimeError("render_bundle_missing")
    # Fulfill from memory/known files; every other request is aborted. There is
    # no application login, provider session, remote font or remote image.
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-quic"])
        try:
            context = await browser.new_context(viewport={"width": 1920, "height": 1080}, service_workers="block", accept_downloads=False)
            async def route(request):
                from urllib.parse import unquote, urlsplit
                url = urlsplit(request.request.url)
                candidate = (bundle / unquote(url.path).lstrip("/")).resolve()
                if url.netloc != "recap.invalid" or not candidate.is_relative_to(bundle) or not candidate.is_file():
                    await request.abort()
                else:
                    await request.fulfill(path=str(candidate))
            await context.route("**/*", route)
            page = await context.new_page()
            await page.goto("http://recap.invalid/index.html", wait_until="load", timeout=10_000)
            await page.wait_for_function("window.recapTemplate === 'espresso-recap.v1'", timeout=10_000)
            for n, scene in enumerate(manifest.scenes):
                await page.evaluate("scene => window.renderRecapScene(scene)", scene.model_dump(mode="json"))
                await page.evaluate("document.fonts.ready")
                await page.screenshot(path=str(directory / f"card{n:02d}.png"))
        finally:
            await browser.close()
    # Every scene is normalized to the exact same stream contract. FFmpeg's
    # concat demuxer then re-encodes once into the single final artifact.
    inputs, filters, chapters = [], [], []
    elapsed = 0
    for n, scene in enumerate(manifest.scenes):
        chapters.append({"label": scene.event.title, "start_ms": elapsed * 1000})
        elapsed += scene.seconds
        source = directory / f"card{n:02d}.png"
        if scene.asset:
            archive = directory / f"capture{n:02d}.zip"
            await storage.download(scene.asset, archive)
            frames_dir = directory / f"frames{n:02d}"
            frames_dir.mkdir()
            frames = unpack_frames(archive, frames_dir)
            archive.unlink()  # Do not retain a second copy of all source media.
            # Preserve observed intervals; stretch neither a long wait nor an
            # omitted operation. Captures fill at most eight seconds.
            lines = []
            for i, frame in enumerate(frames):
                lines.append(f"file '{frame['file']}'")
                interval = frames[i + 1]["at"] - frame["at"] if i + 1 < len(frames) else 0.125
                lines.append(f"duration {max(0.04, min(interval, 1.0)):.4f}")
            lines.append(f"file '{frames[-1]['file']}'")
            capture_list = frames_dir / "frames.txt"
            capture_list.write_text("\n".join(lines) + "\n")
            inputs += ["-f", "concat", "-safe", "1", "-i", str(capture_list)]
        else:
            inputs += ["-loop", "1", "-framerate", "15", "-i", str(source)]
        filters.append(f"[{n}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=15,tpad=stop_mode=clone:stop_duration={scene.seconds},trim=duration={scene.seconds},setpts=PTS-STARTPTS[v{n}]")
        scratch_budget(directory)
    filters.append("".join(f"[v{n}]" for n in range(len(manifest.scenes))) + f"concat=n={len(manifest.scenes)}:v=1:a=0[out]")
    output = directory / "video.mp4"
    started = time.monotonic()
    for bitrate in ("4M", "2M"):
        await command(["ffmpeg", "-v", "error", "-y", "-threads", "2", *inputs,
            "-filter_complex_threads", "1", "-filter_complex", ";".join(filters), "-map", "[out]", "-an",
            "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "23", "-maxrate", bitrate,
            "-bufsize", "8M", "-pix_fmt", "yuv420p", "-r", "15", "-t", "120", "-movflags", "+faststart", str(output)],
            timeout=max(1, 200 - (time.monotonic() - started)))
        if output.stat().st_size <= OUTPUT_BYTES:
            break
    if output.stat().st_size > OUTPUT_BYTES:
        raise ValueError("output_too_large")
    info = json.loads(await command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], timeout=10))
    video = next((stream for stream in info["streams"] if stream["codec_type"] == "video"), {})
    duration = float(info["format"]["duration"])
    if video.get("codec_name") != "h264" or (video.get("width"), video.get("height")) != (1920, 1080) or not 0 < duration <= 120.1:
        raise ValueError("invalid_output_stream")
    await command(["ffmpeg", "-v", "error", "-threads", "2", "-i", str(output), "-f", "null", "-"], timeout=30)
    # A native scene PNG is already a bounded, readable poster and needs no
    # optional FFmpeg image encoder.
    poster = directory / "card00.png"
    scratch_budget(directory)
    return {"video_path": output, "poster_path": poster, "duration_ms": round(duration * 1000), "chapters": chapters}
