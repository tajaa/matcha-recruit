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


RELEASES_TO_KEEP = 2


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
            "scripts/__init__.py",
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
        "scripts/__init__.py",
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
                f"runtime_root={shlex.quote(str(destination))}\n"
                f"repo_root={shlex.quote(str(repo_root))}\n"
                "run_v2() { cd \"$runtime_root\" || exit 1; exec python3 -m scripts.msandbox \"$@\"; }\n"
                "case \"${1:-}\" in\n"
                "  ''|--version|--repo|wizard|session|worktree|pr|test|install|gc) run_v2 \"$@\" ;;\n"
                "  attach) if [ \"$#\" -gt 1 ] && [ ! -e \"${2:-}\" ]; then run_v2 \"$@\"; fi ;;\n"
                "  paste|doctor) if [ \"$#\" -gt 1 ]; then run_v2 \"$@\"; fi ;;\n"
                "esac\n"
                "legacy=\"$repo_root/scripts/agent-sandbox.sh\"\n"
                "if [ ! -x \"$legacy\" ]; then\n"
                "  echo \"msandbox: legacy control plane is unavailable at $legacy\" >&2\n"
                "  exit 1\n"
                "fi\n"
                "exec \"$legacy\" \"$@\"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o755)
        os.replace(temporary, launcher)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_legacy_host_service() -> None:
    """Retire the former container-triggered Xcode LaunchAgent on upgrade."""
    if __import__("sys").platform != "darwin":
        return
    label = "com.matcha.msandbox-hostd"
    if shutil.which("launchctl"):
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{label}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    (Path.home() / f"Library/LaunchAgents/{label}.plist").unlink(missing_ok=True)


def _active_release(releases: Path) -> Path | None:
    current = data_root() / "current"
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise InstallError(f"unsafe msandbox current release pointer: {current}")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(releases.resolve())
    except (OSError, ValueError) as exc:
        raise InstallError(f"unsafe msandbox current release pointer: {current}") from exc
    if not resolved.is_dir():
        raise InstallError(f"msandbox current release is missing: {resolved}")
    manifest_path = resolved / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid msandbox current release: {resolved}") from exc
    if manifest.get("release") != resolved.name:
        raise InstallError(f"msandbox current release manifest mismatch: {resolved}")
    return resolved


def _prune_installed_releases(releases: Path, keep: set[Path]) -> None:
    """Keep one rollback controller; images are rebuilt only if rolled back."""
    keep = {path.resolve() for path in keep}
    candidates: list[Path] = []
    for entry in releases.iterdir():
        if entry.name.startswith("."):
            continue
        manifest_path = entry / "manifest.json"
        if entry.is_symlink() or not entry.is_dir() or not manifest_path.is_file():
            raise InstallError(f"unsafe installed msandbox release: {entry}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise InstallError(f"invalid msandbox release manifest: {entry}") from exc
        if manifest.get("release") != entry.name:
            raise InstallError(f"msandbox release manifest mismatch: {entry}")
        candidates.append(entry)
    for entry in sorted(
        candidates,
        key=lambda candidate: (candidate.stat().st_mtime_ns, candidate.name),
        reverse=True,
    ):
        if len(keep) >= RELEASES_TO_KEEP:
            break
        keep.add(entry.resolve())
    for entry in candidates:
        if entry.resolve() in keep:
            continue
        shutil.rmtree(entry)


def _install_release_locked(*, repo_root: Path | None = None, bin_dir: Path | None = None) -> Path:
    ensure_roots()
    root = (repo_root or source_root()).resolve()
    release_id = _release_id(root)
    releases = data_root() / "releases"
    previous = _active_release(releases)
    destination = releases / release_id
    if destination.exists():
        manifest_path = destination / "manifest.json"
        if destination.is_symlink() or not manifest_path.is_file():
            raise InstallError(f"unsafe existing msandbox release: {destination}")
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest.get("release") != release_id:
            raise InstallError(f"msandbox release manifest mismatch: {destination}")
    else:
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

    keep = {destination}
    if previous is not None:
        keep.add(previous)
    if len(keep) > RELEASES_TO_KEEP:
        raise InstallError("msandbox release retention invariant failed")
    _prune_installed_releases(releases, keep)

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
    if bin_dir is None:
        _remove_legacy_host_service()
    return destination


def install_release(*, repo_root: Path | None = None, bin_dir: Path | None = None) -> Path:
    """Copy a controller release and atomically swap the stable launcher."""
    with state_lock("install", timeout_s=60):
        return _install_release_locked(repo_root=repo_root, bin_dir=bin_dir)


def rollback_release(release_id: str, *, bin_dir: Path | None = None) -> Path:
    if not release_id or release_id in (".", "..") or Path(release_id).name != release_id:
        raise InstallError(f"invalid msandbox release id: {release_id!r}")
    with state_lock("install", timeout_s=60):
        destination = data_root() / "releases" / release_id
        manifest_path = destination / "manifest.json"
        if not manifest_path.is_file() or destination.is_symlink():
            raise InstallError(f"unknown msandbox release: {release_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("release") != release_id or not isinstance(manifest.get("repo_root"), str):
            raise InstallError(f"invalid msandbox release manifest: {release_id}")
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
