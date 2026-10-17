import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.matcha.models.matcha_work.recaps import Event, Manifest, Scene
from app.matcha.services.matcha_work.recaps import capture, render, scope, settings
from .test_lifecycle import NOW, RUN, Conn, source, wire


class Context:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return None


@pytest.mark.asyncio
async def test_renderer_uses_only_trusted_bundle_and_fixed_ffmpeg_contract(tmp_path,monkeypatch):
    from playwright import async_api
    bundle=tmp_path/"bundle";bundle.mkdir();(bundle/"index.html").write_text("<html/>")
    monkeypatch.setattr(render,"get_settings",lambda:SimpleNamespace(espresso_recaps_render_bundle=str(bundle)))
    async def screenshot(**kwargs): Path(kwargs["path"]).write_bytes(b"PNG fixture")
    page=SimpleNamespace(goto=AsyncMock(),wait_for_function=AsyncMock(),evaluate=AsyncMock(),screenshot=screenshot)
    context=SimpleNamespace(route=AsyncMock(),new_page=AsyncMock(return_value=page))
    browser=SimpleNamespace(new_context=AsyncMock(return_value=context),close=AsyncMock())
    pw=Context();pw.chromium=SimpleNamespace(launch=AsyncMock(return_value=browser))
    monkeypatch.setattr(async_api,"async_playwright",lambda:pw)
    calls=[]
    async def command(args,**kwargs):
        calls.append(args)
        if args[0]=="ffprobe":
            return json.dumps({"streams":[{"codec_type":"video","codec_name":"h264","width":1920,"height":1080}],"format":{"duration":"4.0"}}).encode()
        if args[-1].endswith(".mp4"): Path(args[-1]).write_bytes(b"MP4 fixture")
        return b""
    monkeypatch.setattr(render,"command",command)
    output=tmp_path/"output";output.mkdir()
    manifest=Manifest(scenes=[Scene(event=Event(title="Safe <script> text",kind="result",occurred_at=NOW),seconds=4)])
    result=await render.render(manifest,output)
    assert result["duration_ms"]==4000 and result["poster_path"].name=="card00.png"
    assert calls[0][calls[0].index("-c:v")+1]=="libx264" and "+faststart" in calls[0]
    assert "-filter_complex_threads" in calls[0] and "-an" in calls[0]
    assert any(args[-2:]==["null","-"] for args in calls)
    guard=context.route.await_args.args[1]
    denied=SimpleNamespace(request=SimpleNamespace(url="https://outside.example.com/secret"),abort=AsyncMock(),fulfill=AsyncMock())
    await guard(denied);denied.abort.assert_awaited_once();denied.fulfill.assert_not_awaited()
    traversal=SimpleNamespace(request=SimpleNamespace(url="http://recap.invalid/%2e%2e/secret"),abort=AsyncMock(),fulfill=AsyncMock())
    await guard(traversal);traversal.abort.assert_awaited_once()
    allowed=SimpleNamespace(request=SimpleNamespace(url="http://recap.invalid/index.html"),abort=AsyncMock(),fulfill=AsyncMock())
    await guard(allowed);allowed.fulfill.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_bundle_fails_without_starting_chromium(tmp_path,monkeypatch):
    monkeypatch.setattr(render,"get_settings",lambda:SimpleNamespace(espresso_recaps_render_bundle=str(tmp_path)))
    manifest=Manifest(scenes=[Scene(event=Event(title="Result",kind="result",occurred_at=NOW),seconds=4)])
    with pytest.raises(RuntimeError,match="render_bundle_missing"):await render.render(manifest,tmp_path)


class CDP:
    def __init__(self): self.callback=None;self.commands=[];self.detached=False
    def on(self,_event,callback):self.callback=callback
    async def send(self,name,params=None):
        self.commands.append((name,params))
        if name=="Page.startScreencast":
            await self.callback({"sessionId":1,"data":base64.b64encode(b"jpeg fixture").decode()})
    async def detach(self):self.detached=True


@pytest.mark.asyncio
async def test_capture_acks_frames_and_stops_without_replaying_browser_actions(monkeypatch):
    conn=Conn();conn.fetchval.return_value=True;wire(monkeypatch,capture,conn)
    monkeypatch.setattr(settings,"enabled",lambda:True);monkeypatch.setattr(settings,"available",lambda _:True)
    monkeypatch.setattr(capture,"get_settings",lambda:SimpleNamespace(espresso_recaps_capture_enabled=True))
    monkeypatch.setattr(scope,"source_for_run",AsyncMock(return_value=source()))
    cdp=CDP();page=SimpleNamespace(context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=cdp)))
    keep=AsyncMock();monkeypatch.setattr(capture,"_store",keep)
    token=scope.current_run.set(RUN)
    try:
        async with capture.window(page) as window:window.accepted=True
    finally:scope.current_run.reset(token)
    keep.assert_awaited_once()
    assert len(keep.await_args.args[1])==1
    assert {name for name,_ in cdp.commands} >= {"Page.startScreencast","Page.screencastFrameAck","Page.stopScreencast"}
    assert cdp.detached


@pytest.mark.asyncio
async def test_refused_navigation_never_attaches_captured_frames(monkeypatch):
    conn=Conn();conn.fetchval.return_value=True;wire(monkeypatch,capture,conn)
    monkeypatch.setattr(settings,"enabled",lambda:True);monkeypatch.setattr(settings,"available",lambda _:True)
    monkeypatch.setattr(capture,"get_settings",lambda:SimpleNamespace(espresso_recaps_capture_enabled=True))
    monkeypatch.setattr(scope,"source_for_run",AsyncMock(return_value=source()))
    cdp=CDP();page=SimpleNamespace(context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=cdp)))
    keep=AsyncMock();monkeypatch.setattr(capture,"_store",keep)
    token=scope.current_run.set(RUN)
    try:
        with pytest.raises(ValueError):
            async with capture.window(page):raise ValueError("off-site redirect")
    finally:scope.current_run.reset(token)
    keep.assert_not_awaited();assert cdp.detached


@pytest.mark.asyncio
async def test_capture_attachment_is_fenced_after_upload(monkeypatch):
    from app.matcha.models.matcha_work.recaps import Asset
    from app.matcha.services.matcha_work.recaps import storage
    from uuid import uuid4
    conn=Conn();wire(monkeypatch,capture,conn)
    event_id=uuid4();monkeypatch.setattr(scope,"event",AsyncMock(return_value=event_id))
    monkeypatch.setattr(scope,"capture_current",AsyncMock(return_value=True))
    monkeypatch.setattr(capture,"get_settings",lambda:SimpleNamespace(s3_private_bucket="private"))
    async def upload(path,key,mime,**_):return Asset(key=key,sha256="a"*64,bytes=path.stat().st_size,mime=mime)
    monkeypatch.setattr(storage,"upload",upload)
    conn.fetchval.return_value=False
    await capture._store(source(),[(0.0,b"jpeg fixture")])
    assert any("cleanup_jobs" in call.args[0] for call in conn.execute.await_args_list)
    assert not any("SET asset=" in call.args[0] for call in conn.execute.await_args_list)
    conn.fetchval.return_value=True
    await capture._store(source(),[(0.0,b"jpeg fixture")])
    assert any("capture_token=$2" in call.args[0] for call in conn.execute.await_args_list if "SET asset=" in call.args[0])
