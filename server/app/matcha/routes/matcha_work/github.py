"""GitHub integration: commit scan + suggestions, repo connection,
sync/scan-commits, webhook install, and the public push-webhook handler.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import os
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work.elements import _list_project_elements
from app.matcha.routes.matcha_work._shared import (
    _can_edit_project,
    _project_company_id,
    _verify_project_access,
)

router = APIRouter()
public_router = APIRouter()

@router.post("/projects/{project_id}/commit-scan")
async def commit_scan_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    company_id = project.get("company_id") or await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="No company context")
    commits = body.get("commits") or []
    branch = body.get("branch")
    # Stamp branch onto each commit if the client sent it at the top level.
    for c in commits:
        c.setdefault("branch", branch)
    from app.matcha.services.matcha_work import commit_scan_service as cs_svc
    suggestions = await cs_svc.scan_commits(project_id, company_id, commits)
    return {"suggestions": suggestions}

@router.get("/projects/{project_id}/commit-suggestions")
async def list_commit_suggestions_endpoint(
    project_id: UUID,
    task_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services.matcha_work import commit_scan_service as cs_svc
    return await cs_svc.list_pending_suggestions(project_id, task_id)

@router.get("/projects/{project_id}/tasks/{task_id}/commit-completions")
async def list_commit_completions_endpoint(
    project_id: UUID,
    task_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Accepted commit→subtask completions for a task — which commit completed
    each done item, so an in-review reviewer can audit the AI auto-checks."""
    await _verify_project_access(project_id, current_user)
    from app.matcha.services.matcha_work import commit_scan_service as cs_svc
    return await cs_svc.list_accepted_completions(project_id, task_id)

