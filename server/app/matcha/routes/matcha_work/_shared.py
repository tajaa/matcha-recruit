"""Cross-cutting helpers used by 2+ submodules of the matcha_work package.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md for the module map.
"""
import json
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id
from app.matcha.models.matcha_work import MWMessageOut, ThreadDetailResponse
from app.matcha.services import matcha_work_document as doc_svc
from app.matcha.services.matcha_work_ai import _infer_skill_from_state

RESUME_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}

RESUME_UPLOAD_MAX_BYTES = 10 * 1024 * 1024

def _row_to_message(row: dict) -> MWMessageOut:
    raw_meta = row.get("metadata")
    if isinstance(raw_meta, str):
        try:
            raw_meta = json.loads(raw_meta)
        except (json.JSONDecodeError, TypeError):
            raw_meta = None
    # Strip the server-only extracted `text` from file attachments before the
    # message reaches the client. That text is AI context (can be tens of KB),
    # not display data — the client only needs url/filename/size/kind.
    # Also presign s3:// urls so the desktop chip is clickable (CloudFront
    # urls pass through; stored url stays stable for re-extraction).
    if isinstance(raw_meta, dict) and isinstance(raw_meta.get("attachments"), list):
        _storage = get_storage()
        cleaned = []
        for a in raw_meta["attachments"]:
            if not isinstance(a, dict):
                cleaned.append(a)
                continue
            a = {k: v for k, v in a.items() if k != "text"}
            url = a.get("url") or ""
            if isinstance(url, str) and url.startswith("s3://"):
                signed = _storage.get_presigned_download_url(url, expires_in=3600)
                if signed:
                    a["url"] = signed
            cleaned.append(a)
        raw_meta = {**raw_meta, "attachments": cleaned}
    return MWMessageOut(
        id=row["id"],
        thread_id=row["thread_id"],
        role=row["role"],
        content=row["content"],
        version_created=row.get("version_created"),
        metadata=raw_meta,
        created_at=row["created_at"],
    )

async def _build_thread_detail_response(thread_id: UUID, company_id: Optional[UUID], *, user_id: UUID | None = None) -> ThreadDetailResponse:
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=user_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Use the thread's actual company_id — callers who are collaborators on a
    # thread from another company would otherwise pass their own company_id.
    thread_company_id = thread["company_id"]

    thread["current_state"] = await doc_svc.ensure_matcha_work_thread_storage_scope(
        thread_id,
        thread_company_id,
        thread["current_state"],
    )
    messages = await doc_svc.get_thread_messages(thread_id)

    # Fetch collaborators
    collaborators = []
    async with get_connection() as conn:
        collab_rows = await conn.fetch(
            """
            SELECT tc.user_id, tc.role, tc.created_at,
                   u.email, u.avatar_url,
                   COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM mw_thread_collaborators tc
            JOIN users u ON u.id = tc.user_id
            LEFT JOIN clients cl ON cl.user_id = tc.user_id
            LEFT JOIN employees e ON e.user_id = tc.user_id
            LEFT JOIN admins a ON a.user_id = tc.user_id
            WHERE tc.thread_id = $1
            ORDER BY tc.created_at
            """,
            thread_id,
        )
        collaborators = [
            {
                "user_id": str(r["user_id"]),
                "name": r["name"],
                "email": r["email"],
                "role": r["role"],
                "avatar_url": r["avatar_url"],
                "added_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in collab_rows
        ]

    from app.matcha.services.matcha_work_modes import THREAD_MODES

    return ThreadDetailResponse(
        id=thread["id"],
        title=thread["title"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
        task_type=_infer_skill_from_state(thread["current_state"]),
        is_pinned=thread.get("is_pinned", False),
        # Registry-driven so a new mode can't be silently dropped here (the
        # pre-registry version of this serializer lost payer_mode).
        **{m.column: thread.get(m.column, False) for m in THREAD_MODES},
        linked_offer_letter_id=thread.get("linked_offer_letter_id"),
        created_at=thread["created_at"],
        updated_at=thread["updated_at"],
        messages=[_row_to_message(row) for row in messages],
        collaborators=collaborators,
    )

def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"

def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

THREAD_FILE_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".json"}

THREAD_FILE_MAX_BYTES = 10 * 1024 * 1024

THREAD_FILE_TEXT_CAP = 40000

def _strip_markdown(text: str) -> str:
    """Strip common markdown syntax to produce clean plain text for project sections."""
    import re as _re
    t = text
    t = _re.sub(r'\*\*(.+?)\*\*', r'\1', t)       # **bold**
    t = _re.sub(r'__(.+?)__', r'\1', t)             # __bold__
    t = _re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', t)  # *italic*
    t = _re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', t)    # _italic_
    t = _re.sub(r'^#{1,6}\s+', '', t, flags=_re.MULTILINE)  # ## headings
    t = _re.sub(r'`(.+?)`', r'\1', t)               # `code`
    t = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t) # [text](url) → text
    t = _re.sub(r'^[\s]*[-*]\s+', '• ', t, flags=_re.MULTILINE)  # - list → • list
    t = _re.sub(r'^---+$', '', t, flags=_re.MULTILINE)  # ---
    t = _re.sub(r'^>\s*', '', t, flags=_re.MULTILINE)   # > blockquote
    return t.strip()

