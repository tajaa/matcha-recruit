"""Narrow, fail-closed GitHub REST write helpers for Huume draft PRs.

The server token is shared by every tenant.  Consequently every helper checks
``GITHUB_WRITE_ALLOWED_REPOS`` itself; callers cannot accidentally bypass the
allowlist by calling a lower-level primitive.
"""
from __future__ import annotations

import base64
import os
from typing import Iterable

import httpx

from .github_service import GITHUB_API, GitHubError, _headers, _excluded


def write_allowed_repos() -> set[str]:
    return {item.strip().strip("/") for item in os.getenv("GITHUB_WRITE_ALLOWED_REPOS", "").split(",") if item.strip()}


def assert_write_allowed(repo: str) -> str:
    repo = (repo or "").strip().strip("/")
    if repo not in write_allowed_repos():
        raise GitHubError(
            "GitHub writes are not enabled for this repository. "
            "Ask an operator to add it to GITHUB_WRITE_ALLOWED_REPOS."
        )
    return repo


async def _json(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> dict:
    response = await client.request(method, url, headers=_headers(), **kwargs)
    if response.status_code == 401:
        raise GitHubError("GitHub token invalid or missing (GITHUB_TOKEN).")
    if response.status_code == 403:
        raise GitHubError("GitHub refused this write. The server token needs contents:write and pull_requests:write.")
    if response.status_code == 404:
        raise GitHubError("GitHub repository, branch, or object was not found.")
    if response.status_code >= 400:
        detail = response.json().get("message") if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise GitHubError(f"GitHub write failed ({response.status_code}): {detail}")
    return response.json()


async def ensure_branch(repo: str, base_branch: str, new_branch: str) -> str:
    """Create ``new_branch`` from ``base_branch`` unless it already exists.

    Returns the branch-head commit SHA. Existing branches are deliberately
    reused and never force-updated, so a retry commits on top of prior Huume
    work instead of attempting a non-fast-forward ref update.
    """
    repo = assert_write_allowed(repo)
    async with httpx.AsyncClient(timeout=30.0) as client:
        base = await _json(client, "GET", f"{GITHUB_API}/repos/{repo}/git/ref/heads/{base_branch}")
        base_sha = base["object"]["sha"]
        existing = await client.get(f"{GITHUB_API}/repos/{repo}/git/ref/heads/{new_branch}", headers=_headers())
        if existing.status_code == 404:
            await _json(client, "POST", f"{GITHUB_API}/repos/{repo}/git/refs", json={"ref": f"refs/heads/{new_branch}", "sha": base_sha})
            return base_sha
        elif existing.status_code >= 400:
            await _json(client, "GET", f"{GITHUB_API}/repos/{repo}/git/ref/heads/{new_branch}")
        else:
            return existing.json()["object"]["sha"]
    return base_sha


async def commit_files(
    repo: str, branch: str, base_sha: str, files: dict[str, str], deletes: Iterable[str], message: str,
) -> str:
    """Commit one staged file set to a non-default branch; never force-push."""
    repo = assert_write_allowed(repo)
    tree_items: list[dict] = []
    async with httpx.AsyncClient(timeout=45.0) as client:
        base_commit = await _json(client, "GET", f"{GITHUB_API}/repos/{repo}/git/commits/{base_sha}")
        for path, content in files.items():
            if _excluded(path):
                raise GitHubError(f"Refusing to write excluded path: {path}")
            blob = await _json(client, "POST", f"{GITHUB_API}/repos/{repo}/git/blobs", json={
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"), "encoding": "base64",
            })
            tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        for path in deletes:
            if _excluded(path):
                raise GitHubError(f"Refusing to delete excluded path: {path}")
            tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
        tree = await _json(client, "POST", f"{GITHUB_API}/repos/{repo}/git/trees", json={"base_tree": base_commit["tree"]["sha"], "tree": tree_items})
        commit = await _json(client, "POST", f"{GITHUB_API}/repos/{repo}/git/commits", json={"message": message, "tree": tree["sha"], "parents": [base_sha]})
        await _json(client, "PATCH", f"{GITHUB_API}/repos/{repo}/git/refs/heads/{branch}", json={"sha": commit["sha"], "force": False})
    return commit["sha"]


async def open_draft_pr(repo: str, head: str, base: str, title: str, body: str) -> dict:
    repo = assert_write_allowed(repo)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{GITHUB_API}/repos/{repo}/pulls", headers=_headers(), json={
            "title": title, "head": head, "base": base, "body": body, "draft": True,
        })
        if response.status_code != 422:
            if response.status_code == 401:
                raise GitHubError("GitHub token invalid or missing (GITHUB_TOKEN).")
            if response.status_code == 403:
                raise GitHubError("GitHub refused this write. The server token needs contents:write and pull_requests:write.")
            if response.status_code == 404:
                raise GitHubError("GitHub repository, branch, or object was not found.")
            if response.status_code >= 400:
                detail = response.json().get("message") if response.headers.get("content-type", "").startswith("application/json") else response.text
                raise GitHubError(f"GitHub write failed ({response.status_code}): {detail}")
            return response.json()

        # A retry or changes-requested pass reuses its deterministic Huume
        # branch. GitHub rejects a second PR for that branch; return the
        # existing draft so the new commit remains reviewable in the same PR.
        owner = repo.split("/", 1)[0]
        existing = await client.get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            params={"head": f"{owner}:{head}", "base": base, "state": "open"},
            headers=_headers(),
        )
        if existing.status_code >= 400:
            raise GitHubError(f"Unable to look up an existing Huume draft PR ({existing.status_code}).")
        pulls = existing.json()
        if pulls and pulls[0].get("draft"):
            return pulls[0]
        if pulls:
            raise GitHubError("A non-draft pull request already exists for this Huume branch; Huume will not modify it.")
        detail = response.json().get("message") if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise GitHubError(f"GitHub write failed (422): {detail}")
