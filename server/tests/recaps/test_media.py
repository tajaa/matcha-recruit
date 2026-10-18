import asyncio
import json
import os
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.matcha.models.matcha_work.recaps import Event, Fact
from app.matcha.services.matcha_work.recaps import render, storyboard


def package(path, frames):
    with zipfile.ZipFile(path, "w") as out:
        for n, data in enumerate(frames):
            out.writestr(f"{n:03d}.jpg", data)
        out.writestr("frames.json", json.dumps([{"file": f"{n:03d}.jpg", "at": n / 8} for n in range(len(frames))]))


def test_capture_archive_is_not_extracted_and_has_bounded_members(tmp_path):
    archive = tmp_path / "frames.zip"
    target = tmp_path / "frames"; target.mkdir()
    package(archive, [b"jpeg", b"jpeg2"])
    frames = render.unpack_frames(archive, target)
    assert [f["at"] for f in frames] == [0, 0.125]
    assert (target / "000.jpg").read_bytes() == b"jpeg"
    package(archive, [])
    with pytest.raises(ValueError): render.unpack_frames(archive, target)
    package(archive, [b"x"] * 65)
    with pytest.raises(ValueError): render.unpack_frames(archive, target)
    package(archive, [b"x" * (256 * 1024 + 1)])
    with pytest.raises(ValueError): render.unpack_frames(archive, target)
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("frames.json", json.dumps([{"file": "../../escape", "at": 0}]))
        out.writestr("../../escape", b"private")
    with pytest.raises(ValueError): render.unpack_frames(archive, target)
    assert not (tmp_path.parent / "escape").exists()


def test_scratch_limit_is_enforced(tmp_path, monkeypatch):
    (tmp_path / "large").write_bytes(b"12345")
    monkeypatch.setattr(render, "SCRATCH_BYTES", 4)
    with pytest.raises(ValueError, match="scratch_size_limit"):
        render.scratch_budget(tmp_path)