def _guard_sensitive_project_type(project: dict, current_user: CurrentUser) -> None:
    """werk-lite whole-company access: employees may reach company boards, but the
    HR-sensitive project types (discipline cases, recruiting pipelines) are also
    mw_projects under the same company and must stay hidden — even by direct id,
    not just absent from the board list. 404 (not 403) so existence isn't leaked.
    Admins/clients are unaffected."""
    if current_user.role == "employee" and project.get("project_type") in ("discipline", "recruiting"):
        raise HTTPException(status_code=404, detail="Project not found")

async def _verify_project_access(project_id: UUID, current_user: CurrentUser) -> tuple[dict, str]:
    """Check project access. For admins, uses collaborator table. Returns (project, role)."""
    from app.matcha.services import project_service as proj_svc
    if current_user.role == "admin":
        result = await proj_svc.get_project_as_collaborator(project_id, current_user.id)
        if result:
            return result
        raise HTTPException(status_code=404, detail="Project not found")
    company_id = await get_client_company_id(current_user)
    project = None
    if company_id:
        project = await proj_svc.get_project(project_id, company_id, user_id=current_user.id)
    if not project:
        result = await proj_svc.get_project_as_collaborator(project_id, current_user.id)
        if result:
            _guard_sensitive_project_type(result[0], current_user)
            return result
        raise HTTPException(status_code=404, detail="Project not found")
    _guard_sensitive_project_type(project, current_user)
    if not project.get("collaborator_role"):
        project["collaborator_role"] = "owner"
    return project, project["collaborator_role"]

def _can_edit_project(role: Optional[str]) -> bool:
    """Write gate for collab project content (elements, element files/folders,
    notes). Permissive on purpose: only explicit read-only roles are blocked.
    `_verify_project_access` returns role=None / 'owner' for the owner depending
    on access path, so an `in ('owner','editor')` allowlist 403s legitimate
    owners — mirror the client's `canEditElements` (viewer/commenter blocked)."""
    return role not in ("viewer", "commenter")

def _resolve_file_urls(files: list[dict]) -> list[dict]:
    """Rewrite s3:// storage_url values to short-lived presigned https URLs so
    the desktop client's AsyncImage + NSWorkspace.open can fetch them. CloudFront
    URLs pass through unchanged. FastAPI handles UUID/datetime serialization."""
    storage = get_storage()
    out = []
    for f in files:
        d = dict(f)
        url = d.get("storage_url") or ""
        if url.startswith("s3://"):
            signed = storage.get_presigned_download_url(url, expires_in=3600)
            if signed:
                d["storage_url"] = signed
        out.append(d)
    return out

def _project_company_id(project: dict):
    return project.get("company_id")

async def _parse_task_attachment_ids(task_id: UUID, raw_attachments) -> list[UUID]:
    """Validate client-supplied `attachment_ids` for a task-scoped write.

    Each id must parse as a UUID and must already own an `mw_project_files`
    row whose `task_id` is this task — never store a dangling or cross-task
    ref. Any mismatch is a 400 (the whole list is rejected, nothing is
    silently filtered out). Returns the parsed ids; `[]` when none were sent.
    """
    if not raw_attachments:
        return []
    if not isinstance(raw_attachments, list):
        raise HTTPException(status_code=400, detail="attachment_ids must be a list")
    try:
        attachment_ids = [UUID(str(x)) for x in raw_attachments]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="attachment_ids contains invalid UUID")
    async with get_connection() as conn:
        found = await conn.fetch(
            "SELECT id FROM mw_project_files WHERE task_id = $1 AND id = ANY($2::uuid[])",
            task_id, attachment_ids,
        )
    if len(found) != len(attachment_ids):
        raise HTTPException(status_code=400, detail="attachment not found on this task")
    return attachment_ids

async def _verify_task_belongs_to_project(project_id: UUID, task_id: UUID) -> None:
    """Ownership guard for task-scoped routes: the task must live in this project.

    404 (not 403) so a task id in another project isn't confirmed to exist.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM mw_tasks WHERE id = $1 AND project_id = $2",
            task_id, project_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

async def _verify_element_in_project(conn, project_id: UUID, element_id: str) -> None:
    owns = await conn.fetchval(
        "SELECT 1 FROM mw_project_elements WHERE id = $1 AND project_id = $2",
        element_id, str(project_id),
    )
    if not owns:
        raise HTTPException(status_code=404, detail="Element not found")
