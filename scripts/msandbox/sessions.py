from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .agent_adapters import launch_agent, stop_agent, tmux_running
from .docker_runtime import (
    allocate_port_block,
    compose_project,
    container_running,
    ensure_container,
    remove_container_project,
    remove_orphaned_container_project,
    session_home,
    stop_container,
)
from .git_worktrees import (
    GitError,
    branch_publish_state,
    create_detached_worktree,
    current_head,
    dirty_fingerprint,
    fetch_origin,
    initialize_session_git,
    merge_base,
    push_detached_head,
    remote_branch_sha,
    remove_session_git,
    remove_session_worktree,
    resolve_ref,
    session_git_dir,
    session_git_head,
    sync_host_to_session_git,
    sync_session_git_to_host,
)
from .models import PullRequest, ReleaseResult, SessionRecord, SessionSpec, utc_now
from .state import (
    ARTIFACT_LIFECYCLE_LOCK,
    SCHEMA_VERSION,
    data_root,
    list_sessions,
    save_session,
    state_lock,
)


class SessionError(RuntimeError):
    pass


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise SessionError("session name must contain a letter or number")
    return slug[:36]


def _copy_auth_templates(record: SessionRecord) -> None:
    """Copy only credentials needed by the selected agent; never share histories or logs."""
    home = session_home(record)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    candidates: dict[str, list[tuple[Path, Path]]] = {
        "codex": [(Path.home() / ".codex/auth.json", home / ".codex/auth.json")],
        "opencode": [
            (
                Path.home() / ".local/share/opencode/auth.json",
                home / ".local/share/opencode/auth.json",
            )
        ],
        "claude": [
            (Path.home() / ".claude/.credentials.json", home / ".claude/.credentials.json"),
            (Path.home() / ".claude.json", home / ".claude.json"),
        ],
    }
    for source, destination in candidates[record.agent]:
        if not source.is_file() or source.is_symlink():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source, destination, follow_symlinks=False)
        destination.chmod(0o600)
    gh_source = Path.home() / ".config/gh/hosts.yml"
    if gh_source.is_file() and not gh_source.is_symlink():
        gh_destination = home / ".config/gh/hosts.yml"
        gh_destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(gh_source, gh_destination, follow_symlinks=False)
        gh_destination.chmod(0o600)


