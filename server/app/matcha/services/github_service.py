"""GitHub read-only ingestion — fills element repo snapshots from the GitHub API
instead of a connector's local clone. Not machine-tied; works for any
collaborator; handles big repos (fetch by glob server-side).

Auth: a single `GITHUB_TOKEN` env (a fine-grained PAT or the gh-cli token with
`repo` read). Repo defaults to `GITHUB_DEFAULT_REPO` (owner/name). Reuses the
Phase-1 glob matcher + the snapshot store, so nothing downstream changes.
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
from typing import Optional
from uuid import UUID

import httpx

from . import element_repo_service
from .commit_scan_service import path_matches_glob

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
MAX_FILE_BYTES = 40_000
MAX_FILES_PER_ELEMENT = 600
MAX_DIFF_CHARS = 60_000          # per-commit diff cap fed to the matcher
DEFAULT_COMMIT_LIMIT = 15        # how far back a *forced* (full) scan looks; watermark scans only do new commits
_BLOB_CONCURRENCY = 10

EXCLUDED_DIRS = {
    ".git", "node_modules", "dist", "build", ".build", "Pods", "DerivedData",
    ".venv", "venv", "__pycache__", ".next", "target", "vendor",
    ".pytest_cache", "coverage", ".idea", ".turbo", ".cache", ".gradle",
}
EXCLUDED_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Podfile.lock",
    "Cargo.lock", "poetry.lock", "composer.lock", "Gemfile.lock",
}


class GitHubError(Exception):
    pass


def default_repo() -> Optional[str]:
    # load_settings() runs load_dotenv() at app startup, so os.environ is
    # already populated by the time any endpoint reaches here.
    return os.getenv("GITHUB_DEFAULT_REPO")


def _token() -> Optional[str]:
    return os.getenv("GITHUB_TOKEN")


def has_token() -> bool:
    return bool(_token())


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _excluded(path: str) -> bool:
    parts = path.split("/")
    return any(p in EXCLUDED_DIRS for p in parts[:-1]) or parts[-1] in EXCLUDED_NAMES


async def validate_repo(repo: str) -> dict:
    """Confirm the token can read `repo` (owner/name). Returns
    {full_name, default_branch, private}. Raises GitHubError on any problem."""
    if not _token():
        raise GitHubError("GITHUB_TOKEN is not set on the server.")
    repo = (repo or "").strip().strip("/")
    if "/" not in repo:
        raise GitHubError("Repo must be in owner/name form (e.g. tajaa/matcha-recruit).")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{GITHUB_API}/repos/{repo}", headers=_headers())
    if r.status_code == 404:
        raise GitHubError(f"Repo not found or token can't read it: {repo}")
    if r.status_code == 401:
        raise GitHubError("GitHub token invalid (GITHUB_TOKEN).")
    r.raise_for_status()
    j = r.json()
    return {
        "full_name": j.get("full_name"),
        "default_branch": j.get("default_branch"),
        "private": j.get("private"),
    }


async def _fetch_tree(client: httpx.AsyncClient, repo: str, ref: str) -> list[dict]:
    r = await client.get(
        f"{GITHUB_API}/repos/{repo}/git/trees/{ref}",
        params={"recursive": "1"}, headers=_headers(),
    )
    if r.status_code == 404:
        raise GitHubError(f"Repo or ref not found: {repo}@{ref}")
    if r.status_code == 401:
        raise GitHubError("GitHub token invalid or missing (GITHUB_TOKEN).")
    r.raise_for_status()
    return r.json().get("tree", [])


async def _fetch_blob_text(client: httpx.AsyncClient, repo: str, sha: str) -> Optional[str]:
    r = await client.get(f"{GITHUB_API}/repos/{repo}/git/blobs/{sha}", headers=_headers())
    if r.status_code != 200:
        return None
    j = r.json()
    if j.get("encoding") != "base64":
        return None
    try:
        raw = base64.b64decode(j.get("content") or "")
    except Exception:  # noqa: BLE001
        return None
    if not raw or b"\x00" in raw:  # empty or binary
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


async def sync_element(
    project_id: UUID, element_id: str, globs: list[str], *,
    repo: Optional[str] = None, ref: Optional[str] = None,
) -> dict:
    """Fetch the element's globbed text files from GitHub and replace its snapshot.
    Returns {stored, skipped, total_bytes, fetched}."""
    if not _token():
        raise GitHubError("GITHUB_TOKEN is not set on the server.")
    repo = repo or default_repo()
    if not repo:
        raise GitHubError("No repo configured (GITHUB_DEFAULT_REPO).")
    ref = ref or "HEAD"
    if not globs:
        return {"stored": 0, "skipped": 0, "total_bytes": 0, "fetched": 0}

    async with httpx.AsyncClient(timeout=30.0) as client:
        tree = await _fetch_tree(client, repo, ref)
        candidates = [
            t for t in tree
            if t.get("type") == "blob"
            and not _excluded(t.get("path", ""))
            and (t.get("size") or 0) <= MAX_FILE_BYTES
            and any(path_matches_glob(t["path"], g) for g in globs)
        ][:MAX_FILES_PER_ELEMENT]

        sem = asyncio.Semaphore(_BLOB_CONCURRENCY)

        async def one(t: dict) -> Optional[dict]:
            async with sem:
                txt = await _fetch_blob_text(client, repo, t["sha"])
                return {"path": t["path"], "content": txt} if txt is not None else None

        fetched = await asyncio.gather(*[one(t) for t in candidates])

    files = [f for f in fetched if f]
    summary = await element_repo_service.replace_element_snapshot(project_id, element_id, files)
    summary["fetched"] = len(files)
    return summary


def _commit_payload(d: Optional[dict], ref: Optional[str]) -> Optional[dict]:
    """Shape a GitHub commit-detail object into the scan_commits payload. Skips
    missing + merge commits. Diff = concatenated per-file patches, capped."""
    if not d or len(d.get("parents", [])) > 1:
        return None
    sha = d["sha"]
    files = d.get("files", []) or []
    parts, total = [], 0
    for f in files:
        patch = f.get("patch")
        if not patch:
            continue
        block = f"--- {f['filename']}\n{patch}\n"
        if total + len(block) > MAX_DIFF_CHARS:
            break
        parts.append(block)
        total += len(block)
    return {
        "sha": sha,
        "short_sha": sha[:7],
        "message": (d.get("commit", {}) or {}).get("message", ""),
        "branch": ref,
        "changed_files": [f["filename"] for f in files],
        "diff": "".join(parts),
    }


async def fetch_commits_by_sha(repo: str, shas: list[str], ref: Optional[str] = None) -> list[dict]:
    """Fetch detail for specific commit shas (e.g. a webhook push payload) → scan
    payloads, in the given order. Capped to 30."""
    if not _token() or not shas:
        return []
    repo = repo or default_repo()
    async with httpx.AsyncClient(timeout=30.0) as client:
        sem = asyncio.Semaphore(_BLOB_CONCURRENCY)

        async def detail(sha: str) -> Optional[dict]:
            async with sem:
                d = await client.get(f"{GITHUB_API}/repos/{repo}/commits/{sha}", headers=_headers())
                return d.json() if d.status_code == 200 else None

        details = await asyncio.gather(*[detail(s) for s in shas[:30]])
    return [p for d in details if (p := _commit_payload(d, ref)) is not None]


# ---------------------------------------------------------------------------
# Webhook (push → scan) — signature verify + repo hook install
# ---------------------------------------------------------------------------

def webhook_secret() -> Optional[str]:
    return os.getenv("GITHUB_WEBHOOK_SECRET")


def webhook_url() -> Optional[str]:
    return os.getenv("GITHUB_WEBHOOK_URL")


def verify_webhook_signature(raw: bytes, header: Optional[str]) -> bool:
    """Verify GitHub's X-Hub-Signature-256 (HMAC-SHA256 of the raw body)."""
    secret = webhook_secret()
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[len("sha256="):], expected)


