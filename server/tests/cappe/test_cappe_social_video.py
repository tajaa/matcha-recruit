"""Cappe social — dropped videos: the ffmpeg cut, the upload to S3, the cut
each network gets, Reels on Meta, and the worker tasks that run it all.

ffmpeg decisions are pinned through the pure builders; one end-to-end test
cuts a generated clip with the real binary (skipped where ffmpeg isn't
installed). Storage is a fake `s3_client`; Meta is an `httpx.MockTransport`
(the `Graph` fake shared with the photo tests); the database is `QueryConn`.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_social_video.py -q
"""
import io
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.dependencies import require_cappe_account  # noqa: E402
from app.cappe.models.auth import CappeAccount  # noqa: E402
from app.cappe.models.social import CappeSocialMediaItem  # noqa: E402
from app.cappe.routes import social as social_routes  # noqa: E402
from app.cappe.services.social import assets as asset_store  # noqa: E402
from app.cappe.services.social import exports as export_store  # noqa: E402
from app.cappe.services.social import outbound, render, variants  # noqa: E402
from app.cappe.services.social import connections as conn_store  # noqa: E402
from app.cappe.services.social import inbox as inbox_store  # noqa: E402
from app.cappe.services.social import posts as post_store  # noqa: E402
from app.cappe.services.social.providers import meta  # noqa: E402
from app.cappe.services.social.providers.base import Pending, ProviderError, PublishResult  # noqa: E402
from app.workers.tasks import cappe_social_media as media_task  # noqa: E402
from tests._helpers.routes import QueryConn, Queue, route_client  # noqa: E402
from tests.cappe.test_cappe_social_meta import CFG, Graph  # noqa: E402

SITE, ASSET, POST, CONN = uuid4(), uuid4(), uuid4(), uuid4()
ACCOUNT = CappeAccount(id=uuid4(), email="owner@example.com", name="Owner", plan="business")
NOW = datetime.now(timezone.utc).replace(microsecond=0)
SITE_ROW = {"id": SITE, "name": "Po Coffee", "subdomain": "po", "custom_domain": None, "account_id": ACCOUNT.id,
            "timezone": "America/Los_Angeles"}
VERTICAL_URL = "https://cdn.example.test/cappe/social/renders/v.mp4"
LANDSCAPE_URL = "https://cdn.example.test/cappe/social/renders/l.mp4"
FRAMES = [{"url": f"https://cdn.example.test/f{i}.jpg", "t_ms": t} for i, t in enumerate((900, 3000, 5100))]


def asset(**over):
    return {"id": ASSET, "site_id": SITE, "account_id": ACCOUNT.id, "kind": "video", "status": "ready",
            "filename": "latte.mov", "source_path": "s3://private-bucket/cappe/social/sources/x.mov",
            "content_type": "video/quicktime", "bytes": 1234, "duration_ms": 6000, "width": 1080, "height": 1920,
            "has_audio": True, "trimmed": False, "frames": FRAMES,
            "renders": {"vertical": {"url": VERTICAL_URL, "width": 1080, "height": 1920, "duration_ms": 6000}},
            "error": None, "render_attempts": 1, "render_started_at": NOW, "expires_at": NOW + timedelta(days=30),
            "created_at": NOW, "updated_at": NOW, **over}


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TxConn(QueryConn):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.closed = False

    def transaction(self):
        return _Tx()

    async def close(self):
        self.closed = True


def facts(**over):
    base = {"duration_ms": 6000, "width": 1080, "height": 1920, "has_audio": True, "codec": "h264"}
    return render.VideoFacts(**{**base, **over})


def probe_json(width=1920, height=1080, duration="6.0", audio=True, rotation=None, tags=None):
    video = {"codec_type": "video", "codec_name": "hevc", "width": width, "height": height}
    if rotation is not None:
        video["side_data_list"] = [{"side_data_type": "Display Matrix", "rotation": rotation}]
    if tags:
        video["tags"] = tags
    streams = [video] + ([{"codec_type": "audio", "codec_name": "aac"}] if audio else [])
    return {"streams": streams, "format": {"duration": duration}}


# ── render: the pure decisions ──────────────────────────────────────────────

def test_probe_facts_reads_size_duration_audio_and_rotation():
    f = render.probe_facts(probe_json())
    assert (f.width, f.height, f.duration_ms, f.has_audio, f.codec) == (1920, 1080, 6000, True, "hevc")
    assert f.aspect > 1 and not f.trimmed and f.output_seconds == 6.0
    # A phone recording stored landscape with a 90° display matrix is portrait.
    rotated = render.probe_facts(probe_json(rotation=-90))
    assert (rotated.width, rotated.height) == (1080, 1920)
    assert (render.probe_facts(probe_json(tags={"rotate": "270"})).width) == 1080
    assert render.probe_facts(probe_json(audio=False)).has_audio is False
    long = render.probe_facts(probe_json(duration="300.5"))
    assert long.trimmed and long.output_seconds == render.MAX_SECONDS


@pytest.mark.parametrize("data,message", [
    ({"streams": [{"codec_type": "audio"}], "format": {"duration": "5"}}, "no video"),
    ({"streams": [{"codec_type": "video", "disposition": {"attached_pic": 1}, "width": 500, "height": 500}],
      "format": {"duration": "5"}}, "no video"),
    (probe_json(width=0), "size"),
    (probe_json(width="wide"), "size"),
    (probe_json(duration=None), "how long"),
    (probe_json(duration="2.4"), "at least 3 seconds"),
])
def test_probe_facts_refuses_clips_we_cant_post(data, message):
    with pytest.raises(render.RenderError) as exc:
        render.probe_facts(data)
    assert message in str(exc.value) and exc.value.permanent


def test_bad_rotation_values_are_ignored():
    assert render._rotation({"side_data_list": [{"rotation": "sideways"}]}) == 0
    assert render._rotation({"tags": {"rotate": "x"}}) == 0


def test_landscape_clips_get_a_second_cut():
    assert render.specs_for(facts()) == [render.VERTICAL]
    assert render.specs_for(facts(width=1080, height=1080)) == [render.VERTICAL]
    assert render.specs_for(facts(width=1920, height=1080)) == [render.VERTICAL, render.LANDSCAPE]


def test_inputs_are_fenced_to_https_and_video_demuxers():
    assert render.input_args("https://s3.example.test/x.mov?sig=1")[:2] == ["-protocol_whitelist", "https,tls,tcp"]
    guard = render.input_args("/tmp/x.mov")
    assert guard[1] == "file" and "hls" not in guard[3] and "mov" in guard[3] and "webm" in guard[3]


def test_video_graph_fits_never_crops():
    plain = render.video_graph(render.VERTICAL, facts())
    assert plain.startswith("[0:v]scale=1080:1920,") and "overlay" not in plain
    padded = render.video_graph(render.VERTICAL, facts(width=1920, height=1080))
    assert "force_original_aspect_ratio=decrease" in padded and "boxblur" in padded and "overlay" in padded
    # The blur runs at a quarter size, then is scaled back up.
    assert "scale=270:480:force_original_aspect_ratio=increase,crop=270:480" in padded


def test_encode_args_make_what_meta_asks_for():
    args = render.encode_args("https://src.test/a.mp4", render.VERTICAL, facts(), "/tmp/out.mp4")
    joined = " ".join(args)
    for part in ("-c:v libx264", "-profile:v high", "-preset veryfast", "-threads 2", "-g 60", "-ar 48000",
                 "-ac 2", "-movflags +faststart", f"-t {render.MAX_SECONDS}", "-map 0:a:0"):
        assert part in joined
    assert "anullsrc" not in joined and "-shortest" not in args and args[-1] == "/tmp/out.mp4"
    silent = render.encode_args("https://src.test/a.mp4", render.VERTICAL, facts(has_audio=False), "/tmp/o.mp4")
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in silent and "-shortest" in silent
    assert "1:a:0" in silent


def test_frame_points_and_args():
    assert render.frame_points_ms(facts()) == [900, 3000, 5100]
    assert render.frame_points_ms(facts(duration_ms=600_000))[-1] == round(render.MAX_SECONDS * 0.85 * 1000)
    args = render.frame_args("https://src.test/a.mp4", 1500, "/tmp/f.jpg")
    assert args[args.index("-ss") + 1] == "1.500" and args.index("-ss") < args.index("-i")
    assert render.probe_args("https://src.test/a.mp4")[-1] == "https://src.test/a.mp4"


