from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


AgentName = Literal["codex", "opencode", "claude"]
PermissionMode = Literal["standard", "autonomous"]
SessionPhase = Literal[
    "created",
    "running",
    "stopped",
    "submitting",
    "submitted_needs_release",
    "released",
    "orphaned",
]
ValidationStatus = Literal["pass", "fail", "unavailable", "skip"]
CapabilityStatus = Literal["available", "unavailable", "denied"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class CapabilityResult:
    """One measured capability. Never holds a credential, token, connection
    string, PEM path, response body, or unredacted command output."""

    id: str
    title: str
    status: CapabilityStatus
    detail: str
    invocation: str | None = None
    checked_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CapabilityReport:
    schema_version: int
    session_id: str
    results: tuple[CapabilityResult, ...]
    checked_at: str
    # Whether the container was up for this measurement. None on reports written
    # before the field existed.
    container_available: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "checked_at": self.checked_at,
            "container_available": self.container_available,
            "results": [asdict(item) for item in self.results],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CapabilityReport":
        measured = raw.get("container_available")
        return cls(
            schema_version=int(raw["schema_version"]),
            session_id=str(raw["session_id"]),
            results=tuple(CapabilityResult(**item) for item in raw.get("results", ())),
            checked_at=str(raw["checked_at"]),
            container_available=None if measured is None else bool(measured),
        )

    def by_id(self, capability_id: str) -> CapabilityResult | None:
        return next((item for item in self.results if item.id == capability_id), None)


@dataclass(frozen=True)
class SessionSpec:
    name: str
    agent: AgentName
    base_ref: str = "origin/main"
    pr_number: int | None = None
    dev: bool = False
    playwright: bool = False
    start: bool = True
    permission_mode: PermissionMode = "standard"


@dataclass(frozen=True)
class PortSet:
    backend: int
    frontend: int
    tellus: int
    oceanlab: int
    chat: int


@dataclass
class ValidationReference:
    mode: str
    commit_sha: str
    dirty_fingerprint: str
    status: ValidationStatus
    result_path: str
    finished_at: str


@dataclass
class SessionRecord:
    schema_version: int
    id: str
    name: str
    agent: AgentName
    phase: SessionPhase
    repo_root: str
    worktree_path: str
    git_admin_name: str
    compose_project: str
    tmux_session: str
    base_ref: str
    base_sha: str
    target_branch: str | None
    permission_mode: PermissionMode = "standard"
    start_sha: str | None = None
    expected_remote_sha: str | None = None
    synchronized_sha: str | None = None
    agent_session_id: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    remote_head_sha: str | None = None
    ports: PortSet | None = None
    dev: bool = False
    playwright: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    submitted_at: str | None = None
    last_validation: ValidationReference | None = None
    last_capability_check_at: str | None = None
    capability_report_path: str | None = None

    @property
    def repo_path(self) -> Path:
        return Path(self.repo_root)

    @property
    def worktree(self) -> Path:
        return Path(self.worktree_path)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SessionRecord":
        data = dict(raw)
        # Sessions created before permission modes were recorded always used
        # bypass flags/permissive OpenCode config. Preserve and label that
        # behavior instead of silently presenting an old session as Standard.
        data.setdefault("permission_mode", "autonomous")
        if data["permission_mode"] not in ("standard", "autonomous"):
            raise ValueError(f"invalid permission mode: {data['permission_mode']!r}")
        ports = data.get("ports")
        if ports:
            data["ports"] = PortSet(**ports)
        validation = data.get("last_validation")
        if validation:
            data["last_validation"] = ValidationReference(**validation)
        return cls(**data)


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    head: str
    branch: str | None
    git_admin_name: str


@dataclass(frozen=True)
class WorktreeOwner:
    path: Path
    head: str
    branch: str
    managed: bool


@dataclass(frozen=True)
class PublishState:
    head_sha: str
    remote_sha: str | None
    clean: bool
    published: bool


@dataclass(frozen=True)
class ReleaseResult:
    released: bool
    reason: str
    path: Path | None = None


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    branch: str
    head_sha: str


@dataclass(frozen=True)
class Attachment:
    id: str
    original_name: str
    mime_type: str
    sha256: str
    size: int
    host_path: Path
    container_path: Path


@dataclass(frozen=True)
class CommandCheck:
    id: str
    title: str
    argv: tuple[str, ...]
    cwd: str
    required: bool = True
    host: bool = False


@dataclass(frozen=True)
class CommandResult:
    id: str
    title: str
    status: ValidationStatus
    exit_code: int | None
    duration_seconds: float
    output: str


@dataclass(frozen=True)
class TestPlan:
    mode: str
    changed_paths: tuple[str, ...]
    checks: tuple[CommandCheck, ...]
    xcode_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationReport:
    status: ValidationStatus
    commit_sha: str
    dirty_fingerprint: str
    results: tuple[CommandResult, ...]
    result_path: Path
