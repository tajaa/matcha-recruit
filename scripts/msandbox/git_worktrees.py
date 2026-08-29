from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .models import PublishState, ReleaseResult, WorktreeInfo, WorktreeOwner
from .state import data_root


class GitError(RuntimeError):
    pass


def _git(repo: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *argv],
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


def merge_base(repo: Path, left: str, right: str) -> str:
    return _git(repo, "merge-base", left, right).stdout.strip()


def git_common_dir(repo: Path) -> Path:
    raw = _git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def session_git_dir(session_id: str) -> Path:
    if not session_id or any(not (char.isalnum() or char in "_-") for char in session_id):
        raise GitError(f"invalid session id: {session_id!r}")
    return data_root() / "git-sessions" / session_id / "repo.git"


def session_git_pointer(session_id: str) -> Path:
    return session_git_dir(session_id).parent / "workspace.git"


def session_git_head(session_id: str) -> str:
    git_dir = session_git_dir(session_id)
    if not git_dir.is_dir():
        raise GitError(f"isolated Git metadata is missing for session {session_id}")
    return resolve_ref(git_dir, "HEAD")


def initialize_session_git(
    repo: Path,
    worktree: Path,
    session_id: str,
    head_sha: str,
) -> None:
    """Create container-only Git metadata backed by read-only host alternates."""
    git_dir = session_git_dir(session_id)
    pointer = session_git_pointer(session_id)
    if git_dir.exists() or pointer.exists():
        raise GitError(f"isolated Git metadata already exists for session {session_id}")
    git_dir.parent.mkdir(parents=True, exist_ok=False)
    try:
        _git(git_dir.parent, "init", "--bare", str(git_dir))
        _git(git_dir, "config", "core.bare", "false")
        _git(git_dir, "config", "core.worktree", "/workspace")
        origin = _git(repo, "remote", "get-url", "origin").stdout.strip()
        _git(git_dir, "config", "remote.origin.url", origin)
        for key in ("user.name", "user.email"):
            value = _git(repo, "config", "--get", key, check=False).stdout.strip()
            if value:
                _git(git_dir, "config", key, value)
        alternates = git_dir / "objects/info/alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(str(git_common_dir(repo) / "objects") + "\n", encoding="utf-8")
        _git(git_dir, "update-ref", "--no-deref", "HEAD", head_sha)
        _git(git_dir, "read-tree", head_sha)
        pointer.write_text("gitdir: /msandbox-git\n", encoding="utf-8")
        pointer.chmod(0o600)
    except Exception:
        shutil.rmtree(git_dir.parent, ignore_errors=True)
        raise


def sync_host_to_session_git(repo: Path, worktree: Path, session_id: str) -> str:
    """Make the isolated index/HEAD reflect the host worktree before startup."""
    git_dir = session_git_dir(session_id)
    if not git_dir.is_dir():
        raise GitError(f"isolated Git metadata is missing for session {session_id}")
    head = current_head(worktree)
    _git(git_dir, "fetch", "--no-tags", str(repo), head)
    _git(git_dir, "update-ref", "--no-deref", "HEAD", head)
    _git(git_dir, "read-tree", head)
    return head


def sync_session_git_to_host(repo: Path, worktree: Path, session_id: str) -> str:
    """Import the isolated committed HEAD without discarding working files."""
    git_dir = session_git_dir(session_id)
    if not git_dir.is_dir():
        raise GitError(f"isolated Git metadata is missing for session {session_id}")
    head = resolve_ref(git_dir, "HEAD")
    _git(worktree, "fetch", "--no-tags", str(git_dir), head)
    _git(worktree, "reset", "--mixed", head)
    return head


def remove_session_git(session_id: str) -> None:
    root = session_git_dir(session_id).parent
    if root.is_dir() and not root.is_symlink():
        shutil.rmtree(root)


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
            try:
                worktree.path.resolve().relative_to((data_root() / "worktrees").resolve())
                managed = True
            except ValueError:
                managed = False
            return WorktreeOwner(worktree.path, worktree.head, branch, managed)
    return None


def remote_branch_sha(repo: Path, branch: str) -> str | None:
    """Read the branch directly from origin instead of trusting a tracking ref."""
    result = _git(
        repo,
        "ls-remote",
        "--exit-code",
        "--refs",
        "origin",
        f"refs/heads/{branch}",
        check=False,
    )
    if result.returncode == 2:
        return None
    if result.returncode:
        raise GitError(result.stderr.strip() or result.stdout.strip() or "git ls-remote failed")
    output = result.stdout.strip()
    return output.split(None, 1)[0] if output else None


def branch_publish_state(repo: Path, worktree: Path, branch: str) -> PublishState:
    head = current_head(worktree)
    clean = not bool(_git(worktree, "status", "--porcelain=v1").stdout.strip())
    remote_sha = remote_branch_sha(repo, branch)
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


def push_detached_head(
    repo: Path,
    worktree: Path,
    branch: str,
    expected_remote_sha: str | None,
    *,
    head_sha: str | None = None,
) -> str:
    head = head_sha or current_head(worktree)
    destination = f"{head}:refs/heads/{branch}"
    expected = expected_remote_sha or ""
    argv = [
        "push",
        f"--force-with-lease=refs/heads/{branch}:{expected}",
        "origin",
        destination,
    ]
    _git(worktree, *argv)
    fetch_origin(repo, branch)
    remote = resolve_ref(repo, f"refs/remotes/origin/{branch}")
    if remote != head:
        raise GitError(f"remote branch verification failed: expected {head}, found {remote}")
    return head