def _out(width=1080, height=1920, duration="6.0", vcodec="h264", audio=True):
    streams = [{"codec_type": "video", "codec_name": vcodec, "width": width, "height": height}]
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return {"streams": streams, "format": {"duration": duration}}


def test_check_output_catches_a_wrong_cut():
    render.check_output(_out(), render.VERTICAL, facts())
    for bad in (_out(vcodec="hevc"), _out(audio=False), _out(width=720), _out(duration="1.0"), _out(duration="x")):
        with pytest.raises(render.RenderError):
            render.check_output(bad, render.VERTICAL, facts())


# ── render: running ffmpeg ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_returns_output_and_turns_failures_into_owner_messages():
    assert await render.run(["sh", "-c", "printf ok"], timeout=5) == b"ok"
    with pytest.raises(render.RenderError) as exc:
        await render.run(["sh", "-c", "echo bad >&2; exit 3"], timeout=5)
    assert "couldn't read" in str(exc.value) and not exc.value.permanent


@pytest.mark.asyncio
async def test_run_kills_a_process_that_overruns():
    with pytest.raises(render.RenderError) as exc:
        await render.run(["sh", "-c", "sleep 5"], timeout=0.2)
    assert "took too long" in str(exc.value)


@pytest.mark.asyncio
async def test_probe_and_encode_report_unreadable_or_empty_output(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "run", AsyncMock(return_value=b"not json"))
    with pytest.raises(render.RenderError):
        await render.probe("https://src.test/a.mp4")
    monkeypatch.setattr(render, "run", AsyncMock(return_value=b""))
    with pytest.raises(render.RenderError, match="picture"):
        await render.extract_frame("https://src.test/a.mp4", 100, tmp_path, 0)
    with pytest.raises(render.RenderError, match="empty"):
        await render.encode("https://src.test/a.mp4", render.VERTICAL, facts(), tmp_path)


FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def _make_clip(path: Path, size: str, audio: bool, seconds: float = 4.0) -> None:
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25"]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    args += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac"] if audio else []
    subprocess.run([*args, str(path)], check=True, timeout=60)


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
@pytest.mark.asyncio
async def test_a_real_landscape_clip_is_cut_for_every_network(tmp_path):
    source = tmp_path / "source-landscape.mp4"
    _make_clip(source, "640x360", audio=True)
    f = await render.probe(str(source))
    assert (f.width, f.height, f.has_audio) == (640, 360, True)
    frame = await render.extract_frame(str(source), render.frame_points_ms(f)[1], tmp_path, 1)
    assert frame.read_bytes()[:2] == b"\xff\xd8"
    for spec in render.specs_for(f):
        out = await render.encode(str(source), spec, f, tmp_path)
        data = out.read_bytes()
        # The index sits before the media, so Meta can start reading at once.
        assert data.find(b"moov") < data.find(b"mdat")


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
@pytest.mark.asyncio
async def test_a_real_silent_portrait_clip_gets_a_sound_track(tmp_path):
    source = tmp_path / "source-portrait.mp4"
    _make_clip(source, "360x640", audio=False, seconds=3.5)
    f = await render.probe(str(source))
    assert f.has_audio is False and render.specs_for(f) == [render.VERTICAL]
    out = await render.encode(str(source), render.VERTICAL, f, tmp_path)
    probed = json.loads(await render.run(render.probe_args(str(out)), timeout=30))
    assert any(s["codec_type"] == "audio" for s in probed["streams"])


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
@pytest.mark.asyncio
async def test_a_text_playlist_posing_as_a_video_is_not_followed(tmp_path):
    evil = tmp_path / "evil.mp4"
    evil.write_text("#EXTM3U\n#EXTINF:1,\nfile:///etc/hosts\n")
    with pytest.raises(render.RenderError):
        await render.probe(str(evil))


# ── which cut each network gets ─────────────────────────────────────────────

def test_video_cut_per_network():
    both = {"vertical": {"url": VERTICAL_URL}, "landscape": {"url": LANDSCAPE_URL}}
    assert variants.video_cut("instagram", both) == ("reel", "vertical")
    assert variants.video_cut("facebook", both) == ("video", "landscape")
    assert variants.video_cut("facebook", {"vertical": {}}) == ("reel", "vertical")


def test_media_for_swaps_the_video_for_its_cut():
    img = {"kind": "image", "url": "https://cdn.example.test/a.jpg"}
    item = {"kind": "video", "asset_id": str(ASSET), "alt": None}
    out = variants.media_for("instagram", [item], {str(ASSET): asset()})
    assert out == [{**item, "url": VERTICAL_URL, "format": "reel", "duration_ms": 6000, "thumb_offset_ms": 3000}]
    assert variants.media_for("facebook", [img], {}) == [img]
    landscape = asset(renders={"vertical": {"url": VERTICAL_URL}, "landscape": {"url": LANDSCAPE_URL}}, frames=[])
    fb = variants.media_for("facebook", [item], {str(ASSET): landscape})[0]
    assert fb["url"] == LANDSCAPE_URL and fb["format"] == "video" and fb["thumb_offset_ms"] is None


@pytest.mark.parametrize("found,retryable,message", [
    (None, False, "gone"),
    (asset(status="failed", error="Videos need to be at least 3 seconds long."), False, "3 seconds"),
    (asset(status="rendering"), True, "still being prepared"),
    (asset(renders={}), False, "wasn't prepared"),
])
def test_media_for_refuses_a_video_that_isnt_ready(found, retryable, message):
    assets = {str(ASSET): found} if found else {}
    with pytest.raises(ProviderError) as exc:
        variants.media_for("instagram", [{"kind": "video", "asset_id": str(ASSET)}], assets)
    assert exc.value.retryable is retryable and message in str(exc.value)


# ── the asset store ─────────────────────────────────────────────────────────

class FakeS3:
    def __init__(self, head=None, first=b"\x00\x00\x00\x18ftypqt  ", fail_head=False, fail_get=False):
        self.head, self.first, self.fail_head, self.fail_get = head, first, fail_head, fail_get
        self.posts, self.uploads, self.deleted = [], [], []

    def generate_presigned_post(self, **kw):
        self.posts.append(kw)
        return {"url": "https://bucket.s3.example.test/", "fields": {**kw["Fields"], "key": kw["Key"]}}

    def head_object(self, Bucket, Key):
        if self.fail_head:
            raise RuntimeError("404")
        return self.head

    def get_object(self, Bucket, Key, Range):
        if self.fail_get:
            raise RuntimeError("gone")
        assert Range == "bytes=0-15"
        return {"Body": io.BytesIO(self.first)}

    def upload_file(self, path, bucket, key, ExtraArgs, Config):
        self.uploads.append((path, bucket, key, ExtraArgs))

    def delete_object(self, Bucket, Key):
        if Key.endswith("boom.mp4"):
            raise RuntimeError("denied")
        self.deleted.append((Bucket, Key))


def storage(s3=None, **over):
    base = {"s3_client": s3 if s3 is not None else FakeS3(), "bucket": "public-bucket",
            "private_bucket": "private-bucket", "cloudfront_domain": "cdn.example.test",
            "get_presigned_download_url": lambda path, expires_in: f"https://signed.test/{path[5:]}?e={expires_in}"}
    return SimpleNamespace(**{**base, **over})


def test_looks_like_video_reads_the_container_header():
    assert asset_store.looks_like_video(b"\x00\x00\x00\x18ftypmp42", "video/mp4")
    assert asset_store.looks_like_video(b"\x00\x00\x00\x08wide\x00\x00", "video/quicktime")
    assert asset_store.looks_like_video(b"\x1a\x45\xdf\xa3\x01", "video/webm")
    assert not asset_store.looks_like_video(b"#EXTM3U\n#EXT", "video/mp4")
    assert not asset_store.looks_like_video(b"\x00\x00\x00\x18ftyp", "video/webm")
    assert not asset_store.looks_like_video(b"abc", "video/mp4")


