"""Matcha Drive routes — company document store on the business /work surface.

Thin HTTP layer over `services/drive/drive_service.py`; every capability
check lives there. Gated on `matcha_drive` (+ the package-level
`matcha_work` gate) and business workspaces only.

Static paths (`/drive/tree`, `/drive/search`, `/drive/people`) are declared before any
`{folder_id}` / `{file_id}` route.
"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_company_member, require_feature, resolve_accessible_company_scope
from app.matcha.services.drive import drive_service as svc
from app.matcha.services.drive.drive_service import DriveError

router = APIRouter(prefix="/drive", dependencies=[Depends(require_feature("matcha_drive"))])


class FolderCreate(BaseModel):
    parent_id: UUID
    name: str = Field(..., min_length=1, max_length=200)


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    parent_id: Optional[UUID] = None


class FileUpdate(BaseModel):
    filename: Optional[str] = Field(None, min_length=1, max_length=255)
    folder_id: Optional[UUID] = None


class GrantSet(BaseModel):
    user_id: UUID
    permission: Literal["view", "upload", "edit"]


async def _business_company(current_user: CurrentUser) -> UUID:
    # A platform admin has no company of their own: scope resolution would
    # silently pick the oldest tenant and hand them admin rights over its HR
    # space. Drive is per-company, so they're refused here.
    if current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Drive is only available inside a company workspace")
    scope = await resolve_accessible_company_scope(current_user)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        is_personal = await conn.fetchval(
            "SELECT COALESCE(is_personal, false) FROM companies WHERE id = $1", company_id,
        )
    if is_personal:
        raise HTTPException(status_code=403, detail="Drive is only available in business workspaces")
    return company_id


def _raise(exc: DriveError):
    raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/tree")
async def get_tree(current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.get_tree(conn, company_id=company_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.get("/search")
async def search_files(
    q: str = Query(..., min_length=1, max_length=200),
    space: Optional[Literal["general", "hr"]] = None,
    limit: int = Query(25, ge=1, le=50),
    current_user: CurrentUser = Depends(require_company_member),
):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return {"results": await svc.search(conn, company_id=company_id, q=q, actor=actor, space=space, limit=limit)}
        except DriveError as exc:
            _raise(exc)


@router.get("/people")
async def search_people(
    q: Optional[str] = Query(None, max_length=100),
    current_user: CurrentUser = Depends(require_company_member),
):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return {"people": await svc.search_members(conn, company_id=company_id, q=q, actor=actor)}
        except DriveError as exc:
            _raise(exc)


@router.post("/folders", status_code=201)
async def create_folder(body: FolderCreate, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.create_folder(conn, company_id=company_id, parent_id=body.parent_id, name=body.name, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.get("/folders/{folder_id}")
async def get_folder(folder_id: UUID, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.list_folder(conn, company_id=company_id, folder_id=folder_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.patch("/folders/{folder_id}")
async def update_folder(folder_id: UUID, body: FolderUpdate, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.update_folder(
                conn, company_id=company_id, folder_id=folder_id, actor=actor,
                name=body.name, parent_id=body.parent_id,
            )
        except DriveError as exc:
            _raise(exc)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(folder_id: UUID, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            await svc.delete_folder(conn, company_id=company_id, folder_id=folder_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.get("/folders/{folder_id}/grants")
async def list_grants(folder_id: UUID, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return {"grants": await svc.list_grants(conn, company_id=company_id, folder_id=folder_id, actor=actor)}
        except DriveError as exc:
            _raise(exc)


@router.put("/folders/{folder_id}/grants")
async def set_grant(folder_id: UUID, body: GrantSet, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.set_grant(
                conn, company_id=company_id, folder_id=folder_id,
                user_id=body.user_id, permission=body.permission, actor=actor,
            )
        except DriveError as exc:
            _raise(exc)


@router.delete("/folders/{folder_id}/grants/{user_id}", status_code=204)
async def remove_grant(folder_id: UUID, user_id: UUID, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            await svc.remove_grant(conn, company_id=company_id, folder_id=folder_id, user_id=user_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.post("/files", status_code=201)
async def upload_file(
    folder_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_company_member),
):
    company_id = await _business_company(current_user)
    # Permission first: a caller who can't add here must not get to spend
    # a 25 MB read and a PDF/DOCX parse finding that out.
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            await svc.assert_can_add(conn, company_id=company_id, folder_id=folder_id, actor=actor)
        except DriveError as exc:
            _raise(exc)
    data = await file.read(svc.MAX_FILE_BYTES + 1)
    try:
        # Validation + text extraction happen outside a connection.
        prepared = await svc.prepare_file(file.filename or "file", data)
    except DriveError as exc:
        _raise(exc)
    async with get_connection() as conn:
        try:
            return await svc.store_file(
                conn, company_id=company_id, folder_id=folder_id, prepared=prepared,
                uploaded_by=current_user.id, actor=actor,
            )
        except DriveError as exc:
            _raise(exc)


@router.get("/files/{file_id}")
async def get_file(file_id: UUID, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.get_file(conn, company_id=company_id, file_id=file_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.get("/files/{file_id}/download")
async def download_file(file_id: UUID, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.presign_download(conn, company_id=company_id, file_id=file_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.patch("/files/{file_id}")
async def update_file(file_id: UUID, body: FileUpdate, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.update_file(
                conn, company_id=company_id, file_id=file_id, actor=actor,
                filename=body.filename, folder_id=body.folder_id,
            )
        except DriveError as exc:
            _raise(exc)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: UUID, current_user: CurrentUser = Depends(require_company_member)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            await svc.soft_delete_file(conn, company_id=company_id, file_id=file_id, actor=actor)
        except DriveError as exc:
            _raise(exc)
