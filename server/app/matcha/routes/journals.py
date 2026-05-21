"""Journal routes — mounted under matcha_work_router so they inherit
`require_feature("matcha_work")` from the parent. No separate gate.
"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ...core.models.auth import CurrentUser
from ...core.services.storage import get_storage
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import journal_service

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────


class JournalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class JournalPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class EntryCreate(BaseModel):
    title: Optional[str] = None
    content: str = ""
    entry_date: Optional[date] = None


class EntryPatch(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    entry_date: Optional[date] = None


class CollaboratorAdd(BaseModel):
    user_ids: list[UUID]


# ── Journals ────────────────────────────────────────────────────────────


@router.get("/journals")
async def list_journals_endpoint(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    return await journal_service.list_journals(current_user.id, company_id)


@router.post("/journals", status_code=201)
async def create_journal_endpoint(
    body: JournalCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    return await journal_service.create_journal(
        current_user.id,
        company_id,
        title=body.title,
        description=body.description,
        color=body.color,
        icon=body.icon,
    )


@router.get("/journals/{journal_id}")
async def get_journal_endpoint(
    journal_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    j = await journal_service.get_journal(journal_id, current_user.id)
    if j is None:
        raise HTTPException(status_code=404, detail="Journal not found")
    return j


@router.patch("/journals/{journal_id}")
async def update_journal_endpoint(
    journal_id: UUID,
    body: JournalPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        return await journal_service.update_journal(
            journal_id, current_user.id, body.model_dump(exclude_unset=True),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/journals/{journal_id}", status_code=204)
async def archive_journal_endpoint(
    journal_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        await journal_service.archive_journal(journal_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/journals/{journal_id}/permanent", status_code=204)
async def delete_journal_permanent_endpoint(
    journal_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        await journal_service.delete_journal_permanent(journal_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── Entries ─────────────────────────────────────────────────────────────


@router.get("/journals/{journal_id}/entries")
async def list_entries_endpoint(
    journal_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[datetime] = None,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    return await journal_service.list_entries(
        journal_id, current_user.id, limit=limit, before=before,
    )


@router.post("/journals/{journal_id}/entries", status_code=201)
async def create_entry_endpoint(
    journal_id: UUID,
    body: EntryCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        return await journal_service.create_entry(
            journal_id,
            current_user.id,
            title=body.title,
            content=body.content,
            entry_date=body.entry_date,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/journals/{journal_id}/entries/{entry_id}")
async def update_entry_endpoint(
    journal_id: UUID,
    entry_id: UUID,
    body: EntryPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        return await journal_service.update_entry(
            entry_id, current_user.id, body.model_dump(exclude_unset=True),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/journals/{journal_id}/entries/{entry_id}", status_code=204)
async def delete_entry_endpoint(
    journal_id: UUID,
    entry_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        await journal_service.delete_entry(entry_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── Images ──────────────────────────────────────────────────────────────


@router.post("/journals/{journal_id}/images", status_code=201)
async def upload_journal_image_endpoint(
    journal_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a single image to embed in a journal entry. Returns {"url": ...}."""
    j = await journal_service.get_journal(journal_id, current_user.id)
    if j is None:
        raise HTTPException(status_code=404, detail="Journal not found")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image exceeds 10 MB limit")
    url = await get_storage().upload_file(
        content,
        file.filename or "image.png",
        prefix=f"journal-images/{journal_id}",
        content_type=file.content_type,
    )
    return {"url": url}


# ── Collaborators ───────────────────────────────────────────────────────


@router.get("/journals/{journal_id}/collaborators")
async def list_collaborators_endpoint(
    journal_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    return await journal_service.list_collaborators(journal_id, current_user.id)


@router.post("/journals/{journal_id}/collaborators")
async def add_collaborators_endpoint(
    journal_id: UUID,
    body: CollaboratorAdd,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    added = 0
    try:
        for uid in body.user_ids:
            await journal_service.add_collaborator(journal_id, uid, current_user.id)
            added += 1
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"added": added}


@router.delete("/journals/{journal_id}/collaborators/{user_id}", status_code=204)
async def remove_collaborator_endpoint(
    journal_id: UUID,
    user_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        await journal_service.remove_collaborator(journal_id, user_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