def test_presign_pins_the_size_and_type(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(s3))
    out = asset_store.presign_upload(SITE, "latte.mov", "video/quicktime", 5000)
    call = s3.posts[0]
    # The public bucket: its CORS takes browser uploads (the credentials bucket has none).
    assert call["Bucket"] == "public-bucket" and call["Key"].startswith(f"cappe/social/sources/{SITE}/")
    assert call["Key"].endswith(".mov") and ["content-length-range", 5000, 5000] in call["Conditions"]
    assert {"Content-Type": "video/quicktime"} in call["Conditions"]
    assert out["path"] == f"s3://public-bucket/{call['Key']}" and out["fields"]["Content-Type"] == "video/quicktime"


@pytest.mark.parametrize("content_type,size,message", [
    ("video/x-msvideo", 10, "MP4, MOV or WebM"),
    ("video/mp4", 0, "empty"),
    ("video/mp4", asset_store.MAX_VIDEO_BYTES + 1, "500 MB"),
])
def test_presign_refuses_files_we_dont_take(monkeypatch, content_type, size, message):
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage())
    with pytest.raises(ValueError, match=message):
        asset_store.presign_upload(SITE, "a", content_type, size)


def test_presign_needs_storage(monkeypatch):
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(cloudfront_domain=None))
    with pytest.raises(asset_store.AssetStorageUnavailable):
        asset_store.presign_upload(SITE, "a.mp4", "video/mp4", 10)


@pytest.mark.asyncio
@pytest.mark.parametrize("s3,problem", [
    (FakeS3(head={"ContentLength": 1234, "ContentType": "video/quicktime"}), None),
    (FakeS3(fail_head=True), "didn't finish"),
    (FakeS3(head={"ContentLength": 99, "ContentType": "video/quicktime"}), "doesn't match"),
    (FakeS3(head={"ContentLength": 1234, "ContentType": "video/mp4"}), "doesn't match"),
    (FakeS3(head={"ContentLength": 1234, "ContentType": "video/quicktime"}, fail_get=True), "didn't finish"),
    (FakeS3(head={"ContentLength": 1234, "ContentType": "video/quicktime"}, first=b"#EXTM3U\nxxxxxxxx"), "isn't a video"),
])
async def test_verify_upload_checks_what_landed(monkeypatch, s3, problem):
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(s3))
    found = await asset_store.verify_upload(asset(status="uploading"))
    assert found is None if problem is None else problem in found


@pytest.mark.asyncio
async def test_renders_and_frames_upload_from_disk_to_the_public_bucket(monkeypatch, tmp_path):
    s3 = FakeS3()
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(s3))
    clip = tmp_path / "vertical.mp4"
    clip.write_bytes(b"x" * 42)
    out = await asset_store.upload_render(str(clip), ASSET, "vertical")
    path, bucket, key, extra = s3.uploads[0]
    assert bucket == "public-bucket" and key.startswith(f"cappe/social/renders/{ASSET}/vertical-")
    assert out == {"url": f"https://cdn.example.test/{key}", "key": key, "bytes": 42}
    assert extra["ContentType"] == "video/mp4"
    frame_url = await asset_store.upload_frame(str(clip), ASSET, 2)
    assert frame_url.startswith(f"https://cdn.example.test/cappe/social/frames/{ASSET}/2-")
    assert s3.uploads[1][3]["ContentType"] == "image/jpeg"


def test_source_read_url(monkeypatch):
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage())
    assert asset_store.source_read_url("s3://private-bucket/k.mov") == "https://signed.test/private-bucket/k.mov?e=3600"
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(get_presigned_download_url=lambda p, expires_in: None))
    with pytest.raises(asset_store.AssetStorageUnavailable):
        asset_store.source_read_url("s3://private-bucket/k.mov")


@pytest.mark.asyncio
async def test_delete_files_removes_original_and_cuts_but_keeps_frames(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(s3))
    a = asset(renders={"vertical": {"url": "https://cdn.example.test/cappe/social/renders/v.mp4"},
                       "landscape": {"url": "https://elsewhere.test/l.mp4"},
                       "bad": {"url": "https://cdn.example.test/boom.mp4"}})
    await asset_store.delete_files(a)
    assert s3.deleted == [("private-bucket", "cappe/social/sources/x.mov"),
                          ("public-bucket", "cappe/social/renders/v.mp4")]
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(s3=False))
    await asset_store.delete_files(a)  # no S3 configured: nothing to do


@pytest.mark.asyncio
async def test_asset_rows():
    row = {**asset(), "frames": json.dumps(FRAMES), "renders": json.dumps(asset()["renders"])}
    conn = QueryConn(
        fetchrow={"INSERT INTO cappe_social_assets": row, "WHERE id = $1 AND site_id = $2": row,
                  "FROM cappe_social_assets WHERE id = $1": row, "SET status = 'rendering'": {"id": ASSET},
                  "DELETE FROM cappe_social_assets a": row},
        fetch={"WHERE id = ANY($1::uuid[])": [row]},
    )
    created = await asset_store.create(conn, site_id=SITE, account_id=ACCOUNT.id, filename="la<tte>.mov",
                                       path="s3://b/k", content_type="video/quicktime", size=1234)
    assert created["frames"] == FRAMES and conn.args_for("INSERT INTO cappe_social_assets")[2] == "latte.mov"
    assert (await asset_store.get(conn, SITE, ASSET))["renders"]["vertical"]["url"] == VERTICAL_URL
    assert (await asset_store.get_by_id(conn, ASSET))["id"] == ASSET
    assert list(await asset_store.load_many(conn, [ASSET])) == [str(ASSET)]
    assert await asset_store.load_many(conn, []) == {}
    assert await asset_store.mark_rendering(conn, ASSET) is True
    await asset_store.start_render(conn, ASSET)
    await asset_store.record_facts(conn, ASSET, facts(duration_ms=120_000))
    assert conn.args_for("SET duration_ms = $2")[1:] == (120_000, 1080, 1920, True, True)
    await asset_store.record_frames(conn, ASSET, FRAMES)
    await asset_store.record_render(conn, ASSET, "vertical", {"url": VERTICAL_URL})
    assert conn.args_for("renders || jsonb_build_object")[1] == "vertical"
    await asset_store.mark_ready(conn, ASSET)
    await asset_store.mark_failed(conn, ASSET, "x" * 900)
    assert len(conn.args_for("SET status = 'failed'")[1]) == 500
    deleted = await asset_store.delete(conn, SITE, ASSET)
    assert deleted["id"] == ASSET and conn.args_for("DELETE FROM cappe_social_assets a")[2] == str(ASSET)
    assert await asset_store.get(QueryConn(fetchrow={"WHERE id = $1 AND site_id = $2": None}), SITE, ASSET) is None


@pytest.mark.asyncio
async def test_sweep_queries():
    row = asset(status="rendering")
    conn = QueryConn(fetch={"status = 'rendering' AND COALESCE": [row], "DELETE FROM cappe_social_assets WHERE id IN": [row],
                            "a.expires_at < NOW()": [row]})
    assert (await asset_store.stuck_renders(conn, minutes=30, limit=5))[0]["id"] == ASSET
    assert conn.args_for("status = 'rendering' AND COALESCE") == (30, 5)
    assert len(await asset_store.take_abandoned_uploads(conn, limit=5)) == 1
    assert len(await asset_store.expired(conn, limit=5)) == 1
    assert "rendering" in conn.args_for("a.expires_at < NOW()")[1]
    await asset_store.touch_render(conn, ASSET)
    await asset_store.mark_deleted(conn, ASSET)
    assert any("status = 'deleted'" in s for s in conn.sql_for("execute"))


def test_public_view_and_poster():
    view = asset_store.public_view(asset())
    assert "source_path" not in view and view["renders"]["vertical"] == {
        "url": VERTICAL_URL, "width": 1080, "height": 1920, "duration_ms": 6000}
    assert asset_store.poster(asset()) == FRAMES[1]["url"]
    assert asset_store.poster(None) is None and asset_store.poster(asset(frames=[])) is None


# ── posts waiting on a video, and Meta still processing ─────────────────────

