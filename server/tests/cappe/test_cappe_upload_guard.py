import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.upload_guard import (  # noqa: E402
    ALLOWED_DELIVERABLE, ALLOWED_IMAGE, sniff, verify_upload,
)


@pytest.mark.parametrize(("declared", "payload", "stored"), [
    ("image/png", b"\x89PNG\r\n\x1a\n" + b"\0" * 16, "image/png"),
    ("image/jpeg", b"\xff\xd8\xff\xe0" + b"\0" * 16, "image/jpeg"),
    ("application/pdf", b"%PDF-1.7\n" + b"\0" * 16, "application/pdf"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04" + b"\0" * 16,
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("text/csv", b"a,b\n1,2\n", "text/plain"),
])
def test_verify_upload_accepts_backed_types(declared, payload, stored):
    allowed = ALLOWED_IMAGE if declared.startswith("image/") else ALLOWED_DELIVERABLE
    assert verify_upload(payload, declared, allowed) == stored


@pytest.mark.parametrize("declared,payload", [
    ("image/png", b"<svg xmlns='http://www.w3.org/2000/svg'>"),
    ("image/jpeg", b"<!doctype html><script>alert(1)</script>"),
    ("image/gif", b"\x89PNG\r\n\x1a\n" + b"\0" * 16),
])
def test_verify_upload_rejects_mismatch(declared, payload):
    with pytest.raises(HTTPException) as exc:
        verify_upload(payload, declared, ALLOWED_IMAGE)
    assert exc.value.status_code == 400


def test_text_normalizes_and_sniff_unknown_is_none():
    assert verify_upload(b"hello", "text/csv", ALLOWED_DELIVERABLE) == "text/plain"
    assert sniff(b"") is None
