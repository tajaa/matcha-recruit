from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .docker_runtime import session_home
from .git_worktrees import session_git_dir
from .models import SessionRecord


class SessionAuthError(RuntimeError):
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
    completed = subprocess.run(
        [
            "git",
            "--git-dir",
            str(git_dir),
            "config",
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
    config_dir = home / ".config/gh"
    hosts = config_dir / "hosts.yml"
    marker = config_dir / ".msandbox-token-sha256"
    fingerprint = hashlib.sha256(token.encode()).hexdigest()
    if (
        hosts.is_file()
        and not hosts.is_symlink()
        and marker.is_file()
        and not marker.is_symlink()
        and marker.read_text(encoding="utf-8").strip() == fingerprint
    ):
        _configure_github_git(record)
        return

    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".gh-auth.", dir=home) as temporary_name:
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
        _atomic_secret_copy(generated, hosts)

    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker.write_text(fingerprint + "\n", encoding="utf-8")
    marker.chmod(0o600)
    _configure_github_git(record)


def provision_session_auth(record: SessionRecord) -> None:
    _copy_agent_auth(record)
    refresh_github_auth(record)
