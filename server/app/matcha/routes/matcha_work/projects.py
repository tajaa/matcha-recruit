"""Project CRUD, discipline (+ signature webhook), blog, and project-scoped
files/folders/links.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import asyncio
import json
import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile

from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_company_member, get_client_company_id
from app.matcha.routes.matcha_work.elements import _list_project_elements
from app.matcha.routes.matcha_work.pdf_export import _render_project_pdf
from app.matcha.routes.matcha_work._shared import (
    _can_edit_project,
    _resolve_file_urls,
    _verify_element_in_project,
    _verify_project_access,
)

logger = logging.getLogger(__name__)
router = APIRouter()
public_router = APIRouter()

@router.get("/projects")
async def list_projects_endpoint(
    status: Optional[str] = Query(None, pattern="^(active|archived|completed)$"),
    hiring_client_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_company_member),
):
    """List all projects for the current user."""
    from app.matcha.services import project_service as proj_svc
    if current_user.role == "admin":
        # Include the admin's tenant-scoped company so they see projects
        # owned by that company even when they're not explicitly seeded
        # as a collaborator (e.g., legacy projects, projects created by
        # other admins under the same tenant).
        admin_company_id = await get_client_company_id(current_user)
        return await proj_svc.list_projects(admin_company_id, status, user_id=current_user.id)
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    projects = await proj_svc.list_projects(company_id, status, user_id=current_user.id, hiring_client_id=hiring_client_id)
    # werk-lite whole-company access: employees may list company boards, but the
    # HR-sensitive project types (discipline cases, recruiting pipelines) are
    # also stored as mw_projects under the same company_id — never expose those
    # to a regular employee. Admins/clients keep full visibility (the /work product).
    if current_user.role == "employee":
        projects = [p for p in projects if p.get("project_type") not in ("discipline", "recruiting")]
    return projects

@router.post("/projects", status_code=201)
async def create_project_endpoint(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new project with an auto-created first chat."""
    from app.matcha.services import project_service as proj_svc
    from app.matcha.services import entitlements_service
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    title = body.get("title", "Untitled Project")
    project_type = body.get("project_type", "general")

    # Plan gate (creation only — existing projects stay readable/editable):
    # solo types need Lite+, collab/recruiting need Pro/Business.
    if project_type in entitlements_service.COLLAB_PROJECT_TYPES:
        await entitlements_service.require_plan(current_user.id, entitlements_service.PLAN_PRO, "projects_collab")
    else:
        await entitlements_service.require_plan(current_user.id, entitlements_service.PLAN_LITE, "projects_solo")
    icon = body.get("icon")
    hiring_client_id_raw = body.get("hiring_client_id")
    hiring_client_id = UUID(hiring_client_id_raw) if hiring_client_id_raw else None

    extra_data: Optional[dict] = None
    if project_type == "blog":
        blog = body.get("blog") or {}
        extra_data = {
            "title": title,
            "audience": blog.get("audience"),
            "tone": blog.get("tone"),
            "tags": blog.get("tags") or [],
            "author": blog.get("author") or {},
        }

    # Optional starter template (e.g. "proposal", "project_brief"). Only
    # honored for general projects; backend ignores it for other types so
    # blog/recruiting/discipline keep their own seeding paths intact.
    template_id = body.get("template")
    if template_id and project_type == "general":
        extra_data = dict(extra_data or {})
        extra_data["template"] = template_id

    try:
        return await proj_svc.create_project(
            company_id, current_user.id, title, project_type,
            hiring_client_id=hiring_client_id, icon=icon, extra_data=extra_data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/projects/{project_id}")
async def get_project_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Get a project with its chat list."""
    project, _role = await _verify_project_access(project_id, current_user)
    return project

@router.get("/projects/{project_id}/bundle")
async def get_project_bundle_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """One-shot collab project open for the desktop (werk) client: project
    detail + kanban tasks (with embedded attachments) + files + folders + links
    + collaborators + elements in a single round-trip.

    Each field is produced by the SAME service call + post-processing as the
    individual endpoint (GET …/tasks, …/files, …/folders, …/links,
    …/collaborators, …/elements), so the client decodes + caches them
    identically. Verifies access ONCE, then runs the six independent reads
    concurrently — replacing the ~6 sequential round-trips the client used to
    fire on every project open."""
    from app.matcha.services import project_task_service as pt_svc
    from app.matcha.services import project_file_service
    from app.matcha.services import project_service as proj_svc
    project, _role = await _verify_project_access(project_id, current_user)

    async def _tasks_with_attachments() -> list[dict]:
        # Mirror list_project_tasks_endpoint: embed presigned attachments per
        # task so kanban cards render thumbnails without N+1 follow-ups.
        # Week-scoped Done: the desktop board opens from this bundle and pulls
        # earlier finishes on demand. `done_total` below carries the real count.
        tasks = await pt_svc.list_project_tasks(project_id, viewer_id=current_user.id,
                                                done_scope=pt_svc.DONE_SCOPE_WEEK)
        if not tasks:
            return tasks
        task_ids = [UUID(t["id"]) for t in tasks if t.get("id")]
        grouped = await project_file_service.list_files_for_tasks(project_id, task_ids)
        for t in tasks:
            t["attachments"] = _resolve_file_urls(grouped.get(t["id"], []))
        return tasks

    tasks, files, folders, links, collaborators, elements, done_count = await asyncio.gather(
        _tasks_with_attachments(),
        project_file_service.list_project_files(project_id),
        project_file_service.list_project_folders(project_id),
        proj_svc.list_project_links(project_id),
        proj_svc.list_collaborators(project_id),
        _list_project_elements(project_id),
        pt_svc.count_done_tasks(project_id),
    )
    return {
        "project": project,
        "tasks": tasks,
        "files": files,
        "folders": folders,
        "links": links,
        "collaborators": collaborators,
        "elements": elements,
        # `tasks` carries only this week's Done cards (see list_project_tasks).
        # The board needs the full count to label its expander.
        "done_total": done_count["total"],
    }

@router.patch("/projects/{project_id}")
async def update_project_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update project title, status, or hiring client.

    Pin is per-user: a stray `is_pinned` in the body is intercepted and
    routed through the per-user pin store so existing clients keep
    working without flipping the global flag for everyone else.
    """
    from app.matcha.services import project_service as proj_svc
    from app.matcha.services import recruiting_client_service as rc_svc
    project, _role = await _verify_project_access(project_id, current_user)

    # Per-user pin handoff (legacy API compat). Don't write to the global
    # is_pinned column anymore — pin lives in mw_project_pins per caller.
    if "is_pinned" in body:
        new_pinned = bool(body.pop("is_pinned"))
        await proj_svc.set_project_pin(current_user.id, project_id, new_pinned)
        # Reflect the new pin state on the project we already loaded so a
        # pin-only request still returns a coherent response.
        project["is_pinned"] = new_pinned

    if "hiring_client_id" in body and body["hiring_client_id"] is not None:
        company_id = await get_client_company_id(current_user)
        try:
            body["hiring_client_id"] = UUID(body["hiring_client_id"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid hiring_client_id")
        if company_id is None or not await rc_svc.get_client(body["hiring_client_id"], company_id):
            raise HTTPException(status_code=400, detail="Hiring client does not belong to this workspace")

    if not body:
        # Pin-only request — return the project shape we already loaded
        # via _verify_project_access. Avoids a second DB roundtrip and
        # works for cross-tenant collaborators (whose project doesn't
        # match the caller's company_id and would 404 via get_project).
        return project
    return await proj_svc.update_project(project_id, body)

@router.post("/projects/{project_id}/pin")
async def set_project_pin_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Set the per-user star/pin on a project. Body: `{is_pinned: bool}`."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    pinned = bool(body.get("is_pinned", True))
    await proj_svc.set_project_pin(current_user.id, project_id, pinned)
    return {"is_pinned": pinned}

@router.delete("/projects/{project_id}")
async def archive_project_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Archive a project."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    await proj_svc.archive_project(project_id)
    return {"status": "archived"}

@router.delete("/projects/{project_id}/permanent", status_code=204)
async def delete_project_permanent_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Hard-delete a project along with all its threads and messages."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    await proj_svc.delete_project_permanent(project_id)

@router.post("/projects/{project_id}/unarchive")
async def unarchive_project_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Restore an archived project to active status."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    await proj_svc.unarchive_project(project_id)
    return {"status": "active"}

@router.patch("/projects/{project_id}/discipline")
async def patch_discipline_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update discipline project_data (employee, infraction, level)."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    try:
        return await proj_svc.patch_discipline(project_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/projects/{project_id}/discipline/meeting-held")
async def discipline_meeting_held_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Stamp meeting_held_at. Required gate before signature can be requested."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.mark_discipline_meeting_held(project_id)

@router.post("/projects/{project_id}/discipline/signature/request")
async def discipline_request_signature_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send the discipline document for digital signature.

    Renders the project's current sections to PDF, hands the bytes to
    the configured SignatureProvider, and records the envelope id +
    requested_at on the project's signature blob. The webhook handler
    flips draft_status to 'signed' once the recipient signs.
    """
    from app.matcha.services import project_service as proj_svc
    from app.matcha.services.signature_provider import get_signature_provider

    project, _ = await _verify_project_access(project_id, current_user)

    recipient_email = (body.get("employee_email") or body.get("recipient_email") or "").strip()
    if not recipient_email:
        raise HTTPException(status_code=400, detail="employee_email is required")

    if project.get("project_type") != "discipline":
        raise HTTPException(status_code=400, detail="Not a discipline project")

    pdata = project.get("project_data") or {}
    if not pdata.get("meeting_held_at"):
        raise HTTPException(status_code=400, detail="Confirm the disciplinary meeting was held before sending for signature.")

    pdf_bytes = await _render_project_pdf(project)

    provider = get_signature_provider()
    employee = pdata.get("employee") or {}
    result = await provider.send(
        recipient_email=recipient_email,
        recipient_name=employee.get("name"),
        document_pdf=pdf_bytes,
        subject=f"Disciplinary action: {project.get('title') or 'Document'}",
        metadata={"project_id": str(project_id), "kind": "discipline"},
    )

    return await proj_svc.record_discipline_signature_request(
        project_id,
        envelope_id=result.envelope_id,
        method="digital",
        recipient_email=recipient_email,
    )

@router.post("/projects/{project_id}/discipline/signature/refuse")
async def discipline_refuse_signature_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Mark the project as Employee Refused to Sign. Closes the workflow."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    notes = (body.get("notes") or "").strip()
    if len(notes) < 20:
        raise HTTPException(status_code=400, detail="Refusal notes must be at least 20 characters.")
    return await proj_svc.record_discipline_refused(project_id, notes=notes)

@router.post("/projects/{project_id}/discipline/signature/upload-physical")
async def discipline_upload_physical_endpoint(
    project_id: UUID,
    file: UploadFile = File(..., description="Scanned signed PDF"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Accept a scan of a physically-signed discipline document.

    Stores the scan via the existing storage service and records the
    storage path on the project's signature blob. Closes the workflow.
    """
    from app.matcha.services import project_service as proj_svc
    project_record, _ = await _verify_project_access(project_id, current_user)
    company_id = project_record.get("company_id") if isinstance(project_record, dict) else None
    if not company_id:
        company_id = await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")

    contents = await file.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")

    storage = get_storage()
    filename = file.filename or f"signed-{project_id}.pdf"
    storage_path = await storage.upload_file(
        contents,
        filename,
        prefix=f"matcha-work/{company_id}/{project_id}/discipline-signed",
        content_type="application/pdf",
    )

    # Surface in the project's Files panel so HR can find it the same
    # way they find any other project attachment.
    from app.matcha.services import project_file_service as file_svc
    await file_svc.add_project_file(
        project_id=project_id,
        uploaded_by=current_user.id,
        filename=filename,
        storage_url=storage_path,
        content_type="application/pdf",
        file_size=len(contents),
    )

    return await proj_svc.record_discipline_signed(
        project_id,
        signed_pdf_storage_path=storage_path,
        method="physical",
    )

@public_router.post("/signature/webhook")
async def signature_webhook(request: Request):
    """Provider webhook fan-in for completed e-signatures.

    Mounted on the matcha-work public router so the e-sign provider can
    POST without an authenticated session. URL: /api/matcha-work/public/signature/webhook
    Configure DocuSeal (or other provider) to point at this path.

    HMAC verification (X-Docuseal-Signature header) is required — see
    matcha/services/signature_provider.py:verify_webhook_signature.
    """
    from app.matcha.services import project_service as proj_svc
    from app.matcha.services.signature_provider import get_signature_provider, verify_webhook_signature

    raw = await request.body()
    sig_header = (
        request.headers.get("X-Docuseal-Signature")
        or request.headers.get("X-DocuSeal-Signature")
        or request.headers.get("X-Signature")
        or ""
    )
    provider = get_signature_provider()
    if not sig_header or not verify_webhook_signature(provider, raw, sig_header):
        logger.warning("[matcha_work signature_webhook] HMAC verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    envelope_id = body.get("envelope_id")
    project_id_raw = body.get("project_id")
    status_value = body.get("status") or "completed"
    if not envelope_id or not project_id_raw:
        raise HTTPException(status_code=400, detail="envelope_id and project_id required")
    if status_value != "completed":
        return {"ok": True, "ignored": True}

    project_id = UUID(project_id_raw)

    # Integrity check: only honor a webhook for an envelope that we
    # actually issued from this project. Without this anyone with the
    # endpoint could mark any project signed by sending a bogus body.
    # Concrete providers should also verify the request signature
    # via the SignatureProvider.webhook_secret() — that work lands
    # when a real provider replaces the stub.
    project = await proj_svc.get_project_raw(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    pdata = project.get("project_data") or {}
    expected_envelope = ((pdata.get("signature") or {}).get("envelope_id"))
    if not expected_envelope or expected_envelope != envelope_id:
        raise HTTPException(status_code=403, detail="Envelope does not match this project")

    provider = get_signature_provider()
    signed_bytes = await provider.fetch_signed_pdf(envelope_id)
    storage_path: Optional[str] = None
    if signed_bytes:
        company_id = project.get("company_id")
        uploaded_by = project.get("created_by")
        if company_id:
            storage = get_storage()
            filename = f"signed-{envelope_id}.pdf"
            storage_path = await storage.upload_file(
                signed_bytes,
                filename,
                prefix=f"matcha-work/{company_id}/{project_id}/discipline-signed",
                content_type="application/pdf",
            )
            # No authenticated user on a webhook — attribute to the
            # project creator so the file row has a valid uploaded_by.
            if uploaded_by:
                from app.matcha.services import project_file_service as file_svc
                await file_svc.add_project_file(
                    project_id=project_id,
                    uploaded_by=uploaded_by,
                    filename=filename,
                    storage_url=storage_path,
                    content_type="application/pdf",
                    file_size=len(signed_bytes),
                )
    await proj_svc.record_discipline_signed(
        project_id,
        signed_pdf_storage_path=storage_path,
        method="digital",
    )
    return {"ok": True}

@router.patch("/projects/{project_id}/blog")
async def patch_blog_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    try:
        return await proj_svc.patch_blog(project_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/projects/{project_id}/blog/status")
async def transition_blog_status_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    to = (body or {}).get("to")
    if not to:
        raise HTTPException(status_code=400, detail="Missing 'to'")
    try:
        return await proj_svc.transition_blog_status(project_id, to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Re-exported from the service (the single owner of the project-file upload
# policy) — `tasks.py` and `threads.py` import these names from here.
from app.matcha.services.project_file_service import (  # noqa: E402
    ALLOWED_PROJECT_FILE_EXTENSIONS,
    PROJECT_FILE_MAX_BYTES,
)

ALLOWED_BLOG_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic",
    ".mp4", ".mov", ".m4v", ".webm",
}

BLOG_MEDIA_MAX_BYTES = 50 * 1024 * 1024  # 50 MB

@router.post("/projects/{project_id}/files")
async def upload_project_file(
    project_id: UUID,
    file: UploadFile = File(...),
    element_id: Optional[str] = Form(default=None),
    folder_id: Optional[str] = Form(default=None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a file attachment to a project. Pass `element_id` to bucket it
    under an element's context repo (and optionally `folder_id` for a folder
    within that repo); omit both for the project's root Files tab."""
    from app.matcha.services import project_file_service

    project, _role = await _verify_project_access(project_id, current_user)
    company_id = project.get("company_id")
    if not company_id:
        company_id = await get_client_company_id(current_user)

    # Element-scoped uploads follow the same owner/editor gate + ownership check
    # as the element folder/note write endpoints (root uploads stay open to any
    # member, matching the existing Files tab behaviour).
    if element_id:
        if not _can_edit_project(_role):
            raise HTTPException(status_code=403, detail="You don't have edit access to this project")
        async with get_connection() as conn:
            await _verify_element_in_project(conn, project_id, element_id)

    return await project_file_service.validate_and_store_project_upload(
        file,
        project_id=project_id,
        uploaded_by=current_user.id,
        prefix=f"matcha-work/{company_id}/{project_id}/files",
        element_id=element_id,
        folder_id=folder_id,
    )

@router.get("/projects/{project_id}/files")
async def list_project_files_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List file attachments for a project."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    return await project_file_service.list_project_files(project_id)

@router.delete("/projects/{project_id}/files/{file_id}")
async def delete_project_file_endpoint(
    project_id: UUID,
    file_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a file attachment from a project."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)

    record = await project_file_service.get_project_file(file_id, project_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from storage
    try:
        await get_storage().delete_file(record["storage_url"])
    except Exception:
        pass

    await project_file_service.delete_project_file(file_id, project_id)
    return {"deleted": True}

@router.get("/projects/{project_id}/folders")
async def list_project_folders_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List folders for a project's Files tab."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    return await project_file_service.list_project_folders(project_id)

@router.post("/projects/{project_id}/folders")
async def create_project_folder_endpoint(
    project_id: UUID,
    name: str = Body(..., embed=True),
    parent_id: Optional[UUID] = Body(default=None, embed=True),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a folder (optionally nested under parent_id)."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    clean = (name or "").strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Folder name required")
    return await project_file_service.create_project_folder(
        project_id=project_id, name=clean, parent_id=parent_id,
        created_by=current_user.id,
    )

@router.patch("/projects/{project_id}/folders/{folder_id}")
async def update_project_folder_endpoint(
    project_id: UUID,
    folder_id: UUID,
    name: Optional[str] = Body(default=None, embed=True),
    parent_id: Optional[UUID] = Body(default=None, embed=True),
    move_to_root: bool = Body(default=False, embed=True),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Rename and/or reparent a folder. move_to_root=true sends it to the root."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    rec = await project_file_service.update_project_folder(
        folder_id=folder_id, project_id=project_id,
        name=name, parent_id=parent_id, clear_parent=move_to_root,
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Folder not found")
    return rec

@router.delete("/projects/{project_id}/folders/{folder_id}")
async def delete_project_folder_endpoint(
    project_id: UUID,
    folder_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a folder; its files fall back to the root."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    ok = await project_file_service.delete_project_folder(folder_id, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"deleted": True}

@router.patch("/projects/{project_id}/files/{file_id}")
async def move_project_file_endpoint(
    project_id: UUID,
    file_id: UUID,
    folder_id: Optional[UUID] = Body(default=None, embed=True),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Move a file into a folder (folder_id) or to the root (null)."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    rec = await project_file_service.move_file_to_folder(file_id, project_id, folder_id)
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")
    return rec

@router.post("/projects/{project_id}/files/{file_id}/copy")
async def copy_project_file_endpoint(
    project_id: UUID,
    file_id: UUID,
    folder_id: UUID = Body(..., embed=True),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Copy a file into a folder, leaving the original (Media "Add to Files")."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    rec = await project_file_service.copy_file_to_folder(file_id, project_id, folder_id)
    if not rec:
        raise HTTPException(status_code=404, detail="File or folder not found")
    return rec

@router.post("/projects/{project_id}/files/sync-chat")
async def sync_chat_files_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Backfill the project's Files/Media with all discussion-chat attachments.
    Idempotent — called when the Media tab opens so screenshots dropped in chat
    show up even if the per-message mirror didn't run."""
    from app.matcha.services import project_file_service

    await _verify_project_access(project_id, current_user)
    added = await project_file_service.backfill_project_chat_files(project_id)
    return {"added": added}

@router.get("/projects/{project_id}/links")
async def list_project_links_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Links shared in the collab chat — http(s) URLs pulled from messages."""
    from app.matcha.services import project_service

    await _verify_project_access(project_id, current_user)
    return await project_service.list_project_links(project_id)

@router.post("/projects/{project_id}/submit-blog")
async def submit_blog_for_review(
    project_id: UUID,
    body: dict = Body(default_factory=dict),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Submit a Matcha Work blog project to master admin for review.

    Creates (or refreshes) a blog_posts row in 'draft' status with
    submitted_for_review=TRUE so admins see it in their Pending Review queue.
    Re-submitting the same project updates the existing draft instead of
    creating a duplicate. Admins approve by flipping status to 'published';
    reject by clearing submitted_for_review with review_notes.
    """
    project, _role = await _verify_project_access(project_id, current_user)
    if project.get("project_type") != "blog":
        raise HTTPException(status_code=400, detail="Only blog projects can be submitted for review")

    title = (project.get("title") or "Untitled").strip() or "Untitled"
    sections = project.get("sections") or []
    pdata = project.get("project_data") or {}

    # Stitch sections into one markdown document the same way the project
    # markdown export does, minus the frontmatter.
    md_parts: list[str] = [f"# {title}\n"]
    for s in sections:
        if s.get("title"):
            md_parts.append(f"## {s['title']}\n")
        md_parts.append((s.get("content") or "") + "\n")
    content_md = "\n".join(md_parts)

    excerpt_raw = (body.get("excerpt") or pdata.get("excerpt") or "").strip() or None
    cover_image = (body.get("cover_image") or pdata.get("cover_image") or "").strip() or None
    tags = body.get("tags") or pdata.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    submitter_notes = (body.get("notes") or "").strip() or None

    # Slug from project_data if blog-mode populated it, else slugify the title.
    raw_slug = (pdata.get("slug") or "").strip() or _slugify_blog(title)
    base_slug = raw_slug

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT id, slug, status FROM blog_posts
            WHERE source_project_id = $1
            ORDER BY created_at DESC LIMIT 1
            """,
            project_id,
        )

        if existing and existing["status"] != "published":
            # Refresh existing draft / previously-rejected submission.
            await conn.execute(
                """
                UPDATE blog_posts SET
                    title = $1,
                    content = $2,
                    excerpt = COALESCE($3, excerpt),
                    cover_image = COALESCE($4, cover_image),
                    tags = $5::jsonb,
                    submitted_for_review = TRUE,
                    submitted_at = NOW(),
                    submitter_id = $6,
                    review_notes = $7,
                    status = 'draft',
                    updated_at = NOW()
                WHERE id = $8
                """,
                title, content_md, excerpt_raw, cover_image,
                json.dumps(tags), current_user.id, submitter_notes, existing["id"],
            )
            return {"id": str(existing["id"]), "slug": existing["slug"], "resubmitted": True}

        # New submission — pick a unique slug
        slug = base_slug
        attempt = 1
        while await conn.fetchval("SELECT 1 FROM blog_posts WHERE slug = $1", slug):
            attempt += 1
            slug = f"{base_slug}-{attempt}"

        row = await conn.fetchrow(
            """
            INSERT INTO blog_posts (
                author_id, title, slug, content, excerpt, cover_image,
                status, tags, submitted_for_review, submitted_at,
                submitter_id, source_project_id, review_notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'draft', $7::jsonb, TRUE, NOW(), $1, $8, $9)
            RETURNING id, slug
            """,
            current_user.id, title, slug, content_md, excerpt_raw, cover_image,
            json.dumps(tags), project_id, submitter_notes,
        )
        return {"id": str(row["id"]), "slug": row["slug"], "resubmitted": False}

def _slugify_blog(text: str) -> str:
    import re as _re
    s = _re.sub(r"[^a-z0-9\s-]", "", (text or "").lower()).strip()
    s = _re.sub(r"\s+", "-", s)
    s = _re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "untitled"

@router.post("/projects/{project_id}/blog-media")
async def upload_blog_media(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload an inline image or short video for a blog post. Returns {url, kind}.
    The caller embeds the URL in section markdown (image or <video> tag)."""
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = project.get("company_id") or await get_client_company_id(current_user)

    fname = file.filename or "file"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_BLOG_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported media type: {ext}")

    content = await file.read()
    if len(content) > BLOG_MEDIA_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB limit")

    storage_url = await get_storage().upload_file(
        content, fname,
        prefix=f"matcha-work/{company_id}/{project_id}/blog-media",
        content_type=file.content_type,
    )
    kind = "video" if ext in {".mp4", ".mov", ".m4v", ".webm"} else "image"
    return {"url": storage_url, "kind": kind, "filename": fname, "size": len(content)}

@router.post("/projects/{project_id}/complete")
async def complete_project_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Mark project as completed. Owner-only."""
    from app.matcha.services import project_task_service as pt_svc
    _project, role = await _verify_project_access(project_id, current_user)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can mark a project complete")
    return await pt_svc.mark_project_complete(project_id)