@pytest.mark.asyncio
async def test_a_scheduled_video_post_waits_for_its_cut():
    row = {"id": POST, "site_id": SITE, "caption": "", "media": "[]", "link_url": None, "product_id": None,
           "status": "scheduled", "scheduled_at": NOW, "published_at": None, "ai_meta": "{}", "created_at": NOW,
           "updated_at": NOW}
    conn = QueryConn(fetchrow={"INSERT INTO cappe_social_posts": row, "SET status = 'rendering'": {"id": POST}})
    media = [{"kind": "video", "asset_id": str(ASSET)}]
    post = await post_store.create_post(conn, site_id=SITE, caption="", media=media, link_url=None,
                                        product_id=None, scheduled_at=NOW)
    assert post["status"] == "rendering"
    hold = conn.sql_for("fetchrow")[1]
    assert "jsonb_array_elements(p.media)" in hold and "a.status <> 'ready'" in hold
    draft = await post_store.create_post(conn, site_id=SITE, caption="", media=media, link_url=None,
                                         product_id=None, scheduled_at=None)
    assert draft["status"] == "scheduled" and len(conn.sql_for("fetchrow")) == 3  # no hold for a draft


@pytest.mark.asyncio
async def test_release_and_fail_posts_waiting_on_a_video():
    conn = QueryConn(fetch={"SET status = 'scheduled'": [{"id": POST, "scheduled_at": NOW}],
                            "SET status = 'failed'": Queue([[{"id": POST}], []])})
    assert await post_store.release_rendered(conn, ASSET) == [{"id": POST, "scheduled_at": NOW}]
    assert conn.args_for("SET status = 'scheduled'") == (str(ASSET),)
    assert await post_store.fail_rendering(conn, ASSET, "too short") == [POST]
    assert conn.args_for("UPDATE cappe_social_post_targets SET status = 'failed'") == ([POST], "Video: too short")
    assert await post_store.fail_rendering(conn, ASSET, "x") == []


@pytest.mark.asyncio
async def test_settle_renders_releases_ready_posts_and_fails_broken_ones():
    conn = QueryConn(fetch={"SET status = 'failed', updated_at": [{"id": POST}],
                            "SET status = 'scheduled'": [{"id": POST, "scheduled_at": NOW}]})
    out = await post_store.settle_renders(conn, limit=10)
    assert out == {"released": [{"id": POST, "scheduled_at": NOW}], "failed": [POST]}
    failing = conn.sql_for("fetch")[0]
    assert "a.status IN ('failed', 'deleted')" in failing and "a.id IS NULL" in failing
    assert conn.args_for("UPDATE cappe_social_post_targets SET status = 'failed'") == ([POST], post_store.BROKEN_VIDEO)
    scoped = QueryConn(fetch={"SET status = 'failed', updated_at": [], "SET status = 'scheduled'": []})
    assert await post_store.settle_renders(scoped, post_ids=[POST]) == {"released": [], "failed": []}
    assert scoped.args_for("SET status = 'scheduled'") == (200, [POST])
    assert "p.id = ANY($2::uuid[])" in scoped.sql_for("fetch")[0]


@pytest.mark.asyncio
async def test_retrying_a_post_whose_video_failed_fails_it_again_instead_of_waiting():
    conn = QueryConn(fetchrow={"UPDATE cappe_social_posts SET status = $3": {"id": POST},
                               "SET status = 'rendering'": {"id": POST}},
                     fetch={"SET status = 'failed', updated_at": [{"id": POST}], "SET status = 'scheduled'": []})
    assert await post_store.publish_now(conn, SITE, POST)
    assert any("a.status IN ('failed', 'deleted')" in s for s in conn.sql_for("fetch"))


@pytest.mark.asyncio
async def test_record_pending_keeps_the_state_and_gives_back_the_attempt():
    conn = QueryConn()
    await post_store.record_pending(conn, POST, Pending("instagram_processing", {"container_id": "c1"}, 1))
    sql, args = conn.sql_for("execute")[0], conn.calls[0][2]
    assert "attempts = GREATEST(attempts - 1, 0)" in sql
    assert json.loads(args[1]) == {"container_id": "c1", "phase": "instagram_processing"} and args[2] == 5


@pytest.mark.asyncio
async def test_recover_stale_claims_and_target_phase():
    conn = QueryConn(fetch={"WHERE status = 'publishing' AND claimed_at": [{"post_id": POST}, {"post_id": POST}]})
    assert await post_store.recover_stale_claims(conn, 20) == [POST]
    assert conn.args_for("claimed_at <") == (20, post_store.MAX_ATTEMPTS, post_store.INTERRUPTED)
    # A target with no handle to resume from fails (it may have gone out)
    # instead of being posted again; one with a handle resumes.
    sql = conn.sql_for("fetch")[0]
    assert "state = '{}'::jsonb THEN 'failed'" in sql
    target = post_store._row_to_target({"status": "pending", "metrics": None, "state": '{"phase": "facebook_processing"}'})
    assert target["phase"] == "facebook_processing" and "state" not in target
    assert post_store._row_to_target({"status": "failed", "metrics": None, "state": {"phase": "x"}})["phase"] is None


@pytest.mark.asyncio
async def test_posts_carry_their_video_poster():
    posts = [{"media": [{"kind": "image", "url": "https://cdn.example.test/a.jpg"},
                        {"kind": "video", "asset_id": str(ASSET)}]}]
    conn = QueryConn(fetch={"SELECT id, frames FROM cappe_social_assets": [{"id": ASSET, "frames": json.dumps(FRAMES)}]})
    await post_store.attach_posters(conn, posts)
    assert posts[0]["media"][1]["poster"] == FRAMES[1]["url"] and "poster" not in posts[0]["media"][0]
    quiet = QueryConn()
    await post_store.attach_posters(quiet, [{"media": [{"kind": "image", "url": "u"}]}])
    assert quiet.calls == []


@pytest.mark.asyncio
async def test_publish_target_sends_the_cut_and_parks_a_pending_publish(monkeypatch):
    post_row = {"id": POST, "site_id": SITE, "caption": "New latte", "media": [{"kind": "video", "asset_id": str(ASSET)}],
                "link_url": None, "status": "publishing"}
    conn = QueryConn(fetchrow={"FROM cappe_social_posts WHERE id": post_row})
    monkeypatch.setattr(conn_store, "credentials", AsyncMock(return_value={
        "id": CONN, "platform": "instagram", "external_id": "ig1", "token": "tok", "status": "connected"}))
    monkeypatch.setattr(asset_store, "load_many", AsyncMock(return_value={str(ASSET): asset()}))
    publish = AsyncMock(return_value=Pending("instagram_processing", {"container_id": "c9"}, 30))
    monkeypatch.setattr(meta, "publish", publish)
    record = AsyncMock()
    monkeypatch.setattr(post_store, "record_pending", record)
    monkeypatch.setattr(post_store, "rollup_post", AsyncMock(return_value="publishing"))
    claim = {"id": uuid4(), "post_id": POST, "connection_id": CONN, "attempts": 1, "state": {"container_id": "c1"}}
    assert await outbound.publish_target(conn, CFG, claim) == "pending"
    kwargs = publish.await_args.kwargs
    assert kwargs["media"][0]["url"] == VERTICAL_URL and kwargs["state"] == {"container_id": "c1"}
    assert record.await_args.args[2].state == {"container_id": "c9"}
    # Still being cut: a retryable failure, not a lost post.
    monkeypatch.setattr(asset_store, "load_many", AsyncMock(return_value={str(ASSET): asset(status="rendering")}))
    failure = AsyncMock(return_value="pending")
    monkeypatch.setattr(post_store, "record_failure", failure)
    assert await outbound.publish_target(conn, CFG, claim) == "pending"
    assert failure.await_args.args[3].retryable is True


# ── Meta: Reels and Page videos ─────────────────────────────────────────────

VIDEO = {"kind": "video", "url": VERTICAL_URL, "format": "reel", "thumb_offset_ms": 3000}


