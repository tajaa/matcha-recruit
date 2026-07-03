"""GitHub integration: commit scan + suggestions, repo connection,
sync/scan-commits, webhook install, and the public push-webhook handler.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
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
    from app.matcha.services import commit_scan_service as cs_svc
    suggestions = await cs_svc.scan_commits(project_id, company_id, commits)
    return {"suggestions": suggestions}

@router.get("/projects/{project_id}/commit-suggestions")
async def list_commit_suggestions_endpoint(
    project_id: UUID,
    task_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import commit_scan_service as cs_svc
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
    from app.matcha.services import commit_scan_service as cs_svc
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
    from app.matcha.services import commit_scan_service as cs_svc
    from app.matcha.services import project_subtask_service as st_svc
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
    from app.matcha.services import commit_scan_service as cs_svc
    resolved = await cs_svc.resolve_suggestion(
        project_id, suggestion_id, status="dismissed", actor_user_id=current_user.id,
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Suggestion not found or already resolved")
    return {"dismissed": True, "suggestion": resolved}

def _resolve_github_repo(project: dict, body: dict):
    """The repo/branch a sync or scan should use: the project's connected repo,
    then a body override, then the server default. (branch may be None.)"""
    from app.matcha.services import github_service as gh_svc
    repo = (body or {}).get("repo") or project.get("github_repo") or gh_svc.default_repo()
    ref = (body or {}).get("ref") or project.get("github_branch")
    return repo, ref

@router.get("/projects/{project_id}/github/connection")
async def get_github_connection(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    project, _role = await _verify_project_access(project_id, current_user)
    from app.matcha.services import github_service as gh_svc
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
    _project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    from app.matcha.services import github_service as gh_svc
    repo = ((body or {}).get("repo") or "").strip().strip("/")
    branch = ((body or {}).get("branch") or "").strip() or None
    if not repo:
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
    """Fetch every bound element's globbed files from the project's connected
    GitHub repo (read-only token, server-side) and refresh its snapshot."""
    project, role = await _verify_project_access(project_id, current_user)
    if not _can_edit_project(role):
        raise HTTPException(status_code=403, detail="You don't have edit access to this project")
    from app.matcha.services import github_service as gh_svc
    repo, ref = _resolve_github_repo(project, body)
    if not repo:
        raise HTTPException(status_code=400, detail="No GitHub repo connected to this project.")

    elements = await _list_project_elements(project_id)
    bound = [el for el in elements if (el.get("repo_paths") or [])]
    if not bound:
        raise HTTPException(status_code=400, detail="No element has repo path globs bound yet.")

    results = []
    total = 0
    for el in bound:
        try:
            summary = await gh_svc.sync_element(
                project_id, el["id"], el.get("repo_paths") or [],
                repo=repo, ref=ref or el.get("repo_branch"),
            )
            total += summary.get("stored", 0)
            results.append({"element_id": el["id"], "name": el.get("name"), **summary})
        except gh_svc.GitHubError as e:
            results.append({"element_id": el["id"], "name": el.get("name"), "error": str(e)})
    return {"repo": repo, "total_stored": total, "elements": results}

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
    from app.matcha.services import github_service as gh_svc
    from app.matcha.services import commit_scan_service as cs_svc
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
    from app.matcha.services import github_service as gh_svc
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

@public_router.post("/github/webhook")
async def github_push_webhook(request: Request):
    """GitHub push webhook → scan the pushed commits for every project connected
    to that repo+branch. Public (no JWT); authenticated by HMAC signature.
    URL: /api/matcha-work/public/github/webhook"""
    from app.matcha.services import github_service as gh_svc
    raw = await request.body()
    if not gh_svc.verify_webhook_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="bad signature")
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"ok": True, "pong": True}
    if event != "push":
        return {"ignored": event}

    import json as _json
    payload = _json.loads(raw or b"{}")
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

    from app.matcha.services import commit_scan_service as cs_svc
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
