"""Cappe social — exports: a dropped video cut for Instagram, TikTok and
YouTube to download, with the spoken words burned in when asked.

Pure pieces (presets, captions, the step order) are pinned directly; the
Gemini call is a fake client; ffmpeg runs for real only where the build has
libass (Debian's does, Homebrew's doesn't), so the caption e2e test is
skipped on a Mac. Storage is the video tests' fake S3, the database
`QueryConn`.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_social_exports.py -q
"""
import asyncio
import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from celery.exceptions import SoftTimeLimitExceeded  # noqa: E402
from google.genai import types as genai_types  # noqa: E402

from app.cappe.dependencies import require_cappe_account  # noqa: E402
from app.cappe.routes import social_exports as export_routes  # noqa: E402
from app.cappe.services.social import assets as asset_store  # noqa: E402
from app.cappe.services.social import exports as export_store  # noqa: E402
from app.cappe.services.social import presets, render, subtitles, transcribe  # noqa: E402
from app.workers.tasks import cappe_social_media as media_task  # noqa: E402
from tests._helpers.routes import QueryConn, route_client  # noqa: E402
from tests.cappe.test_cappe_social_video import (  # noqa: E402
    ACCOUNT, ASSET, NOW, SITE, SITE_ROW, VERTICAL_URL, FakeS3, TxConn, asset, ent, facts, storage,
)

EXPORT = uuid4()
V_KEY = "1080x1920-180"
V_CAP = "1080x1920-180-captions"
L_CAP = "1920x1080-180-captions"
WORDS = [subtitles.Word(t, s, e) for t, s, e in (
    ("Fresh", 100, 400), ("oat", 400, 600), ("lattes", 600, 1100), ("are", 1100, 1200), ("back", 1200, 1500),
    ("this", 1500, 1600), ("week.", 1600, 2200), ("Come", 2300, 2500), ("by", 2500, 2600))]
TRANSCRIPT = {"words": subtitles.compact(WORDS), "text": "Fresh oat lattes are back this week. Come by",
              "language": "en"}
FACTS = {"duration_ms": 6000, "width": 1080, "height": 1920, "has_audio": True}


def export(**over):
    return {"id": EXPORT, "site_id": SITE, "account_id": ACCOUNT.id, "asset_id": ASSET, "status": "working",
            "platforms": ["instagram", "tiktok", "youtube"], "captions": True, "facts": None, "targets": {},
            "outputs": {}, "srt": None, "texts": {}, "warnings": [], "step": None, "provenance": {}, "error": None,
            "attempts": 1, "started_at": NOW, "expires_at": NOW + timedelta(days=30), "created_at": NOW,
            "updated_at": NOW, **over}


def made(key, **over):
    return {"url": f"https://cdn.example.test/cappe/social/renders/{ASSET}/{key}.mp4",
            "key": f"cappe/social/renders/{ASSET}/{key}.mp4", "width": 1080, "height": 1920, "duration_ms": 6000,
            "bytes": 9, "trimmed": False, "shared": False, **over}


# ── presets ─────────────────────────────────────────────────────────────────

def test_recipe_keys_round_trip_and_junk_is_refused():
    r = presets.Recipe(render.VERTICAL, True)
    assert r.key == V_CAP and r.box is presets.VERTICAL_BOX
    assert presets.Recipe.from_key(V_CAP) == r
    wide = presets.Recipe.from_key("1920x1080-180")
    assert wide.spec is render.LANDSCAPE and not wide.captions and wide.box is presets.LANDSCAPE_BOX
    for junk in ("", "1080x1920", "720x1280-180", "1080x1920-180-subs"):
        with pytest.raises(ValueError):
            presets.Recipe.from_key(junk)


def test_the_three_vertical_apps_share_one_file_and_youtube_goes_wide_for_landscape():
    tall = facts()
    assert presets.targets_for(["instagram", "tiktok", "youtube", "facebook"], tall, captions=False) == {
        "instagram": V_KEY, "tiktok": V_KEY, "youtube": V_KEY}
    wide = facts(width=1920, height=1080)
    assert presets.targets_for(["tiktok", "youtube"], wide, captions=True) == {"tiktok": V_CAP, "youtube": L_CAP}
    assert presets.spec_for("youtube", facts(width=1080, height=1000)) is render.VERTICAL


def test_reusable_render_only_for_an_uncaptioned_cut_the_trim_didnt_touch():
    plain = presets.Recipe(render.VERTICAL, False)
    stored = {"vertical": {"url": VERTICAL_URL, "key": "k/v.mp4", "duration_ms": 6000, "bytes": 5}}
    got = presets.reusable_render(plain, asset(renders=stored))
    assert got == {"url": VERTICAL_URL, "key": "k/v.mp4", "width": 1080, "height": 1920, "duration_ms": 6000,
                   "bytes": 5, "trimmed": False, "shared": True}
    assert presets.reusable_render(presets.Recipe(render.VERTICAL, True), asset(renders=stored)) is None
    assert presets.reusable_render(plain, asset(status="rendering", renders=stored)) is None
    assert presets.reusable_render(plain, asset(duration_ms=91_000, renders=stored)) is None
    assert presets.reusable_render(presets.Recipe(render.LANDSCAPE, False), asset(renders=stored)) is None


def test_download_names_read_well():
    assert presets.download_name("Po Coffee", "Oat Latte!.MOV", "tiktok", ".mp4") == "po-coffee-oat-latte-tiktok.mp4"
    assert presets.download_name(None, None, "captions", ".srt") == "site-captions.srt"
    assert len(presets.download_name("x" * 200, "y" * 200, "youtube", ".mp4")) <= 80 + len("-youtube.mp4")


# ── captions ────────────────────────────────────────────────────────────────

def test_lines_break_on_length_word_count_pauses_and_sentences():
    lines = subtitles.group(WORDS, max_chars=18)
    assert [line.text for line in lines] == ["Fresh oat lattes", "are back this", "week.", "Come by"]
    assert [line.text for line in subtitles.group(WORDS, max_chars=99, max_words=2)][:2] == ["Fresh oat",
                                                                                          "lattes are"]
    paused = [subtitles.Word("one", 0, 200), subtitles.Word("two", 900, 1100)]
    assert len(subtitles.group(paused, max_chars=40)) == 2


def test_a_line_holds_after_its_last_word_but_never_into_the_next():
    lines = subtitles.group(WORDS, max_chars=18)
    assert (lines[0].start_ms, lines[0].end_ms) == (100, 1100)  # cut at the next line's start
    assert lines[-1].end_ms == 2600 + subtitles.HOLD_MS
    short = subtitles.group([subtitles.Word("Hi", 0, 50)], max_chars=10, hold_ms=0)
    assert short[0].end_ms == subtitles.MIN_SHOW_MS