@router.post("/projects/{project_id}/commit-suggestions/{suggestion_id}/accept")
async def accept_commit_suggestion_endpoint(
    project_id: UUID,
    suggestion_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    from app.matcha.services.matcha_work import commit_scan_service as cs_svc
    from app.matcha.services.matcha_work import project_subtask_service as st_svc
    # Atomic claim: resolve_suggestion only flips a *pending* row, so a
    # double-accept (or racing client) no-ops on the second call.
    resolved = await cs_svc.resolve_suggestion(
        project_id, suggestion_id, status="accepted", actor_user_id=current_user.id,
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Suggestion not found or already resolved")
    updated = await st_svc.update_subtask(
        project_id, UUID(resolved["task_id"]), UUID(resolved["subtask_id"]),
        {"is_done": True}, actor_user_id=current_user.id,
    )
    return {"accepted": True, "subtask": updated, "suggestion": resolved}

@router.post("/projects/{project_id}/commit-suggestions/{suggestion_id}/dismiss")
async def dismiss_commit_suggestion_endpoint(
    project_id: UUID,
    suggestion_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    from app.matcha.services.matcha_work import commit_scan_service as cs_svc
    resolved = await cs_svc.resolve_suggestion(
        project_id, suggestion_id, status="dismissed", actor_user_id=current_user.id,
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Suggestion not found or already resolved")
    return {"dismissed": True, "suggestion": resolved}

def _resolve_github_repo(project: dict, body: dict):
    """The repo/branch a sync or scan should use: the project's connected repo,
    then a body override, then the server default. (branch may be None.)"""
    from app.matcha.services.matcha_work import github_service as gh_svc
    repo = (body or {}).get("repo") or project.get("github_repo") or gh_svc.default_repo()
    ref = (body or {}).get("ref") or project.get("github_branch")
    return repo, ref

@router.get("/projects/{project_id}/github/connection")
async def get_github_connection(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    from app.matcha.services.matcha_work import github_service as gh_svc
    repo = project.get("github_repo")
    return {
        "repo": repo,
        "branch": project.get("github_branch"),
        "connected": bool(repo),
        "default_repo": gh_svc.default_repo(),
        "token_present": gh_svc.has_token(),
    }

@router.put("/projects/{project_id}/github/connection")
async def put_github_connection(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Connect (or change) this project's GitHub repo. Empty repo disconnects.
    Validates the repo is readable with the server token before saving."""
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    from app.matcha.services.matcha_work import github_service as gh_svc
    repo = ((body or {}).get("repo") or "").strip().strip("/")
    branch = ((body or {}).get("branch") or "").strip() or None
    if not repo:
        await gh_svc.clear_repository_snapshot(project_id, delete_element=True)
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE mw_projects SET github_repo = NULL, github_branch = NULL WHERE id = $1",
                str(project_id),
            )
        return {"repo": None, "branch": None, "connected": False, "default_repo": gh_svc.default_repo()}
    try:
        info = await gh_svc.validate_repo(repo)
    except gh_svc.GitHubError as e:
        raise HTTPException(status_code=400, detail=str(e))
    branch = branch or info.get("default_branch")
    if repo != project.get("github_repo") or branch != project.get("github_branch"):
        await gh_svc.clear_repository_snapshot(project_id)
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_projects SET github_repo = $1, github_branch = $2 WHERE id = $3",
            repo, branch, str(project_id),
        )
    return {"repo": repo, "branch": branch, "connected": True,
            "default_branch": info.get("default_branch"), "private": info.get("private")}

@router.post("/projects/{project_id}/github/sync")
async def github_sync_endpoint(
    project_id: UUID,
    body: dict = Body(default={}),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Index the connected GitHub repo, then refresh any custom element scopes."""
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    from app.matcha.services.matcha_work import github_service as gh_svc
    repo, ref = _resolve_github_repo(project, body)
    if not repo:
        raise HTTPException(status_code=400, detail="No GitHub repo connected to this project.")

    # Always keep one complete, hidden project snapshot. Custom element globs
    # are optional refinements for component-scoped Props and commit matching;
    # they must not be a prerequisite for understanding a connected repo.
    repository_element_id = await gh_svc.ensure_repository_snapshot_element(
        project_id, repo, ref,
    )
    try:
        repository_summary = await gh_svc.sync_element(
            project_id, repository_element_id, gh_svc.REPOSITORY_SNAPSHOT_GLOBS,
            repo=repo, ref=ref,
        )
    except gh_svc.GitHubError as e:
        raise HTTPException(status_code=400, detail=str(e))

    elements = await _list_project_elements(project_id)
    bound = [el for el in elements if (el.get("repo_paths") or [])]
    results = [{
        "element_id": repository_element_id,
        "name": repo,
        "scope": "repository",
        **repository_summary,
    }]
    for el in bound:
        try:
            summary = await gh_svc.sync_element(
                project_id, el["id"], el.get("repo_paths") or [],
                repo=repo, ref=ref or el.get("repo_branch"),
            )
            results.append({"element_id": el["id"], "name": el.get("name"), **summary})
        except gh_svc.GitHubError as e:
            results.append({"element_id": el["id"], "name": el.get("name"), "error": str(e)})
    return {
        "repo": repo,
        "total_stored": repository_summary.get("stored", 0),
        "elements": results,
    }

@router.post("/projects/{project_id}/github/scan-commits")
async def github_scan_commits_endpoint(
    project_id: UUID,
    body: dict = Body(default={}),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Pull NEW commits from GitHub (since the last scan) and run them through the
    commit→subtask matcher → suggestions on tickets. A watermark
    (mw_projects.github_last_scanned_sha) means an auto-scan with nothing new makes
    zero Gemini calls. `force` (the manual button) re-scans recent commits so a
    newly-added ticket can match already-merged work."""
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    company_id = _project_company_id(project) or await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="No company context")
    from app.matcha.services.matcha_work import github_service as gh_svc
    from app.matcha.services.matcha_work import commit_scan_service as cs_svc
    repo, ref = _resolve_github_repo(project, body)
    if not repo:
        raise HTTPException(status_code=400, detail="No GitHub repo connected to this project.")
    force = bool((body or {}).get("force"))
    since = None if force else project.get("github_last_scanned_sha")
    try:
        commits, newest_sha = await gh_svc.fetch_recent_commits(
            repo=repo, ref=ref,
            limit=int((body or {}).get("limit") or gh_svc.DEFAULT_COMMIT_LIMIT),
            since_sha=since,
        )
    except gh_svc.GitHubError as e:
        raise HTTPException(status_code=400, detail=str(e))
    suggestions = await cs_svc.scan_commits(
        project_id, company_id, commits, actor_user_id=current_user.id,
    )
    if newest_sha:
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE mw_projects SET github_last_scanned_sha = $1 WHERE id = $2",
                newest_sha, str(project_id),
            )
    return {"scanned": len(commits), "suggestions": suggestions}

@router.post("/projects/{project_id}/github/webhook/install")
async def install_github_webhook_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Register a push webhook on the connected repo so a merge to its branch
    auto-triggers a scan (no polling). Edit-gated."""
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    from app.matcha.services.matcha_work import github_service as gh_svc
    repo, _ref = _resolve_github_repo(project, {})
    if not repo:
        raise HTTPException(status_code=400, detail="No GitHub repo connected to this project.")
    url, secret = gh_svc.webhook_url(), gh_svc.webhook_secret()
    if not url or not secret:
        raise HTTPException(
            status_code=400,
            detail="Server webhook not configured (set GITHUB_WEBHOOK_URL + GITHUB_WEBHOOK_SECRET).",
        )
    try:
        result = await gh_svc.install_repo_webhook(repo, url, secret)
    except gh_svc.GitHubError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"repo": repo, **result}

# kanban-autopr's PR-body trailer — the primary way a delivery resolves to a
# card. Fallback for a PR opened without one (e.g. a hand-made
# task/<id8>-... branch a human pushed and opened themselves): match the
# head branch's id8 against mw_tasks.id with hyphens stripped.
_TASK_TRAILER_RE = re.compile(r"<!--\s*matcha-task:\s*([0-9a-fA-F-]{36})\s*-->")
_TASK_BRANCH_RE = re.compile(r"^(?:bot/task|task)-?/?([0-9a-f]{8})")
_PRODUCTION_BUILD_RE = re.compile(r"<!--\s*matcha-production-build:\s*([0-9]+)\s*-->")
_PRODUCTION_BACKEND_SHA_RE = re.compile(
    r"<!--\s*matcha-production-backend-sha:\s*([0-9a-f]{7,40})\s*-->", re.IGNORECASE
)
_PRODUCTION_FRONTEND_SHA_RE = re.compile(
    r"<!--\s*matcha-production-frontend-sha:\s*([0-9a-f]{7,40})\s*-->", re.IGNORECASE
)
_AUTOPR_CRITICALITY_RE = re.compile(
    r"<!--\s*matcha-autopr-criticality:\s*(red|orange|yellow)\s*-->", re.IGNORECASE
)
_AUTOPR_CONFIDENCE_SCORE_RE = re.compile(
    r"<!--\s*matcha-autopr-confidence-score:\s*([0-9]{1,3})\s*-->", re.IGNORECASE
)
_AUTOPR_LEGACY_STRUCTURED_NOTE_RE = re.compile(
    r"^from auto setup · build [0-9]+ · prod "
    r"(?:[0-9a-f]{7,40}|backend [0-9a-f]{7,40} / frontend [0-9a-f]{7,40})"
    r"(?: · PR #[0-9]+)?"
    r"(?: · [^·]+ C[0-9]+ · (?:awaiting answers|ready for review|no safe action))?"
    r"(?: · \[autopr:no-spec [^]]+\] "
    r"(?:already_fixed|migration_required|policy_blocked|external_dependency))?",
    re.IGNORECASE,
)
_AUTOPR_STRUCTURED_NOTE_RE = re.compile(
    r"^🤖 AUTO SETUP · [^·]+"
    r"(?: · build [0-9]+)?"
    r"(?: · prod (?:[0-9a-f]{7,40}|backend [0-9a-f]{7,40} / frontend [0-9a-f]{7,40}))?"
    r"(?: · PR #[0-9]+)?"
    r"(?: · [^·]+ C[0-9]+)?"
    r"(?: · \[autopr:no-spec [^]]+\] "
    r"(?:already_fixed|migration_required|policy_blocked|external_dependency))?",
    re.IGNORECASE,
)

# install_repo_webhook is shared by every company that connects its own repo
# for commit-scanning — GITHUB_WEBHOOK_SECRET is one global value across all
# of them, and this feature's WEBHOOK_EVENTS upgrade turns on `pull_request`
# for every one of those hooks, not just this repo's. Neither resolution
# path above proves the delivery came from kanban-autopr's own repo, so
# without this check a PR opened against ANY connected customer repo could
# move a card here just by matching the trailer/branch pattern. kanban-autopr
# only ever runs against this one repo, so gate on it explicitly.
_KANBAN_AUTOPR_REPO = os.environ.get("KANBAN_AUTOPR_REPO", "tajaa/matcha-recruit")

# Second boundary, independent of the repo check: only ever move a card that
# belongs to one of the four projects kanban-autopr actually targets (kept
# in sync with scripts/seed/autopr_bot.py's PROJECTS list). Even a PR that
# legitimately lands in this repo — a human's own hand-made branch, not the
# bot's — must not be able to move a card in an unrelated project.
_KANBAN_AUTOPR_PROJECT_IDS = {
    "7f728636-3219-4d83-9df3-a4682e3242de",  # WerkWerk
    "fade10b4-36ff-4c60-af59-5cc6058285ab",  # Beetlejuse
    "84823d21-c752-4abd-9696-4c93c8b3c21e",  # Gummfit
    "8b924347-d6e4-4000-8e7d-ca8f46f76fba",  # MATCHA
}

_AUTOPR_PROGRESS_NOTE = "🤖 AUTO SETUP"
_AUTOPR_LEGACY_PROGRESS_NOTE = "from auto setup"


def _with_autopr_progress_note(
    existing: Optional[str],
    *,
    pr_body: str = "",
    pr_number: Optional[int] = None,
) -> str:
    """Mark an auto-setup card without discarding its current progress note.

    publish.sh normally writes the detailed marker as soon as it opens the PR.
    Reconstruct it from machine trailers on merge as a recovery path if the PR
    was created but the card PATCH failed.
    """
    # A merged PR is no longer merely "ready"; state that outcome first so
    # the narrow card face shows it before build provenance.
    marker = f"{_AUTOPR_PROGRESS_NOTE} · MERGED: READY FOR REVIEW"
    build_match = _PRODUCTION_BUILD_RE.search(pr_body)
    backend_match = _PRODUCTION_BACKEND_SHA_RE.search(pr_body)
    frontend_match = _PRODUCTION_FRONTEND_SHA_RE.search(pr_body)
    criticality_match = _AUTOPR_CRITICALITY_RE.search(pr_body)
    confidence_match = _AUTOPR_CONFIDENCE_SCORE_RE.search(pr_body)
    if build_match:
        marker += f" · build {build_match.group(1)}"
        if backend_match and frontend_match:
            backend_sha = backend_match.group(1)
            frontend_sha = frontend_match.group(1)
            if backend_sha == frontend_sha:
                marker += f" · prod {backend_sha}"
            else:
                marker += f" · prod backend {backend_sha} / frontend {frontend_sha}"
    if pr_number is not None:
        marker += f" · PR #{pr_number}"
    if criticality_match and confidence_match:
        emoji = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}[
            criticality_match.group(1).lower()
        ]
        marker += f" · {emoji} C{confidence_match.group(1)}"

    current = (existing or "").strip()
    if not current:
        return marker
    if current.casefold().startswith(marker.casefold()):
        return current
    auto_prefixes = (_AUTOPR_PROGRESS_NOTE, _AUTOPR_LEGACY_PROGRESS_NOTE)
    if any(current.casefold() == prefix.casefold() for prefix in auto_prefixes):
        return marker
    if any(
        current.casefold().startswith(f"{prefix} · ".casefold())
        for prefix in auto_prefixes
    ):
        # A later rework PR has a new build/PR marker. Replace the old system
        # prefix while retaining text a human wrote after it.
        if marker != _AUTOPR_PROGRESS_NOTE:
            structured = (
                _AUTOPR_STRUCTURED_NOTE_RE.match(current)
                or _AUTOPR_LEGACY_STRUCTURED_NOTE_RE.match(current)
            )
            if structured:
                remainder = current[structured.end():].removeprefix(" · ")
            else:
                matched_prefix = next(
                    prefix for prefix in auto_prefixes
                    if current.casefold().startswith(prefix.casefold())
                )
                remainder = current[len(matched_prefix):].removeprefix(" · ")
            return f"{marker} · {remainder}" if remainder else marker
        return current
    return f"{marker} · {current}"


async def _resolve_pull_request_tasks(payload: dict) -> list[dict]:
    repo_full_name = (payload.get("repository") or {}).get("full_name") or ""
    if repo_full_name != _KANBAN_AUTOPR_REPO:
        return []

    pr = payload.get("pull_request") or {}
    body = pr.get("body") or ""
    head_ref = (pr.get("head") or {}).get("ref") or ""
    pr_number = pr.get("number")

    task_id: Optional[str] = None
    m = _TASK_TRAILER_RE.search(body)
    if m:
        task_id = m.group(1)
    else:
        m2 = _TASK_BRANCH_RE.match(head_ref)
        if m2:
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    "SELECT id::text AS id FROM mw_tasks WHERE replace(id::text, '-', '') LIKE $1",
                    m2.group(1) + "%",
                )
            if row:
                task_id = row["id"]
    async with get_connection() as conn:
        select_sql = """SELECT id, project_id, board_column, progress_note,
                                to_jsonb(mw_tasks) ->> 'pr_url' AS pr_url,
                                (to_jsonb(mw_tasks) ->> 'pr_number')::integer AS pr_number,
                                ((to_jsonb(mw_tasks) ? 'pr_url') AND
                                 (to_jsonb(mw_tasks) ? 'pr_number')) AS pr_columns_exist
                           FROM mw_tasks"""
        tasks = []
        if task_id:
            primary_task = await conn.fetchrow(
                select_sql + " WHERE id = $1",
                UUID(task_id),
            )
            if primary_task:
                tasks.append(primary_task)
        if isinstance(pr_number, int):
            # Cross-lane scope ownership deliberately links a card to an
            # existing PR whose body and branch belong to another bot. The
            # exact persisted PR number therefore resolves every linked card,
            # including secondary cards beside a trailer-owned primary task.
            linked_tasks = await conn.fetch(
                select_sql
                + " WHERE to_jsonb(mw_tasks) ->> 'pr_number' = $1 ORDER BY created_at",
                str(pr_number),
            )
            tasks.extend(linked_tasks)

    unique_tasks = {}
    for task in tasks:
        if str(task["project_id"]) in _KANBAN_AUTOPR_PROJECT_IDS:
            unique_tasks[str(task["id"])] = task
    return list(unique_tasks.values())


async def _handle_pull_request_event(payload: dict) -> dict:
    """Card <-> PR sync. Every transition is a no-op unless the card is
    currently in the listed source column, so redelivery is idempotent and a
    card can never be dragged backwards by a webhook replay."""
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    tasks = await _resolve_pull_request_tasks(payload)
    if not tasks:
        return {"ok": True, "task": None}

    action = payload.get("action") or ""
    pr = payload.get("pull_request") or {}
    task_ids = [str(task["id"]) for task in tasks]

    def result(**extra) -> dict:
        response = {"ok": True, "task": task_ids[0], **extra}
        if len(task_ids) > 1:
            response["tasks"] = task_ids
        return response

    if action in ("opened", "reopened"):
        for task in tasks:
            if task["board_column"] == "todo":
                patch = {"board_column": "in_progress"}
                # Older schemas can still process the lifecycle transition;
                # only optional link persistence waits for the migration.
                pr_columns_exist = (
                    "pr_columns_exist" not in task
                    or bool(task["pr_columns_exist"])
                )
                if pr_columns_exist:
                    patch.update({
                        "pr_url": pr.get("html_url"),
                        "pr_number": pr.get("number"),
                    })
                await pt_svc.update_project_task(
                    task["project_id"], task["id"], patch,
                )
        return result()

    if action == "closed":
        merged = bool(pr.get("merged"))
        for task in tasks:
            column = task["board_column"]
            if not merged or column == "done":
                continue
            patch = {}
            progress_note = _with_autopr_progress_note(
                task["progress_note"],
                pr_body=pr.get("body") or "",
                pr_number=pr.get("number"),
            )
            if progress_note != task["progress_note"]:
                patch["progress_note"] = progress_note
            pr_columns_exist = (
                "pr_columns_exist" not in task
                or bool(task["pr_columns_exist"])
            )
            if pr_columns_exist:
                if pr.get("html_url") and pr["html_url"] != task["pr_url"]:
                    patch["pr_url"] = pr["html_url"]
                if pr.get("number") is not None and pr["number"] != task["pr_number"]:
                    patch["pr_number"] = pr["number"]
            if column in ("todo", "in_progress", "changes_requested"):
                patch["board_column"] = "review"
            if patch:
                await pt_svc.update_project_task(task["project_id"], task["id"], patch)
        return result(merged=merged)

    return {"ignored": action}


@public_router.post("/github/webhook")
async def github_push_webhook(request: Request):
    """GitHub push/pull_request webhook. Push scans commits for every project
    connected to that repo+branch; pull_request syncs a kanban-autopr card's
    column (see _handle_pull_request_event). Public (no JWT); authenticated by
    HMAC signature. URL: /api/matcha-work/public/github/webhook"""
    from app.matcha.services.matcha_work import github_service as gh_svc
    raw = await request.body()
    if not gh_svc.verify_webhook_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="bad signature")
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"ok": True, "pong": True}

    import json as _json
    payload = _json.loads(raw or b"{}")

    if event == "pull_request":
        return await _handle_pull_request_event(payload)

    if event != "push":
        return {"ignored": event}

    ref = payload.get("ref", "") or ""
    if not ref.startswith("refs/heads/"):
        return {"ignored": "non-branch ref"}
    branch = ref[len("refs/heads/"):]
    repo = (payload.get("repository") or {}).get("full_name") or ""
    shas = [c.get("id") for c in (payload.get("commits") or []) if c.get("id")]
    after = payload.get("after")
    if not repo or not shas:
        return {"ok": True, "nothing": True}

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, company_id FROM mw_projects
            WHERE github_repo = $1 AND (github_branch = $2 OR github_branch IS NULL)
            """,
            repo, branch,
        )
    if not rows:
        return {"ok": True, "projects": 0}

    from app.matcha.services.matcha_work import commit_scan_service as cs_svc
    commits = await gh_svc.fetch_commits_by_sha(repo, shas, branch)
    for r in rows:
        if not r["company_id"]:
            continue
        await cs_svc.scan_commits(r["id"], r["company_id"], commits)
        if after:
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE mw_projects SET github_last_scanned_sha = $1 WHERE id = $2",
                    after, str(r["id"]),
                )
    return {"ok": True, "projects": len(rows), "commits": len(commits)}
