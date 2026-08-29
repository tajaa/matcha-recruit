from __future__ import annotations

import os
import socket
import subprocess
import time
import hashlib
import platform
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .git_worktrees import git_common_dir, session_git_dir, session_git_pointer
from .models import PortSet, SessionRecord
from .state import data_root, state_lock, state_root


class DockerError(RuntimeError):
    pass


# Every content-addressed workspace build is a tag under this repository. The
# `:latest` tag in the same repository is NOT content-addressed — it is the
# legacy/AutoPR lane's image (docker-compose.sandbox.yml) and must never be
# treated as a collectable build.
IMAGE_REPOSITORY = "matcha-agent-sandbox-workspace"


def compose_project(session_id: str) -> str:
    safe = "".join(char if char.isalnum() else "-" for char in session_id.lower()).strip("-")
    return f"matcha-ms-{safe}"[:63]


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def allocate_port_block() -> PortSet:
    """Allocate one deterministic five-port slot under the global registry lock."""
    with state_lock("ports"):
        used = set()
        sessions_root = state_root() / "sessions"
        if sessions_root.is_dir():
            import json

            for record_path in sessions_root.glob("*/session.json"):
                try:
                    raw = json.loads(record_path.read_text(encoding="utf-8"))
                    if raw.get("phase") == "released":
                        continue
                    used.update(int(value) for value in (raw.get("ports") or {}).values())
                except (OSError, ValueError, TypeError):
                    continue
        for slot in range(0, 200):
            ports = PortSet(
                backend=18001 + slot,
                frontend=15174 + slot,
                tellus=15191 + slot,
                oceanlab=15201 + slot,
                chat=18080 + slot,
            )
            values = tuple(asdict(ports).values())
            if not any(port in used for port in values) and all(_port_available(port) for port in values):
                return ports
    raise DockerError("no free msandbox development port block is available")


def session_home(record: SessionRecord) -> Path:
    return data_root() / "homes" / record.id


def attachment_dir(record: SessionRecord) -> Path:
    return data_root() / "attachments" / record.id


def _dependency_volume(prefix: str, paths: Sequence[Path], template_id: str) -> str:
    digest = hashlib.sha256()
    digest.update(platform.machine().encode())
    digest.update(b"msandbox-dependencies-v3")
    digest.update(template_id.encode())
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return f"matcha-ms-deps-{prefix}-{digest.hexdigest()[:16]}"


def build_context_sources(record: SessionRecord, runtime_root: Path) -> dict[str, Path]:
    """The exact file set whose bytes name this session's image."""
    return {
        "docker/agent-sandbox/Dockerfile": runtime_root / "docker/agent-sandbox/Dockerfile",
        "docker/agent-sandbox/Dockerfile.dockerignore": runtime_root
        / "docker/agent-sandbox/Dockerfile.dockerignore",
        "docker/agent-sandbox/entrypoint.sh": runtime_root / "docker/agent-sandbox/entrypoint.sh",
        "server/requirements.txt": record.worktree / "server/requirements.txt",
        "client/package.json": record.worktree / "client/package.json",
        "client/package-lock.json": record.worktree / "client/package-lock.json",
        "client/tellus/package.json": record.worktree / "client/tellus/package.json",
        "client/tellus/package-lock.json": record.worktree / "client/tellus/package-lock.json",
        "client/oceanlab/package.json": record.worktree / "client/oceanlab/package.json",
        "client/oceanlab/package-lock.json": record.worktree / "client/oceanlab/package-lock.json",
    }


def build_identifier(sources: dict[str, Path], *, playwright: bool) -> str:
    """Content-address a build. Pure — garbage collection reads it without
    materializing a context directory for every candidate it has to consider."""
    digest = hashlib.sha256()
    digest.update(platform.machine().encode())
    digest.update(f"playwright={playwright}".encode())
    for relative, source in sources.items():
        if not source.is_file():
            raise DockerError(f"sandbox build input is missing: {source}")
        digest.update(relative.encode())
        digest.update(source.read_bytes())
    return digest.hexdigest()[:20]


def _materialize_build_context(record: SessionRecord, runtime_root: Path) -> tuple[Path, str, str]:
    """Create one immutable Docker context for this controller+lockfile set."""
    sources = build_context_sources(record, runtime_root)
    identifier = build_identifier(sources, playwright=record.playwright)
    destination = data_root() / "build-contexts" / identifier
    if not destination.is_dir():
        with state_lock(f"build-context-{identifier}"):
            if not destination.is_dir():
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temporary = Path(
                    tempfile.mkdtemp(prefix=f".{identifier}.", dir=destination.parent)
                )
                try:
                    for relative, source in sources.items():
                        target = temporary / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                    os.replace(temporary, destination)
                finally:
                    shutil.rmtree(temporary, ignore_errors=True)
    return destination, f"{IMAGE_REPOSITORY}:{identifier}", identifier