@pytest.mark.asyncio
async def test_instagram_reel_starts_then_checks_then_publishes():
    graph = Graph({
        ("POST", "ig1/media"): {"id": "c1"},
        ("GET", "c1"): {"status_code": "IN_PROGRESS"},
    })
    async with graph.client() as client:
        first = await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="New",
                                   media=[VIDEO], link_url="https://po.example.test/shop/latte", client=client)
        assert first == Pending("instagram_processing", {"container_id": "c1", "checks": 0}, meta.FIRST_CHECK_SECONDS)
        form = graph.form("POST", "ig1/media")
        assert form["media_type"] == "REELS" and form["video_url"] == VERTICAL_URL and form["thumb_offset"] == "3000"
        assert form["share_to_feed"] == "true" and form["caption"].endswith("https://po.example.test/shop/latte")
        again = await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="New",
                                   media=[VIDEO], state=first.state, client=client)
        assert again.state["checks"] == 1 and again.retry_after_s == meta.CHECK_SECONDS
        assert graph.paths().count(("POST", "ig1/media")) == 1  # never re-uploaded
    graph.routes.update({("GET", "c1"): {"status_code": "FINISHED"}, ("POST", "ig1/media_publish"): {"id": "m1"},
                         ("GET", "m1"): {"permalink": "https://instagram.example.test/reel/m1"}})
    async with graph.client() as client:
        done = await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="New",
                                  media=[VIDEO], state={"container_id": "c1", "checks": 3}, client=client)
    assert done == PublishResult(external_post_id="m1", permalink="https://instagram.example.test/reel/m1")


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,state,expect", [
    ({"status_code": "ERROR", "status": "Error: 2207026"}, {}, "couldn't process the video (Error: 2207026)"),
    ({"status_code": "EXPIRED"}, {}, "EXPIRED"),
    ({"status_code": "IN_PROGRESS"}, {"checks": meta.IG_MAX_CHECKS - 1}, "after 10 minutes"),
])
async def test_instagram_reel_gives_up_cleanly(answer, state, expect):
    graph = Graph({("GET", "c1"): answer})
    async with graph.client() as client:
        with pytest.raises(ProviderError) as exc:
            await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="x",
                               media=[VIDEO], state={"container_id": "c1", **state}, client=client)
    assert expect in str(exc.value) and exc.value.retryable is False


@pytest.mark.asyncio
async def test_instagram_reel_recorded_late_and_missing_ids():
    graph = Graph({("GET", "c1"): {"status_code": "PUBLISHED"}, ("POST", "ig1/media"): {}})
    async with graph.client() as client:
        late = await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="x",
                                  media=[VIDEO], state={"container_id": "c1"}, client=client)
        assert late == PublishResult(external_post_id="c1")
        with pytest.raises(ProviderError, match="no media container") as exc:
            await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="x",
                               media=[VIDEO], client=client)
        assert exc.value.retryable
    graph = Graph({("GET", "c1"): {"status_code": "FINISHED"}, ("POST", "ig1/media_publish"): {}})
    async with graph.client() as client:
        with pytest.raises(ProviderError, match="no media id"):
            await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="x",
                               media=[VIDEO], state={"container_id": "c1"}, client=client)


@pytest.mark.asyncio
async def test_instagram_needs_a_photo_or_a_video():
    with pytest.raises(ProviderError, match="a photo or a video"):
        await meta.publish(CFG, platform="instagram", external_id="ig1", token="t", caption="x", media=[],
                           client=Graph({}).client())


def _rupload_ok(request, form):
    assert request.headers["authorization"] == "OAuth t" and request.headers["file_url"] == VERTICAL_URL
    return {"success": True}


@pytest.mark.asyncio
async def test_facebook_reel_uploads_by_url_then_checks():
    graph = Graph({
        ("POST", "p1/video_reels"): lambda req, form: {"video_id": "v1"} if form["upload_phase"] == "start"
        else {"success": True},
        ("POST", f"/video-upload/{CFG.version}/v1"): _rupload_ok,
        ("GET", "v1"): {"status": {"video_status": "processing", "publishing_phase": {"status": "not_started"}}},
    })
    async with graph.client() as client:
        started = await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="New latte",
                                     media=[VIDEO], client=client)
        # The Reel's id is saved before the upload, so a retry finishes it.
        assert started.phase == "facebook_uploading" and started.state == {"video_id": "v1", "upload": True, "checks": 0}
        assert not [p for m, p, _, f in graph.requests if f.get("upload_phase") == "finish"]
        first = await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="New latte",
                                   media=[VIDEO], state=started.state, client=client)
        assert first.phase == "facebook_processing" and first.state == {"video_id": "v1", "checks": 0}
        assert len([p for m, p, _, f in graph.requests if f.get("upload_phase") == "start"]) == 1
        finish = [f for m, p, _, f in graph.requests if p == "p1/video_reels" and f.get("upload_phase") == "finish"][0]
        assert finish == {"video_id": "v1", "upload_phase": "finish", "video_state": "PUBLISHED",
                          "description": "New latte"}
        waiting = await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="x",
                                     media=[VIDEO], state=first.state, client=client)
        assert waiting.state["checks"] == 1
    graph.routes[("GET", "v1")] = {"status": {"video_status": "ready", "publishing_phase": {
        "status": "complete", "publish_status": "published"}}, "permalink_url": "/reel/v1/"}
    async with graph.client() as client:
        done = await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="x",
                                  media=[VIDEO], state={"video_id": "v1"}, client=client)
    assert done == PublishResult(external_post_id="v1", permalink="https://www.facebook.com/reel/v1/")


@pytest.mark.asyncio
async def test_facebook_landscape_video_goes_to_page_videos():
    graph = Graph({("POST", "p1/videos"): {"id": "v2"},
                   ("GET", "v2"): {"status": {"video_status": "ready"}, "permalink_url": "https://fb.example.test/v2"}})
    landscape = {**VIDEO, "url": LANDSCAPE_URL, "format": "video"}
    async with graph.client() as client:
        first = await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="Wide",
                                   media=[landscape], client=client)
        assert graph.form("POST", "p1/videos") == {"file_url": LANDSCAPE_URL, "description": "Wide", "published": "true"}
        done = await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="Wide",
                                  media=[landscape], state=first.state, client=client)
    assert done.permalink == "https://fb.example.test/v2"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,state,expect", [
    ({"video_status": "error"}, {}, "(error)"),
    ({"video_status": "processing", "processing_phase": {"status": "error", "error": {"message": "Bad codec"}}}, {},
     "Bad codec"),
    ({"video_status": "ready", "publishing_phase": {"status": "error"}}, {}, "publishing failed"),
    ({"video_status": "processing"}, {"checks": meta.FB_MAX_CHECKS - 1}, "after 30 minutes"),
])
async def test_facebook_video_gives_up_cleanly(status, state, expect):
    graph = Graph({("GET", "v1"): {"status": status}})
    async with graph.client() as client:
        with pytest.raises(ProviderError) as exc:
            await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="x",
                               media=[VIDEO], state={"video_id": "v1", **state}, client=client)
    assert expect in str(exc.value) and not exc.value.retryable


@pytest.mark.asyncio
async def test_facebook_reel_upload_failures():
    def start_only(req, form):
        return {"video_id": "v1"} if form["upload_phase"] == "start" else {"success": False}

    cases = [
        ({("POST", "p1/video_reels"): {}}, "no video id", True),
        ({("POST", "p1/video_reels"): start_only,
          ("POST", f"/video-upload/{CFG.version}/v1"): (400, {"error": {"message": "bad url", "code": 100}})},
         "bad url", False),
        ({("POST", "p1/video_reels"): start_only, ("POST", f"/video-upload/{CFG.version}/v1"): {"ok": 1}},
         "didn't take the video upload", True),
        ({("POST", "p1/video_reels"): start_only, ("POST", f"/video-upload/{CFG.version}/v1"): {"success": True}},
         "didn't publish the Reel", True),
    ]
    for routes, expect, retryable in cases:
        graph = Graph(routes)
        state = {} if expect == "no video id" else {"video_id": "v1", "upload": True}
        async with graph.client() as client:
            with pytest.raises(ProviderError) as exc:
                await meta.publish(CFG, platform="facebook", external_id="p1", token="t", caption="x",
                                   media=[VIDEO], state=state, client=client)
        assert expect in str(exc.value) and exc.value.retryable is retryable, expect


@pytest.mark.asyncio
async def test_rupload_unreachable_and_unreadable():
    def broken(request):
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as client:
        with pytest.raises(ProviderError) as exc:
            await meta._rupload(CFG, "v1", "t", VERTICAL_URL, client)
    assert exc.value.retryable
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok"))) as client:
        with pytest.raises(ProviderError, match="didn't take"):
            await meta._rupload(CFG, "v1", "t", VERTICAL_URL, client)
    assert meta._absolute_fb_url(None) is None


# ── routes ──────────────────────────────────────────────────────────────────

def ent(*features):
    return SimpleNamespace(has=lambda f: f in features)


