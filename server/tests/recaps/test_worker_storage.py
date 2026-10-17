import asyncio
import hashlib
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.matcha.models.matcha_work.recaps import Asset, Event, Manifest, Scene
from app.matcha.services.matcha_work.recaps import reconcile, render, settings, storage, supervisor
from .test_lifecycle import NOW, RECAP, Conn, row, wire


def key(name="video.mp4"):
    return "espresso-recaps/"+"/".join(str(uuid4()) for _ in range(3))+"/renders/"+str(uuid4())+"/"+str(uuid4())+"/"+name


@pytest.mark.asyncio
async def test_private_upload_download_and_sign_are_streamed_and_verified(tmp_path,monkeypatch):
    path=tmp_path/"media";path.write_bytes(b"fixture")
    calls=[];metadata={}
    def upload(filename,bucket,object_key,**kwargs):
        calls.append((filename,bucket,object_key,kwargs));metadata.update(kwargs["ExtraArgs"]["Metadata"])
    def download(bucket,object_key,filename,**kwargs):
        __import__("pathlib").Path(filename).write_bytes(b"fixture")
    s3=SimpleNamespace(upload_file=upload,download_file=download,
        head_object=lambda **_: {"ContentLength":7,"Metadata":metadata},
        generate_presigned_url=Mock(return_value="https://private.example.com/signed"))
    monkeypatch.setattr(storage,"client",lambda:(s3,"private"))
    asset=await storage.upload(path,key(),"video/mp4")
    assert calls[0][1]=="private" and calls[0][3]["ExtraArgs"]["ServerSideEncryption"]=="AES256"
    assert asset.sha256==hashlib.sha256(b"fixture").hexdigest()
    await storage.download(asset,tmp_path/"download")
    assert (tmp_path/"download").read_bytes()==b"fixture"
    assert storage.signed(asset).startswith("https://private")
    assert s3.generate_presigned_url.call_args.kwargs["ExpiresIn"]==300
    with pytest.raises(ValueError): await storage.upload(path,key(),"video/mp4",limit=1)
    s3.head_object=lambda **_: {"ContentLength":8,"Metadata":metadata}
    with pytest.raises(ValueError): await storage.download(asset,tmp_path/"bad")


@pytest.mark.asyncio
async def test_cleanup_deletes_versions_and_rejects_foreign_prefixes(monkeypatch):
    prefix=key().rsplit("/",1)[0]+"/"
    deleted=[]
    s3=SimpleNamespace(list_object_versions=lambda **_: {"Versions":[{"Key":prefix+"video.mp4","VersionId":"old"}],"DeleteMarkers":[]},
        delete_objects=lambda **kwargs: deleted.append(kwargs) or {}, list_objects_v2=lambda **_: {})
    monkeypatch.setattr(storage,"client",lambda:(s3,"private"))
    assert not await storage.cleanup("private",prefix)
    assert deleted[0]["Delete"]["Objects"][0]["VersionId"]=="old"
    s3.list_object_versions=lambda **_: {}
    assert await storage.cleanup("private",prefix)
    with pytest.raises(ValueError): await storage.cleanup("public",prefix)
    with pytest.raises(ValueError): await storage.cleanup("private","../../")


@pytest.mark.asyncio
async def test_media_claim_and_publish_are_token_fenced(tmp_path,monkeypatch):
    manifest=Manifest(scenes=[Scene(event=Event(title="Result",kind="result",occurred_at=NOW),seconds=4)])
    conn=Conn();wire(monkeypatch,reconcile,conn)
    conn.fetchrow.return_value=row(state="rendering",manifest=manifest.model_dump(mode="json"),manifest_sha256=manifest.digest(),render_attempts=1)
    conn.fetchval.side_effect=[True,True]
    monkeypatch.setattr(settings,"available",lambda _:True)
    monkeypatch.setattr(reconcile,"get_settings",lambda:SimpleNamespace(s3_private_bucket="private"))
    async def render_fixture(_manifest,directory):
        video=directory/"video.mp4";video.write_bytes(b"video")
        poster=directory/"card00.png";poster.write_bytes(b"poster")
        return {"video_path":video,"poster_path":poster,"duration_ms":4000,"chapters":[]}
    monkeypatch.setattr(render,"render",render_fixture)
    async def upload(path,object_key,mime,**_):
        return Asset(key=object_key,sha256="a"*64,bytes=path.stat().st_size,mime=mime)
    monkeypatch.setattr(storage,"upload",upload)
    await reconcile.render_job(RECAP)
    claim=conn.fetchrow.await_args.args[0]
    publish=conn.fetchval.await_args.args[0]
    assert "render_attempts<3" in claim and "owner_user_id" in claim
    assert "render_token=$2" in publish and "p.enabled" in publish and "state='rendering'" in publish