def test_clean_drops_empty_words_and_puts_them_in_order():
    messy = [subtitles.Word("b", 500, 400), subtitles.Word("  ", 0, 10), subtitles.Word("a\tz", 100, 200)]
    assert subtitles.clean(messy) == [subtitles.Word("a z", 100, 200), subtitles.Word("b", 500, 500)]


def test_the_ass_file_lights_each_spoken_word_in_turn():
    doc = subtitles.ass_document(subtitles.group(WORDS[:3], max_chars=18), width=1080, height=1920,
                                 box=presets.VERTICAL_BOX)
    assert "PlayResX: 1080\nPlayResY: 1920" in doc and "WrapStyle: 2" in doc
    assert "Style: Pop,DejaVu Sans,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,140,140,520,1" in doc
    events = [line for line in doc.splitlines() if line.startswith("Dialogue:")]
    assert events == [
        "Dialogue: 0,0:00:00.10,0:00:00.40,Pop,,0,0,0,,{\\c&H0035E6A3&}Fresh{\\r} oat lattes",
        "Dialogue: 0,0:00:00.40,0:00:00.60,Pop,,0,0,0,,Fresh {\\c&H0035E6A3&}oat{\\r} lattes",
        "Dialogue: 0,0:00:00.60,0:00:01.40,Pop,,0,0,0,,Fresh oat {\\c&H0035E6A3&}lattes{\\r}",
    ]
    # A word with no time of its own is skipped rather than shown for 0 s.
    same = subtitles.group([subtitles.Word("a", 0, 0), subtitles.Word("b", 0, 300)], max_chars=10)
    assert len([e for e in subtitles.ass_document(same, width=10, height=10, box=presets.VERTICAL_BOX).splitlines()
                if e.startswith("Dialogue")]) == 1


def test_text_can_never_open_an_override_block():
    assert subtitles.escape_ass("{\\pos(1,1)}hi\\N\x07") == "(/pos(1,1))hi/N "


def test_time_formats():
    assert subtitles.ass_time(3_723_456) == "1:02:03.45" and subtitles.ass_time(-5) == "0:00:00.00"
    assert subtitles.srt_time(3_723_456) == "01:02:03,456"


def test_the_srt_file_is_whole_phrases():
    srt = subtitles.srt_document(subtitles.srt_lines(WORDS))
    assert srt == ("1\n00:00:00,100 --> 00:00:02,300\nFresh oat lattes are back this week.\n\n"
                   "2\n00:00:02,300 --> 00:00:02,900\nCome by\n")
    assert subtitles.srt_document([]) == ""


def test_words_are_kept_compactly_and_junk_is_dropped():
    assert subtitles.expand(subtitles.compact(WORDS)) == WORDS
    assert subtitles.expand([{"t": "ok", "s": "1", "e": 2}, {"t": ""}, {"t": "x", "s": "nope"}, "junk"]) == [
        subtitles.Word("ok", 1, 2)]
    assert subtitles.expand(None) == []


# ── render: captions on the frame ───────────────────────────────────────────

def test_captions_are_drawn_on_the_finished_frame():
    graph = render.video_graph(render.VERTICAL, facts(width=1920, height=1080), subtitles="/tmp/c/captions.ass",
                               fonts_dir="/usr/share/fonts/truetype/dejavu")
    assert graph.endswith("overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,"
                          "ass=filename=/tmp/c/captions.ass:fontsdir=/usr/share/fonts/truetype/dejavu,format=yuv420p[v]")
    plain = render.video_graph(render.VERTICAL, facts(), subtitles="/tmp/c.ass")
    assert plain == "[0:v]scale=1080:1920,setsar=1,fps=30,ass=filename=/tmp/c.ass,format=yuv420p[v]"
    assert "ass=" not in render.video_graph(render.VERTICAL, facts())


@pytest.mark.parametrize("bad", ["", "/tmp/a b.ass", "/tmp/a:b.ass", "/tmp/a,b.ass", "/tmp/a'b.ass", "/tmp/[a].ass"])
def test_a_captions_path_that_needs_escaping_is_refused(bad):
    with pytest.raises(render.RenderError):
        render.filter_path(bad)


def test_export_cuts_have_their_own_length_and_size_cap():
    args = render.encode_args("https://signed.test/src", render.VERTICAL, facts(duration_ms=200_000), "/tmp/o.mp4",
                              max_seconds=180, max_bytes=presets.EXPORT_MAX_BYTES, subtitles="/tmp/c.ass")
    assert args[args.index("-t") + 1] == "180" and args[args.index("-fs") + 1] == str(presets.EXPORT_MAX_BYTES)
    assert "ass=filename=/tmp/c.ass" in args[args.index("-filter_complex") + 1]
    long = facts(duration_ms=200_000)
    good = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
                        {"codec_type": "audio"}], "format": {"duration": "180.02"}}
    render.check_output(good, render.VERTICAL, long, max_seconds=180)
    with pytest.raises(render.RenderError):
        render.check_output(good, render.VERTICAL, long)  # the 90 s posting cut would be wrong here
    assert render.clip_seconds(long, 180) == 180 and long.output_seconds == 90


def test_has_filter_reads_ffmpegs_list(monkeypatch):
    listing = b" T.C ass               V->V       Render ASS subtitles\n ... scale  V->V  Scale\nFilters:\n"
    run = Mock(return_value=SimpleNamespace(stdout=listing))
    monkeypatch.setattr(render.subprocess, "run", run)
    render.has_filter.cache_clear()
    try:
        assert render.has_filter("ass") and render.has_filter("scale") and not render.has_filter("drawtext")
        render.has_filter.cache_clear()
        monkeypatch.setattr(render.subprocess, "run", Mock(side_effect=OSError("no ffmpeg")))
        assert render.has_filter("ass") is False
    finally:
        render.has_filter.cache_clear()


FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


@pytest.mark.skipif(not (FFMPEG and render.has_filter("ass")), reason="ffmpeg with libass is not installed")
@pytest.mark.asyncio
async def test_a_real_clip_gets_its_captions_burned_in(tmp_path):
    source = tmp_path / "landscape.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=640x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)],
                   check=True)
    recipe = presets.Recipe(render.VERTICAL, True)
    ass = tmp_path / "captions.ass"
    ass.write_text(subtitles.ass_document(subtitles.group(WORDS, max_chars=18), width=1080, height=1920,
                                          box=recipe.box))
    f = await render.probe(str(source))
    out = await render.encode(str(source), recipe.spec, f, tmp_path, name=recipe.key, max_seconds=180,
                              max_bytes=presets.EXPORT_MAX_BYTES, subtitles=str(ass))
    assert out.name == f"cut-{V_CAP}.mp4" and out.stat().st_size > 0