@pytest.fixture
def world(monkeypatch):
    conn = TxConn(fetchrow={"FROM cappe_sites WHERE id = $1 AND account_id": SITE_ROW})
    monkeypatch.setattr(social_routes, "get_connection", lambda: conn)
    monkeypatch.setattr(social_routes, "resolve_entitlements",
                        AsyncMock(return_value=ent("social", "social_video", "social_autoreply")))
    monkeypatch.setattr(social_routes, "check_rate_limit", AsyncMock())
    w = SimpleNamespace(conn=conn, mp=monkeypatch)
    with route_client(social_routes.router, overrides={require_cappe_account: ACCOUNT}) as client:
        w.client = client
        yield w


BASE = f"/sites/{SITE}/social"
LA = ZoneInfo("America/Los_Angeles")
# A wall-clock time a few days out, as the composer sends it (no zone).
SOON_LOCAL = (datetime.now(LA) + timedelta(days=5)).replace(hour=14, minute=0, second=0, microsecond=0, tzinfo=None)


def test_presign_creates_the_row_and_hands_back_the_post(world):
    world.mp.setattr(asset_store, "presign_upload", Mock(return_value={
        "upload_url": "https://bucket.s3.example.test/", "fields": {"key": "k"}, "path": "s3://b/k"}))
    create = AsyncMock(return_value=asset(status="uploading"))
    world.mp.setattr(asset_store, "create", create)
    res = world.client.post(f"{BASE}/assets/presign", json={"filename": "latte.mov", "content_type": "video/quicktime",
                                                            "size": 1234})
    assert res.status_code == 201
    assert res.json() == {"asset_id": str(ASSET), "upload_url": "https://bucket.s3.example.test/",
                          "fields": {"key": "k"}, "max_bytes": asset_store.MAX_VIDEO_BYTES}
    assert create.await_args.kwargs["path"] == "s3://b/k" and create.await_args.kwargs["size"] == 1234


def test_presign_refusals(world):
    body = {"filename": "a.mp4", "content_type": "video/mp4", "size": 10}
    world.mp.setattr(social_routes, "resolve_entitlements", AsyncMock(return_value=ent("social")))
    assert world.client.post(f"{BASE}/assets/presign", json=body).status_code == 402
    world.mp.setattr(social_routes, "resolve_entitlements", AsyncMock(return_value=ent("social", "social_video")))
    world.mp.setattr(asset_store, "presign_upload", Mock(side_effect=asset_store.AssetStorageUnavailable("no S3")))
    assert world.client.post(f"{BASE}/assets/presign", json=body).status_code == 503
    world.mp.setattr(asset_store, "presign_upload", Mock(side_effect=ValueError("Videos can be up to 200 MB")))
    res = world.client.post(f"{BASE}/assets/presign", json=body)
    assert res.status_code == 400 and "200 MB" in res.json()["detail"]
    assert world.client.post(f"{BASE}/assets/presign", json={**body, "content_type": "video/avi"}).status_code == 422


def test_complete_verifies_then_queues_the_cut(world):
    rows = Queue([asset(status="uploading"), asset(status="rendering", frames=[], renders={})])
    world.mp.setattr(asset_store, "get", AsyncMock(side_effect=lambda *a: rows.pop(0)))
    world.mp.setattr(asset_store, "verify_upload", AsyncMock(return_value=None))
    rendering = AsyncMock(return_value=True)
    world.mp.setattr(asset_store, "mark_rendering", rendering)
    delay = Mock()
    world.mp.setattr(media_task.render_cappe_social_video, "delay", delay)
    res = world.client.post(f"{BASE}/assets/{ASSET}/complete")
    assert res.status_code == 200 and res.json()["status"] == "rendering" and "source_path" not in res.json()
    delay.assert_called_once_with(str(ASSET))
    # A broker hiccup doesn't fail the upload: the sweep re-queues it.
    rows.extend([asset(status="uploading"), asset(status="rendering")])
    world.mp.setattr(media_task.render_cappe_social_video, "delay", Mock(side_effect=RuntimeError("broker")))
    assert world.client.post(f"{BASE}/assets/{ASSET}/complete").status_code == 200


def test_complete_refusals(world):
    world.mp.setattr(asset_store, "get", AsyncMock(return_value=None))
    assert world.client.post(f"{BASE}/assets/{ASSET}/complete").status_code == 404
    world.mp.setattr(asset_store, "get", AsyncMock(return_value=asset()))
    assert world.client.post(f"{BASE}/assets/{ASSET}/complete").json()["status"] == "ready"  # already done
    world.mp.setattr(asset_store, "get", AsyncMock(return_value=asset(status="uploading")))
    failed = AsyncMock()
    world.mp.setattr(asset_store, "mark_failed", failed)
    world.mp.setattr(asset_store, "verify_upload", AsyncMock(return_value="That file isn't a video we can read."))
    res = world.client.post(f"{BASE}/assets/{ASSET}/complete")
    assert res.status_code == 400 and failed.await_args.args[2] == "That file isn't a video we can read."
    world.mp.setattr(asset_store, "verify_upload", AsyncMock(side_effect=asset_store.AssetStorageUnavailable("x")))
    assert world.client.post(f"{BASE}/assets/{ASSET}/complete").status_code == 503


def test_get_and_delete_a_video(world):
    world.mp.setattr(asset_store, "get", AsyncMock(return_value=asset()))
    assert world.client.get(f"{BASE}/assets/{ASSET}").json()["frames"][1]["t_ms"] == 3000
    files = AsyncMock()
    world.mp.setattr(asset_store, "delete_files", files)
    world.mp.setattr(asset_store, "delete", AsyncMock(return_value=asset()))
    assert world.client.delete(f"{BASE}/assets/{ASSET}").status_code == 204 and files.await_count == 1
    world.mp.setattr(asset_store, "delete", AsyncMock(return_value=None))
    assert world.client.delete(f"{BASE}/assets/{ASSET}").status_code == 409
    world.mp.setattr(asset_store, "get", AsyncMock(return_value=None))
    assert world.client.delete(f"{BASE}/assets/{ASSET}").status_code == 404
    assert world.client.get(f"{BASE}/assets/{ASSET}").status_code == 404


def _post_view(**over):
    return {"id": POST, "site_id": SITE, "caption": "", "media": [{"kind": "video", "asset_id": str(ASSET),
                                                                    "poster": FRAMES[1]["url"]}],
            "link_url": None, "product_id": None, "status": "rendering", "scheduled_at": NOW, "published_at": None,
            "ai_meta": {}, "created_at": NOW, "updated_at": NOW, "targets": [], **over}


def test_create_a_video_post_names_the_asset(world):
    world.mp.setattr(conn_store, "list_connections", AsyncMock(return_value=[
        {"id": CONN, "platform": "instagram"}]))
    world.mp.setattr(asset_store, "load_many", AsyncMock(return_value={str(ASSET): asset(status="rendering")}))
    create = AsyncMock(return_value={"id": POST})
    world.mp.setattr(post_store, "create_post", create)
    world.mp.setattr(post_store, "set_targets", AsyncMock())
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=_post_view()))
    res = world.client.post(f"{BASE}/posts", json={
        "caption": "", "media": [{"kind": "video", "asset_id": str(ASSET), "url": "https://x.example.test/ignored"}],
        "connection_ids": [str(CONN)], "scheduled_at": SOON_LOCAL.isoformat()})
    assert res.status_code == 201 and res.json()["media"][0]["poster"] == FRAMES[1]["url"]
    kwargs = create.await_args.kwargs
    assert kwargs["media"] == [{"kind": "video", "asset_id": str(ASSET), "alt": None}]
    # A time without a zone is the store's wall clock (Los Angeles here).
    assert kwargs["scheduled_at"] == SOON_LOCAL.replace(tzinfo=LA).astimezone(timezone.utc)