def _safe_git_subdirectory(common_dir: Path, relative: Path) -> Path:
    common_dir = common_dir.resolve()
    candidate = common_dir / relative
    if candidate.is_symlink() or not candidate.is_dir():
        raise DockerError(f"unsafe or missing Git metadata directory: {candidate}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(common_dir)
    except ValueError as exc:
        raise DockerError(f"Git metadata directory escapes the common directory: {candidate}") from exc
    return resolved


def compose_environment(record: SessionRecord) -> dict[str, str]:
    common_dir = git_common_dir(record.repo_path)
    objects_dir = _safe_git_subdirectory(common_dir, Path("objects"))
    isolated_git_dir = session_git_dir(record.id)
    isolated_git_pointer = session_git_pointer(record.id)
    expected_root = (data_root() / "git-sessions").resolve()
    try:
        isolated_git_dir.resolve().relative_to(expected_root)
        isolated_git_pointer.resolve().relative_to(expected_root)
    except ValueError as exc:
        raise DockerError("isolated Git metadata escapes the msandbox data root") from exc
    if (
        isolated_git_dir.is_symlink()
        or not isolated_git_dir.is_dir()
        or isolated_git_pointer.is_symlink()
        or not isolated_git_pointer.is_file()
    ):
        raise DockerError(f"isolated Git metadata is missing or unsafe for {record.id}")
    home = session_home(record)
    attachments = attachment_dir(record)
    for directory in (home, attachments):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime_root = Path(os.environ.get("MSANDBOX_RUNTIME_ROOT", record.repo_path))
    # Build inputs are copied to a content-addressed context. This prevents two
    # parallel PRs with different lockfiles from racing on one mutable `latest`
    # image, and keeps the controller/Dockerfile stable across branch switches.
    build_context, image, template_id = _materialize_build_context(record, runtime_root)
    environment = dict(os.environ)
    environment.update(
        {
            "SANDBOX_BUILD_CONTEXT": str(build_context),
            "SANDBOX_DOCKERFILE": "docker/agent-sandbox/Dockerfile",
            "SANDBOX_IMAGE": image,
            "SANDBOX_WORKSPACE_DIR": str(record.worktree),
            "SANDBOX_GIT_OBJECTS_DIR": str(objects_dir),
            "MSANDBOX_GIT_DIR": str(isolated_git_dir.resolve()),
            "MSANDBOX_GIT_POINTER_FILE": str(isolated_git_pointer.resolve()),
            "SANDBOX_DEPENDENCY_TEMPLATE_ID": template_id,
            "MSANDBOX_SESSION_ID": record.id,
            "MSANDBOX_SESSION_HOME": str(home),
            "MSANDBOX_ATTACHMENTS_HOST_DIR": str(attachments),
            "SANDBOX_AWS_DIR": str(Path.home() / ".aws"),
            "SANDBOX_UID": str(os.getuid()),
            "SANDBOX_GID": str(os.getgid()),
            "INSTALL_PLAYWRIGHT_BROWSERS": "true" if record.playwright else "false",
        }
    )
    environment.update(
        {
            "SANDBOX_SERVER_VENV_VOLUME": _dependency_volume(
                "server",
                [record.worktree / "server/requirements.txt"],
                template_id,
            ),
            "SANDBOX_CLIENT_NODE_MODULES_VOLUME": _dependency_volume(
                "client",
                [record.worktree / "client/package-lock.json"],
                template_id,
            ),
            "SANDBOX_TELLUS_NODE_MODULES_VOLUME": _dependency_volume(
                "tellus",
                [record.worktree / "client/tellus/package-lock.json"],
                template_id,
            ),
            "SANDBOX_OCEANLAB_NODE_MODULES_VOLUME": _dependency_volume(
                "oceanlab",
                [record.worktree / "client/oceanlab/package-lock.json"],
                template_id,
            ),
        }
    )
    if record.ports:
        environment.update(
            {
                "SANDBOX_HOST_BACKEND_PORT": str(record.ports.backend),
                "SANDBOX_HOST_FRONTEND_PORT": str(record.ports.frontend),
                "SANDBOX_HOST_TELLUS_PORT": str(record.ports.tellus),
                "SANDBOX_HOST_OCEANLAB_PORT": str(record.ports.oceanlab),
                "SANDBOX_HOST_CHAT_PORT": str(record.ports.chat),
            }
        )
    return environment


def compose_command(record: SessionRecord, *argv: str, test_services: bool = False) -> list[str]:
    root = Path(os.environ.get("MSANDBOX_RUNTIME_ROOT", record.repo_path))
    command = [
        "docker",
        "compose",
        "--project-name",
        record.compose_project,
        "--file",
        str(root / "docker-compose.sandbox.yml"),
        "--file",
        str(root / "docker-compose.sandbox-session.yml"),
    ]
    if record.dev:
        command.extend(["--file", str(root / "docker-compose.sandbox-dev.yml")])
    if test_services:
        command.extend(["--file", str(root / "docker-compose.sandbox-test.yml")])
    return [*command, *argv]


def _run_compose(
    record: SessionRecord,
    *argv: str,
    check: bool = True,
    capture: bool = False,
    test_services: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        compose_command(record, *argv, test_services=test_services),
        env=compose_environment(record),
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode:
        message = (result.stderr or result.stdout or "docker compose failed").strip()
        raise DockerError(message)
    return result


def require_docker() -> None:
    result = subprocess.run(
        ["docker", "info"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        raise DockerError("Docker is not running or is not accessible")


def ensure_container(record: SessionRecord, *, test_services: bool = False) -> None:
    require_docker()
    services = ["--detach"]
    if test_services:
        services.extend(["postgres", "redis"])
    services.append("workspace")
    environment = compose_environment(record)
    # Content-addressed images can build concurrently; BuildKit deduplicates
    # identical layers. Only initialization of shared dependency volumes needs
    # the cross-session lock below.
    build = subprocess.run(
        compose_command(record, "build", "workspace", test_services=test_services),
        env=environment,
        check=False,
        text=True,
    )
    if build.returncode:
        raise DockerError("workspace image build failed")
    # A successful build is the exact moment the image it supersedes became
    # garbage, so reclaim here rather than waiting for someone to remember.
    # Imported late: docker_gc reads this module's primitives.
    from .docker_gc import collect_garbage_quietly

    collect_garbage_quietly(record)
    with state_lock("dependency-initialization", timeout_s=600):
        for variable in (
            "SANDBOX_SERVER_VENV_VOLUME",
            "SANDBOX_CLIENT_NODE_MODULES_VOLUME",
            "SANDBOX_TELLUS_NODE_MODULES_VOLUME",
            "SANDBOX_OCEANLAB_NODE_MODULES_VOLUME",
        ):
            volume = environment[variable]
            inspected = subprocess.run(
                ["docker", "volume", "inspect", volume],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if inspected.returncode:
                subprocess.run(["docker", "volume", "create", volume], check=True, stdout=subprocess.DEVNULL)
        initialize = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--env",
                "MSANDBOX_INITIALIZE_DEPENDENCIES=1",
                "--volume",
                f"{environment['SANDBOX_SERVER_VENV_VOLUME']}:/workspace/server/venv",
                "--volume",
                f"{environment['SANDBOX_CLIENT_NODE_MODULES_VOLUME']}:/workspace/client/node_modules",
                "--volume",
                f"{environment['SANDBOX_TELLUS_NODE_MODULES_VOLUME']}:/workspace/client/tellus/node_modules",
                "--volume",
                f"{environment['SANDBOX_OCEANLAB_NODE_MODULES_VOLUME']}:/workspace/client/oceanlab/node_modules",
                environment["SANDBOX_IMAGE"],
                "true",
            ],
            check=False,
            text=True,
        )
        if initialize.returncode:
            raise DockerError("workspace dependency initialization failed")
    _run_compose(record, "up", "--no-build", *services, test_services=test_services)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        ready = _run_compose(
            record,
            "exec",
            "--no-TTY",
            "workspace",
            "test",
            "-f",
            "/run/msandbox-ready",
            check=False,
            capture=True,
            test_services=test_services,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.25)
    raise DockerError("workspace dependency initialization did not become ready within 180 seconds")


def stop_container(record: SessionRecord) -> None:
    if not shutil_which("docker"):
        return
    _run_compose(record, "stop", "workspace", check=False)


def remove_container_project(record: SessionRecord, *, volumes: bool = False) -> None:
    if not shutil_which("docker"):
        return
    argv = ["down", "--remove-orphans"]
    if volumes:
        argv.append("--volumes")
    _run_compose(record, *argv, check=False, test_services=True)


def remove_orphaned_container_project(record: SessionRecord) -> None:
    """Remove resources by the exact Compose label when manifests are unavailable."""
    if not shutil_which("docker"):
        return
    label = f"label=com.docker.compose.project={record.compose_project}"
    for resource in ("container", "volume", "network"):
        listed = subprocess.run(
            [
                "docker",
                resource,
                "ls",
                *(["--all"] if resource == "container" else []),
                "--quiet",
                "--filter",
                label,
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        identifiers = (listed.stdout or "").split()
        if not identifiers:
            continue
        command = ["docker", resource, "rm"]
        if resource == "container":
            command.append("--force")
        subprocess.run([*command, *identifiers], check=False, capture_output=True)


def container_running(record: SessionRecord) -> bool:
    if not shutil_which("docker"):
        return False
    result = _run_compose(
        record,
        "ps",
        "--status",
        "running",
        "--quiet",
        "workspace",
        check=False,
        capture=True,
    )
    return result.returncode == 0 and bool((result.stdout or "").strip())


def exec_in_session(
    record: SessionRecord,
    argv: Sequence[str],
    *,
    tty: bool,
    login_shell: bool = False,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = list(argv)
    if login_shell:
        import shlex

        command = ["bash", "-lc", shlex.join(command)]
    compose_argv = ["exec"]
    if not tty:
        compose_argv.append("--no-TTY")
    compose_argv.extend(["--user", f"{os.getuid()}:{os.getgid()}", "workspace", *command])
    return _run_compose(record, *compose_argv, capture=capture, check=False)


def shutil_which(binary: str) -> str | None:
    import shutil

    return shutil.which(binary)