# ── transcription ───────────────────────────────────────────────────────────

def test_audio_is_the_first_track_as_16k_mono_flac():
    args = transcribe.audio_args("https://signed.test/src", "/tmp/a.flac", max_seconds=180)
    assert args[args.index("-map") + 1] == "0:a:0" and args[args.index("-t") + 1] == "180"
    assert args[args.index("-ar") + 1] == "16000" and args[args.index("-ac") + 1] == "1" and args[-3:] == [
        "-f", "flac", "/tmp/a.flac"]
    assert "-protocol_whitelist" in args and "-vn" in args


@pytest.mark.parametrize("value,expected", [
    ("1.200s", 1200), ("3s", 3000), ("250ms", 250), (1.5, 1500), (2, 2000), ({"seconds": 1, "nanos": 500_000_000}, 1500),
    (None, None), (True, None), ("soon", None), ({"seconds": "x"}, None), (-1, 0),
])
def test_offsets_in_every_shape(value, expected):
    assert transcribe.offset_ms(value) == expected


def test_words_come_from_sdk_models_and_plain_dicts():
    sdk = genai_types.Transcription(text="Hi there.", words=[
        genai_types.WordInfo(word="Hi", start_offset="0.100s", end_offset="0.300s"),
        genai_types.WordInfo(word="there.", start_offset="0.300s", end_offset="0.200s"),
        genai_types.WordInfo(word="lost", start_offset=None, end_offset="1s")])
    plain = {"words": [{"text": "yo", "startOffset": "2s", "endOffset": "2.5s"}, {"text": " "}]}
    assert transcribe.words_from([sdk, plain]) == [
        subtitles.Word("Hi", 100, 300), subtitles.Word("there.", 300, 300), subtitles.Word("yo", 2000, 2500)]


class FakeModels:
    def __init__(self, response=None, error=None, delay=0.0):
        self.response, self.error, self.delay, self.calls = response, error, delay, []

    async def generate_content(self, **kw):
        self.calls.append(kw)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.response


def _gemini(monkeypatch, models, *, key="k", limited=False):
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    monkeypatch.setattr(transcribe, "get_genai_client", lambda: client)
    monkeypatch.setattr(transcribe, "get_settings", lambda: SimpleNamespace(gemini_api_key=key, use_vertex_ai=False))
    from app.core.services import rate_limiter

    limiter = SimpleNamespace(check_and_record=AsyncMock(
        side_effect=rate_limiter.RateLimitExceeded("full", "hourly", 10, 10) if limited else None))
    monkeypatch.setattr(rate_limiter, "get_rate_limiter", lambda provider="gemini": limiter)
    return limiter


def _response(words, text="Hi there"):
    part = genai_types.Part(text=text, audio_transcription=genai_types.Transcription(
        text=text, language_code="en-US", words=words))
    return genai_types.GenerateContentResponse(candidates=[genai_types.Candidate(
        content=genai_types.Content(role="model", parts=[part]))])


@pytest.mark.asyncio
async def test_transcribe_asks_for_word_timings_and_reads_them(monkeypatch):
    models = FakeModels(_response([genai_types.WordInfo(word="Hi", start_offset="0.1s", end_offset="0.4s")]))
    limiter = _gemini(monkeypatch, models)
    heard = await transcribe.transcribe(b"fLaC")
    assert heard.words == [subtitles.Word("Hi", 100, 400)] and heard.text == "Hi there" and heard.language == "en-US"
    call = models.calls[0]
    assert call["model"] == "gemini-3.5-transcribe"
    assert call["config"].audio_transcription_config.word_timestamp is True
    assert call["contents"][0].inline_data.mime_type == "audio/flac"
    assert limiter.check_and_record.await_args.args == ("cappe_social", "transcribe")


@pytest.mark.asyncio
async def test_transcribe_says_not_now_without_a_key_or_with_a_full_bucket(monkeypatch):
    _gemini(monkeypatch, FakeModels(), key=None)
    with pytest.raises(transcribe.TranscribeUnavailable):
        await transcribe.transcribe(b"x")
    _gemini(monkeypatch, FakeModels(), limited=True)
    with pytest.raises(transcribe.TranscribeUnavailable):
        await transcribe.transcribe(b"x")


@pytest.mark.asyncio
async def test_transcribe_failures_are_errors_not_crashes(monkeypatch):
    _gemini(monkeypatch, FakeModels(error=RuntimeError("500")))
    with pytest.raises(transcribe.TranscribeError):
        await transcribe.transcribe(b"x")
    _gemini(monkeypatch, FakeModels(response=None, delay=0.2))
    monkeypatch.setattr(transcribe, "CALL_TIMEOUT", 0.01)
    with pytest.raises(transcribe.TranscribeError):
        await transcribe.transcribe(b"x")


@pytest.mark.asyncio
async def test_a_broken_limiter_never_blocks_captions(monkeypatch):
    limiter = _gemini(monkeypatch, FakeModels(_response([], text="")))
    limiter.check_and_record.side_effect = RuntimeError("db down")
    heard = await transcribe.transcribe(b"x")
    assert heard.words == [] and heard.text == ""


@pytest.mark.asyncio
async def test_extract_audio_reads_and_bounds_the_sound(monkeypatch, tmp_path):
    async def run(args, *, timeout):
        Path(args[-1]).write_bytes(b"fLaC" * 4)
        return b""
    monkeypatch.setattr(render, "run", run)
    assert await transcribe.extract_audio("https://signed.test/src", tmp_path, max_seconds=180) == b"fLaC" * 4
    assert not (tmp_path / "speech.flac").exists()
    monkeypatch.setattr(transcribe, "MAX_AUDIO_BYTES", 3)
    with pytest.raises(transcribe.TranscribeError):
        await transcribe.extract_audio("https://signed.test/src", tmp_path, max_seconds=180)

    async def silent(args, *, timeout):
        return b""
    monkeypatch.setattr(render, "run", silent)
    with pytest.raises(transcribe.TranscribeError):
        await transcribe.extract_audio("https://signed.test/src", tmp_path, max_seconds=180)

    async def broken(args, *, timeout):
        raise render.RenderError("We couldn't read that video.")
    monkeypatch.setattr(render, "run", broken)
    with pytest.raises(transcribe.TranscribeError):
        await transcribe.extract_audio("https://signed.test/src", tmp_path, max_seconds=180)


# ── the export store ───────────────────────────────────────────────────────

