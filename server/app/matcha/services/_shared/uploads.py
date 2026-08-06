"""Shared upload-reading helpers. Leaf module: imports only FastAPI's HTTPException.

Lifted from routes/ir_incidents/_shared.py so any route package can bound an
upload without importing another router package.
"""
from fastapi import HTTPException, UploadFile


async def read_upload_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an UploadFile in chunks, aborting at ``max_bytes``.

    Chunked rather than a bare ``await file.read()`` so an oversize body is
    rejected AT the cap instead of after it has already been pulled into the
    process. A bare read passed as a call argument
    (``fn(content=await file.read())``) is the worst shape: the whole body is
    materialized before the callee gets a chance to reject it on extension,
    size, or authorization.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {max_bytes // (1024 * 1024)} MB per file.",
            )
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return b"".join(chunks)


_ALLOWED_AUDIO_MIME = {"audio/wav", "audio/x-wav", "audio/wave"}
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


async def read_wav_or_400(file: UploadFile) -> bytes:
    """Bound + validate a WAV voice-dictation upload. Content-type is
    client-controlled, so it's checked as an allow-list hint and then the
    bytes themselves are checked for the real RIFF/WAVE magic header.
    Lifted from routes/ir_incidents/_shared.py's _read_audio_or_400 so any
    route package can reuse it without importing another router package."""
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_AUDIO_MIME:
        raise HTTPException(status_code=400, detail="Audio must be WAV (audio/wav).")
    audio = await read_upload_capped(file, _MAX_AUDIO_BYTES)
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail="Not a valid WAV file.")
    return audio
