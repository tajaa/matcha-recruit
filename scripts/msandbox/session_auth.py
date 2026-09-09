from __future__ import annotations

import errno
import hashlib
import os
import secrets
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from .docker_runtime import session_home
from .git_worktrees import session_git_dir
from .models import SessionRecord


class SessionAuthError(RuntimeError):
    pass


AGENT_AUTH_FILES = {
    "codex": (".codex/auth.json",),
    "claude": (".claude/.credentials.json", ".claude.json"),
    "opencode": (".local/share/opencode/auth.json",),
}


@contextmanager
def switching_agent_auth(record: SessionRecord) -> Iterator[None]:
    """Remove other logins while stopped; restore login files if switching fails.

    Open every parent before changing anything. Directory symlinks fail closed;
    final symlinks are unlinked without ever following their targets. Histories
    and other harness files are untouched.
    """
    with ExitStack() as stack:
        files = []
        for agent, paths in AGENT_AUTH_FILES.items():
            for path in paths:
                relative = Path(path)
                fd = stack.enter_context(
                    _private_directory(session_home(record), *relative.parts[:-1])
                )
                files.append(
                    (agent, fd, relative.name, stack.enter_context(
                        _credential_backup(fd, relative.name)
                    ))
                )
        try:
            for agent, fd, name, _ in files:
                if agent != record.agent:
                    try:
                        os.unlink(name, dir_fd=fd)
                    except FileNotFoundError:
                        pass
            yield
        except BaseException:
            for _, fd, name, payload in files:
                if payload is not None:
                    payload.seek(0)
                    _atomic_private_write(fd, name, payload)
                else:
                    try:
                        os.unlink(name, dir_fd=fd)
                    except FileNotFoundError:
                        pass
            raise


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
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
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
            payload = handle.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise SessionAuthError(f"private credential file {name} exceeds 1 MiB")
            return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def _credential_backup(directory_fd: int, name: str):
    """Keep rollback copies outside the mounted home without a memory-size cap."""
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno not in (errno.ENOENT, errno.ELOOP):
            raise
        yield None
        return
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            yield None
            return
        with tempfile.TemporaryFile() as backup:
            shutil.copyfileobj(source, backup, length=1024 * 1024)
            backup.seek(0)
            yield backup


def _atomic_private_write(directory_fd: int, name: str, payload) -> None:
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
            if isinstance(payload, bytes):
                handle.write(payload)
            else:
                shutil.copyfileobj(payload, handle, length=1024 * 1024)
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


def _copy_agent_auth(record: SessionRecord, *, require_login: bool = False) -> None:
    """Seed only the selected agent's login; never copy histories or logs."""
    home = session_home(record)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    copied_login = False
    for path in AGENT_AUTH_FILES[record.agent]:
        source = Path.home() / path
        if source.is_file() and not source.is_symlink():
            relative = Path(path)
            with _private_directory(home, *relative.parts[:-1]) as directory_fd:
                fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    metadata = os.fstat(stream.fileno())
                    if not stat.S_ISREG(metadata.st_mode):
                        raise SessionAuthError("login source is not a regular file")
                    _atomic_private_write(directory_fd, relative.name, stream)
                    if path != ".claude.json" and metadata.st_size:
                        copied_login = True
    if require_login and not copied_login:
        raise SessionAuthError(
            f"No host {record.agent} login file is available. Authenticate with "
            f"{record.agent} on the host, then retry Change harness. Previous login is preserved."
        )


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


def provision_session_auth(record: SessionRecord, *, require_login: bool = False) -> None:
    _copy_agent_auth(record, require_login=require_login)
    refresh_github_auth(record)
