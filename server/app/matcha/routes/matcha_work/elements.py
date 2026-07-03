"""Project elements (context-repo bindings: files/folders/notes bucket),
their CRUD, repo-snapshot sync, and files/folders/notes sub-resources.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client
from app.matcha.routes.matcha_work._shared import (
    _can_edit_project,
    _verify_element_in_project,
    _verify_project_access,
)

router = APIRouter()

async def _list_project_elements(project_id: UUID) -> list[dict]:
    """Project elements with resolved assignee names. Shared by the /elements
    endpoint and the /bundle aggregate so the query stays in one place."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id, e.project_id, e.name, e.kind, e.description,
                   e.assigned_to, e."order", e.repo_paths, e.repo_branch,
                   e.created_at, e.updated_at,
                   COALESCE(c.name, CONCAT(emp.first_name, ' ', emp.last_name), a.name) AS assigned_name
            FROM mw_project_elements e
            LEFT JOIN clients c ON c.user_id::text = e.assigned_to
            LEFT JOIN employees emp ON emp.user_id::text = e.assigned_to
            LEFT JOIN admins a ON a.user_id::text = e.assigned_to
            WHERE e.project_id = $1
            ORDER BY e."order" ASC, e.created_at ASC
            """,
            str(project_id),
        )
    return [_serialize_element(dict(r)) for r in rows]

@router.get("/projects/{project_id}/elements")
async def list_project_elements(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    return await _list_project_elements(project_id)

@router.post("/projects/{project_id}/elements", status_code=201)
async def create_project_element(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    kind = body.get("kind")
    description = body.get("description")
    assigned_to = body.get("assigned_to") or None
    repo_paths = body.get("repo_paths") or []
    repo_branch = body.get("repo_branch") or None
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_project_elements (project_id, name, kind, description, assigned_to, repo_paths, repo_branch)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, project_id, name, kind, description, assigned_to, "order",
                      repo_paths, repo_branch, created_at, updated_at
            """,
            str(project_id), name, kind, description, assigned_to, repo_paths, repo_branch,
        )
        assigned_name = None
        if assigned_to:
            name_row = await conn.fetchrow(
                """
                SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name) AS n
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id::text = $1
                """,
                assigned_to,
            )
            if name_row:
                assigned_name = name_row["n"]
    d = _serialize_element(dict(row))
    d["assigned_name"] = assigned_name
    return d