def test_next_step_walks_probe_words_cuts_captions_done():
    a = asset()
    targets = {"instagram": V_CAP, "tiktok": V_CAP, "youtube": L_CAP}
    assert export_store.next_step(export(), a).kind == "probe"
    e = export(facts=FACTS, targets=targets)
    assert export_store.next_step(e, a).kind == "transcribe"
    a = asset(transcript=TRANSCRIPT)
    assert export_store.next_step(e, a) == export_store.Step("encode", V_CAP)
    e["outputs"] = {V_CAP: made(V_CAP)}
    assert export_store.next_step(e, a) == export_store.Step("encode", L_CAP)
    e["outputs"][L_CAP] = {"error": "too long"}
    assert export_store.next_step(e, a).kind == "srt"
    e["srt"] = {"url": "u", "key": "k"}
    assert export_store.next_step(e, a).kind == "done"
    # No words (or no captions asked for): no transcription, no .srt.
    quiet = export(facts=FACTS, targets={"tiktok": V_KEY}, outputs={V_KEY: made(V_KEY)}, captions=False)
    assert export_store.next_step(quiet, asset()).kind == "done"
    silent = export(facts=FACTS, targets={"tiktok": V_CAP}, outputs={V_CAP: made(V_CAP)})
    assert export_store.next_step(silent, asset(transcript={"words": [], "reason": "no_audio"})).kind == "done"
    assert export_store.Step("encode", V_CAP).as_json() == {"kind": "encode", "recipe": V_CAP}


def test_rollup():
    targets = {"tiktok": V_CAP, "youtube": L_CAP}
    assert export_store.rollup(export(targets=targets, outputs={V_CAP: made(V_CAP), L_CAP: made(L_CAP)})) == "ready"
    assert export_store.rollup(export(targets=targets, outputs={V_CAP: made(V_CAP), L_CAP: {"error": "x"}})) == "partial"
    assert export_store.rollup(export(targets=targets, outputs={V_CAP: {"error": "x"}})) == "failed"
    assert export_store.rollup(export()) == "failed"


@pytest.mark.asyncio
async def test_create_keeps_the_video_as_long_as_the_export():
    conn = QueryConn(fetchrow={"INSERT INTO cappe_social_exports": export(status="queued", platforms=["tiktok"],
                                                                         texts='{"tiktok": {"text": "hi"}}')})
    row = await export_store.create(conn, site_id=SITE, account_id=ACCOUNT.id, asset_id=ASSET,
                                    platforms=["youtube", "facebook", "tiktok"], captions=True,
                                    texts={"tiktok": {"text": "hi"}}, provenance={"source": "test"})
    insert = conn.calls[0]
    assert insert[2][3] == ["tiktok", "youtube"]  # known platforms, in a fixed order
    assert row["texts"] == {"tiktok": {"text": "hi"}} and row["platforms"] == ["tiktok"]
    kind, sql, args = conn.calls[1]
    assert kind == "execute" and "GREATEST(expires_at" in sql and args == (ASSET,)


@pytest.mark.asyncio
async def test_store_queries():
    row = export()
    conn = QueryConn(fetchrow={"UPDATE cappe_social_exports SET status = 'working'": row,
                               "SELECT id, site_id": row, "DELETE FROM cappe_social_exports": row},
                     fetch={"FROM cappe_social_exports": [row]})
    assert (await export_store.claim(conn, EXPORT))["id"] == EXPORT
    assert (await export_store.get(conn, SITE, EXPORT))["id"] == EXPORT
    assert (await export_store.get_by_id(conn, EXPORT))["id"] == EXPORT
    assert len(await export_store.list_for_site(conn, SITE)) == 1
    assert len(await export_store.load_many(conn, [EXPORT])) == 1 and await export_store.load_many(conn, []) == []
    assert len(await export_store.stuck(conn, minutes=30, limit=5)) == 1
    assert len(await export_store.expired(conn, limit=5)) == 1
    assert (await export_store.delete(conn, SITE, EXPORT))["id"] == EXPORT
    await export_store.set_step(conn, EXPORT, export_store.Step("encode", V_CAP))
    await export_store.set_step(conn, EXPORT, None)
    await export_store.record_facts(conn, EXPORT, facts(), {"tiktok": V_KEY})
    await export_store.record_output(conn, EXPORT, V_KEY, made(V_KEY))
    await export_store.record_srt(conn, EXPORT, {"url": "u"})
    await export_store.add_warning(conn, EXPORT, "note")
    await export_store.finish(conn, EXPORT, "ready")
    await export_store.requeue(conn, EXPORT)
    await export_store.mark_deleted(conn, EXPORT)
    writes = [c for c in conn.calls if c[0] == "execute"]
    assert writes[0][2][1] == '{"kind": "encode", "recipe": "1080x1920-180-captions"}' and writes[1][2][1] is None
    assert writes[2][2][2] == '{"tiktok": "1080x1920-180"}'
    assert "jsonb_build_object($2::text, $3::jsonb)" in writes[3][1]
    assert "NOT warnings @>" in writes[5][1]
    assert writes[6][2][:3] == (EXPORT, "ready", None)
    claim_sql = conn.calls[0][1]
    assert "attempts = attempts + 1" in claim_sql and conn.calls[0][2][1] == ["queued", "working"]


