"""What one run knows about itself: who asked, where, and with what limits."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Protocol
from uuid import UUID

from .registry import Target

if TYPE_CHECKING:
    from .policy import PolicyContext

Surface = Literal["card", "assistant", "project_chat"]
CommitMode = Literal["dry_run", "live"]


class ProgressSink(Protocol):
    async def note(self, text: str, *, force: bool = False) -> None: ...

    async def step(self, seq: int, kind: str, label: str, status: str) -> None: ...


class NoProgress:
    async def note(self, text: str, *, force: bool = False) -> None:
        return None

    async def step(self, seq: int, kind: str, label: str, status: str) -> None:
        return None


@dataclass(frozen=True)
class RunLimits:
    max_model_calls: int = 8
    wall_seconds: float = 300.0
    max_repairs: int = 1
    max_hosted_per_response: int = 6
    max_hosted_per_run: int = 12
    max_tool_output_chars: int = 12_000


@dataclass(frozen=True)
class FrozenAction:
    """A commit the policy held for the user's yes.

    Approval executes exactly these arguments. The model never gets to restate
    the action between the question and the answer.
    """

    tool: str
    args: dict
    targets: tuple[Target, ...] = ()
    preview: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        return {
            "tool": self.tool,
            "args": self.args,
            "targets": [{"kind": t.kind, "value": t.value, "ref": t.ref} for t in self.targets],
            "preview": self.preview,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "FrozenAction":
        return cls(
            tool=str(payload["tool"]),
            args=dict(payload.get("args") or {}),
            targets=tuple(
                Target(kind=t["kind"], value=t["value"], ref=t.get("ref"))
                for t in payload.get("targets") or []
            ),
            preview=dict(payload.get("preview") or {}),
        )


@dataclass
class RunState:
    """Mutable, per run. Tool handlers read and extend it; nothing persists it."""

    started: float
    provenance: set[str] = field(default_factory=set)
    calls: dict[str, int] = field(default_factory=dict)
    commits: dict[str, int] = field(default_factory=dict)
    hosted_calls: int = 0
    sessions: dict[str, Any] = field(default_factory=dict)
    # Thread or event id -> the addresses on it, filled by read tools. Only the
    # refs the user pointed at ever ground a target (see policy.is_grounded).
    ref_participants: dict[str, frozenset[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)
    seq: int = 0


@dataclass(frozen=True)
class RunContext:
    run_id: UUID
    user_id: UUID
    company_id: UUID
    role: str
    surface: Surface
    ask: str
    storage_prefix: str
    progress: ProgressSink
    limits: RunLimits
    usage_feature: str
    model: str
    channel_id: UUID | None = None
    project_id: UUID | None = None
    task_id: UUID | None = None
    policy: "PolicyContext | None" = None
    granted_scopes: frozenset[str] = frozenset()
    grants: dict[str, dict] = field(default_factory=dict)  # ability key -> its settings
    commit_mode: CommitMode = "dry_run"
    resume: FrozenAction | None = None
    # The confirmation whose yes this run carries out: what makes a commit
    # idempotent per approval (a purchase row is UNIQUE on it).
    resume_prompt_id: UUID | None = None
    on_receipt: Callable[[dict], Awaitable[None]] | None = None
    reasoning_effort: str = "medium"
    store_responses: bool = True
