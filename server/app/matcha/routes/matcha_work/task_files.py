"""Attachments scoped to a single kanban task (upload / list / delete).

Split out of `tasks.py` (2026-07-19). Handlers moved verbatim -- no path,
signature, or response-shape change.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work._shared import (
    _resolve_file_urls,
    _verify_project_access,
    _verify_task_belongs_to_project,
)

logger = logging.getLogger(__name__)
router = APIRouter()

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

    record = await project_file_service.validate_and_store_project_upload(
        file,
        project_id=project_id,
        uploaded_by=current_user.id,
        prefix=f"matcha-work/{company_id}/{project_id}/tasks/{task_id}/files",
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
        # The DB row is deleted regardless — a stranded blob is preferable to a
        # 500 on an otherwise-successful delete. Log so it can be reaped later.
        logger.warning(
            "Failed to delete task file blob from storage: %s",
            record.get("storage_url"),
            exc_info=True,
        )

    await project_file_service.delete_project_file(file_id, project_id)
    return {"deleted": True}
