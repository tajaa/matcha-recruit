"""Matcha admin (hey-matcha.com/admin/cappe → Studio bank): the photos and
graphics every site's Gummfit Studio shows first (`studio/bank.py`,
cappemag11).

Behind matcha's `require_admin`, mounted at /matcha-admin like
`matcha_admin.py`, and audited in the same format.

  * A photo is re-encoded without its metadata, with its responsive sizes,
    under `cappe/bank/`, exactly as a site's library upload is.
  * A graphic is cleaned (`graphics.clean_svg`: drawing only, no scripts,
    styles, links or entities) and stored by its sha256 at
    `cappe/graphics/<sha>.svg`, where the built-in bank's live. Whether it is
    one colour (a silhouette the Studio recolours) is read from its paints
    unless the admin says.
  * A graphic is hidden, never deleted: pages name it by sha. A photo can be
    deleted; sites that placed it keep their copy.
"""
import asyncio
import hashlib
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from ...core.dependencies import require_admin
from ...core.services.cappe_admin_audit import record_matcha_admin_action
from ...core.services.storage import get_storage
from ...database import get_connection
from ..services import media, upload_guard
from ..services.magazine.studio import bank, graphics
from ._shared import read_capped

router = APIRouter()

MAX_PHOTO_BYTES = 15 * 1024 * 1024
Group = Literal["shapes", "lines", "badges", "icons", "stickers", "patterns"]


class BankPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=bank.MAX_NAME)
    tags: Optional[list[str]] = Field(default=None, max_length=bank.MAX_TAGS)
    collection: Optional[str] = Field(default=None, max_length=bank.MAX_COLLECTION)
    status: Optional[Literal["live", "hidden"]] = None
    sort_order: Optional[int] = Field(default=None, ge=-100_000, le=100_000)
    creator: Optional[str] = Field(default=None, max_length=200)
    credit_line: Optional[str] = Field(default=None, max_length=bank.MAX_CREDIT)
    license: Optional[Literal["gummfit", "cc0", "pdm", "by", "by-sa"]] = None
    source_url: Optional[str] = Field(default=None, max_length=2000)


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _name(value: Optional[str]) -> str:
    name = bank.clean_name(value)
    if not name:
        raise _bad("Give it a name: the Studio shows it, and searches it.")
    return name


def _url(value: Optional[str]) -> Optional[str]:
    url = (value or "").strip()
    if url and not url.startswith(("https://", "http://")):
        raise _bad("The source link should start with https://.")
    return url or None


@router.get("/studio-bank")
async def list_bank(kind: Literal["photo", "graphic"] = Query(...)):
    async with get_connection() as conn:
        return await bank.admin_list(conn, kind)


@router.post("/studio-bank/photos", status_code=status.HTTP_201_CREATED)
async def add_photo(
    file: UploadFile = File(...),
    name: str = Form(..., max_length=500),
    tags: str = Form("", max_length=1000),
    collection: str = Form("", max_length=200),
    creator: str = Form("", max_length=200),
    credit_line: str = Form("", max_length=bank.MAX_CREDIT),
    license: Literal["gummfit", "cc0", "pdm", "by", "by-sa"] = Form("gummfit"),
    source_url: str = Form("", max_length=2000),
    admin=Depends(require_admin),
):
    clean_name, url = _name(name), _url(source_url)
    if license in ("by", "by-sa") and not creator.strip():
        raise _bad("A CC BY photo is credited to its creator: say who that is.")
    if file.content_type not in upload_guard.ALLOWED_IMAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use a JPEG, PNG, WebP or GIF.")
    data = await read_capped(file, MAX_PHOTO_BYTES, "Photo too large (max 15 MB)")
    content_type = upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_IMAGE)
    try:
        image = await asyncio.to_thread(media.process_image, data, content_type, derivatives=True)
    except media.ImageRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    stored = await media.store_processed(image, prefix="cappe/bank", filename=file.filename)
    async with get_connection() as conn:
        async with conn.transaction():
            item = await bank.add_photo(
                conn, url=stored.url, variants=stored.variants, width=stored.width, height=stored.height,
                size_bytes=stored.bytes, mime=stored.mime, name=clean_name, tags=bank.clean_tags(tags),
                collection=bank.clean_collection(collection), creator=creator.strip() or None,
                credit_line=bank.credit(creator, credit_line), license=license, source_url=url, email=admin.email,
            )
            await record_matcha_admin_action(conn, admin.email, "studio_bank.add_photo", str(item["id"]),
                                             {"name": clean_name, "license": license})
    return item


