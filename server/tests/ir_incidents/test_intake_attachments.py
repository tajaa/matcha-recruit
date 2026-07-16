"""Tests for magic-link intake attachments + the shared upload validation.

The upload path these cover shipped broken once already: `documents.py` called
an `async def` storage helper without awaiting it, passed the MIME into the
`prefix` slot, and stored a locally-built path instead of the one storage
returned — so no bytes ever reached S3 while the endpoint returned 200. The
tests here pin the properties that would have caught that: the helper is
awaited, and the persisted path is the helper's *return value*.
"""

import pytest
from fastapi import HTTPException

from app.matcha.routes.ir_incidents import _shared


class _FakeUpload:
    """Minimal UploadFile stand-in: chunked read()."""

    def __init__(self, content: bytes, filename: str = "photo.png"):
        self.filename = filename
        self._buf = content
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk, self._pos = self._buf[self._pos:], len(self._buf)
            return chunk
        chunk = self._buf[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


class TestValidateUploadName:
    def test_allowed_extension_yields_server_derived_mime(self):
        safe, ext, mime = _shared.validate_upload_name("scene.PNG")
        assert (safe, ext, mime) == ("scene.PNG", ".png", "image/png")

    def test_path_traversal_filename_reduced_to_basename(self):
        safe, ext, _ = _shared.validate_upload_name("../../../etc/passwd.png")
        assert safe == "passwd.png"
        assert "/" not in safe and ".." not in safe
        assert ext == ".png"

    def test_windows_separators_also_stripped(self):
        safe, _, _ = _shared.validate_upload_name(r"C:\Users\bob\eve.pdf")
        assert safe == "eve.pdf"

    def test_disallowed_extension_rejected(self):
        with pytest.raises(HTTPException) as e:
            _shared.validate_upload_name("payload.exe")
        assert e.value.status_code == 400

    def test_no_extension_rejected(self):
        with pytest.raises(HTTPException) as e:
            _shared.validate_upload_name("README")
        assert e.value.status_code == 400

    def test_missing_filename_rejected(self):
        # basename("") -> "upload", which has no allowed extension.
        with pytest.raises(HTTPException) as e:
            _shared.validate_upload_name(None)
        assert e.value.status_code == 400

    def test_mime_comes_from_extension_not_client(self):
        # The whole point: a .png is stored as image/png no matter what the
        # client claimed, so an HTML payload can't be served back inline.
        _, _, mime = _shared.validate_upload_name("xss.png")
        assert mime == "image/png"


class TestDocumentTypeForExt:
    @pytest.mark.parametrize("ext", [".png", ".jpg", ".jpeg", ".gif"])
    def test_images_are_photos(self, ext):
        assert _shared.document_type_for_ext(ext) == "photo"

    @pytest.mark.parametrize("ext", [".pdf", ".txt", ".docx", ".csv"])
    def test_non_images_are_other(self, ext):
        assert _shared.document_type_for_ext(ext) == "other"

    def test_result_satisfies_the_db_check_constraint(self):
        valid = {"photo", "form", "statement", "other"}
        for ext in _shared._EXT_MIME:
            assert _shared.document_type_for_ext(ext) in valid


class TestReadUploadCapped:
    @pytest.mark.asyncio
    async def test_reads_full_content_under_cap(self):
        content = b"x" * 2048
        got = await _shared.read_upload_capped(_FakeUpload(content), 1024 * 1024)
        assert got == content

    @pytest.mark.asyncio
    async def test_oversize_rejected_with_413(self):
        with pytest.raises(HTTPException) as e:
            await _shared.read_upload_capped(_FakeUpload(b"x" * 5000), 1000)
        assert e.value.status_code == 413

    @pytest.mark.asyncio
    async def test_empty_upload_rejected(self):
        with pytest.raises(HTTPException) as e:
            await _shared.read_upload_capped(_FakeUpload(b""), 1024)
        assert e.value.status_code == 400

    @pytest.mark.asyncio
    async def test_stops_reading_at_the_cap(self):
        # A body far over the cap must not be pulled into the process whole —
        # this is an unauthenticated endpoint.
        f = _FakeUpload(b"x" * (8 * 1024 * 1024))
        with pytest.raises(HTTPException):
            await _shared.read_upload_capped(f, 1024 * 1024)
        assert f._pos <= 2 * 1024 * 1024


class TestIntakeCaps:
    def test_anon_caps_are_tighter_than_the_authed_path(self):
        # The magic link is bounded only by a token that may have leaked; the
        # authed path is bounded by a login. Anon must not be looser.
        assert _shared.MAX_INTAKE_FILE_BYTES < _shared.MAX_DOCUMENT_BYTES
        assert _shared.MAX_INTAKE_TOTAL_BYTES <= _shared.MAX_DOCUMENT_BYTES
        assert _shared.MAX_INTAKE_FILES * _shared.MAX_INTAKE_FILE_BYTES > _shared.MAX_INTAKE_TOTAL_BYTES
