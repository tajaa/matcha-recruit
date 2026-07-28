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
