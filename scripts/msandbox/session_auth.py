from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .docker_runtime import session_home
from .git_worktrees import session_git_dir
from .models import SessionRecord


class SessionAuthError(RuntimeError):
    pass


def _directory_open_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise SessionAuthError("host does not support no-follow credential directories")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def _private_directory(root: Path, *parts: str) -> Iterator[int]:
    """Open a private directory chain without following session-created links."""
    if any(not part or part in (".", "..") or "/" in part for part in parts):
        raise SessionAuthError("invalid private directory component")
    descriptors: list[int] = []
    target = root.joinpath(*parts)
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        current = os.open(root, _directory_open_flags())
        descriptors.append(current)
        os.fchmod(current, 0o700)
        for part in parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current)
            except FileExistsError:
                pass
            current = os.open(part, _directory_open_flags(), dir_fd=current)
            descriptors.append(current)
            os.fchmod(current, 0o700)
    except OSError as exc:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise SessionAuthError(
            f"unsafe private controller directory {target}: {exc}"
        ) from exc
    try:
        yield current
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_private_regular_file(directory_fd: int, name: str) -> bytes | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        return None
    except OSError:
        # A symlink or another unsafe entry is treated as stale. Atomic replace
        # below can safely replace a final symlink without following it.
        return None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _atomic_private_write(directory_fd: int, name: str, payload: bytes) -> None:
    if not name or name in (".", "..") or "/" in name:
        raise SessionAuthError("invalid private credential filename")
    temporary = f".{name}.{secrets.token_hex(8)}"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o600)
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
    except OSError as exc:
        raise SessionAuthError(f"could not safely replace private file {name}: {exc}") from exc
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _atomic_secret_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _copy_agent_auth(record: SessionRecord) -> None:
    """Seed only the selected agent's login; never copy histories or logs."""
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
        if source.is_file() and not source.is_symlink():
            _atomic_secret_copy(source, destination)


def _github_origin(record: SessionRecord) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(record.repo_path), "remote", "get-url", "origin"],
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0 and "github.com" in completed.stdout.lower()


def _configure_github_git(record: SessionRecord) -> None:
    git_dir = session_git_dir(record.id)
    if not git_dir.is_dir():
        return
    with _private_directory(git_dir) as git_fd:
        config = _read_private_regular_file(git_fd, "config")
        if config is None:
            raise SessionAuthError(
                f"isolated Git config is unsafe or missing: {git_dir / 'config'}"
            )
        with tempfile.TemporaryDirectory(prefix=".msandbox-git-config.") as temporary_name:
            temporary_config = Path(temporary_name) / "config"
            temporary_config.write_bytes(config)
            temporary_config.chmod(0o600)
            completed = subprocess.run(
                [
                    "git",
                    "config",
                    "--file",
                    str(temporary_config),
                    "--no-includes",
                    "credential.https://github.com.helper",
                    "!gh auth git-credential",
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            if completed.returncode:
                raise SessionAuthError(
                    completed.stderr.strip() or "could not configure GitHub Git credentials"
                )
            _atomic_private_write(git_fd, "config", temporary_config.read_bytes())


def refresh_github_auth(record: SessionRecord) -> None:
    """Materialize the host keychain token in this isolated session home.

    Modern macOS gh installations keep the OAuth token in Keychain, so copying
    hosts.yml alone produces a Linux config that names an account but has no
    usable token. The host controller resolves the active token in memory and
    asks gh to write a private, session-local config. The token never enters a
    Compose environment, Docker metadata, command line, or shared Git config.
    """
    if not _github_origin(record):
        return
    gh = shutil.which("gh")
    if not gh:
        raise SessionAuthError("GitHub CLI is missing on the host")
    token_result = subprocess.run(
        [gh, "auth", "token", "--hostname", "github.com"],
        check=False,
        text=True,
        capture_output=True,
    )
    token = token_result.stdout.strip()
    if token_result.returncode or not token:
        raise SessionAuthError(
            "host GitHub login is unavailable; run `gh auth login --hostname github.com "
            "--git-protocol https --web`, then reopen the msandbox session"
        )

    home = session_home(record)
    fingerprint = hashlib.sha256(token.encode()).hexdigest()
    with _private_directory(home, ".config", "gh") as config_fd:
        hosts = _read_private_regular_file(config_fd, "hosts.yml")
        marker = _read_private_regular_file(config_fd, ".msandbox-token-sha256")
        if (
            hosts is not None
            and marker is not None
            and marker.strip() == fingerprint.encode()
        ):
            _configure_github_git(record)
            return

        # Keep the plaintext staging config outside the container's mounted
        # home so a running session cannot race or replace it before copying.
        with tempfile.TemporaryDirectory(prefix=".gh-auth.") as temporary_name:
            temporary_config = Path(temporary_name)
            environment = dict(os.environ)
            environment.pop("GH_TOKEN", None)
            environment.pop("GITHUB_TOKEN", None)
            environment["GH_CONFIG_DIR"] = str(temporary_config)
            login = subprocess.run(
                [
                    gh,
                    "auth",
                    "login",
                    "--hostname",
                    "github.com",
                    "--git-protocol",
                    "https",
                    "--with-token",
                    "--insecure-storage",
                ],
                input=token + "\n",
                env=environment,
                check=False,
                text=True,
                capture_output=True,
            )
            generated = temporary_config / "hosts.yml"
            if login.returncode or not generated.is_file():
                raise SessionAuthError(
                    login.stderr.strip() or "could not create isolated GitHub CLI credentials"
                )
            _atomic_private_write(config_fd, "hosts.yml", generated.read_bytes())
        _atomic_private_write(
            config_fd,
            ".msandbox-token-sha256",
            fingerprint.encode() + b"\n",
        )
    _configure_github_git(record)


def provision_session_auth(record: SessionRecord) -> None:
    _copy_agent_auth(record)
    refresh_github_auth(record)
