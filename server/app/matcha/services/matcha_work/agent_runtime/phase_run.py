"""One model phase of a chain, as an ordinary agent-runtime run.

A chain's model phase (job search's plan, screen and approach) is a caller of
`runner.run_agent`, like the chat assistant and agent cards: there is still
one loop. Each call writes its own `mw_project_agent_runs` row (the owner's
run kind, pointing at the owner's row) so steps, tokens and failures are
audited like any other run. `RunOwner` says whose run it is.

Runs are not stored by the provider (`store_responses=False`): an owner's
input can carry what the person gave it (job search's ask and résumé).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Mapping, Sequence, get_args
from uuid import UUID

from app.database import connection_or_direct
from app.matcha.services.huume.luna_client import text_item
from app.matcha.services.matcha_work.project_agent import store

from . import models, runner
from .context import CommitMode, ProgressSink, RunContext, RunLimits, Surface
from .registry import Ability

if TYPE_CHECKING:
    from .policy import PolicyContext

logger = logging.getLogger(__name__)

# Whose run it is: the run kind, and the column on the run row that points at
# the owner's row. SQL is built only from these names.
RunKind = Literal["job_search", "agent_task"]
OwnerColumn = Literal["job_search_id", "agent_task_id"]

_NOTE_SECONDS = 1.5


@dataclass(frozen=True, kw_only=True)
class RunOwner:
    """The row a model phase runs for, and how its runs are counted."""

    kind: RunKind
    fk_column: OwnerColumn
    owner_id: UUID
    user_id: UUID
    company_id: UUID
    model: str
    usage_feature: str
    storage_prefix: str
    surface: Surface
    # account(stats): count the run on the owner's own row (runs, tokens).
    # The workspace's token budget is charged here, not by the owner.
    account: Callable[[dict], Awaitable[None]]
    role: str = "client"
    dispatch_token: UUID | None = None
    recap_generation: int | None = None
    recap_round: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in get_args(RunKind):
            raise ValueError(f"not a run owner kind: {self.kind!r}")
        if self.fk_column not in get_args(OwnerColumn):
            raise ValueError(f"not a run owner column: {self.fk_column!r}")
        if self.surface not in get_args(Surface):
            raise ValueError(f"not a run surface: {self.surface!r}")


def default_client(model: str) -> Any:
    """The model client for a model id: Claude's for a Claude model, else Luna's."""
    from app.matcha.services.huume.claude_client import get_claude_client
    from app.matcha.services.huume.luna_client import get_luna_client

    return get_claude_client() if models.is_claude(model) else get_luna_client()


def total_tokens(stats: dict) -> int:
    return int((stats.get("token_usage") or {}).get("total_tokens") or 0)


@dataclass
class NoteProgress:
    """Progress notes on the owner's row, throttled; steps stay on the run row."""

    note_fn: Callable[[str], Any]
    _last: float = 0.0

    async def note(self, text: str, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < _NOTE_SECONDS:
            return
        self._last = now
        try:
            await self.note_fn(text)
        except Exception:
            logger.debug("phase progress note failed", exc_info=True)

    async def step(self, seq: int, kind: str, label: str, status: str) -> None:
        return None


async def _insert_run(owner: RunOwner, phase: str, abilities: list[str]) -> UUID:
    async with connection_or_direct() as conn:
        run_id = await conn.fetchval(
            f"""INSERT INTO mw_project_agent_runs
                   (company_id, requested_by, agent_key, kind, prompt, status, started_at,
                    model, surface, abilities, {owner.fk_column})
               VALUES ($1, $2, 'espresso', '{owner.kind}', $3, 'running', NOW(), $4, '{owner.surface}', $5, $6)
               RETURNING id""",
            owner.company_id, owner.user_id, f"{phase}:{owner.owner_id}", owner.model, abilities,
            owner.owner_id,
        )

        from ..recaps.scope import phase_run
        from ..recaps import settings as recap_settings
        if recap_settings.enabled():
            try:
                async with conn.transaction():
                    await phase_run(conn, run_id, owner)
            except Exception:
                logger.warning("recap phase binding missing run=%s", run_id, exc_info=True)
        return run_id


async def _account(owner: RunOwner, stats: dict) -> None:
    """Count the run on its owner and charge the workspace's token budget.
    Accounting never turns a finished phase into a failed one."""
    total = total_tokens(stats)
    try:
        await owner.account(stats)
        if total > 0:
            from app.matcha.services.billing import token_budget_service

            async with connection_or_direct() as conn, conn.transaction():
                await token_budget_service.deduct_tokens(conn, owner.company_id, total)
    except Exception:
        logger.warning("%s token accounting failed id=%s", owner.kind, owner.owner_id, exc_info=True)


async def run_model_phase(
    owner: RunOwner,
    *,
    phase: str,
    abilities: Sequence[Ability],
    contract: runner.ResultContract,
    instructions: str,
    user_text: str,
    limits: RunLimits,
    progress: ProgressSink,
    reasoning_effort: str = "low",
    client_factory: Callable[[str], Any] = default_client,
    first_note: str | None = None,
    first_input: list[dict[str, Any]] | None = None,
    seed_provenance: frozenset[str] | set[str] = frozenset(),
    policy: "PolicyContext | None" = None,
    grants: Mapping[str, dict] | None = None,
    commit_modes: Mapping[str, CommitMode] | None = None,
    on_receipt: Callable[[dict], Awaitable[None]] | None = None,
    timezone: str | None = None,
) -> runner.RunOutcome:
    """Run one bounded loop. Raises `runner.AgentRunError` when no usable result came.

    `first_input` replaces the single user turn built from `user_text` (to send
    images, say); `user_text` is still the run's recorded ask. The rest pass
    straight through to the run's context and the runner.
    """
    run_id = await _insert_run(owner, phase, [a.key for a in abilities])
    ctx = RunContext(
        run_id=run_id,
        user_id=owner.user_id,
        company_id=owner.company_id,
        role=owner.role,
        surface=owner.surface,
        ask=user_text[:12_000],
        storage_prefix=owner.storage_prefix,
        progress=progress,
        limits=limits,
        usage_feature=owner.usage_feature,
        model=owner.model,
        reasoning_effort=reasoning_effort,
        store_responses=False,
        policy=policy,
        grants=dict(grants or {}),
        commit_modes=dict(commit_modes or {}),
        on_receipt=on_receipt,
        timezone=timezone,
    )
    stats: dict = {}
    try:
        outcome = await runner.run_agent(
            ctx,
            client=client_factory(owner.model),
            abilities=abilities,
            contract=contract,
            instructions=instructions,
            first_input=first_input if first_input is not None else [text_item("user", user_text)],
            first_note=first_note,
            seed_provenance=seed_provenance,
            stats=stats,
        )
    except Exception as exc:
        await store.mark_run(
            run_id, status="failed", error=str(exc)[:500] or type(exc).__name__,
            model_calls=int(stats.get("model_calls") or 0),
            token_usage=stats.get("token_usage") or {},
            search_calls=int(stats.get("search_calls") or 0),
        )
        await _account(owner, stats)
        raise
    await store.mark_run(
        run_id, status="done", result={"phase": phase, "result": outcome.result,
                                       "warnings": outcome.warnings[:20]},
        model_calls=outcome.model_calls, token_usage=outcome.token_usage,
        search_calls=outcome.search_calls,
    )
    await _account(owner, {"token_usage": outcome.token_usage})
    return outcome
