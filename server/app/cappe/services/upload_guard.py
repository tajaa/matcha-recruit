"""Validate uploaded bytes against the client-declared MIME type."""
from typing import Optional

from fastapi import HTTPException, status

ALLOWED_IMAGE: set[str] = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEO: set[str] = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_DELIVERABLE: set[str] = ALLOWED_IMAGE | {
    "application/pdf", "application/zip", "application/x-zip-compressed",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/csv",
}

_EXPECTED: dict[str, set[str]] = {
    "image/jpeg": {"image/jpeg"}, "image/png": {"image/png"},
    "image/gif": {"image/gif"}, "image/webp": {"image/webp"},
    "video/mp4": {"video/mp4"}, "video/quicktime": {"video/mp4"},
    "video/webm": {"video/webm"}, "application/pdf": {"application/pdf"},
    "application/zip": {"application/zip"}, "application/x-zip-compressed": {"application/zip"},
    "application/msword": {"application/vnd.ms-office"},
    "application/vnd.ms-excel": {"application/vnd.ms-office"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {"application/zip"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {"application/zip"},
    "text/plain": set(), "text/csv": set(),
}


def sniff(data: bytes) -> Optional[str]:
    if len(data) < 4:
        return None
    if data.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")): return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP": return "image/webp"
    if data.startswith(b"%PDF-"): return "application/pdf"
    if data.startswith(b"PK\x03\x04"): return "application/zip"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"): return "application/vnd.ms-office"
    if len(data) >= 8 and data[4:8] == b"ftyp": return "video/mp4"
    if data.startswith(b"\x1aE\xdf\xa3"): return "video/webm"
    return None


def verify_upload(data: bytes, declared: Optional[str], allowed: set[str]) -> str:
    if not data or declared not in allowed or declared not in _EXPECTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type" if data else "Empty file")
    expected = _EXPECTED[declared]
    if not expected:
        return "text/plain"
    if sniff(data) not in expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File contents don't match the declared type")
    return declared