async def install_repo_webhook(repo: str, url: str, secret: str) -> dict:
    """Create a push webhook on the repo (idempotent on url). Needs a token with
    repo-admin/hook scope."""
    if not _token():
        raise GitHubError("GITHUB_TOKEN is not set on the server.")
    async with httpx.AsyncClient(timeout=15.0) as client:
        existing = await client.get(f"{GITHUB_API}/repos/{repo}/hooks", headers=_headers())
        if existing.status_code == 200:
            for h in existing.json():
                if (h.get("config") or {}).get("url") == url:
                    return {"installed": True, "id": h.get("id"), "existing": True}
        r = await client.post(
            f"{GITHUB_API}/repos/{repo}/hooks", headers=_headers(),
            json={
                "name": "web", "active": True, "events": ["push"],
                "config": {"url": url, "content_type": "json", "secret": secret, "insecure_ssl": "0"},
            },
        )
        if r.status_code not in (200, 201):
            raise GitHubError(f"Couldn't create webhook ({r.status_code}): {r.text[:200]}")
        return {"installed": True, "id": r.json().get("id"), "existing": False}


async def fetch_recent_commits(
    repo: Optional[str] = None, ref: Optional[str] = None,
    limit: int = DEFAULT_COMMIT_LIMIT, since_sha: Optional[str] = None,
) -> tuple[list[dict], Optional[str]]:
    """Non-merge commits on `ref`, shaped for `commit_scan_service.scan_commits`,
    oldest-first. If `since_sha` is given, returns only commits NEWER than it
    (stops when the list reaches it) — the watermark optimization so we don't
    re-evaluate commits every scan. Returns `(commits, newest_sha)` where
    newest_sha = branch HEAD (persist as the new watermark, even when nothing is
    new and `commits` is empty). Fetches per-commit detail (list omits files/patch)
    only for the commits actually returned."""
    if not _token():
        raise GitHubError("GITHUB_TOKEN is not set on the server.")
    repo = repo or default_repo()
    if not repo:
        raise GitHubError("No repo configured (GITHUB_DEFAULT_REPO).")

    async with httpx.AsyncClient(timeout=30.0) as client:
        params = {"per_page": str(limit)}
        if ref:
            params["sha"] = ref
        r = await client.get(f"{GITHUB_API}/repos/{repo}/commits", params=params, headers=_headers())
        if r.status_code == 404:
            raise GitHubError(f"Repo or ref not found: {repo}@{ref or 'default'}")
        if r.status_code == 401:
            raise GitHubError("GitHub token invalid or missing (GITHUB_TOKEN).")
        r.raise_for_status()
        all_shas = [c["sha"] for c in r.json()]
        newest_sha = all_shas[0] if all_shas else None
        # Only the commits newer than the watermark (those above it in the list).
        if since_sha and since_sha in all_shas:
            shas = all_shas[:all_shas.index(since_sha)]
        else:
            shas = all_shas

        sem = asyncio.Semaphore(_BLOB_CONCURRENCY)

        async def detail(sha: str) -> Optional[dict]:
            async with sem:
                d = await client.get(f"{GITHUB_API}/repos/{repo}/commits/{sha}", headers=_headers())
                return d.json() if d.status_code == 200 else None

        details = await asyncio.gather(*[detail(s) for s in shas])

    out = [p for d in details if (p := _commit_payload(d, ref)) is not None]
    out.reverse()  # GitHub returns newest-first; scan oldest-first
    return out, newest_sha