@pytest.mark.asyncio
async def test_deleting_an_export_leaves_the_videos_own_cut(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(export_store, "get_storage", lambda: storage(s3))
    gone = export(outputs={V_KEY: made(V_KEY, shared=True), L_CAP: made(L_CAP), "x": {"error": "e"},
                           "boom": made("boom")}, srt={"key": "k/captions.srt"})
    await export_store.delete_files(gone)
    assert [k for _, k in s3.deleted] == [made(L_CAP)["key"], "k/captions.srt"]
    await export_store.delete_files(export())  # nothing to remove
    monkeypatch.setattr(export_store, "get_storage", lambda: storage(None, s3_client=None))
    await export_store.delete_files(gone)


def test_public_view_has_a_file_per_platform_and_no_storage_keys():
    e = export(status="partial", facts=FACTS, targets={"instagram": V_CAP, "tiktok": V_CAP, "youtube": L_CAP},
               outputs={V_CAP: made(V_CAP), L_CAP: {"error": "too long"}}, srt={"url": "u", "key": "k"},
               step={"kind": "srt"}, texts={"tiktok": {"text": "hi"}}, warnings=["w"])
    view = export_store.public_view(e, asset())
    assert view["files"]["tiktok"]["url"] == made(V_CAP)["url"] and "key" not in view["files"]["tiktok"]
    assert view["files"]["youtube"] == {"url": None, "width": None, "height": None, "duration_ms": None,
                                        "bytes": None, "trimmed": None, "error": "too long"}
    assert view["progress"] == {"done": 2, "total": 2, "step": "srt"} and view["srt"] is True
    assert view["poster"] and view["filename"] == "latte.mov" and view["original"] is True
    bare = export_store.public_view(export(targets={"tiktok": V_KEY}, outputs={V_KEY: "junk"}), None)
    assert bare["files"] == {"tiktok": None} and bare["original"] is False and bare["poster"] is None
    assert export_store._row(None) is None


# ── worker: one step per run ───────────────────────────────────────────────

class Steps:
    """Stands in for the stores and tools one export step drives."""

    def __init__(self, monkeypatch, row, a=None):
        self.calls: list[tuple] = []
        self.conn = TxConn()
        self.row = row
        monkeypatch.setattr(media_task, "get_db_connection", AsyncMock(return_value=self.conn))
        monkeypatch.setattr(export_store, "claim", AsyncMock(return_value=row))
        monkeypatch.setattr(export_store, "get_by_id", AsyncMock(return_value=row))
        monkeypatch.setattr(asset_store, "get_by_id", AsyncMock(return_value=a if a is not None else asset()))
        monkeypatch.setattr(asset_store, "source_read_url", lambda path: "https://signed.test/src")
        for name in ("set_step", "record_facts", "record_output", "record_srt", "add_warning", "finish", "requeue"):
            monkeypatch.setattr(export_store, name, self._rec(name))
        monkeypatch.setattr(asset_store, "record_transcript", self._rec("record_transcript"))
        monkeypatch.setattr(asset_store, "upload_render", AsyncMock(
            side_effect=lambda path, aid, name: {"url": f"https://cdn.example.test/{name}.mp4", "key": f"k/{name}.mp4",
                                                 "bytes": 9}))
        monkeypatch.setattr(asset_store, "upload_text", AsyncMock(
            side_effect=lambda path, aid, name, ext, ct: {"url": "https://cdn.example.test/c.srt", "key": "k/c.srt",
                                                          "bytes": Path(path).stat().st_size}))
        self.encodes: list[dict] = []

        async def encode(source, spec, f, work, **kw):
            if kw.get("subtitles"):
                self.encodes.append({"ass": Path(kw["subtitles"]).read_text(), **kw})
            else:
                self.encodes.append(kw)
            path = Path(work) / f"cut-{kw['name']}.mp4"
            path.write_bytes(b"mp4")
            return path
        monkeypatch.setattr(render, "encode", encode)
        monkeypatch.setattr(render, "has_filter", lambda name: True)

    def _rec(self, name):
        async def record(*args, **kw):
            self.calls.append((name, *args[1:], *kw.values()))
        return record

    def names(self):
        return [c[0] for c in self.calls]

    def get(self, name):
        return [c[1:] for c in self.calls if c[0] == name]


@pytest.mark.asyncio
async def test_probe_records_what_each_platform_gets(monkeypatch):
    steps = Steps(monkeypatch, export())
    monkeypatch.setattr(render, "probe", AsyncMock(return_value=facts(width=1920, height=1080, duration_ms=200_000)))
    out = await media_task.prepare_step(str(EXPORT))
    assert out == {"step": "probe", "recipe": None, "next": 0}
    assert steps.names() == ["set_step", "record_facts", "add_warning", "set_step", "requeue"]
    _, _, targets = steps.get("record_facts")[0]
    assert targets == {"instagram": V_CAP, "tiktok": V_CAP, "youtube": L_CAP}
    assert steps.get("add_warning")[0][1] == media_task.TRIMMED and steps.conn.closed


@pytest.mark.asyncio
async def test_listening_keeps_the_words_on_the_video(monkeypatch):
    steps = Steps(monkeypatch, export(facts=FACTS, targets={"tiktok": V_CAP}))
    monkeypatch.setattr(transcribe, "extract_audio", AsyncMock(return_value=b"fLaC"))
    monkeypatch.setattr(transcribe, "transcribe", AsyncMock(return_value=transcribe.Transcript(
        words=WORDS, text="Fresh oat", language="en")))
    out = await media_task.prepare_step(str(EXPORT))
    assert out["step"] == "transcribe" and out["next"] == 0
    assert steps.get("record_transcript")[0] == (ASSET, {"words": subtitles.compact(WORDS), "text": "Fresh oat",
                                                         "language": "en"})


@pytest.mark.asyncio
@pytest.mark.parametrize("has_audio,heard,error,attempts,warning,reason,next_run", [
    (False, None, None, 1, media_task.NO_AUDIO, "no_audio", 0),
    (True, transcribe.Transcript(words=[], text="mm"), None, 1, media_task.NO_WORDS, "no_timings", 0),
    (True, None, transcribe.TranscribeError("bad"), 1, media_task.NO_WORDS, "no_timings", 0),
    (True, None, transcribe.TranscribeUnavailable("busy"), 1, None, None, media_task.TRANSCRIBE_RETRY_SECONDS),
    (True, None, transcribe.TranscribeUnavailable("busy"), media_task.TRANSCRIBE_MAX_RUNS,
     media_task.NO_CAPTIONS_NOW, "unavailable", 0),
])
async def test_when_the_words_cant_be_had(monkeypatch, has_audio, heard, error, attempts, warning, reason, next_run):
    steps = Steps(monkeypatch, export(facts={**FACTS, "has_audio": has_audio}, targets={"tiktok": V_CAP},
                                      attempts=attempts))
    monkeypatch.setattr(transcribe, "extract_audio", AsyncMock(return_value=b"fLaC"))
    monkeypatch.setattr(transcribe, "transcribe", AsyncMock(return_value=heard, side_effect=error))
    out = await media_task.prepare_step(str(EXPORT))
    assert out["next"] == next_run
    assert [w[1] for w in steps.get("add_warning")] == ([warning] if warning else [])
    assert [t[1]["reason"] for t in steps.get("record_transcript")] == ([reason] if reason else [])


@pytest.mark.asyncio
async def test_a_captioned_cut_burns_the_words_in(monkeypatch):
    steps = Steps(monkeypatch, export(facts=FACTS, targets={"tiktok": V_CAP}), asset(transcript=TRANSCRIPT))
    monkeypatch.setattr(media_task.os.path, "isdir", lambda path: True)
    out = await media_task.prepare_step(str(EXPORT))
    assert out == {"step": "encode", "recipe": V_CAP, "next": 0}
    cut = steps.encodes[0]
    assert cut["max_seconds"] == 180 and cut["max_bytes"] == presets.EXPORT_MAX_BYTES
    assert cut["fonts_dir"] == presets.FONTS_DIR and "{\\c&H0035E6A3&}Fresh{\\r} oat lattes" in cut["ass"]
    key, output = steps.get("record_output")[0][1:]
    assert key == V_CAP and output == {"url": f"https://cdn.example.test/{V_CAP}.mp4", "key": f"k/{V_CAP}.mp4",
                                       "bytes": 9, "width": 1080, "height": 1920, "duration_ms": 6000,
                                       "trimmed": False, "shared": False}


@pytest.mark.asyncio
async def test_without_words_or_libass_the_cut_has_no_captions(monkeypatch):
    # No words: the video's own posting cut is the same file, so it is reused.
    stored = {"vertical": {"url": VERTICAL_URL, "key": "k/v.mp4", "duration_ms": 6000}}
    steps = Steps(monkeypatch, export(facts=FACTS, targets={"tiktok": V_CAP}),
                  asset(renders=stored, transcript={"words": [], "reason": "no_audio"}))
    await media_task.prepare_step(str(EXPORT))
    assert steps.encodes == [] and steps.get("record_output")[0][2]["shared"] is True
    # Words, but this ffmpeg can't draw them: a plain cut and a note.
    steps = Steps(monkeypatch, export(facts={**FACTS, "duration_ms": 120_000}, targets={"tiktok": V_CAP}),
                  asset(transcript=TRANSCRIPT, duration_ms=120_000))  # past the 90 s posting trim
    monkeypatch.setattr(render, "has_filter", lambda name: False)
    await media_task.prepare_step(str(EXPORT))
    assert "ass" not in steps.encodes[0] and steps.get("add_warning")[0][1] == media_task.NO_LIBASS


@pytest.mark.asyncio
async def test_a_bad_cut_fails_on_its_own(monkeypatch):
    steps = Steps(monkeypatch, export(facts=FACTS, targets={"youtube": L_CAP}), asset(transcript=TRANSCRIPT))
    monkeypatch.setattr(render, "encode", AsyncMock(side_effect=render.RenderError("Too big", permanent=True)))
    out = await media_task.prepare_step(str(EXPORT))
    assert out == {"step": "encode", "error": "Too big", "next": 0}
    assert steps.get("record_output")[0][1:] == (L_CAP, {"error": "Too big"}) and "requeue" in steps.names()
    # A passing failure goes to the task (which retries once).
    Steps(monkeypatch, export(facts=FACTS, targets={"youtube": L_CAP}), asset(transcript=TRANSCRIPT))
    monkeypatch.setattr(render, "encode", AsyncMock(side_effect=render.RenderError("flaky")))
    with pytest.raises(render.RenderError):
        await media_task.prepare_step(str(EXPORT))


@pytest.mark.asyncio
async def test_the_captions_file_is_written_for_youtube(monkeypatch):
    steps = Steps(monkeypatch, export(facts=FACTS, targets={"youtube": V_CAP}, outputs={V_CAP: made(V_CAP)}),
                  asset(transcript=TRANSCRIPT))
    out = await media_task.prepare_step(str(EXPORT))
    assert out["step"] == "srt" and steps.get("record_srt")[0][1]["key"] == "k/c.srt"


@pytest.mark.asyncio
async def test_finishing_and_giving_up(monkeypatch):
    done = export(facts=FACTS, targets={"tiktok": V_KEY}, outputs={V_KEY: made(V_KEY)}, captions=False)
    steps = Steps(monkeypatch, done)
    assert (await media_task.prepare_step(str(EXPORT))) == {"done": "ready", "next": None}
    assert steps.get("finish")[0][1:] == ("ready", None)
    failed = export(facts=FACTS, targets={"tiktok": V_KEY}, outputs={V_KEY: {"error": "x"}}, captions=False)
    steps = Steps(monkeypatch, failed)
    await media_task.prepare_step(str(EXPORT))
    assert steps.get("finish")[0][1:] == ("failed", "None of the files could be made.")
    steps = Steps(monkeypatch, export(attempts=export_store.MAX_RUNS + 1))
    assert (await media_task.prepare_step(str(EXPORT)))["gave_up"]
    steps = Steps(monkeypatch, export(), asset(status="deleted", error=None))
    assert (await media_task.prepare_step(str(EXPORT)))["failed"]
    assert steps.get("finish")[0][1:] == ("failed", "The video is gone.")
    Steps(monkeypatch, None)
    assert (await media_task.prepare_step(str(EXPORT))) == {"skipped": True, "next": None}
    steps = Steps(monkeypatch, export())
    monkeypatch.setattr(asset_store, "source_read_url", Mock(side_effect=asset_store.AssetStorageUnavailable("no S3")))
    assert (await media_task.prepare_step(str(EXPORT)))["failed"] and steps.get("finish")[0][1] == "failed"
    steps = Steps(monkeypatch, export())
    monkeypatch.setattr(render, "probe", AsyncMock(side_effect=render.RenderError("No video", permanent=True)))
    assert (await media_task.prepare_step(str(EXPORT)))["next"] is None
    assert steps.get("finish")[0][1:] == ("failed", "No video")


@pytest.mark.asyncio
@pytest.mark.parametrize("step,expect,go_on", [
    ({"kind": "encode", "recipe": V_CAP}, "record_output", True),
    ({"kind": "transcribe", "recipe": None}, "record_transcript", True),
    ({"kind": "srt", "recipe": None}, "record_srt", True),
    ({"kind": "probe", "recipe": None}, "finish", False),
    (None, "finish", False),
])
async def test_abandoning_a_step_fails_only_that_step(monkeypatch, step, expect, go_on):
    steps = Steps(monkeypatch, export(step=step))
    assert await media_task.abandon_step(str(EXPORT), "Too long") is go_on
    assert expect in steps.names() and (("requeue" in steps.names()) is go_on)
    monkeypatch.setattr(export_store, "get_by_id", AsyncMock(return_value=export(status="ready")))
    assert await media_task.abandon_step(str(EXPORT), "x") is False


def _task(monkeypatch, *, result=None, error=None, retries=0, go_on=True):
    async def step(export_id):
        if error:
            raise error
        return result

    monkeypatch.setattr(media_task, "prepare_step", step)
    monkeypatch.setattr(media_task, "abandon_step", AsyncMock(return_value=go_on))
    queued = Mock()
    monkeypatch.setattr(media_task, "_queue_export", queued)
    task = media_task.prepare_cappe_social_export
    monkeypatch.setattr(task, "retry", Mock(side_effect=RuntimeError("retrying")))
    task.push_request(retries=retries)
    return task, queued


def test_the_task_queues_the_next_step(monkeypatch):
    task, queued = _task(monkeypatch, result={"step": "probe", "next": 0})
    try:
        assert task.run(str(EXPORT))["status"] == "success" and queued.call_args.args == (str(EXPORT), 0)
    finally:
        task.pop_request()


def test_the_task_gives_up_a_step_that_runs_out_of_time_or_fails_twice(monkeypatch):
    task, queued = _task(monkeypatch, error=SoftTimeLimitExceeded())
    try:
        out = task.run(str(EXPORT))
        assert out["status"] == "step_failed" and "too long" in out["error"]
        assert queued.call_args.args == (str(EXPORT), 0)
    finally:
        task.pop_request()
    task, queued = _task(monkeypatch, error=RuntimeError("flaky"), retries=0)
    try:
        with pytest.raises(RuntimeError, match="retrying"):
            task.run(str(EXPORT))
    finally:
        task.pop_request()
    task, queued = _task(monkeypatch, error=render.RenderError("Unreadable"), retries=1, go_on=False)
    try:
        assert task.run(str(EXPORT))["error"] == "Unreadable" and queued.call_args.args == (str(EXPORT), None)
    finally:
        task.pop_request()


def test_queueing_steps(monkeypatch):
    task = media_task.prepare_cappe_social_export
    delay, later = Mock(), Mock()
    monkeypatch.setattr(task, "delay", delay)
    monkeypatch.setattr(task, "apply_async", later)
    media_task._queue_export("e1", None)
    media_task._queue_export("e1", 0)
    media_task._queue_export("e1", 300)
    media_task.queue_exports([EXPORT])
    assert delay.call_count == 2 and later.call_args.kwargs == {"args": ["e1"], "countdown": 300}
    monkeypatch.setattr(task, "delay", Mock(side_effect=RuntimeError("broker")))
    media_task._queue_export("e1", 0)  # logged; the sweep picks it up


@pytest.mark.asyncio
async def test_the_sweep_restarts_stalled_exports_and_clears_expired_ones(monkeypatch):
    for name in ("stuck_renders", "take_abandoned_uploads", "expired"):
        monkeypatch.setattr(asset_store, name, AsyncMock(return_value=[]))
    from app.cappe.services.social import posts as post_store

    monkeypatch.setattr(post_store, "recover_stale_claims", AsyncMock(return_value=[]))
    stalled, hopeless = export(id=uuid4()), export(id=uuid4(), attempts=export_store.MAX_RUNS)
    monkeypatch.setattr(export_store, "stuck", AsyncMock(return_value=[stalled, hopeless]))
    monkeypatch.setattr(export_store, "expired", AsyncMock(return_value=[export(outputs={V_KEY: made(V_KEY)})]))
    finish, requeue, files, deleted = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    for name, fake in (("finish", finish), ("requeue", requeue), ("delete_files", files), ("mark_deleted", deleted)):
        monkeypatch.setattr(export_store, name, fake)
    delay = Mock(side_effect=[None, RuntimeError("broker")])
    monkeypatch.setattr(media_task.prepare_cappe_social_export, "delay", delay)
    out = await media_task.sweep(TxConn(), 50)
    assert (out["exports_requeued"], out["exports_failed"], out["exports_expired"]) == (1, 1, 1)
    assert requeue.await_args.args[1] == stalled["id"] and finish.await_args.args[2] == "failed"
    assert files.await_count == 1 and deleted.await_count == 1
    monkeypatch.setattr(export_store, "stuck", AsyncMock(return_value=[stalled]))
    assert (await media_task.sweep(TxConn(), 50))["exports_requeued"] == 0


def test_the_export_task_is_registered():
    from app.workers.celery_app import celery_app

    assert "app.workers.tasks.cappe_social_media.prepare_cappe_social_export" in celery_app.tasks
    text = Path(__file__).resolve().parents[2].joinpath(
        "alembic/versions/cappesocial03_social_exports.py").read_text()
    assert 'down_revision = "cappesocial02"' in text and "ADD COLUMN IF NOT EXISTS transcript JSONB" in text


# ── assets: what exports add ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assets_hold_their_words_and_stay_while_an_export_needs_them(monkeypatch):
    conn = QueryConn(fetchrow={"DELETE FROM cappe_social_assets": None}, fetch={"FROM cappe_social_assets a": []})
    await asset_store.record_transcript(conn, ASSET, {"words": []})
    await asset_store.delete(conn, SITE, ASSET)
    await asset_store.expired(conn, limit=5)
    sqls = [c[1] for c in conn.calls]
    assert "transcript = $2::jsonb" in sqls[0]
    assert "FROM cappe_social_exports e WHERE e.asset_id = a.id AND e.status <> 'deleted'" in sqls[1]
    assert "FROM cappe_social_exports e" in sqls[2] and "e.status <> 'deleted'" in sqls[2]


@pytest.mark.asyncio
async def test_download_links_save_under_a_readable_name(monkeypatch, tmp_path):
    calls = []
    s3 = FakeS3()
    s3.generate_presigned_url = lambda op, Params, ExpiresIn: calls.append((op, Params, ExpiresIn)) or "https://dl.test/x"
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(s3))
    url = asset_store.download_url("k/v.mp4", filename='po-"tiktok".mp4', content_type="video/mp4")
    assert url == "https://dl.test/x"
    op, params, ttl = calls[0]
    assert op == "get_object" and params["Bucket"] == "public-bucket" and ttl == asset_store.DOWNLOAD_TTL_SECONDS
    assert params["ResponseContentDisposition"] == 'attachment; filename="po-tiktok.mp4"'
    assert asset_store.public_key("https://cdn.example.test/a/b.mp4") == "a/b.mp4"
    assert asset_store.public_key("https://elsewhere.test/a.mp4") is None
    assert asset_store.source_location(asset()) == ("private-bucket", "cappe/social/sources/x.mov")
    srt = tmp_path / "c.srt"
    srt.write_text("1\n")
    stored = await asset_store.upload_text(str(srt), ASSET, "captions", ".srt", "application/x-subrip")
    assert stored["key"].startswith(f"cappe/social/renders/{ASSET}/captions-") and stored["key"].endswith(".srt")
    assert s3.uploads[0][3]["ContentType"] == "application/x-subrip" and stored["bytes"] == 2
    monkeypatch.setattr(asset_store, "get_storage", lambda: storage(s3, cloudfront_domain=None))
    assert asset_store.public_key("https://cdn.example.test/a.mp4") is None


