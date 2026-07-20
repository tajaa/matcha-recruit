"""Attachments scoped to a single kanban task (upload / list / delete).

Split out of `tasks.py` (2026-07-19). Handlers moved verbatim -- no path,
signature, or response-shape change.
"""
import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work.projects import (
    ALLOWED_PROJECT_FILE_EXTENSIONS,
    PROJECT_FILE_MAX_BYTES,
)
from app.matcha.routes.matcha_work._shared import _resolve_file_urls, _verify_project_access

logger = logging.getLogger(__name__)
router = APIRouter()

async def _verify_task_belongs_to_project(project_id: UUID, task_id: UUID) -> None:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

@router.post("/projects/{project_id}/tasks/{task_id}/files")
async def upload_task_file_endpoint(
    project_id: UUID,
    task_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload an attachment scoped to a single kanban task."""
    from app.matcha.services import project_file_service

    project, _role = await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)
    company_id = project.get("company_id") or await get_client_company_id(current_user)

    fname = file.filename or "file"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_PROJECT_FILE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    content = await file.read()
    if len(content) > PROJECT_FILE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    storage_url = await get_storage().upload_file(
        content, fname,
        prefix=f"matcha-work/{company_id}/{project_id}/tasks/{task_id}/files",
        content_type=file.content_type,
    )

    record = await project_file_service.add_project_file(
        project_id=project_id,
        uploaded_by=current_user.id,
        filename=fname,
        storage_url=storage_url,
        content_type=file.content_type,
        file_size=len(content),
        task_id=task_id,
    )
    return _resolve_file_urls([record])[0]

@router.get("/projects/{project_id}/tasks/{task_id}/files")
async def list_task_files_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import project_file_service
    await _verify_project_access(project_id, current_user)
    await _verify_task_belongs_to_project(project_id, task_id)
    files = await project_file_service.list_task_files(project_id, task_id)
    return _resolve_file_urls(files)

@router.delete("/projects/{project_id}/tasks/{task_id}/files/{file_id}")
async def delete_task_file_endpoint(
    project_id: UUID,
    task_id: UUID,
    file_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    record = await project_file_service.get_task_file(file_id, project_id, task_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        await get_storage().delete_file(record["storage_url"])
    except Exception:
        pass

    await project_file_service.delete_project_file(file_id, project_id)
    return {"deleted": True}
