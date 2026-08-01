"""Tests for inbox._process_uploads validation (app.werk.routes.inbox).

Covers the two upload-hardening fixes:
- extension is the primary gate (a spoofed Content-Type no longer lets a
  disallowed extension through the old OR-check)
- the body is read via the shared capped reader instead of a bare
  `await file.read()`, so an oversize body is rejected mid-stream
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# ── Stub google.genai before importing app code ──
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

MOD = "app.werk.routes.inbox"


class _FakeUploadFile:
    """Minimal stand-in for fastapi.UploadFile — matches what
    read_upload_capped needs: chunked `await file.read(n)`."""

    def __init__(self, data: bytes, filename: str, content_type: str, chunk_size: int = 1024 * 1024):
        self.filename = filename
        self.content_type = content_type
        self._data = data
        self._chunk_size = chunk_size
        self._pos = 0

    async def read(self, n: int = -1) -> bytes:
        size = n if n and n > 0 else self._chunk_size
        chunk = self._data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


def _fake_storage():
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value="https://cdn.example.test/inbox/file")
    return storage


@pytest.mark.asyncio
async def test_disallowed_extension_rejected_even_with_spoofed_image_content_type():
    from app.werk.routes.inbox import _process_uploads

    f = _FakeUploadFile(b"MZ\x90\x00fake-exe-bytes", "payload.exe", "image/png")

    with patch(f"{MOD}.get_storage", return_value=_fake_storage()):
        with pytest.raises(HTTPException) as exc:
            await _process_uploads([f])
    assert exc.value.status_code == 400
    assert "payload.exe" in exc.value.detail


@pytest.mark.asyncio
async def test_allowed_extension_with_octet_stream_content_type_passes():
    from app.werk.routes.inbox import _process_uploads

    f = _FakeUploadFile(b"%PDF-1.4 fake pdf bytes", "resume.pdf", "application/octet-stream")

    with patch(f"{MOD}.get_storage", return_value=_fake_storage()):
        out = await _process_uploads([f])
    assert len(out) == 1
    assert out[0]["filename"] == "resume.pdf"


@pytest.mark.asyncio
async def test_oversize_file_rejected_via_capped_read():
    from app.werk.routes.inbox import _process_uploads, MAX_FILE_SIZE

    oversized = b"x" * (MAX_FILE_SIZE + 1024)
    f = _FakeUploadFile(oversized, "big.png", "image/png", chunk_size=64 * 1024)

    with patch(f"{MOD}.get_storage", return_value=_fake_storage()):
        with pytest.raises(HTTPException) as exc:
            await _process_uploads([f])
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_disallowed_content_type_with_allowed_extension_still_rejected():
    """Extension alone isn't a free pass either — content type must be a
    known type or the generic octet-stream fallback."""
    from app.werk.routes.inbox import _process_uploads

    f = _FakeUploadFile(b"whatever", "notes.txt", "application/x-msdownload")

    with patch(f"{MOD}.get_storage", return_value=_fake_storage()):
        with pytest.raises(HTTPException) as exc:
            await _process_uploads([f])
    assert exc.value.status_code == 400
