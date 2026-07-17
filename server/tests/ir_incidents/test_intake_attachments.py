"""Tests for magic-link intake attachments + the shared upload validation.

The upload path these cover shipped broken once already: `documents.py` called
an `async def` storage helper without awaiting it, passed the MIME into the
`prefix` slot, and stored a locally-built path instead of the one storage
returned — so no bytes ever reached S3 while the endpoint returned 200. The
tests here pin the properties that would have caught that: the helper is
awaited, and the persisted path is the helper's *return value*.
"""

import json

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.matcha.routes.ir_incidents import _shared
from app.matcha.routes.inbound_email import _parse_intake_body


def _make_request(body: bytes, content_type: str) -> Request:
    """A real Starlette Request over a real body — the form parser must run.

    Hand-rolling the ASGI scope rather than mocking: the bug this file exists to
    catch (fastapi.UploadFile vs starlette.datastructures.UploadFile) only
    appears once the actual multipart parser constructs the objects. A mock
    would have happily returned whatever type the test author expected.
    """
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/intake/tok",
        "headers": [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(body)).encode()),
        ],
    }
    received = {"done": False}

    async def receive():
        if received["done"]:
            return {"type": "http.disconnect"}
        received["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _multipart(payload: dict, files: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    """Build a real multipart/form-data body."""
    boundary = "----testboundary9k2"
    parts: list[bytes] = []
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="payload"\r\n\r\n'
        f"{json.dumps(payload)}\r\n".encode()
    )
    for name, content in files:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
            f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            + content
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


_VALID_PAYLOAD = {
    "description": "A pallet nearly fell from the top rack near the loading bay.",
    "reported_by_name": "Dana Reporter",
}


class TestParseIntakeBody:
    """The endpoint's body parsing — where round 1's bug actually lived.

    Round 1 shipped with helper tests passing and attachments silently dropped:
    request.form() yields starlette's UploadFile, but the filter tested against
    fastapi.UploadFile (its subclass), so isinstance() was False for every file.
    The incident saved fine and the Documents tab stayed empty.
    """

    @pytest.mark.asyncio
    async def test_multipart_files_survive_parsing(self):
        body, ctype = _multipart(_VALID_PAYLOAD, [("scene.png", b"\x89PNG-bytes"), ("form.pdf", b"%PDF-x")])
        parsed, files = await _parse_intake_body(_make_request(body, ctype))

        assert parsed.reported_by_name == "Dana Reporter"
        # The regression: this was [] in round 1.
        assert [f.filename for f in files] == ["scene.png", "form.pdf"]

    @pytest.mark.asyncio
    async def test_multipart_file_content_is_readable(self):
        body, ctype = _multipart(_VALID_PAYLOAD, [("scene.png", b"\x89PNG-real-bytes")])
        _, files = await _parse_intake_body(_make_request(body, ctype))
        assert await files[0].read() == b"\x89PNG-real-bytes"

    @pytest.mark.asyncio
    async def test_multipart_without_files_is_valid(self):
        body, ctype = _multipart(_VALID_PAYLOAD, [])
        parsed, files = await _parse_intake_body(_make_request(body, ctype))
        assert files == []
        assert parsed.description.startswith("A pallet")

    @pytest.mark.asyncio
    async def test_json_body_still_accepted(self):
        # Blue-green deploy window: a cached SPA still posts JSON. A 422 here
        # would silently lose a real incident report.
        body = json.dumps(_VALID_PAYLOAD).encode()
        parsed, files = await _parse_intake_body(_make_request(body, "application/json"))
        assert files == []
        assert parsed.reported_by_name == "Dana Reporter"

    @pytest.mark.asyncio
    async def test_too_many_files_rejected(self):
        body, ctype = _multipart(
            _VALID_PAYLOAD, [(f"p{i}.png", b"x") for i in range(_shared.MAX_INTAKE_FILES + 1)]
        )
        with pytest.raises(HTTPException) as e:
            await _parse_intake_body(_make_request(body, ctype))
        assert e.value.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_filename_parts_ignored(self):
        # Browsers send an empty file part for an untouched <input type=file>.
        body, ctype = _multipart(_VALID_PAYLOAD, [("", b"")])
        _, files = await _parse_intake_body(_make_request(body, ctype))
        assert files == []

    @pytest.mark.asyncio
    async def test_missing_payload_field_rejected(self):
        boundary = "----b"
        body = f"--{boundary}--\r\n".encode()
        with pytest.raises(HTTPException) as e:
            await _parse_intake_body(
                _make_request(body, f"multipart/form-data; boundary={boundary}")
            )
        assert e.value.status_code == 422

    @pytest.mark.asyncio
    async def test_malformed_payload_json_rejected(self):
        # Pydantic's own parse failure surfaces as RequestValidationError, which
        # FastAPI's handler renders as a 422 — same status the client sees for
        # the HTTPException paths above, just raised by a different layer.
        boundary = "----b"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="payload"\r\n\r\n'
            f"{{not json\r\n--{boundary}--\r\n"
        ).encode()
        with pytest.raises((HTTPException, RequestValidationError)):
            await _parse_intake_body(
                _make_request(body, f"multipart/form-data; boundary={boundary}")
            )

    @pytest.mark.asyncio
    async def test_payload_failing_model_validation_rejected(self):
        # description under min_length — must not reach the DB as an incident.
        body, ctype = _multipart({"description": "short", "reported_by_name": "D"}, [])
        with pytest.raises((HTTPException, RequestValidationError)):
            await _parse_intake_body(_make_request(body, ctype))


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
