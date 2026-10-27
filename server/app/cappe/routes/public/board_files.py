"""Cappe public surface — a mood board's private files, by signed link.

`GET /public/board-files/{token}`: the token names a pin and which of its
files (`services/boards/files.py`), signed by a board answer of ours, so this
serves only what the owner was handed; the file itself is looked up by pin
(`store.file_for`), so no storage path is ever in a link and a deleted pin's
links die with it. Anonymous because an `<img>` can't carry the dashboard's
bearer token — the signature is the permission. A picture is streamed from
our origin (the dashboard's CSP loads images only from here and CloudFront);
a document redirects to a short presigned S3 link with its own name, so it
never opens on our origin.
"""
from fastapi import Request, status
from fastapi.responses import RedirectResponse, Response

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....core.services.storage import get_storage
from ....database import get_connection
from ...services.boards import files, store
from ._body_limit import limited_public_router

router = limited_public_router()

_PICTURE_TYPES = files.IMAGE_TYPES | {"image/webp"}
_DOCUMENT_SECONDS = 300


@router.get("/public/board-files/{token}")
async def board_file(token: str, request: Request):
    await check_rate_limit(client_ip(request), "cappe_board_file", 3000, 600)
    claim = files.verify(token)
    if claim is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    pin_id, part = claim
    async with get_connection() as conn:
        found = await store.file_for(conn, pin_id, part)
    if found is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    path, mime, name = found
    storage = get_storage()
    if part == "doc":
        url = storage.get_presigned_download_url(path, expires_in=_DOCUMENT_SECONDS,
                                                 disposition=files.disposition(name, mime))
        if not url:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND, headers={"Cache-Control": "no-store"})
    if mime not in _PICTURE_TYPES:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    try:
        data = await storage.download_file(path)
    except RuntimeError:  # gone, or storage unreachable
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return Response(data, media_type=mime, headers={
        "Cache-Control": "private, max-age=21600",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
        "Content-Disposition": "inline",
    })
