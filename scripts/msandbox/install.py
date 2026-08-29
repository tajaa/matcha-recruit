from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import hashlib
from pathlib import Path

from . import __version__
from .state import config_root, data_root, ensure_roots, state_lock


class InstallError(RuntimeError):
    pass


def source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _release_id(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
        check=False,
        text=True,
        capture_output=True,
    )
    sha = result.stdout.strip() if result.returncode == 0 else "uncommitted"
    dirty = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--",
            "scripts/msandbox",
            "docker-compose.sandbox.yml",
            "docker-compose.sandbox-session.yml",
            "docker-compose.sandbox-dev.yml",
            "docker-compose.sandbox-test.yml",
            "docker-compose.autopr-sandbox.yml",
            "docker/agent-sandbox",
            "server/requirements.txt",
            "client/package.json",
            "client/package-lock.json",
            "client/tellus/package.json",
            "client/tellus/package-lock.json",
            "client/oceanlab/package.json",
            "client/oceanlab/package-lock.json",
        ],
        check=False,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if not dirty:
        return sha
    digest = hashlib.sha256()
    for relative in (
        "scripts/msandbox",
        "docker-compose.sandbox.yml",
        "docker-compose.sandbox-session.yml",
        "docker-compose.sandbox-dev.yml",
        "docker-compose.sandbox-test.yml",
        "docker-compose.autopr-sandbox.yml",
        "docker/agent-sandbox",
        "server/requirements.txt",
        "client/package.json",
        "client/package-lock.json",
        "client/tellus/package.json",
        "client/tellus/package-lock.json",
        "client/oceanlab/package.json",
        "client/oceanlab/package-lock.json",
    ):
        candidate = root / relative
        paths = sorted(candidate.rglob("*")) if candidate.is_dir() else [candidate]
        for path in paths:
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(str(path.relative_to(root)).encode())
                digest.update(path.read_bytes())
    return f"{sha}-dirty-{digest.hexdigest()[:10]}"


def _write_launcher(destination: Path, repo_root: Path, bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "msandbox"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".msandbox.", dir=bin_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/bin/sh\n"
                f"export MSANDBOX_RUNTIME_ROOT={shlex.quote(str(destination))}\n"
                f"export MATCHA_REPO_ROOT={shlex.quote(str(repo_root))}\n"
                f"cd {shlex.quote(str(destination))}\n"
                "exec python3 -m scripts.msandbox \"$@\"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o755)
        os.replace(temporary, launcher)
    finally:
        temporary.unlink(missing_ok=True)


def _install_release_locked(*, repo_root: Path | None = None, bin_dir: Path | None = None) -> Path:
    ensure_roots()
    root = (repo_root or source_root()).resolve()
    release_id = _release_id(root)
    releases = data_root() / "releases"
    destination = releases / release_id
    if not destination.exists():
        temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=releases))
        try:
            (temporary / "scripts").mkdir(parents=True)
            shutil.copy2(root / "scripts/__init__.py", temporary / "scripts/__init__.py")
            shutil.copytree(
                root / "scripts/msandbox",
                temporary / "scripts/msandbox",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            for compose in (
                "docker-compose.sandbox.yml",
                "docker-compose.sandbox-session.yml",
                "docker-compose.sandbox-dev.yml",
                "docker-compose.sandbox-test.yml",
                "docker-compose.autopr-sandbox.yml",
            ):
                shutil.copy2(root / compose, temporary / compose)
            shutil.copytree(root / "docker/agent-sandbox", temporary / "docker/agent-sandbox")
            # Dockerfiles may only COPY files inside their build context. Preserve
            # the dependency manifests in the immutable release so `msandbox`
            # remains buildable after the source checkout switches branches.
            for relative in (
                "server/requirements.txt",
                "client/package.json",
                "client/package-lock.json",
                "client/tellus/package.json",
                "client/tellus/package-lock.json",
                "client/oceanlab/package.json",
                "client/oceanlab/package-lock.json",
            ):
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / relative, target)
            manifest = {"version": __version__, "release": release_id, "repo_root": str(root)}
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, destination)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    current = data_root() / "current"
    next_link = data_root() / ".current.next"
    next_link.unlink(missing_ok=True)
    next_link.symlink_to(destination)
    os.replace(next_link, current)

    config = config_root() / "config.json"
    descriptor, config_temporary_name = tempfile.mkstemp(prefix=".config.", dir=config.parent)
    config_temporary = Path(config_temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "repo_root": str(root)}, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(config_temporary, 0o600)
        os.replace(config_temporary, config)
    finally:
        config_temporary.unlink(missing_ok=True)
    resolved_bin_dir = (bin_dir or Path.home() / ".local/bin").expanduser()
    _write_launcher(destination, root, resolved_bin_dir)
    if bin_dir is None and __import__("sys").platform == "darwin" and os.environ.get("MSANDBOX_SKIP_HOST_SERVICE") != "1":
        from .host_actions import install_host_service

        install_host_service(msandbox_bin=resolved_bin_dir / "msandbox")
    return destination


def install_release(*, repo_root: Path | None = None, bin_dir: Path | None = None) -> Path:
    """Copy a controller release and atomically swap the stable launcher."""
    with state_lock("install", timeout_s=60):
        return _install_release_locked(repo_root=repo_root, bin_dir=bin_dir)


def rollback_release(release_id: str, *, bin_dir: Path | None = None) -> Path:
    destination = data_root() / "releases" / release_id
    manifest_path = destination / "manifest.json"
    if not manifest_path.is_file():
        raise InstallError(f"unknown msandbox release: {release_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = data_root() / "current"
    next_link = data_root() / ".current.next"
    next_link.unlink(missing_ok=True)
    next_link.symlink_to(destination)
    os.replace(next_link, current)
    _write_launcher(
        destination,
        Path(manifest["repo_root"]),
        (bin_dir or Path.home() / ".local/bin").expanduser(),
    )
    return destination