# ── routes ──────────────────────────────────────────────────────────────────

BASE = f"/sites/{SITE}/social/exports"


@pytest.fixture
def world(monkeypatch):
    conn = TxConn(fetchrow={"FROM cappe_sites WHERE id = $1 AND account_id": SITE_ROW})
    w = SimpleNamespace(conn=conn, mp=monkeypatch, depth=0, seen_depth=[])

    class Ctx:
        async def __aenter__(self):
            w.depth += 1
            return conn

        async def __aexit__(self, *exc):
            w.depth -= 1
            return False

    monkeypatch.setattr(export_routes, "get_connection", lambda: Ctx())
    monkeypatch.setattr(export_routes, "resolve_entitlements", AsyncMock(return_value=ent("social", "social_video")))
    monkeypatch.setattr(export_routes, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(asset_store, "get", AsyncMock(return_value=asset()))
    monkeypatch.setattr(asset_store, "get_by_id", AsyncMock(return_value=asset()))
    monkeypatch.setattr(asset_store, "load_many", AsyncMock(return_value={str(ASSET): asset()}))
    w.queued = []
    monkeypatch.setattr(export_routes, "queue", lambda ids: (w.seen_depth.append(w.depth), w.queued.extend(ids)))
    with route_client(export_routes.router, overrides={require_cappe_account: ACCOUNT}) as client:
        w.client = client
        yield w


def test_list_and_get(world):
    row = export(status="ready", facts=FACTS, targets={"tiktok": V_KEY}, outputs={V_KEY: made(V_KEY)})
    world.mp.setattr(export_store, "list_for_site", AsyncMock(return_value=[row]))
    res = world.client.get(BASE)
    assert res.status_code == 200 and res.json()[0]["files"]["tiktok"]["url"] == made(V_KEY)["url"]
    world.mp.setattr(export_store, "get", AsyncMock(return_value=row))
    assert world.client.get(f"{BASE}/{EXPORT}").json()["status"] == "ready"
    world.mp.setattr(export_store, "get", AsyncMock(return_value=None))
    assert world.client.get(f"{BASE}/{EXPORT}").status_code == 404
    world.mp.setattr(export_routes, "resolve_entitlements", AsyncMock(return_value=ent()))
    assert world.client.get(BASE).status_code == 402


def test_create_starts_the_export_once_the_row_is_saved(world):
    create = AsyncMock(return_value=export(status="queued", platforms=["tiktok", "youtube"]))
    world.mp.setattr(export_store, "create", create)
    res = world.client.post(BASE, json={"asset_id": str(ASSET), "platforms": ["tiktok", "youtube"], "captions": True})
    assert res.status_code == 201 and res.json()["platforms"] == ["tiktok", "youtube"]
    kw = create.await_args.kwargs
    assert kw["captions"] is True and kw["platforms"] == ["tiktok", "youtube"] and kw["provenance"] == {
        "source": "exports_tab"}
    assert world.queued == [EXPORT] and world.seen_depth == [0]  # queued after the connection is back


def test_create_refusals(world):
    body = {"asset_id": str(ASSET)}
    world.mp.setattr(asset_store, "get", AsyncMock(return_value=asset(status="failed", error="No video in it")))
    res = world.client.post(BASE, json=body)
    assert res.status_code == 422 and res.json()["detail"] == "No video in it"
    world.mp.setattr(asset_store, "get", AsyncMock(return_value=None))
    assert world.client.post(BASE, json=body).status_code == 422
    assert world.client.post(BASE, json={**body, "platforms": []}).status_code == 422
    assert world.client.post(BASE, json={**body, "platforms": ["facebook"]}).status_code == 422
    world.mp.setattr(export_routes, "resolve_entitlements", AsyncMock(return_value=ent("social")))
    assert world.client.post(BASE, json=body).status_code == 402


def _download(world, row, target, a=None):
    world.mp.setattr(export_store, "get", AsyncMock(return_value=row))
    world.mp.setattr(asset_store, "get_by_id", AsyncMock(return_value=a if a is not None else asset()))
    link = Mock(return_value="https://dl.test/x")
    world.mp.setattr(asset_store, "download_url", link)
    return world.client.get(f"{BASE}/{EXPORT}/download", params={"target": target}), link


def test_downloads_save_each_file_under_a_readable_name(world):
    row = export(status="ready", facts=FACTS, targets={"tiktok": V_CAP, "youtube": V_CAP},
                 outputs={V_CAP: made(V_CAP)}, srt={"url": "u", "key": "k/c.srt"})
    res, link = _download(world, row, "tiktok")
    assert res.status_code == 200 and res.json() == {"url": "https://dl.test/x",
                                                     "filename": "po-coffee-latte-tiktok.mp4", "expires_in": 600}
    assert link.call_args.args == (made(V_CAP)["key"],) and link.call_args.kwargs["content_type"] == "video/mp4"
    res, link = _download(world, row, "captions")
    assert link.call_args.args == ("k/c.srt",) and res.json()["filename"] == "po-coffee-latte-captions.srt"
    res, link = _download(world, row, "original")
    assert link.call_args.kwargs["bucket"] == "private-bucket" and res.json()["filename"].endswith("-original.mov")
    # A shared cut stored before keys were kept is found from its URL.
    old = export(targets={"tiktok": V_KEY}, outputs={V_KEY: {"url": "https://cdn.example.test/a/v.mp4"}})
    world.mp.setattr(asset_store, "get_storage", lambda: storage())
    res, link = _download(world, old, "tiktok")
    assert link.call_args.args == ("a/v.mp4",)


def test_download_refusals(world):
    row = export(targets={"tiktok": V_CAP}, outputs={}, platforms=["tiktok"])
    assert _download(world, row, "tiktok")[0].status_code == 409
    assert _download(world, row, "youtube")[0].status_code == 422
    assert _download(world, row, "captions")[0].status_code == 409
    assert _download(world, row, "original", asset(status="deleted"))[0].status_code == 409
    assert _download(world, row, "facebook")[0].status_code == 422
    world.mp.setattr(export_store, "get", AsyncMock(return_value=None))
    assert world.client.get(f"{BASE}/{EXPORT}/download", params={"target": "tiktok"}).status_code == 404
    done = export(targets={"tiktok": V_CAP}, outputs={V_CAP: made(V_CAP)})
    world.mp.setattr(export_store, "get", AsyncMock(return_value=done))
    world.mp.setattr(asset_store, "download_url", Mock(side_effect=asset_store.AssetStorageUnavailable("no S3")))
    assert world.client.get(f"{BASE}/{EXPORT}/download", params={"target": "tiktok"}).status_code == 503


def test_delete_removes_the_row_then_the_files(world):
    row = export(outputs={V_CAP: made(V_CAP)})
    world.mp.setattr(export_store, "delete", AsyncMock(return_value=row))
    files = AsyncMock()
    world.mp.setattr(export_store, "delete_files", files)
    assert world.client.delete(f"{BASE}/{EXPORT}").status_code == 204 and files.await_args.args == (row,)
    world.mp.setattr(export_store, "delete", AsyncMock(return_value=None))
    assert world.client.delete(f"{BASE}/{EXPORT}").status_code == 404


def test_queue_hands_exports_to_the_worker(monkeypatch):
    queued = Mock()
    monkeypatch.setattr(media_task, "queue_exports", queued)
    export_routes.queue([EXPORT])
    export_routes.queue([])
    assert queued.call_count == 1 and queued.call_args.args == ([EXPORT],)
    monkeypatch.setattr(media_task, "queue_exports", Mock(side_effect=RuntimeError("broker")))
    export_routes.queue([EXPORT])  # logged; the sweep starts it
