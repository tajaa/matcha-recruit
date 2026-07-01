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
from ..services import entitlements_service
from ..services import journal_service

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────


class JournalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    kind: Optional[str] = None          # note|blog|todo|novel|screenplay|journal
    # Initial hub-folder placement. Omitted entirely -> auto-filed into the
    # caller's default "Notes" notebook. Explicitly sent as null -> genuinely
    # unfiled; distinguished via `model_fields_set` (a bare Optional can't
    # tell "omitted" from "null" once parsed) — same trick as JournalPatch.
    folder_id: Optional[UUID] = None


class JournalPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    kind: Optional[str] = None
    # folder move; an explicit null moves the journal to the hub root, so this
    # is sent through model_dump(exclude_unset=True) to distinguish "untouched"
    # from "move to root".
    folder_id: Optional[UUID] = None


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[UUID] = None
    color: Optional[str] = None


class FolderPatch(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[UUID] = None
    color: Optional[str] = None


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
    status: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    return await journal_service.list_journals(current_user.id, company_id, status=status or "active")


@router.post("/journals", status_code=201)
async def create_journal_endpoint(
    body: JournalCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    # Basic kinds (note/todo/journal) are free; novel/screenplay/blog need Lite+.
    if body.kind in entitlements_service.PREMIUM_JOURNAL_KINDS:
        await entitlements_service.require_plan(current_user.id, entitlements_service.PLAN_LITE, "journals_full")
    return await journal_service.create_journal(
        current_user.id,
        company_id,
        title=body.title,
        description=body.description,
        color=body.color,
        icon=body.icon,
        kind=body.kind,
        folder_id=body.folder_id,
        folder_id_provided="folder_id" in body.model_fields_set,
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


@router.post("/journals/{journal_id}/unarchive")
async def unarchive_journal_endpoint(
    journal_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        await journal_service.unarchive_journal(journal_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"ok": True}


@router.delete("/journals/{journal_id}/permanent", status_code=204)
async def delete_journal_permanent_endpoint(
    journal_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    try:
        await journal_service.delete_journal_permanent(journal_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── Folders (hub organization) ──────────────────────────────────────────


@router.get("/journal-folders")
async def list_journal_folders_endpoint(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    return await journal_service.list_journal_folders(company_id, current_user.id)


@router.post("/journal-folders", status_code=201)
async def create_journal_folder_endpoint(
    body: FolderCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    try:
        return await journal_service.create_journal_folder(
            current_user.id, company_id, name=body.name, parent_id=body.parent_id,
            color=body.color,
        )
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/journal-folders/{folder_id}")
async def update_journal_folder_endpoint(
    folder_id: UUID,
    body: FolderPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    try:
        return await journal_service.update_journal_folder(
            folder_id, company_id, current_user.id, body.model_dump(exclude_unset=True),
        )
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/journal-folders/{folder_id}", status_code=204)
async def delete_journal_folder_endpoint(
    folder_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    try:
        await journal_service.delete_journal_folder(folder_id, company_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