@router.patch("/projects/{project_id}/elements/{element_id}")
async def update_project_element(
    project_id: UUID,
    element_id: str,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM mw_project_elements WHERE id = $1 AND project_id = $2",
            element_id, str(project_id),
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Element not found")

        patch = {}
        for key in ("name", "kind", "description"):
            if key in body:
                patch[key] = body[key]
        if "assigned_to" in body:
            patch["assigned_to"] = body["assigned_to"] or None
        if "order" in body:
            patch["order"] = body["order"]
        if "repo_paths" in body:
            patch["repo_paths"] = body["repo_paths"] or []
        if "repo_branch" in body:
            patch["repo_branch"] = body["repo_branch"] or None

        cols = ('id, project_id, name, kind, description, assigned_to, "order", '
                "repo_paths, repo_branch, created_at, updated_at")
        if not patch:
            row = await conn.fetchrow(
                f"SELECT {cols} FROM mw_project_elements WHERE id = $1",
                element_id,
            )
        else:
            # Quote each identifier — "order" is a reserved PostgreSQL keyword.
            set_clauses = ", ".join(f'"{k}" = ${i+2}' for i, k in enumerate(patch))
            values = list(patch.values())
            row = await conn.fetchrow(
                f"""
                UPDATE mw_project_elements
                SET {set_clauses}, updated_at = now()
                WHERE id = $1
                RETURNING {cols}
                """,
                element_id, *values,
            )

        assigned_to = dict(row).get("assigned_to")
        assigned_name = None
        if assigned_to:
            name_row = await conn.fetchrow(
                """
                SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name) AS n
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id::text = $1
                """,
                assigned_to,
            )
            if name_row:
                assigned_name = name_row["n"]
    d = _serialize_element(dict(row))
    d["assigned_name"] = assigned_name
    return d

@router.delete("/projects/{project_id}/elements/{element_id}")
async def delete_project_element(
    project_id: UUID,
    element_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_project_elements WHERE id = $1 AND project_id = $2",
            element_id, str(project_id),
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Element not found")
    return {"deleted": True}

@router.put("/projects/{project_id}/elements/{element_id}/repo-snapshot")
async def put_element_repo_snapshot(
    project_id: UUID,
    element_id: str,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Connector uploads the element's code snapshot. Edit-gated."""
    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    async with get_connection() as conn:
        await _verify_element_in_project(conn, project_id, element_id)
    from app.matcha.services import element_repo_service as repo_svc
    summary = await repo_svc.replace_element_snapshot(project_id, element_id, body.get("files") or [])
    return summary

@router.get("/projects/{project_id}/elements/{element_id}/repo-snapshot/stats")
async def get_element_repo_snapshot_stats(
    project_id: UUID,
    element_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import element_repo_service as repo_svc
    return await repo_svc.get_snapshot_stats(element_id)

def _serialize_element(d: dict) -> dict:
    for k in ("id", "project_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    for k in ("created_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d

@router.get("/projects/{project_id}/elements/{element_id}/files")
async def list_element_files_endpoint(
    project_id: UUID,
    element_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Files bucketed under one element's context repo."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    async with get_connection() as conn:
        await _verify_element_in_project(conn, project_id, element_id)
    return await project_file_service.list_element_files(project_id, element_id)

@router.get("/projects/{project_id}/elements/{element_id}/folders")
async def list_element_folders_endpoint(
    project_id: UUID,
    element_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Folder tree scoped to one element."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    async with get_connection() as conn:
        await _verify_element_in_project(conn, project_id, element_id)
    return await project_file_service.list_element_folders(project_id, element_id)

@router.post("/projects/{project_id}/elements/{element_id}/folders", status_code=201)
async def create_element_folder_endpoint(
    project_id: UUID,
    element_id: str,
    name: str = Body(..., embed=True),
    parent_id: Optional[UUID] = Body(default=None, embed=True),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a folder inside an element's repo (optionally nested)."""
    from app.matcha.services import project_file_service

    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    async with get_connection() as conn:
        await _verify_element_in_project(conn, project_id, element_id)
    clean = (name or "").strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Folder name required")
    return await project_file_service.create_project_folder(
        project_id=project_id, name=clean, parent_id=parent_id,
        created_by=current_user.id, element_id=element_id,
    )

@router.get("/projects/{project_id}/elements/{element_id}/notes")
async def list_element_notes_endpoint(
    project_id: UUID,
    element_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Notes + links pinned to an element."""
    from app.matcha.services import element_notes_service

    await _verify_project_access(project_id, current_user)
    async with get_connection() as conn:
        await _verify_element_in_project(conn, project_id, element_id)
    return await element_notes_service.list_element_notes(project_id, element_id)

@router.post("/projects/{project_id}/elements/{element_id}/notes", status_code=201)
async def add_element_note_endpoint(
    project_id: UUID,
    element_id: str,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Pin a note ('note', free text) or a link ('link', url) to an element."""
    from app.matcha.services import element_notes_service

    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    async with get_connection() as conn:
        await _verify_element_in_project(conn, project_id, element_id)
    try:
        rec = await element_notes_service.add_element_note(
            project_id=project_id,
            element_id=element_id,
            created_by=current_user.id,
            kind=body.get("kind", "note"),
            body=body.get("body"),
            url=body.get("url"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rec:
        raise HTTPException(status_code=404, detail="Element not found")
    return rec

@router.delete("/projects/{project_id}/elements/{element_id}/notes/{note_id}")
async def delete_element_note_endpoint(
    project_id: UUID,
    element_id: str,
    note_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import element_notes_service

    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    ok = await element_notes_service.delete_element_note(project_id, element_id, note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": True}
