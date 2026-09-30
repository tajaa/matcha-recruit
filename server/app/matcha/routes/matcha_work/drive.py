"""Matcha Drive routes — company document store on the business /work surface.

Thin HTTP layer over `services/drive/drive_service.py`; every capability
check lives there. Gated on `matcha_drive` (+ the package-level
`matcha_work` gate) and business workspaces only.

Static paths (`/drive/tree`, `/drive/search`, `/drive/people`,
`/drive/google/*`) are declared before any `{folder_id}` / `{file_id}` route.

Google's OAuth callback lives on `oauth_callback_router` (no bearer token, no
feature gate), included into the package's ungated callback router — it only
consumes a one-time state handle and stores the caller's own token.
"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

import logging
import urllib.parse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_feature, resolve_accessible_company_scope
from app.matcha.services.drive import drive_service as svc
from app.matcha.services.drive import google_drive_service as gdrive
from app.matcha.services.drive.drive_service import DriveError
from app.matcha.services.drive.google_drive_service import GoogleDriveError, GoogleDriveService
from app.matcha.services.matcha_work import oauth_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drive", dependencies=[Depends(require_feature("matcha_drive"))])
oauth_callback_router = APIRouter()

GOOGLE_IMPORT_LIMIT = (30, 3600)  # per user per hour


class FolderCreate(BaseModel):
    parent_id: UUID
    name: str = Field(..., min_length=1, max_length=200)


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    parent_id: Optional[UUID] = None


class FileUpdate(BaseModel):
    filename: Optional[str] = Field(None, min_length=1, max_length=255)
    folder_id: Optional[UUID] = None


class GoogleImport(BaseModel):
    url: str = Field(..., min_length=10, max_length=2000)
    folder_id: UUID


class GrantSet(BaseModel):
    user_id: UUID
    permission: Literal["view", "upload", "edit"]


async def _business_company(current_user: CurrentUser) -> UUID:
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
async def get_tree(current_user: CurrentUser = Depends(require_admin_or_client)):
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
    current_user: CurrentUser = Depends(require_admin_or_client),
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
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return {"people": await svc.search_members(conn, company_id=company_id, q=q, actor=actor)}
        except DriveError as exc:
            _raise(exc)


def _google_redirect_uri() -> str:
    return f"{get_settings().app_base_url}{gdrive.CALLBACK_PATH}"


def _popup(message: str, text: str, status_code: int = 200) -> Response:
    # `message` is one of a fixed set of literals, never request input.
    return Response(
        content=(
            "<!DOCTYPE html><html><body><script>window.opener && "
            f"window.opener.postMessage('{message}', '*'); window.close();</script>"
            f"<p>{text}</p></body></html>"
        ),
        media_type="text/html",
        status_code=status_code,
    )


@router.get("/google/status")
async def google_status(current_user: CurrentUser = Depends(require_admin_or_client)):
    await _business_company(current_user)
    return await GoogleDriveService(current_user.id).get_status()


@router.post("/google/connect")
async def google_connect(current_user: CurrentUser = Depends(require_admin_or_client)):
    await _business_company(current_user)
    try:
        creds = gdrive._client_credentials()
        state = await oauth_state.issue_state(gdrive.OAUTH_STATE_PREFIX, current_user.id)
    except GoogleDriveError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    except oauth_state.OAuthStateUnavailable as exc:
        logger.error("[gdrive] cannot issue OAuth state: %s", exc)
        raise HTTPException(status_code=503, detail="Google connection is temporarily unavailable. Please try again.") from exc
    params = {
        "client_id": creds["client_id"],
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": " ".join(gdrive.GDRIVE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "state": state,
    }
    return {"auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"}


@router.delete("/google/disconnect")
async def google_disconnect(current_user: CurrentUser = Depends(require_admin_or_client)):
    await _business_company(current_user)
    await GoogleDriveService(current_user.id).disconnect()
    return {"connected": False}


@router.post("/google/import", status_code=201)
async def google_import(body: GoogleImport, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    file_id = gdrive.parse_file_id(body.url)
    if not file_id:
        raise HTTPException(status_code=400, detail="Paste a link to a Google Doc, Sheet, Slides deck or Drive file.")
    await check_rate_limit(str(current_user.id), "drive_google_import", *GOOGLE_IMPORT_LIMIT)
    # Check the destination before calling Google: a person who can't add
    # here shouldn't spend a Google fetch finding that out.
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            await svc.assert_can_add(conn, company_id=company_id, folder_id=body.folder_id, actor=actor)
        except DriveError as exc:
            _raise(exc)
    try:
        fetched = await GoogleDriveService(current_user.id).fetch_file(file_id)
    except GoogleDriveError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    try:
        prepared = await svc.prepare_file(fetched.name, fetched.data)
    except DriveError as exc:
        _raise(exc)
    async with get_connection() as conn:
        try:
            return await svc.store_file(
                conn, company_id=company_id, folder_id=body.folder_id, prepared=prepared,
                uploaded_by=current_user.id, actor=actor,
                source="google_drive", source_ref=fetched.file_id,
            )
        except DriveError as exc:
            _raise(exc)


@oauth_callback_router.get("/drive/google/callback", include_in_schema=False)
async def google_callback(
    state: str = Query(...),
    code: str | None = Query(None),
    error: str | None = Query(None),
):
    try:
        user_id = await oauth_state.consume_state(gdrive.OAUTH_STATE_PREFIX, state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except oauth_state.OAuthStateUnavailable as exc:
        logger.error("[gdrive] cannot consume OAuth state: %s", exc)
        raise HTTPException(status_code=503, detail="Google connection is temporarily unavailable. Please try again.") from exc
    if error == "access_denied":
        return _popup("gdrive-cancelled", "Google Drive connection canceled. You can close this window.")
    if error or not code:
        return _popup("gdrive-error", "Google couldn't complete the connection. Close this window and try again.", 400)
    try:
        await GoogleDriveService(user_id).exchange_code(code, _google_redirect_uri())
    except GoogleDriveError as exc:
        return _popup("gdrive-error", exc.detail, exc.status)
    return _popup("gdrive-connected", "Google Drive connected. You can close this window.")


@router.post("/folders", status_code=201)
async def create_folder(body: FolderCreate, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.create_folder(conn, company_id=company_id, parent_id=body.parent_id, name=body.name, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.get("/folders/{folder_id}")
async def get_folder(folder_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.list_folder(conn, company_id=company_id, folder_id=folder_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.patch("/folders/{folder_id}")
async def update_folder(folder_id: UUID, body: FolderUpdate, current_user: CurrentUser = Depends(require_admin_or_client)):
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
async def delete_folder(folder_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            await svc.delete_folder(conn, company_id=company_id, folder_id=folder_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.get("/folders/{folder_id}/grants")
async def list_grants(folder_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return {"grants": await svc.list_grants(conn, company_id=company_id, folder_id=folder_id, actor=actor)}
        except DriveError as exc:
            _raise(exc)


@router.put("/folders/{folder_id}/grants")
async def set_grant(folder_id: UUID, body: GrantSet, current_user: CurrentUser = Depends(require_admin_or_client)):
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
async def remove_grant(folder_id: UUID, user_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
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
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _business_company(current_user)
    data = await file.read(svc.MAX_FILE_BYTES + 1)
    try:
        # Validation + text extraction happen before taking a connection.
        prepared = await svc.prepare_file(file.filename or "file", data)
    except DriveError as exc:
        _raise(exc)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.store_file(
                conn, company_id=company_id, folder_id=folder_id, prepared=prepared,
                uploaded_by=current_user.id, actor=actor,
            )
        except DriveError as exc:
            _raise(exc)


@router.get("/files/{file_id}")
async def get_file(file_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.get_file(conn, company_id=company_id, file_id=file_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.get("/files/{file_id}/download")
async def download_file(file_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            return await svc.presign_download(conn, company_id=company_id, file_id=file_id, actor=actor)
        except DriveError as exc:
            _raise(exc)


@router.patch("/files/{file_id}")
async def update_file(file_id: UUID, body: FileUpdate, current_user: CurrentUser = Depends(require_admin_or_client)):
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
async def delete_file(file_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_company(current_user)
    async with get_connection() as conn:
        actor = await svc.load_actor(conn, user=current_user, company_id=company_id)
        try:
            await svc.soft_delete_file(conn, company_id=company_id, file_id=file_id, actor=actor)
        except DriveError as exc:
            _raise(exc)