def resolve_pr(repo: Path, number: int) -> tuple[str, str]:
    result = subprocess.run(
        ["gh", "pr", "view", str(number), "--repo", _github_repo(repo), "--json", "headRefName,headRefOid"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SessionError(result.stderr.strip() or f"could not resolve PR #{number}")
    data = json.loads(result.stdout)
    return str(data["headRefName"]), str(data["headRefOid"])


def _github_repo(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        check=True,
        text=True,
        capture_output=True,
    )
    remote = result.stdout.strip().removesuffix(".git")
    if remote.startswith("git@github.com:"):
        return remote.removeprefix("git@github.com:")
    if "github.com/" in remote:
        return remote.split("github.com/", 1)[1]
    raise SessionError(f"origin is not a GitHub repository: {remote}")


def create_session(repo: Path, spec: SessionSpec, extra_agent_args: Sequence[str] = ()) -> SessionRecord:
    repo = repo.resolve()
    slug = slugify(spec.name)
    with state_lock(f"repo-{repo.name}"):
        active_sessions = list_sessions()
        if any(item.name == spec.name for item in active_sessions):
            raise SessionError(f"an active session named {spec.name!r} already exists")
        session_id = f"{slug}-{secrets.token_hex(3)}"
        start_ref = spec.base_ref
        target_branch = f"codex/{slug}"
        pr_number = spec.pr_number
        advertised_pr_head: str | None = None
        if pr_number is not None:
            target_branch, advertised_pr_head = resolve_pr(repo, pr_number)
            fetch_origin(repo, target_branch)
            if spec.base_ref.startswith("origin/") and os.environ.get("MSANDBOX_SKIP_FETCH") != "1":
                fetch_origin(repo, spec.base_ref.removeprefix("origin/"))
            start_ref = f"origin/{target_branch}"
        elif start_ref.startswith("origin/") and os.environ.get("MSANDBOX_SKIP_FETCH") != "1":
            fetch_origin(repo, start_ref.removeprefix("origin/"))

        if any(
            item.repo_path.resolve() == repo and item.target_branch == target_branch
            for item in active_sessions
        ):
            raise SessionError(f"target branch {target_branch!r} is already owned by an active session")

        start_sha = resolve_ref(repo, start_ref)
        if advertised_pr_head is not None and start_sha != advertised_pr_head:
            raise SessionError(
                f"fetched PR head does not match GitHub: expected {advertised_pr_head}, found {start_sha}"
            )
        comparison_base_sha = (
            merge_base(repo, spec.base_ref, start_ref) if pr_number is not None else start_sha
        )
        expected_remote_sha = remote_branch_sha(repo, target_branch)

        worktree_path = data_root() / "worktrees" / session_id / "repo"
        info = create_detached_worktree(repo, session_id, start_ref, worktree_path)
        record = SessionRecord(
            schema_version=SCHEMA_VERSION,
            id=session_id,
            name=spec.name,
            agent=spec.agent,
            phase="created",
            repo_root=str(repo),
            worktree_path=str(worktree_path),
            git_admin_name=info.git_admin_name,
            compose_project=compose_project(session_id),
            tmux_session=f"ms-{session_id}"[:64],
            base_ref=spec.base_ref,
            base_sha=comparison_base_sha,
            target_branch=target_branch,
            start_sha=info.head,
            expected_remote_sha=expected_remote_sha,
            synchronized_sha=info.head,
            pr_number=pr_number,
            ports=allocate_port_block() if spec.dev else None,
            dev=spec.dev,
            playwright=spec.playwright,
        )
        try:
            initialize_session_git(repo, worktree_path, session_id, info.head)
            # The home exists before the first SessionRecord otherwise. Keep
            # registration atomic with GC so a concurrent sweep cannot erase a
            # newly copied login before it knows the session is live.
            with state_lock(ARTIFACT_LIFECYCLE_LOCK, timeout_s=600):
                _copy_auth_templates(record)
                save_session(record)
            if spec.start:
                start_session(record, extra_agent_args)
        except Exception:
            stop_agent(record, force=True)
            try:
                remove_container_project(record, volumes=True)
            except Exception:
                pass
            try:
                if session_git_dir(record.id).is_dir():
                    sync_session_git_to_host(repo, worktree_path, record.id)
            except (GitError, OSError):
                pass
            # A failed startup must never force-delete work the agent may have
            # already produced. Only remove the pristine worktree we created.
            pristine = False
            try:
                pristine = (
                    current_head(worktree_path) == info.head
                    and dirty_fingerprint(worktree_path) == "clean"
                    and (
                        not session_git_dir(record.id).is_dir()
                        or session_git_head(record.id) == info.head
                    )
                )
            except (GitError, OSError):
                pass
            if pristine:
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-C",
                        str(repo),
                        "worktree",
                        "remove",
                        str(worktree_path),
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                remove_session_git(record.id)
            else:
                record.phase = "orphaned"
                save_session(record)
            raise
        return record


def _ensure_isolated_git(record: SessionRecord) -> None:
    if session_git_dir(record.id).is_dir():
        return
    head = current_head(record.worktree)
    initialize_session_git(record.repo_path, record.worktree, record.id, head)
    record.synchronized_sha = head
    save_session(record)


def _reconcile_isolated_git(record: SessionRecord) -> str:
    """Synchronize the one side that moved since the last proven common HEAD."""
    _ensure_isolated_git(record)
    host_head = current_head(record.worktree)
    isolated_head = session_git_head(record.id)
    baseline = record.synchronized_sha or record.start_sha or record.base_sha
    if host_head == isolated_head:
        sync_host_to_session_git(record.repo_path, record.worktree, record.id)
        synchronized = host_head
    elif host_head == baseline:
        synchronized = sync_session_git_to_host(
            record.repo_path, record.worktree, record.id
        )
    elif isolated_head == baseline:
        synchronized = sync_host_to_session_git(
            record.repo_path, record.worktree, record.id
        )
    else:
        raise SessionError(
            "host and isolated Git HEADs diverged; inspect both before continuing the session"
        )
    record.synchronized_sha = synchronized
    save_session(record)
    return synchronized


def start_session(
    record: SessionRecord,
    extra_agent_args: Sequence[str] = (),
    *,
    _lock_held: bool = False,
) -> SessionRecord:
    if not _lock_held:
        with state_lock(f"session-{record.id}"):
            return start_session(record, extra_agent_args, _lock_held=True)
    _reconcile_isolated_git(record)
    ensure_container(record)
    launch_agent(record, extra_agent_args)
    record.phase = "running"
    save_session(record)
    return record


def reconcile_session(record: SessionRecord, *, _lock_held: bool = False) -> SessionRecord:
    if not _lock_held:
        with state_lock(f"session-{record.id}"):
            return reconcile_session(record, _lock_held=True)
    if record.phase == "released":
        return record
    if not record.worktree.exists():
        record.phase = "orphaned"
    else:
        _ensure_isolated_git(record)
        if container_running(record) and tmux_running(record):
            record.phase = "running"
        elif record.phase == "running":
            record.phase = "stopped"
    save_session(record)
    return record


def stop_session(
    record: SessionRecord,
    *,
    force: bool = False,
    _lock_held: bool = False,
) -> None:
    if record.phase == "released":
        return
    if not _lock_held:
        with state_lock(f"session-{record.id}"):
            stop_session(record, force=force, _lock_held=True)
            return
    stop_agent(record, force=force)
    if not record.worktree.exists():
        remove_orphaned_container_project(record)
        record.phase = "orphaned"
        save_session(record)
        return
    if record.worktree.exists():
        _ensure_isolated_git(record)
    stop_container(record)
    if record.worktree.exists() and session_git_dir(record.id).is_dir():
        _reconcile_isolated_git(record)
    if record.phase not in ("released", "orphaned"):
        record.phase = "stopped"
        save_session(record)


def _validation_current(
    record: SessionRecord,
    head: str | None = None,
    fingerprint: str | None = None,
) -> bool:
    validation = record.last_validation
    current_sha = head or current_head(record.worktree)
    current_fingerprint = fingerprint or dirty_fingerprint(record.worktree)
    return bool(
        validation
        and validation.status == "pass"
        and validation.mode in ("pr", "all")
        and validation.commit_sha == current_sha
        and validation.dirty_fingerprint == current_fingerprint
    )


def _find_or_create_pr(record: SessionRecord, *, draft: bool, title: str | None) -> tuple[int, str]:
    assert record.target_branch
    repo_name = _github_repo(record.repo_path)
    listed = subprocess.run(
        ["gh", "pr", "list", "--repo", repo_name, "--head", record.target_branch, "--state", "open", "--json", "number,url"],
        check=False,
        text=True,
        capture_output=True,
    )
    if listed.returncode == 0:
        matches = json.loads(listed.stdout)
        if matches:
            return int(matches[0]["number"]), str(matches[0]["url"])
    command = [
        "gh",
        "pr",
        "create",
        "--repo",
        repo_name,
        "--head",
        record.target_branch,
        "--base",
        "main",
        "--title",
        title or record.name,
        "--body",
        f"Created from msandbox session `{record.name}`.",
    ]
    if draft:
        command.append("--draft")
    created = subprocess.run(command, check=False, text=True, capture_output=True)
    if created.returncode:
        raise SessionError(created.stderr.strip() or "gh pr create failed")
    url = created.stdout.strip().splitlines()[-1]
    number = int(url.rstrip("/").rsplit("/", 1)[-1])
    return number, url


def submit_session(record: SessionRecord, *, draft: bool = True, title: str | None = None) -> PullRequest:
    """Publish detached HEAD, verify the PR branch, then release the worktree."""
    if not record.target_branch:
        raise SessionError("session has no target branch")
    with state_lock(f"session-{record.id}"):
        # Stop the managed agent and workspace before selecting the exact
        # commit and validation record that will be published.
        stop_session(record, _lock_held=True)
        head = current_head(record.worktree)
        fingerprint = dirty_fingerprint(record.worktree)
        status = subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(record.worktree),
                "status",
                "--porcelain=v1",
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        if status:
            raise SessionError("session has uncommitted changes; commit them before submit")
        if os.environ.get("MSANDBOX_NO_VERIFY") != "1" and not _validation_current(
            record, head, fingerprint
        ):
            raise SessionError("PR validation is missing or stale; run `msandbox test <session> --pr`")
        live_remote_sha = remote_branch_sha(record.repo_path, record.target_branch)
        if live_remote_sha != record.expected_remote_sha:
            raise SessionError(
                "target branch changed on origin after this session started; "
                "create a fresh session or explicitly reconcile the remote branch"
            )
        if current_head(record.worktree) != head or dirty_fingerprint(record.worktree) != fingerprint:
            raise SessionError("session changed while preparing submission; validate it again")
        record.phase = "submitting"
        save_session(record)
        pushed_head = push_detached_head(
            record.repo_path,
            record.worktree,
            record.target_branch,
            record.expected_remote_sha,
            head_sha=head,
        )
        record.expected_remote_sha = pushed_head
        record.remote_head_sha = pushed_head
        save_session(record)
        number, url = _find_or_create_pr(record, draft=draft, title=title)
        record.pr_number = number
        record.pr_url = url
        record.submitted_at = utc_now()
        save_session(record)
        release = release_session(record, _lock_held=True)
        if not release.released:
            record.phase = "submitted_needs_release"
            save_session(record)
        return PullRequest(number, url, record.target_branch, pushed_head)


def release_session(
    record: SessionRecord,
    *,
    keep_worktree: bool = False,
    _lock_held: bool = False,
) -> ReleaseResult:
    if not _lock_held:
        with state_lock(f"session-{record.id}"):
            return release_session(record, keep_worktree=keep_worktree, _lock_held=True)
    if not record.target_branch:
        return ReleaseResult(False, "session has no target branch", record.worktree)
    if not record.worktree.exists():
        stop_agent(record)
        remove_orphaned_container_project(record)
        if session_git_dir(record.id).is_dir():
            isolated_head = session_git_head(record.id)
            if remote_branch_sha(record.repo_path, record.target_branch) != isolated_head:
                return ReleaseResult(
                    False,
                    "worktree is absent but isolated Git HEAD is not published to origin",
                    record.worktree,
                )
        remove_session_git(record.id)
        record.phase = "released"
        record.ports = None
        save_session(record)
        return ReleaseResult(True, "worktree already absent", record.worktree)
    stop_session(record, _lock_held=True)
    if keep_worktree:
        return ReleaseResult(True, "session stopped; worktree retained", record.worktree)
    publish_state = branch_publish_state(record.repo_path, record.worktree, record.target_branch)
    if not publish_state.clean:
        return ReleaseResult(False, "worktree has uncommitted changes", record.worktree)
    if not publish_state.published:
        return ReleaseResult(False, "worktree HEAD is not published to origin", record.worktree)
    # Compose needs the worktree's manifests to resolve its environment, so
    # tear down containers and per-session volumes before removing the tree.
    remove_container_project(record, volumes=True)
    result = remove_session_worktree(record.repo_path, record.worktree, record.target_branch)
    if result.released:
        remove_session_git(record.id)
        record.phase = "released"
        record.ports = None
        save_session(record)
    return result
