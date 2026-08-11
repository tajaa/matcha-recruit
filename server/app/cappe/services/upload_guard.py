"""Validate and normalize uploaded bytes."""
import io
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


def compress_image_for_storage(
    data: bytes,
    content_type: str,
    filename: str,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    max_edge: int = 2560,
) -> tuple[bytes, str, str]:
    """Compress an oversized raster image to a bounded JPEG.

    Images already within the storage cap pass through byte-for-byte. This is
    intentionally server-side so uploads do not depend on browser codec or
    canvas support (notably for large phone photos).
    """
    if len(data) <= max_bytes:
        return data, content_type, filename

    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as source:
            source.seek(0)
            image = ImageOps.exif_transpose(source)
            image.thumbnail((max_edge, max_edge))
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                image = flattened
            elif image.mode != "RGB":
                image = image.convert("RGB")

            for quality in (85, 75, 65, 55):
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
                compressed = output.getvalue()
                if len(compressed) <= max_bytes:
                    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
                    return compressed, "image/jpeg", f"{stem or 'upload'}.jpg"
    except Exception as exc:  # Pillow raises several format/decode-specific errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image could not be decoded. Try a JPG, PNG, GIF, or WebP image.",
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail="Image could not be compressed below 5 MB",
    )
