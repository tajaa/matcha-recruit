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
    push_detached_head,
    remove_session_worktree,
    resolve_ref,
)
from .models import PullRequest, ReleaseResult, SessionRecord, SessionSpec, utc_now
from .state import SCHEMA_VERSION, data_root, list_sessions, save_session, state_lock


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
        duplicates = [item for item in list_sessions() if item.name == spec.name]
        if duplicates:
            raise SessionError(f"an active session named {spec.name!r} already exists")
        session_id = f"{slug}-{secrets.token_hex(3)}"
        start_ref = spec.base_ref
        target_branch = f"codex/{slug}"
        pr_number = spec.pr_number
        if pr_number is not None:
            target_branch, _ = resolve_pr(repo, pr_number)
            fetch_origin(repo, target_branch)
            start_ref = f"origin/{target_branch}"
        elif start_ref.startswith("origin/") and os.environ.get("MSANDBOX_SKIP_FETCH") != "1":
            fetch_origin(repo, start_ref.removeprefix("origin/"))

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
            base_ref=start_ref,
            base_sha=info.head,
            target_branch=target_branch,
            pr_number=pr_number,
            ports=allocate_port_block() if spec.dev else None,
            dev=spec.dev,
            playwright=spec.playwright,
        )
        try:
            _copy_auth_templates(record)
            save_session(record)
            if spec.start:
                start_session(record, extra_agent_args)
        except Exception:
            stop_agent(record, force=True)
            remove_container_project(record)
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree_path)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            raise
        return record


def start_session(record: SessionRecord, extra_agent_args: Sequence[str] = ()) -> SessionRecord:
    ensure_container(record)
    launch_agent(record, extra_agent_args)
    record.phase = "running"
    save_session(record)
    return record


def reconcile_session(record: SessionRecord) -> SessionRecord:
    if record.phase == "released":
        return record
    if not record.worktree.exists():
        record.phase = "orphaned"
    elif container_running(record) and tmux_running(record):
        record.phase = "running"
    elif record.phase == "running":
        record.phase = "stopped"
    save_session(record)
    return record


def stop_session(record: SessionRecord, *, force: bool = False) -> None:
    stop_agent(record, force=force)
    stop_container(record)
    if record.phase not in ("released", "orphaned"):
        record.phase = "stopped"
        save_session(record)


def _validation_current(record: SessionRecord) -> bool:
    validation = record.last_validation
    return bool(
        validation
        and validation.status == "pass"
        and validation.commit_sha == current_head(record.worktree)
        and validation.dirty_fingerprint == dirty_fingerprint(record.worktree)
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
        status = subprocess.run(
            ["git", "-C", str(record.worktree), "status", "--porcelain=v1"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        if status:
            raise SessionError("session has uncommitted changes; commit them before submit")
        if os.environ.get("MSANDBOX_NO_VERIFY") != "1" and not _validation_current(record):
            raise SessionError("PR validation is missing or stale; run `msandbox test <session> --pr`")
        record.phase = "submitting"
        save_session(record)
        # Fetch the remote namespace without requiring this new PR branch to
        # exist yet. `git fetch origin <missing-branch>` aborts first submit.
        fetch_origin(record.repo_path)
        remote_result = subprocess.run(
            ["git", "-C", str(record.repo_path), "rev-parse", "--verify", f"origin/{record.target_branch}^{{commit}}"],
            check=False,
            text=True,
            capture_output=True,
        )
        expected = remote_result.stdout.strip() if remote_result.returncode == 0 else None
        head = push_detached_head(record.repo_path, record.worktree, record.target_branch, expected)
        number, url = _find_or_create_pr(record, draft=draft, title=title)
        record.pr_number = number
        record.pr_url = url
        record.remote_head_sha = head
        record.submitted_at = utc_now()
        save_session(record)
        release = release_session(record)
        if not release.released:
            record.phase = "submitted_needs_release"
            save_session(record)
        return PullRequest(number, url, record.target_branch, head)


def release_session(record: SessionRecord, *, keep_worktree: bool = False) -> ReleaseResult:
    if not record.target_branch:
        return ReleaseResult(False, "session has no target branch", record.worktree)
    stop_session(record)
    if keep_worktree:
        return ReleaseResult(True, "session stopped; worktree retained", record.worktree)
    result = remove_session_worktree(record.repo_path, record.worktree, record.target_branch)
    if result.released:
        remove_container_project(record)
        record.phase = "released"
        save_session(record)
    return result
