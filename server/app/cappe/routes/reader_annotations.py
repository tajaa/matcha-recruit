"""Private reader annotations. Never served on a public magazine or to its writer."""
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.cappe.dependencies import require_cappe_account
from app.cappe.models.auth import CappeAccount
from app.cappe.models.reader import ReaderAnnotationCreate
from app.cappe.services.magazine import annotations
from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection

router = APIRouter(prefix="/reader/magazines/{slug}/stories/{story_slug}/annotations")
_PRIVATE = {"Cache-Control": "no-store, private"}


@router.get("")
async def listing(slug: str, story_slug: str, account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_reader_annotations_read", 300, 3600)
    async with get_connection() as conn:
        post_id = await annotations.readable_post(conn, account.id, slug, story_slug)
        rows = await annotations.listing(conn, account.id, post_id)
    return JSONResponse({"annotations": rows}, headers=_PRIVATE)


@router.put("/{annotation_id}")
async def save(slug: str, story_slug: str, annotation_id: UUID, body: ReaderAnnotationCreate,
               account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_reader_annotations_write", 300, 3600)
    async with get_connection() as conn:
        post_id = await annotations.readable_post(conn, account.id, slug, story_slug)
        row = await annotations.save(conn, account.id, post_id, annotation_id, body)
    return JSONResponse(row, headers=_PRIVATE)


@router.delete("/{annotation_id}")
async def remove(slug: str, story_slug: str, annotation_id: UUID,
                 account: CappeAccount = Depends(require_cappe_account)):
    await check_rate_limit(str(account.id), "cappe_reader_annotations_write", 300, 3600)
    async with get_connection() as conn:
        post_id = await annotations.readable_post(conn, account.id, slug, story_slug)
        await annotations.remove(conn, account.id, post_id, annotation_id)
    return JSONResponse({"deleted": True}, headers=_PRIVATE)
