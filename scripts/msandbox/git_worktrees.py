from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import PublishState, ReleaseResult, WorktreeInfo, WorktreeOwner


class GitError(RuntimeError):
    pass


def _git(repo: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *argv],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        raise GitError(result.stderr.strip() or result.stdout.strip())
    return result


def resolve_ref(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").stdout.strip()


def git_common_dir(repo: Path) -> Path:
    raw = _git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def current_head(worktree: Path) -> str:
    return resolve_ref(worktree, "HEAD")


def dirty_fingerprint(worktree: Path) -> str:
    status = _git(worktree, "status", "--porcelain=v1", "-z").stdout.encode()
    if not status:
        return "clean"
    import hashlib

    digest = hashlib.sha256()
    digest.update(status)
    for entry in status.decode(errors="surrogateescape").split("\0"):
        if not entry:
            continue
        relative = entry[3:] if len(entry) > 3 else ""
        candidate = worktree / relative
        if candidate.is_file() and not candidate.is_symlink():
            digest.update(relative.encode(errors="surrogateescape"))
            try:
                digest.update(candidate.read_bytes())
            except OSError:
                pass
    return digest.hexdigest()


def create_detached_worktree(repo: Path, session_id: str, start_ref: str, path: Path) -> WorktreeInfo:
    """Create a worktree without making refs/heads/* owned by that worktree."""
    if path.exists():
        raise GitError(f"worktree path already exists: {path}")
    head = resolve_ref(repo, start_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "--detach", str(path), head)
    git_file = path / ".git"
    if not git_file.is_file():
        raise GitError(f"worktree admin file missing: {git_file}")
    gitdir_line = git_file.read_text(encoding="utf-8").strip()
    if not gitdir_line.startswith("gitdir: "):
        raise GitError(f"unexpected worktree admin file: {git_file}")
    git_admin_name = Path(gitdir_line.removeprefix("gitdir: ")).name
    return WorktreeInfo(path=path, head=head, branch=None, git_admin_name=git_admin_name)


def list_worktrees(repo: Path) -> list[WorktreeInfo]:
    raw = _git(repo, "worktree", "list", "--porcelain", "-z").stdout
    records: list[WorktreeInfo] = []
    current: dict[str, str] = {}
    for field in raw.split("\0"):
        if not field:
            if current.get("worktree"):
                path = Path(current["worktree"])
                records.append(
                    WorktreeInfo(
                        path=path,
                        head=current.get("HEAD", ""),
                        branch=current.get("branch"),
                        git_admin_name="",
                    )
                )
            current = {}
            continue
        key, _, value = field.partition(" ")
        current[key] = value
    if current.get("worktree"):
        records.append(
            WorktreeInfo(
                path=Path(current["worktree"]),
                head=current.get("HEAD", ""),
                branch=current.get("branch"),
                git_admin_name="",
            )
        )
    return records


def resolve_worktree_owner(repo: Path, branch: str) -> WorktreeOwner | None:
    full_branch = branch if branch.startswith("refs/heads/") else f"refs/heads/{branch}"
    for worktree in list_worktrees(repo):
        if worktree.branch == full_branch:
            managed = "/matcha-msandbox/worktrees/" in str(worktree.path) or "/matcha-msandbox/" in str(worktree.path)
            return WorktreeOwner(worktree.path, worktree.head, branch, managed)
    return None


def branch_publish_state(repo: Path, worktree: Path, branch: str) -> PublishState:
    head = current_head(worktree)
    clean = not bool(_git(worktree, "status", "--porcelain=v1").stdout.strip())
    remote = _git(repo, "rev-parse", "--verify", f"refs/remotes/origin/{branch}^{{commit}}", check=False)
    remote_sha = remote.stdout.strip() if remote.returncode == 0 else None
    return PublishState(head, remote_sha, clean, bool(remote_sha and remote_sha == head))


def detach_branch_owner(
    repo: Path,
    owner: WorktreeOwner,
    *,
    require_clean: bool = True,
    require_published: bool = True,
) -> ReleaseResult:
    state = branch_publish_state(repo, owner.path, owner.branch)
    if require_clean and not state.clean:
        return ReleaseResult(False, "worktree has uncommitted changes", owner.path)
    if require_published and not state.published:
        return ReleaseResult(False, "worktree HEAD is not published to origin", owner.path)
    result = _git(owner.path, "switch", "--detach", state.head_sha, check=False)
    if result.returncode:
        return ReleaseResult(False, result.stderr.strip() or "git switch --detach failed", owner.path)
    return ReleaseResult(True, "branch owner detached", owner.path)


def remove_session_worktree(repo: Path, worktree: Path, branch: str) -> ReleaseResult:
    if not worktree.exists():
        _git(repo, "worktree", "prune", check=False)
        return ReleaseResult(True, "worktree already absent", worktree)
    state = branch_publish_state(repo, worktree, branch)
    if not state.clean:
        return ReleaseResult(False, "worktree has uncommitted changes", worktree)
    if not state.published:
        return ReleaseResult(False, "worktree HEAD is not published to origin", worktree)
    result = _git(repo, "worktree", "remove", str(worktree), check=False)
    if result.returncode:
        return ReleaseResult(False, result.stderr.strip() or "git worktree remove failed", worktree)
    _git(repo, "worktree", "prune", check=False)
    return ReleaseResult(True, "clean published worktree removed", worktree)


def prune_stale_worktree_metadata(repo: Path, *, apply: bool = False) -> list[Path]:
    stale = [item.path for item in list_worktrees(repo) if not item.path.exists()]
    if apply and stale:
        _git(repo, "worktree", "prune")
    return stale


def fetch_origin(repo: Path, ref: str | None = None) -> None:
    argv = ["fetch", "--prune", "origin"]
    if ref:
        argv.append(ref)
    _git(repo, *argv)


def push_detached_head(repo: Path, worktree: Path, branch: str, expected_remote_sha: str | None) -> str:
    head = current_head(worktree)
    destination = f"HEAD:refs/heads/{branch}"
    argv = ["push", "origin", destination]
    if expected_remote_sha:
        argv = [
            "push",
            f"--force-with-lease=refs/heads/{branch}:{expected_remote_sha}",
            "origin",
            destination,
        ]
    _git(worktree, *argv)
    fetch_origin(repo, branch)
    remote = resolve_ref(repo, f"refs/remotes/origin/{branch}")
    if remote != head:
        raise GitError(f"remote branch verification failed: expected {head}, found {remote}")
    return head