@router.post("/studio-bank/graphics", status_code=status.HTTP_201_CREATED)
async def add_graphic(
    file: UploadFile = File(...),
    name: str = Form(..., max_length=500),
    tags: str = Form("", max_length=1000),
    collection: str = Form("", max_length=200),
    group: Group = Form("shapes"),
    colour: Literal["auto", "one", "own"] = Form("auto"),
    fit: Optional[Literal["contain", "stretch", "tile"]] = Form(None),
    admin=Depends(require_admin),
):
    clean_name = _name(name)
    data = await read_capped(file, graphics.MAX_SVG_BYTES, "An SVG of at most 200 KB")
    try:
        clean, w, h = graphics.clean_svg(data)
    except graphics.SvgError as exc:
        raise _bad(f"That isn't an SVG the Studio can use ({exc}).") from exc
    sha = hashlib.sha256(clean).hexdigest()
    if graphics.by_sha(sha) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That graphic is built into the Studio already.")
    mono = bank.one_colour(clean) if colour == "auto" else colour == "one"
    key = graphics.GRAPHIC_KEY.format(sha=sha)
    storage = get_storage()
    if await storage.get_key(key) is None:
        await storage.put_key(key, clean, "image/svg+xml")
    async with get_connection() as conn:
        async with conn.transaction():
            try:
                item = await bank.add_graphic(
                    conn, sha=sha, w=round(w, 2), h=round(h, 2), mono=mono, fit=fit or bank.default_fit(group),
                    group=group, name=clean_name, tags=bank.clean_tags(tags),
                    collection=bank.clean_collection(collection), email=admin.email,
                )
            except bank.Exists as exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            await record_matcha_admin_action(conn, admin.email, "studio_bank.add_graphic", str(item["id"]),
                                             {"name": clean_name, "sha": sha, "mono": mono})
    return item


@router.patch("/studio-bank/{item_id}")
async def update_bank_item(item_id: UUID, body: BankPatch, admin=Depends(require_admin)):
    sent = body.model_dump(exclude_unset=True)
    fields: dict = {}
    for key, value in sent.items():
        if key == "name":
            fields[key] = _name(value)
        elif key == "tags":
            fields[key] = bank.clean_tags(value)
        elif key == "collection":
            fields[key] = bank.clean_collection(value)
        elif key == "source_url":
            fields[key] = _url(value)
        elif key in ("creator", "credit_line"):
            fields[key] = (value or "").strip() or None
        elif value is not None:
            fields[key] = value
    async with get_connection() as conn:
        async with conn.transaction():
            item = await bank.get_item(conn, item_id)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not in the bank")
            if item["kind"] == "graphic" and set(fields) & set(bank.PHOTO_ONLY):
                raise _bad("A graphic has no credit or licence to change.")
            if item["kind"] == "photo" and fields.get("license", item["license"]) in ("by", "by-sa") \
                    and not fields.get("creator", item["creator"]):
                # As on upload: a placed photo's credit is copied out and its site can't change it.
                raise _bad("A CC BY photo is credited to its creator: say who that is.")
            if item["kind"] == "photo" and ("credit_line" in fields or "creator" in fields):
                # A credit the admin wrote stays; the automatic one follows the creator.
                automatic = item["credit_line"] == bank.credit(item["creator"], None)
                line = fields["credit_line"] if "credit_line" in fields else None if automatic else item["credit_line"]
                fields["credit_line"] = bank.credit(fields.get("creator", item["creator"]), line)
            updated = await bank.update_item(conn, item_id, fields)
            await record_matcha_admin_action(conn, admin.email, "studio_bank.update", str(item_id), fields)
    return updated


@router.delete("/studio-bank/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_item(item_id: UUID, admin=Depends(require_admin)):
    async with get_connection() as conn:
        async with conn.transaction():
            item = await bank.get_item(conn, item_id)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not in the bank")
            if item["kind"] == "graphic":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Hide a graphic instead: pages may use it.")
            await bank.delete_photo(conn, item_id)
            await record_matcha_admin_action(conn, admin.email, "studio_bank.delete", str(item_id),
                                             {"name": item["name"]})
