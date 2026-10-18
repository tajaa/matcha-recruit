"""Eight-second windows from the already-open, public, guarded page only."""
from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import logging
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import get_settings
from app.database import connection_or_direct

from . import scope, settings, storage
from app.matcha.models.matcha_work.recaps import Event

logger = logging.getLogger(__name__)


FRAME_BYTES = 256 * 1024


class Window:
    """One capture window. Leaving it only stops the screencast; `store`
    keeps an accepted window afterwards, outside the caller's time budget, so
    recap storage never turns a page that loaded fine into a timeout."""
    accepted = False

    def __init__(self):
        self._kept = None
        self._fallback = None

    def accept(self, fallback_png: bytes | None = None):
        """The view succeeded. `fallback_png`: the screenshot it already took,
        kept as the one frame if the screencast sent none."""
        self.accepted = True
        self._fallback = fallback_png

    async def store(self):
        """Keep the accepted window. Never raises; bounded to ten seconds."""
        kept, self._kept = self._kept, None
        if kept is None:
            return
        source, frames = kept
        try:
            if not frames and self._fallback:
                data = await asyncio.to_thread(_jpeg, self._fallback)
                if len(data) <= FRAME_BYTES:
                    frames.append((0.0, data))
            if frames:
                await asyncio.wait_for(_store(source, frames), timeout=10)
        except Exception:
            logger.info("recap capture omitted run=%s", source.get("run_id"))


def _jpeg(png: bytes) -> bytes:
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        out = io.BytesIO()
        image.convert("RGB").save(out, format="JPEG", quality=65)
    return out.getvalue()


@asynccontextmanager
async def window(page, result: Window | None = None):
    result = Window() if result is None else result
    run_id = scope.current_run.get()
    if not settings.enabled() or not get_settings().espresso_recaps_capture_enabled or run_id is None:
        yield result
        return
    source = None
    cdp = None
    timer = None
    frames = []
    reserved = False
    started = time.monotonic()
    try:
        async with connection_or_direct() as conn, conn.transaction():
            source = await scope.source_for_run(conn, run_id)
            if source and not settings.available(source["owner_user_id"]):
                source = None
            if source and not await scope.capture_current(conn, source):
                source = None
            if source:
                reserved = await conn.fetchval(
                    """UPDATE mw_agent_recaps r SET capture_windows_reserved=capture_windows_reserved+1
                       WHERE id=$1 AND state IN ('collecting','waiting') AND capture_windows_reserved<8
                       AND capture_bytes_stored < 134217728 AND EXISTS (
                           SELECT 1 FROM mw_agent_recap_preferences p WHERE p.user_id=r.owner_user_id
                           AND p.company_id=r.company_id AND p.enabled) RETURNING true""", source["recap_id"],
                )
                if not reserved:
                    source = None
        if source:
            cdp = await page.context.new_cdp_session(page)
            async def frame(event):
                elapsed = time.monotonic() - started
                # Ack every received frame, including discarded ones. No model
                # or browser action waits for an encoder.
                await cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
                if elapsed > 8 or len(frames) >= 64 or (frames and elapsed - frames[-1][0] < 0.125):
                    return
                raw = event.get("data", "")
                if len(raw) > 350_000:
                    return
                try:
                    data = base64.b64decode(raw, validate=True)
                except (ValueError, binascii.Error):
                    return
                if len(data) <= FRAME_BYTES:
                    frames.append((elapsed, data))
            cdp.on("Page.screencastFrame", frame)
            await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 65, "maxWidth": 1440, "maxHeight": 900, "everyNthFrame": 1})
            async def stop_later():
                await asyncio.sleep(8)
                try:
                    await cdp.send("Page.stopScreencast")
                except Exception:
                    pass
            timer = asyncio.create_task(stop_later())
    except Exception:
        # CDP is Chromium-specific. The result card/checkpoint remains valid.
        logger.info("recap capture unavailable run=%s", run_id)
        if not reserved:
            source = None
    try:
        yield result
    finally:
        if timer:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)
        if cdp:
            try:
                await asyncio.wait_for(_stop(cdp), timeout=2)
            except Exception:
                pass
        if source and result.accepted and not asyncio.current_task().cancelling():
            result._kept = (source, list(frames))


async def _stop(cdp):
    await cdp.send("Page.stopScreencast")
    await cdp.detach()


async def _store(source, frames):
    token = uuid4()
    async with connection_or_direct() as conn, conn.transaction():
        if not await scope.capture_current(conn, source, lock=True):
            return
        event_id = await scope.event(conn, source, f"capture:{token}", Event(
            kind="phase_completed", title="Viewed a public page", occurred_at=datetime.now(timezone.utc),
        ))
        if not event_id:
            return
        await conn.execute("UPDATE mw_agent_recap_events SET capture_token=$2 WHERE id=$1", event_id, token)
        prefix = f"espresso-recaps/{source['company_id']}/{source['owner_user_id']}/{source['recap_id']}/source/{event_id}/{token}/"
        await conn.execute(
            """INSERT INTO mw_agent_recap_cleanup_jobs(bucket,prefix,not_before) VALUES($1,$2,NOW()+INTERVAL '7 days')
               ON CONFLICT DO NOTHING""", get_settings().s3_private_bucket, prefix,
        )
    with tempfile.TemporaryDirectory(prefix="espresso-capture-") as scratch:
        path = Path(scratch) / "frames.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as package:
            index = []
            origin = frames[0][0]
            for n, (at, data) in enumerate(frames):
                name = f"{n:03d}.jpg"
                package.writestr(name, data)
                index.append({"file": name, "at": round(at - origin, 4)})
            package.writestr("frames.json", json.dumps(index))
        asset = await storage.upload(path, prefix + "frames.zip", "application/zip", limit=16 * 1024 * 1024)
        async with connection_or_direct() as conn, conn.transaction():
            if not await scope.capture_current(conn, source, lock=True):
                return
            # Root lock fences freezing/deletion and makes the byte budget atomic.
            allowed = await conn.fetchval(
                """UPDATE mw_agent_recaps SET capture_bytes_stored=capture_bytes_stored+$2
                   WHERE id=$1 AND state IN ('collecting','waiting') AND source_completed_at IS NULL
                   AND capture_bytes_stored+$2<=134217728 RETURNING true""", source["recap_id"], asset.bytes,
            )
            if allowed:
                await conn.execute(
                    "UPDATE mw_agent_recap_events SET asset=$3::jsonb WHERE id=$1 AND capture_token=$2",
                    event_id, token, asset.model_dump_json(),
                )
