"""A magazine's own licensed fonts in Gummfit Studio (`services/magazine/
studio/custom_fonts.py`).

The owner uploads a face with a licence attestation; it is read and written
again as a TrueType file, stored by its sha at `cappe/fonts/<sha>.ttf` (the
public font route serves it like the catalog's faces) and listed in the
Character panel's font picker as one of "Your fonts". Fonts belong to the
site; any plan with `magazine` may add them. A face is hidden, never deleted:
pages that set it keep it.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from ...core.services.redis_cache import check_rate_limit
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount
from ..services.entitlements import resolve_entitlements
from ..services.magazine.studio import custom_fonts as C
from ._shared import get_owned_site, read_capped
from .public.fonts import FONT_KEY

router = APIRouter()

UPLOADS_PER_HOUR = 30


async def _designer(account: CappeAccount = Depends(require_cappe_account)) -> CappeAccount:
    if account.account_type == "reader":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"code": "reader_account", "message": "A reader account doesn't design pages."})
    return account


async def _magazine_site(conn, site_id: UUID, account: CappeAccount):
    site = await get_owned_site(conn, site_id, account.id)
    ent = await resolve_entitlements(account.plan, conn=conn)
    if not ent.has("magazine"):
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail={"code": "plan_required", "message": "Your own fonts come with a magazine plan."})
    return site


def _conflict(exc: C.FontConflict) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})


@router.get("/sites/{site_id}/studio/fonts")
async def list_fonts(site_id: UUID, account: CappeAccount = Depends(_designer)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        return {"fonts": await C.list_fonts(conn, site_id)}


@router.post("/sites/{site_id}/studio/fonts", status_code=status.HTTP_201_CREATED)
async def upload_font(
    site_id: UUID,
    response: Response,
    file: UploadFile = File(...),
    name: str = Form(..., max_length=200),
    weight: Optional[int] = Form(default=None),
    italic: Optional[bool] = Form(default=None),
    licence_attested: bool = Form(False),
    account: CappeAccount = Depends(_designer),
):
    """Add a face. The owner says they hold a licence to publish it on the
    web; the same file again is the face it already is."""
    if not licence_attested:
        raise HTTPException(status_code=422, detail={
            "code": "licence_required", "message": "Confirm your licence lets you use this font on the web."})
    clean = C.clean_name(name)
    if not clean:
        raise HTTPException(status_code=422, detail="Give the font a name.")
    await check_rate_limit(str(account.id), "cappe_studio_font_upload", UPLOADS_PER_HOUR, 3600)
    async with get_connection() as conn:
        await _magazine_site(conn, site_id, account)

    data = await read_capped(file, C.MAX_UPLOAD_BYTES, "A font file can be at most 10 MB.")
    try:
        ttf, meta = await asyncio.to_thread(C.process, data)
    except C.FontError as exc:
        raise HTTPException(status_code=422,
                            detail={"code": "bad_font", "message": str(exc)}) from exc
    sha = hashlib.sha256(ttf).hexdigest()
    await get_storage().put_key(FONT_KEY.format(sha=sha), ttf, "font/ttf")

    async with get_connection() as conn:
        try:
            out, created = await C.create_font(
                conn, site_id=site_id, account_id=account.id, name=clean, sha=sha, size=len(ttf), meta=meta,
                weight=C.round_weight(weight, meta["weight"]) if weight is not None else meta["weight"],
                italic=meta["italic"] if italic is None else bool(italic), filename=file.filename,
            )
        except C.FontConflict as exc:
            raise _conflict(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return out


class FamilyRename(BaseModel):
    name: str = Field(max_length=200)


@router.patch("/sites/{site_id}/studio/fonts/families/{family}")
async def rename_family(site_id: UUID, family: str, body: FamilyRename, account: CappeAccount = Depends(_designer)):
    clean = C.clean_name(body.name)
    if not clean:
        raise HTTPException(status_code=422, detail="Give the font a name.")
    if not C.is_custom(family):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Font not found")
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        try:
            renamed = await C.rename_family(conn, site_id, family, clean)
        except C.FontConflict as exc:
            raise _conflict(exc) from exc
    if not renamed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Font not found")
    return {"family": family, "name": clean}


@router.delete("/sites/{site_id}/studio/fonts/{font_id}", status_code=status.HTTP_204_NO_CONTENT)
async def hide_font(site_id: UUID, font_id: UUID, account: CappeAccount = Depends(_designer)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if not await C.hide_font(conn, site_id, font_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Font not found")