@pytest.mark.asyncio
@pytest.mark.parametrize("error,attempt,manual,state",[(RuntimeError("store"),1,None,"queued"),(RuntimeError("store"),3,None,"failed"),(ValueError("invalid"),1,None,"failed"),(RuntimeError("store"),2,uuid4(),"failed")])
async def test_render_failure_has_its_own_retry_budget(monkeypatch,error,attempt,manual,state):
    manifest=Manifest(scenes=[Scene(event=Event(title="Result",kind="result",occurred_at=NOW),seconds=4)])
    conn=Conn();wire(monkeypatch,reconcile,conn)
    conn.fetchrow.return_value=row(state="rendering",manifest=manifest.model_dump(mode="json"),manifest_sha256=manifest.digest(),render_attempts=attempt,manual_retry_request_id=manual)
    conn.fetchval.return_value=True
    monkeypatch.setattr(settings,"available",lambda _:True)
    monkeypatch.setattr(reconcile,"get_settings",lambda:SimpleNamespace(s3_private_bucket="private"))
    monkeypatch.setattr(render,"render",AsyncMock(side_effect=error))
    await reconcile.render_job(RECAP)
    update=next(call for call in conn.execute.await_args_list if "next_attempt_at" in call.args[0])
    assert update.args[3]==state and "render_token=$2" in update.args[0]


@pytest.mark.asyncio
async def test_stale_or_opted_out_render_does_no_media_work(monkeypatch):
    conn=Conn();wire(monkeypatch,reconcile,conn);conn.fetchrow.return_value=None
    draw=AsyncMock();monkeypatch.setattr(render,"render",draw)
    await reconcile.render_job(RECAP)
    draw.assert_not_awaited()
    conn.fetchrow.return_value=row(state="rendering");conn.fetchval.return_value=False
    await reconcile.render_job(RECAP)
    draw.assert_not_awaited()
    assert "state='skipped'" in conn.execute.await_args.args[0]


def test_process_watchdog_is_independent_of_async_executor(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(supervisor.sys,"platform","linux")
    monkeypatch.setattr(supervisor.ctypes,"CDLL",lambda *_,**__:SimpleNamespace(prctl=lambda *args:0))
    process=SimpleNamespace(wait=Mock(return_value=0))
    start=Mock(return_value=process);monkeypatch.setattr(supervisor.subprocess,"Popen",start)
    def child_scratch(*args, **kwargs):
        nested = Path(kwargs["env"]["TMPDIR"]) / "chromium-profile"
        nested.mkdir(); (nested / "unfinished-download").write_bytes(b"partial")
        return process
    start.side_effect = child_scratch
    stop=Mock();monkeypatch.setattr(supervisor,"stop_owned_children",stop)
    supervisor.run("render",uuid4(),seconds=240)
    assert start.call_args.kwargs["start_new_session"] is True
    assert not Path(start.call_args.kwargs["env"]["TMPDIR"]).exists()
    process.wait.assert_called_once_with(timeout=240)
    stop.assert_called_once()
    process.wait.side_effect=subprocess.TimeoutExpired("media",240)
    with pytest.raises(subprocess.TimeoutExpired):supervisor.run("render",uuid4(),seconds=240)
    assert stop.call_count==2
    assert not Path(start.call_args.kwargs["env"]["TMPDIR"]).exists()


def test_watchdog_does_not_accept_arbitrary_operations(monkeypatch):
    monkeypatch.setattr(supervisor.sys,"platform","linux")
    with pytest.raises(ValueError):supervisor.run("shell",uuid4(),seconds=1)