@pytest.mark.asyncio
async def test_process_timeout_kills_only_owned_group(monkeypatch):
    process = SimpleNamespace(pid=123456, returncode=None, communicate=AsyncMock(side_effect=TimeoutError), wait=AsyncMock())
    create = AsyncMock(return_value=process)
    monkeypatch.setattr(render.asyncio, "create_subprocess_exec", create)
    kills = []
    monkeypatch.setattr(render.os, "killpg", lambda *args: kills.append(args))
    with pytest.raises(TimeoutError): await render.command(["ffmpeg", "-version"], timeout=0.01)
    assert kills == [(123456, render.signal.SIGKILL)]
    assert create.await_args.kwargs["start_new_session"] is True
    process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_process_does_not_publish_output(monkeypatch):
    process = SimpleNamespace(returncode=1, communicate=AsyncMock(return_value=(b"", None)))
    monkeypatch.setattr(render.asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(RuntimeError, match="media_process_failed"):
        await render.command(["ffmpeg"])


LABELS = {
    "jobs": ["Search criteria", "Discovered postings", "Screened relevance", "Checked posting pay", "Ranked matches", "Prepared approaches", "Reviewed outcomes", "Top job matches"],
    "apartments": ["Search constraints", "Found buildings", "Checked availability", "Compared monthly rent", "Applied pet criteria", "Ranked homes", "Reviewed unconfirmed facts", "Top apartment matches"],
    "calendar": ["Checked availability", "Selected a time", "Prepared change", "Requested confirmation", "Received confirmation", "Updated event", "Verified outcome", "Calendar result"],
    "email": ["Selected messages", "Read relevant threads", "Prepared draft", "Applied labels", "Archived selected mail", "Resolved send outcome", "Reviewed actions", "Email result"],
}


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("RUN_RECAP_MEDIA_TESTS") != "1", reason="opt-in local Chromium/FFmpeg smoke; no database or providers")
@pytest.mark.parametrize("category", list(LABELS))
async def test_real_1080p_media_smoke(category, tmp_path, monkeypatch):
    """Synthetic 30-minute timelines; fixture cards are explicitly demonstrations."""
    bundle = Path(__file__).resolve().parents[3] / "client/dist-recap"
    assert bundle.is_dir(), "Run cd client && npm run build:recaps first"
    monkeypatch.setattr(render, "get_settings", lambda: SimpleNamespace(espresso_recaps_render_bundle=str(bundle)))
    start = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    events = []
    for n, label in enumerate(LABELS[category]):
        snapshot = Event(kind="request" if n == 0 else "result" if n == 7 else "phase_completed",
            title=f"Demonstration: {label}", occurred_at=start + timedelta(seconds=n * 1800 / 7),
            facts=[Fact(label="Fixture", value=f"Synthetic {category} task; no customer actions"),
                   Fact(label="Elapsed task time", value=f"{round(n * 30 / 7)} minutes"),
                   Fact(label="Outcome", value="Verified fixture record")])
        events.append({"snapshot": snapshot.model_dump(mode="json")})
    manifest = storyboard.build(events)
    output_base = Path(os.getenv("RECAP_MEDIA_OUTPUT_DIR", str(tmp_path))) / category
    output_base.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    result = await render.render(manifest, output_base)
    metrics = {"category": category, "task_elapsed_seconds": 1800, "duration_ms": result["duration_ms"],
               "render_seconds": round(time.monotonic() - began, 2), "video_bytes": result["video_path"].stat().st_size,
               "dimensions": [1920, 1080], "template": manifest.template_version}
    (output_base / "metrics.json").write_text(json.dumps(metrics, indent=2))
    assert 60_000 <= result["duration_ms"] <= 120_000
    assert result["video_path"].stat().st_size <= render.OUTPUT_BYTES
    assert result["poster_path"].is_file()


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("RUN_RECAP_MEDIA_TESTS") != "1", reason="opt-in local pinned Chromium capture; no external browsing")
async def test_real_transition_capture_and_stitch(tmp_path, monkeypatch):
    from playwright.async_api import async_playwright
    from app.matcha.models.matcha_work.recaps import Asset, Manifest, Scene
    from app.matcha.services.matcha_work.recaps import capture, scope, settings, storage
    from .test_lifecycle import Conn, RUN, source, wire
    import shutil

    conn = Conn(); conn.fetchval.return_value = True
    wire(monkeypatch, capture, conn)
    monkeypatch.setattr(settings, "enabled", lambda: True)
    monkeypatch.setattr(settings, "available", lambda _: True)
    monkeypatch.setattr(capture, "get_settings", lambda: SimpleNamespace(espresso_recaps_capture_enabled=True))
    monkeypatch.setattr(scope, "source_for_run", AsyncMock(return_value=source()))
    archive = tmp_path / "real-capture.zip"
    captured = []
    async def keep(_source, frames):
        captured.extend(frames)
        with zipfile.ZipFile(archive, "w") as out:
            index = []
            for n, (at, data) in enumerate(frames):
                out.writestr(f"{n:03d}.jpg", data)
                index.append({"file": f"{n:03d}.jpg", "at": round(at - frames[0][0], 4)})
            out.writestr("frames.json", json.dumps(index))
    monkeypatch.setattr(capture, "_store", keep)
    token = scope.current_run.set(RUN)
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width":1440,"height":900})
                await page.route("**/*", lambda route: route.abort())
                await page.set_content("<body style='font:48px sans-serif;background:#f5f1e9'><h1>Demonstration: checking results</h1><p id='stage'>Step 1</p></body>")
                async with capture.window(page) as window:
                    for n in range(6):
                        await page.evaluate("n => {document.getElementById('stage').textContent='Step '+n;document.body.style.background=n%2?'#eadbc2':'#f5f1e9'}", n+1)
                        await asyncio.sleep(0.2)
                    window.accepted = True
                await window.store()
            finally:
                await browser.close()
    finally:
        scope.current_run.reset(token)
    assert 2 <= len(captured) <= 64
    assert all(0 <= frame[0] <= 8 for frame in captured)
    bundle = Path(__file__).resolve().parents[3] / "client/dist-recap"
    monkeypatch.setattr(render, "get_settings", lambda: SimpleNamespace(espresso_recaps_render_bundle=str(bundle)))
    async def local_download(_asset, target): shutil.copyfile(archive,target)
    monkeypatch.setattr(storage,"download",local_download)
    from uuid import uuid4
    asset = Asset(key="espresso-recaps/"+"/".join(str(uuid4()) for _ in range(3))+"/source/"+str(uuid4())+"/"+str(uuid4())+"/frames.zip",
                  sha256=storage.checksum(archive),bytes=archive.stat().st_size,mime="application/zip")
    now=datetime.now(timezone.utc)
    manifest=Manifest(scenes=[Scene(event=Event(title="Demonstration: browser transition",kind="phase_completed",occurred_at=now),seconds=4,asset=asset)])
    output=tmp_path/"stitched";output.mkdir()
    result=await render.render(manifest,output)
    assert 3900 <= result["duration_ms"] <= 4100
