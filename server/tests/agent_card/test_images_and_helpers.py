import io
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from app.core.services.openai_responses import cited_urls, web_search_calls
from app.core.services.safe_fetch import FetchedResponse, UnsafeURL
from app.matcha.services.matcha_work.agent_card import images


def _png(size=(2000, 1000)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(out, format="PNG")
    return out.getvalue()


def _fetched(body, ctype="image/png", status=200, truncated=False):
    return FetchedResponse(url="u", final_url="u", status=status, content_type=ctype, body=body, truncated=truncated)


def test_reencode_bounds_size_and_outputs_webp():
    webp = images._reencode(_png())
    with Image.open(io.BytesIO(webp)) as img:
        assert img.format == "WEBP" and max(img.size) == images.MAX_SIDE


def test_reencode_refuses_non_images():
    with pytest.raises(Exception):
        images._reencode(b"<svg onload=alert(1)>")


class _Storage:
    def __init__(self, url="https://cdn.example/agent/x.webp"):
        self.url = url
        self.uploads = []

    async def upload_file(self, data, filename, prefix, content_type):
        self.uploads.append((filename, prefix, content_type))
        return self.url


def _result():
    pick = lambda name, n: {"name": name, "images": [
        {"source_url": f"https://img.example/{name}{i}.png", "page_url": "https://shop.example/p", "alt": ""} for i in range(n)]}
    return {"top_pick": pick("A", 3), "alternatives": [pick("B", 3), pick("C", 3)]}


@pytest.mark.asyncio
async def test_rehost_replaces_urls_caps_per_run_and_scopes_prefix(monkeypatch):
    storage = _Storage()
    monkeypatch.setattr(images, "get_storage", lambda: storage)
    monkeypatch.setattr(images, "fetch_public", AsyncMock(return_value=_fetched(_png((50, 50)))))
    company, project, task = uuid4(), uuid4(), uuid4()
    result = _result()
    warnings = await images.rehost_images(result, company_id=company, project_id=project, task_id=task)
    kept = [len(p["images"]) for p in [result["top_pick"], *result["alternatives"]]]
    assert kept == [3, 3, 0] and sum(kept) == images.MAX_IMAGES_PER_RUN
    assert warnings == []
    first = result["top_pick"]["images"][0]
    assert first == {"url": storage.url, "page_url": "https://shop.example/p", "alt": "A"}
    assert storage.uploads[0] == ("photo.webp", f"matcha-work/{company}/{project}/agent/{task}", "image/webp")


@pytest.mark.asyncio
@pytest.mark.parametrize("fetch", [
    AsyncMock(side_effect=UnsafeURL("private")),
    AsyncMock(return_value=_fetched(b"x", ctype="text/html")),
    AsyncMock(return_value=_fetched(b"x", status=404)),
    AsyncMock(return_value=_fetched(b"x", truncated=True)),
    AsyncMock(return_value=_fetched(b"not really a png")),
])
async def test_unsafe_or_bad_images_are_dropped_never_shown_raw(monkeypatch, fetch):
    monkeypatch.setattr(images, "get_storage", lambda: _Storage())
    monkeypatch.setattr(images, "fetch_public", fetch)
    result = {"top_pick": {"name": "A", "images": [{"source_url": "https://i.example/a", "page_url": "p", "alt": ""}]}, "alternatives": []}
    warnings = await images.rehost_images(result, company_id=uuid4(), project_id=uuid4(), task_id=uuid4())
    assert result["top_pick"]["images"] == [] and len(warnings) == 1


@pytest.mark.asyncio
async def test_local_storage_path_is_not_a_client_url(monkeypatch):
    monkeypatch.setattr(images, "get_storage", lambda: _Storage(url="/uploads/resumes/x.webp"))
    monkeypatch.setattr(images, "fetch_public", AsyncMock(return_value=_fetched(_png((20, 20)))))
    result = {"top_pick": {"name": "A", "images": [{"source_url": "https://i.example/a", "page_url": "p", "alt": ""}]}}
    await images.rehost_images(result, company_id=uuid4(), project_id=uuid4(), task_id=uuid4())
    assert result["top_pick"]["images"] == []


def test_response_helpers_read_search_calls_and_citations():
    output = [
        {"type": "web_search_call", "action": {"query": "q", "sources": [{"url": "https://a.example"}, {"bad": 1}]}},
        {"type": "message", "content": [{"type": "output_text", "text": "t", "annotations": [
            {"type": "url_citation", "url": "https://b.example"}, {"type": "file_citation"}]}]},
        {"type": "function_call", "name": "x"},
        "junk",
    ]
    assert len(web_search_calls(output)) == 1
    assert cited_urls(output) == ["https://a.example", "https://b.example"]
    assert cited_urls([]) == [] and web_search_calls(None) == []


@pytest.mark.asyncio
async def test_luna_client_sends_hosted_tool_controls(monkeypatch):
    from app.matcha.services.huume import luna_client

    captured = {}

    async def fake_post(self, payload, **_kw):
        captured.update(payload)
        return {"id": "r", "output": [{"type": "web_search_call", "action": {}}]}, 0.0

    monkeypatch.setattr(luna_client.LunaSession, "_post", fake_post)
    monkeypatch.setattr(luna_client, "record_openai_response", AsyncMock())
    monkeypatch.setattr(luna_client, "get_settings", lambda: type("S", (), {"openai_api_key": "k"})())
    session = luna_client.LunaSession()
    resp = await session.create_response(model="m", input=[], instructions="i", max_tool_calls=3,
                                         include=["web_search_call.action.sources"])
    assert captured["max_tool_calls"] == 3 and captured["include"] == ["web_search_call.action.sources"]
    assert resp.output_items[0]["type"] == "web_search_call"
    captured.clear()
    await luna_client.LunaSession().create_response(model="m", input=[], instructions="i")
    assert "max_tool_calls" not in captured and "include" not in captured


def _one_image_result():
    return {"top_pick": {"name": "A", "images": [
        {"source_url": "https://img.example/a.png", "page_url": "https://shop.example/p", "alt": ""}]}}


@pytest.mark.asyncio
async def test_an_s3_upload_error_drops_that_photo_not_the_run(monkeypatch):
    class _Boom:
        async def upload_file(self, *a, **k):
            raise RuntimeError("Failed to upload to S3: AccessDenied")

    monkeypatch.setattr(images, "get_storage", lambda: _Boom())
    monkeypatch.setattr(images, "fetch_public", AsyncMock(return_value=_fetched(_png((20, 20)))))
    result = _one_image_result()
    warnings = await images.rehost_images(result, company_id=uuid4(), project_id=uuid4(), task_id=uuid4())
    assert result["top_pick"]["images"] == [] and len(warnings) == 1


@pytest.mark.asyncio
async def test_storage_without_a_public_url_says_so_once_and_stops_uploading(monkeypatch):
    storage = _Storage(url="s3://matcha-bucket/matcha-work/x.webp")
    monkeypatch.setattr(images, "get_storage", lambda: storage)
    monkeypatch.setattr(images, "fetch_public", AsyncMock(return_value=_fetched(_png((20, 20)))))
    result = _result()
    warnings = await images.rehost_images(result, company_id=uuid4(), project_id=uuid4(), task_id=uuid4())
    assert len(storage.uploads) == 1  # not one orphaned object per photo
    assert sum("no public URL" in w for w in warnings) == 1
    for pick in [result["top_pick"], *result["alternatives"]]:
        assert pick["images"] == []


@pytest.mark.asyncio
async def test_a_slow_image_host_cannot_stall_past_the_total_budget(monkeypatch):
    import asyncio
    import time

    async def hang(*_a, **_k):
        await asyncio.sleep(30)

    monkeypatch.setattr(images, "get_storage", lambda: _Storage())
    monkeypatch.setattr(images, "fetch_public", hang)
    monkeypatch.setattr(images, "_PER_IMAGE_SECONDS", 0.05)
    result = _result()
    started = time.monotonic()
    await images.rehost_images(result, company_id=uuid4(), project_id=uuid4(), task_id=uuid4(), total_seconds=2)
    assert time.monotonic() - started < 3
    for pick in [result["top_pick"], *result["alternatives"]]:
        assert all("url" in image for image in pick["images"])  # never a half-rehosted entry


@pytest.mark.asyncio
async def test_out_of_time_still_leaves_every_pick_with_only_rehosted_images(monkeypatch):
    monkeypatch.setattr(images, "get_storage", lambda: _Storage())
    monkeypatch.setattr(images, "fetch_public", AsyncMock(return_value=_fetched(_png((20, 20)))))
    result = _result()
    await images.rehost_images(result, company_id=uuid4(), project_id=uuid4(), task_id=uuid4(), total_seconds=0)
    for pick in [result["top_pick"], *result["alternatives"]]:
        assert pick["images"] == []
