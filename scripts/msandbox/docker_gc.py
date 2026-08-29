"""Reclaim msandbox Docker artifacts that no live session can reach.

Every workspace build is content-addressed
(:func:`docker_runtime._materialize_build_context`), so any edit to the
Dockerfile, the entrypoint, or one of the seven lockfiles mints a brand-new
multi-GB image and strands the previous one. The dependency volume names are
derived from that same identifier, so the four `matcha-ms-deps-*` volumes rotate
with it. Nothing else in the controller ever deletes either. This module
computes what is still reachable and removes the rest.

Reachability is deliberately conservative. Anything it cannot prove is garbage
is kept, and if any live session's inputs cannot be read at all it collects
nothing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .docker_runtime import (
    IMAGE_REPOSITORY,
    DockerError,
    _dependency_volume,
    build_context_sources,
    build_identifier,
)
from .models import SessionRecord
from .state import data_root, list_sessions, state_lock

SESSION_PREFIX = "matcha-ms-"

# `:latest` is not content-addressed. docker-compose.sandbox.yml:9 defaults to
# it and both the legacy interactive lane and the AutoPR lane run it, so no
# SessionRecord ever names it.
PROTECTED_IMAGES = frozenset({f"{IMAGE_REPOSITORY}:latest"})

# Compose projects that live outside the session model entirely — the legacy
# lane plus the three AutoPR lanes (scripts/agent-sandbox.sh:59-62). They have
# no SessionRecord, so nothing below can mark their volumes reachable. Chief
# among them is matcha-agent-sandbox_sandbox_home, which holds every agent's
# login and cannot be regenerated without four interactive sign-ins.
PROTECTED_PROJECTS = (
    "matcha-agent-sandbox",
    "matcha-kanban-autopr-sandbox",
    "matcha-error-autofix-sandbox",
    "matcha-autopr-self-audit-sandbox",
)

# The dependency volumes are shared between sessions and content-addressed, so a
# given volume keeps the compose label of whichever project created it first.
# Selecting them by label would therefore delete a volume a live session is
# using; they are matched by name against the recomputed reachable set instead.
# Mirrors the four volumes ensure_container initializes in docker_runtime.
DEPENDENCY_MANIFESTS = (
    ("server", "server/requirements.txt"),
    ("client", "client/package-lock.json"),
    ("tellus", "client/tellus/package-lock.json"),
    ("oceanlab", "client/oceanlab/package-lock.json"),
)


@dataclass
class Reachable:
    images: set[str] = field(default_factory=lambda: set(PROTECTED_IMAGES))
    volumes: set[str] = field(default_factory=set)
    projects: set[str] = field(default_factory=lambda: set(PROTECTED_PROJECTS))
    build_contexts: set[str] = field(default_factory=set)
    session_ids: set[str] = field(default_factory=set)
    complete: bool = True
    reason: str | None = None

    def covers_volume(self, name: str) -> bool:
        if name in self.volumes:
            return True
        return any(name.startswith(f"{project}_") for project in self.projects)


@dataclass
class GcItem:
    kind: str
    name: str
    detail: str | None = None


@dataclass
class GcReport:
    collected: list[GcItem] = field(default_factory=list)
    failed: list[GcItem] = field(default_factory=list)
    skipped: str | None = None

    def __bool__(self) -> bool:
        return bool(self.collected or self.failed)


def _docker(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *argv],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    if result.returncode:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def runtime_roots(repo: Path) -> list[Path]:
    """Every root whose Dockerfile could name an image that must be kept.

    The installed launcher exports MSANDBOX_RUNTIME_ROOT pointing at a release
    under data_root()/releases (install.py), and `msandbox install --rollback`
    can activate any release still on disk. Each carries its own copy of
    docker/agent-sandbox, so each names a different content-addressed tag.
    Collecting against a single root would delete a rollback target's image.
    """
    candidates = [repo]
    current = os.environ.get("MSANDBOX_RUNTIME_ROOT")
    if current:
        candidates.append(Path(current))
    releases = data_root() / "releases"
    if releases.is_dir():
        candidates.extend(
            entry for entry in sorted(releases.iterdir()) if entry.is_dir() and not entry.is_symlink()
        )
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in seen and (resolved / "docker/agent-sandbox/Dockerfile").is_file():
            seen.add(resolved)
            roots.append(resolved)
    return roots


def reachable(repo: Path) -> Reachable:
    """What every live session, and every release it could roll back to, needs."""
    result = Reachable()
    roots = runtime_roots(repo)
    for record in list_sessions():
        result.session_ids.add(record.id)
        result.projects.add(record.compose_project)
        for root in roots:
            sources = build_context_sources(record, root)
            # A session can flip to Playwright mid-life (`msandbox test
            # --browser` sets record.playwright and rebuilds), so both variants
            # of the same worktree stay reachable.
            for playwright in (False, True):
                try:
                    identifier = build_identifier(sources, playwright=playwright)
                except DockerError as exc:
                    result.complete = False
                    result.reason = f"{record.id}: {exc}"
                    return result
                result.images.add(f"{IMAGE_REPOSITORY}:{identifier}")
                result.build_contexts.add(identifier)
                for prefix, manifest in DEPENDENCY_MANIFESTS:
                    result.volumes.add(
                        _dependency_volume(prefix, [record.worktree / manifest], identifier)
                    )
    return result


def _containers() -> list[tuple[str, str, str, str]]:
    """(name, state, image, compose project) for every container, running or not.

    `.Label` and not `index .Labels`: in `docker ps --format` the Labels field
    is a comma-joined string, so indexing it as a map fails the template and
    silently yields no rows at all.
    """
    result = _docker(
        "ps",
        "--all",
        "--format",
        '{{.Names}}\t{{.State}}\t{{.Image}}\t{{.Label "com.docker.compose.project"}}',
    )
    rows = []
    for line in _lines(result):
        parts = line.split("\t")
        if len(parts) == 4:
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def _mounted_volumes(names: list[str]) -> set[str]:
    if not names:
        return set()
    result = _docker(
        "inspect",
        "--format",
        "{{range .Mounts}}{{println .Name}}{{end}}",
        *names,
    )
    return set(_lines(result))


def collect_garbage(repo: Path, *, apply: bool = False) -> GcReport:
    """Remove unreachable sandbox images, volumes, containers and host state."""
    report = GcReport()
    if not shutil.which("docker"):
        report.skipped = "docker is not available"
        return report
    live = reachable(repo)
    if not live.complete:
        # A live session whose build inputs cannot be read makes every image
        # indistinguishable from garbage. Collect nothing rather than guess.
        report.skipped = f"reachability is incomplete ({live.reason})"
        return report

    # A stopped container of a dead project pins its image and volumes, so it
    # has to go first or the sweeps below cannot reach them. Only non-running
    # containers are ever removed. The survivors — not the current `docker ps`
    # — define what is still in use, so a dry run previews exactly what
    # `--apply` would collect instead of under-reporting by one pass.
    containers = _containers()
    doomed = {
        name
        for name, state, _, project in containers
        if project.startswith(SESSION_PREFIX) and project not in live.projects and state != "running"
    }
    survivors = [row for row in containers if row[0] not in doomed]
    for name in sorted(doomed):
        if not apply:
            report.collected.append(GcItem("container", name))
            continue
        removed = _docker("rm", name)
        item = GcItem("container", name, None if removed.returncode == 0 else removed.stderr.strip())
        (report.collected if removed.returncode == 0 else report.failed).append(item)

    in_use_images = {image for _, _, image, _ in survivors}
    for image in _lines(
        _docker("images", "--filter", f"reference={IMAGE_REPOSITORY}:*", "--format", "{{.Repository}}:{{.Tag}}")
    ):
        if image in live.images or image in in_use_images or image.endswith(":<none>"):
            continue
        if not apply:
            report.collected.append(GcItem("image", image))
            continue
        removed = _docker("rmi", image)
        item = GcItem("image", image, None if removed.returncode == 0 else removed.stderr.strip())
        (report.collected if removed.returncode == 0 else report.failed).append(item)

    # ensure_container creates dependency volumes under this lock between an
    # inspect and a create (docker_runtime.py); taking it here keeps GC from
    # deleting a volume in that window.
    with state_lock("dependency-initialization", timeout_s=600):
        mounted = _mounted_volumes([name for name, _, _, _ in survivors])
        for volume in _lines(_docker("volume", "ls", "--format", "{{.Name}}")):
            if not volume.startswith(SESSION_PREFIX):
                continue
            if live.covers_volume(volume) or volume in mounted:
                continue
            if not apply:
                report.collected.append(GcItem("volume", volume))
                continue
            removed = _docker("volume", "rm", volume)
            item = GcItem("volume", volume, None if removed.returncode == 0 else removed.stderr.strip())
            (report.collected if removed.returncode == 0 else report.failed).append(item)

    for kind, directory, keep in (
        ("build-context", data_root() / "build-contexts", live.build_contexts),
        ("session-home", data_root() / "homes", live.session_ids),
    ):
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.name in keep or entry.is_symlink() or not entry.is_dir():
                continue
            if not apply:
                report.collected.append(GcItem(kind, entry.name))
                continue
            try:
                shutil.rmtree(entry)
            except OSError as exc:
                report.failed.append(GcItem(kind, entry.name, str(exc)))
            else:
                report.collected.append(GcItem(kind, entry.name))
    return report


def collect_garbage_quietly(record: SessionRecord) -> None:
    """Best-effort GC after a successful build — the moment the image it just
    superseded became garbage. Never allowed to fail the build that triggered it."""
    if os.environ.get("MSANDBOX_SKIP_GC") == "1":
        return
    try:
        collect_garbage(record.repo_path, apply=True)
    except Exception:  # noqa: BLE001 - reclaiming disk must never break a build
        pass