@pytest.mark.parametrize("found,features,code,detail", [
    ({}, ("social", "social_video"), 404, "Video not found"),
    ({str(ASSET): asset(site_id=uuid4())}, ("social", "social_video"), 404, "Video not found"),
    ({str(ASSET): asset(status="failed", error="Too short")}, ("social", "social_video"), 422, "Too short"),
    ({str(ASSET): asset(status="failed", error=None)}, ("social", "social_video"), 422, "couldn't be prepared"),
    ({str(ASSET): asset(status="uploading")}, ("social", "social_video"), 422, "finished uploading"),
    ({str(ASSET): asset()}, ("social",), 402, "Video posts"),
])
def test_create_refuses_a_video_it_cant_use(world, found, features, code, detail):
    world.mp.setattr(social_routes, "resolve_entitlements", AsyncMock(return_value=ent(*features)))
    world.mp.setattr(asset_store, "load_many", AsyncMock(return_value=found))
    res = world.client.post(f"{BASE}/posts", json={"media": [{"kind": "video", "asset_id": str(ASSET)}]})
    assert res.status_code == code and detail in res.json()["detail"]


def test_edit_a_rendering_post_and_settings_say_video(world):
    world.mp.setattr(asset_store, "load_many", AsyncMock(return_value={str(ASSET): asset()}))
    target = {"id": uuid4(), "connection_id": CONN, "platform": "instagram", "status": "pending", "attempts": 0,
              "metrics": {}, "phase": None}
    world.mp.setattr(post_store, "get_post", AsyncMock(return_value=_post_view(targets=[target])))
    update = AsyncMock()
    world.mp.setattr(post_store, "update_post", update)
    world.mp.setattr(post_store, "set_schedule", AsyncMock(return_value=True))
    world.mp.setattr(post_store, "validate_for_targets", Mock(return_value=None))
    res = world.client.patch(f"{BASE}/posts/{POST}", json={
        "media": [{"kind": "video", "asset_id": str(ASSET)}], "scheduled_at": SOON_LOCAL.isoformat()})
    assert res.status_code == 200
    assert update.await_args.args[3]["media"] == [{"kind": "video", "asset_id": str(ASSET), "alt": None}]
    world.mp.setattr(inbox_store, "get_settings", AsyncMock(return_value=dict(inbox_store.SETTINGS_DEFAULTS)))
    world.mp.setattr(social_routes.social_ai, "available", AsyncMock(return_value=True))
    assert world.client.get(f"{BASE}/settings").json()["video_available"] is True
    world.mp.setattr(post_store, "list_posts", AsyncMock(return_value=[_post_view()]))
    assert world.client.get(f"{BASE}/posts?status=rendering").status_code == 200


def test_check_schedule_reads_naive_times_in_the_site_zone():
    la = social_routes.site_zone({"timezone": "America/Los_Angeles"})
    assert la == LA
    assert social_routes.site_zone({"timezone": "Mars/Base"}) == ZoneInfo("UTC")
    assert social_routes.site_zone(None) == ZoneInfo("UTC")
    when = social_routes.check_schedule(SOON_LOCAL, la)
    assert when == SOON_LOCAL.replace(tzinfo=LA).astimezone(timezone.utc) and when.tzinfo == timezone.utc
    aware = (NOW + timedelta(days=3)).replace(tzinfo=timezone.utc)
    assert social_routes.check_schedule(aware, la) == aware
    with pytest.raises(HTTPException):
        social_routes.check_schedule(datetime(2000, 1, 1), la)


def test_media_item_needs_a_source():
    assert CappeSocialMediaItem(kind="video", asset_id=ASSET).url is None
    with pytest.raises(ValueError):
        CappeSocialMediaItem(kind="video")
    with pytest.raises(ValueError):
        CappeSocialMediaItem(kind="image")


# ── worker: the cut ─────────────────────────────────────────────────────────

class Recorder:
    """Stands in for the asset/post stores the render task drives."""

    def __init__(self, monkeypatch, row, released=None):
        self.calls: list[tuple] = []
        self.conn = TxConn()
        monkeypatch.setattr(media_task, "get_db_connection", AsyncMock(return_value=self.conn))
        monkeypatch.setattr(asset_store, "get_by_id", AsyncMock(return_value=row))
        monkeypatch.setattr(asset_store, "source_read_url", lambda path: "https://signed.test/src")
        for name in ("start_render", "record_facts", "record_frames", "record_render", "mark_ready", "mark_failed"):
            monkeypatch.setattr(asset_store, name, self._rec(name))
        monkeypatch.setattr(asset_store, "upload_frame",
                            AsyncMock(side_effect=lambda path, aid, i: f"https://cdn.example.test/f{i}.jpg"))
        monkeypatch.setattr(asset_store, "upload_render",
                            AsyncMock(side_effect=lambda path, aid, name: {"url": f"https://cdn.example.test/{name}.mp4",
                                                                          "bytes": 9}))
        monkeypatch.setattr(post_store, "release_rendered", AsyncMock(return_value=released or []))
        monkeypatch.setattr(post_store, "fail_rendering", AsyncMock(return_value=[POST]))
        self.publish = Mock()
        monkeypatch.setattr(media_task, "_publish", self.publish)

    def _rec(self, name):
        async def record(*args):
            self.calls.append((name, *args[1:]))
        return record

    def names(self):
        return [c[0] for c in self.calls]


def _fake_render(monkeypatch, facts_value, fail_on=None):
    async def probe(source):
        if fail_on == "probe":
            raise render.RenderError("Videos need to be at least 3 seconds long.", permanent=True)
        return facts_value

    async def frame(source, at_ms, work, index):
        path = Path(work) / f"f{index}.jpg"
        path.write_bytes(b"\xff\xd8")
        return path

    async def encode(source, spec, f, work):
        if fail_on == "encode":
            raise render.RenderError("We couldn't read that video.")
        path = Path(work) / f"{spec.name}.mp4"
        path.write_bytes(b"mp4")
        return path

    monkeypatch.setattr(render, "probe", probe)
    monkeypatch.setattr(render, "extract_frame", frame)
    monkeypatch.setattr(render, "encode", encode)


@pytest.mark.asyncio
async def test_render_cuts_frames_and_each_spec_then_releases_due_posts(monkeypatch):
    rec = Recorder(monkeypatch, asset(status="rendering", frames=[], renders={}),
                   released=[{"id": POST, "scheduled_at": NOW - timedelta(minutes=1)},
                             {"id": uuid4(), "scheduled_at": NOW + timedelta(days=1)}])
    _fake_render(monkeypatch, facts(width=1920, height=1080, duration_ms=200_000))
    out = await media_task.render_one(str(ASSET))
    assert out == {"ready": True, "posts_released": 2, "posts_due": 1}
    assert rec.names() == ["start_render", "record_facts", "record_frames", "record_render", "record_render",
                           "mark_ready"]
    frames = [c for c in rec.calls if c[0] == "record_frames"][0][2]
    assert [f["t_ms"] for f in frames] == render.frame_points_ms(facts(duration_ms=200_000))
    vertical = [c for c in rec.calls if c[0] == "record_render"][0]
    assert vertical[2:4] == ("vertical", {"url": "https://cdn.example.test/vertical.mp4", "bytes": 9, "width": 1080,
                                          "height": 1920, "duration_ms": render.MAX_SECONDS * 1000})
    rec.publish.assert_called_once_with([POST])
    assert rec.conn.closed


@pytest.mark.asyncio
async def test_render_resumes_and_skips_what_is_done(monkeypatch):
    rec = Recorder(monkeypatch, asset(status="rendering"))
    _fake_render(monkeypatch, facts())
    await media_task.render_one(str(ASSET))
    assert rec.names() == ["start_render", "record_facts", "mark_ready"]
    Recorder(monkeypatch, asset(status="ready"))
    assert await media_task.render_one(str(ASSET)) == {"skipped": True, "reason": "ready"}
    Recorder(monkeypatch, None)
    assert await media_task.render_one(str(ASSET)) == {"skipped": True, "reason": "missing"}


@pytest.mark.asyncio
async def test_render_fails_the_clip_and_its_posts_for_an_unusable_file(monkeypatch):
    rec = Recorder(monkeypatch, asset(status="rendering", frames=[], renders={}))
    _fake_render(monkeypatch, facts(), fail_on="probe")
    out = await media_task.render_one(str(ASSET))
    assert out["failed"] and out["posts_failed"] == 1 and "3 seconds" in out["error"]
    assert rec.calls[-1][0] == "mark_failed"
    rec = Recorder(monkeypatch, asset(status="rendering"))
    monkeypatch.setattr(asset_store, "source_read_url",
                        Mock(side_effect=asset_store.AssetStorageUnavailable("Couldn't read the uploaded video.")))
    assert (await media_task.render_one(str(ASSET)))["error"] == "Couldn't read the uploaded video."


@pytest.mark.asyncio
async def test_render_raises_a_passing_failure_for_a_retry(monkeypatch):
    Recorder(monkeypatch, asset(status="rendering", renders={}))
    _fake_render(monkeypatch, facts(), fail_on="encode")
    with pytest.raises(render.RenderError):
        await media_task.render_one(str(ASSET))


def test_render_task_retries_once_then_fails_with_a_reason(monkeypatch):
    async def ok(asset_id):
        return {"ready": True}

    monkeypatch.setattr(media_task, "render_one", ok)
    assert media_task.render_cappe_social_video(str(ASSET)) == {"status": "success", "ready": True}

    async def flaky(asset_id):
        raise render.RenderError("We couldn't read that video.")

    monkeypatch.setattr(media_task, "render_one", flaky)
    with pytest.raises(render.RenderError):
        media_task.render_cappe_social_video(str(ASSET))  # first failure: retried
    failed = AsyncMock()
    monkeypatch.setattr(media_task, "fail_asset", failed)
    out = media_task.render_cappe_social_video.apply(args=[str(ASSET)], retries=1).get()
    assert out == {"status": "failed", "error": "We couldn't read that video."}

    async def crash(asset_id):
        raise OSError("disk full")

    monkeypatch.setattr(media_task, "render_one", crash)
    out = media_task.render_cappe_social_video.apply(args=[str(ASSET)], retries=1).get()
    assert out["error"] == media_task._GENERIC_FAILURE

    async def slow(asset_id):
        raise media_task.SoftTimeLimitExceeded()

    monkeypatch.setattr(media_task, "render_one", slow)
    with pytest.raises(media_task.SoftTimeLimitExceeded):
        media_task.render_cappe_social_video(str(ASSET))  # out of time once: retried (it resumes)
    out = media_task.render_cappe_social_video.apply(args=[str(ASSET)], retries=1).get()
    assert "too long" in out["error"]


@pytest.mark.asyncio
async def test_fail_asset_and_publish_dispatch(monkeypatch):
    conn = TxConn()
    monkeypatch.setattr(media_task, "get_db_connection", AsyncMock(return_value=conn))
    failed = AsyncMock()
    monkeypatch.setattr(asset_store, "mark_failed", failed)
    monkeypatch.setattr(post_store, "fail_rendering", AsyncMock(return_value=[]))
    await media_task.fail_asset(str(ASSET), "nope")
    assert failed.await_args.args[1:] == (ASSET, "nope") and conn.closed
    from app.workers.tasks import cappe_social_publisher as publisher

    delay = Mock()
    monkeypatch.setattr(publisher.run_cappe_social_publish_post, "delay", delay)
    media_task._publish([POST])
    delay.assert_called_once_with(str(POST))
    media_task._publish([])
    monkeypatch.setattr(publisher.run_cappe_social_publish_post, "delay", Mock(side_effect=RuntimeError("broker")))
    media_task._publish([POST])  # logged; the minute sweep publishes it


# ── worker: the sweep ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sweep_recovers_renders_targets_and_removes_expired_files(monkeypatch):
    stale = asset(id=uuid4(), status="rendering", render_attempts=1)
    hopeless = asset(id=uuid4(), status="rendering", render_attempts=2)
    monkeypatch.setattr(asset_store, "stuck_renders", AsyncMock(return_value=[stale, hopeless]))
    touch = AsyncMock()
    monkeypatch.setattr(asset_store, "touch_render", touch)
    monkeypatch.setattr(asset_store, "mark_failed", AsyncMock())
    monkeypatch.setattr(post_store, "fail_rendering", AsyncMock(return_value=[POST]))
    delay = Mock(side_effect=[None])
    monkeypatch.setattr(media_task.render_cappe_social_video, "delay", delay)
    monkeypatch.setattr(asset_store, "take_abandoned_uploads", AsyncMock(return_value=[asset(status="uploading")]))
    files = AsyncMock()
    monkeypatch.setattr(asset_store, "delete_files", files)
    monkeypatch.setattr(post_store, "recover_stale_claims", AsyncMock(return_value=[POST]))
    rollup = AsyncMock()
    monkeypatch.setattr(post_store, "rollup_post", rollup)
    monkeypatch.setattr(asset_store, "expired", AsyncMock(return_value=[asset()]))
    deleted = AsyncMock()
    monkeypatch.setattr(asset_store, "mark_deleted", deleted)
    monkeypatch.setattr(export_store, "stuck", AsyncMock(return_value=[]))
    monkeypatch.setattr(export_store, "expired", AsyncMock(return_value=[]))
    due, later = uuid4(), uuid4()
    monkeypatch.setattr(post_store, "settle_renders", AsyncMock(return_value={
        "released": [{"id": due, "scheduled_at": NOW - timedelta(minutes=1)},
                     {"id": later, "scheduled_at": NOW + timedelta(days=1)}], "failed": [POST]}))
    published = Mock()
    monkeypatch.setattr(media_task, "_publish", published)
    out = await media_task.sweep(TxConn(), 50)
    assert out == {"renders_requeued": 1, "renders_failed": 1, "uploads_cleared": 1, "targets_recovered": 1,
                   "expired": 1, "exports_requeued": 0, "exports_failed": 0, "exports_expired": 0,
                   "posts_released": 2, "posts_failed": 1}
    published.assert_called_once_with([due])
    assert touch.await_args.args[1] == stale["id"] and delay.call_args.args == (str(stale["id"]),)
    assert files.await_count == 2 and deleted.await_args.args[1] == ASSET and rollup.await_args.args[1] == POST
    # A broker outage leaves the render for the next sweep.
    monkeypatch.setattr(asset_store, "stuck_renders", AsyncMock(return_value=[stale]))
    monkeypatch.setattr(media_task.render_cappe_social_video, "delay", Mock(side_effect=RuntimeError("broker")))
    assert (await media_task.sweep(TxConn(), 50))["renders_requeued"] == 0


@pytest.mark.asyncio
async def test_sweep_chain_guard(monkeypatch):
    conn = TxConn(fetchval={"UPDATE scheduler_settings SET last_run_at": Queue([True, None])})
    monkeypatch.setattr(media_task, "get_db_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(media_task, "scheduler_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(media_task, "scheduler_settings_row", AsyncMock(return_value={"max_per_cycle": 9000}))
    sweep = AsyncMock(return_value={"expired": 0})
    monkeypatch.setattr(media_task, "sweep", sweep)
    assert await media_task._run_sweep() == {"expired": 0, "reschedule": True}
    assert sweep.await_args.args[1] == 500 and conn.closed
    assert (await media_task._run_sweep())["reason"] == "another_chain"
    monkeypatch.setattr(media_task, "scheduler_enabled", AsyncMock(return_value=False))
    assert (await media_task._run_sweep())["reason"] == "disabled"


def test_sweep_task_reschedules_and_retries(monkeypatch):
    async def ran():
        return {"reschedule": True}

    monkeypatch.setattr(media_task, "_run_sweep", ran)
    apply_async = Mock()
    monkeypatch.setattr(media_task.run_cappe_social_media_sweep, "apply_async", apply_async)
    assert media_task.run_cappe_social_media_sweep()["status"] == "success"
    apply_async.assert_called_once_with(countdown=media_task.SWEEP_SECONDS)
    monkeypatch.setattr(media_task.run_cappe_social_media_sweep, "apply_async", Mock(side_effect=RuntimeError("x")))
    media_task._reschedule(60)

    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(media_task, "_run_sweep", boom)
    with pytest.raises(RuntimeError):
        media_task.run_cappe_social_media_sweep()


def test_video_migration_and_task_registration():
    from app.workers.celery_app import _SCHEDULED_TASKS, celery_app

    root = Path(__file__).resolve().parents[2]
    migration = (root / "alembic" / "versions" / "cappesocial02_social_video.py").read_text()
    assert 'down_revision = "cappesocial01"' in migration
    assert "jsonb_build_object('social_video', true)" in migration
    assert "'cappe_social_media_sweep'" in migration and "'rendering'" in migration
    assert ("cappe_social_media_sweep", "app.workers.tasks.cappe_social_media", "run_cappe_social_media_sweep") \
        in _SCHEDULED_TASKS
    assert "app.workers.tasks.cappe_social_media" in celery_app.conf.include

