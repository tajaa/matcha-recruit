"""Runs a long agent job as a chain of short worker tasks, one phase each.

No `AGENT_*_QUEUE` is set on prod, so every task shares the single-slot main
worker. A whole job in one task would hold that worker for half an hour; a
chain of short tasks interleaves with everything else. Job search
(`../job_search/orchestrator.py`) is the first owner; each owner describes its
row once as a `ChainSpec` and calls the functions here with it.

The chain is held together by the row's `dispatch_token`:

* A task runs only if its token is the row's current one and no other task
  holds the lease (`claim`). A duplicate delivery, a retired chain or a
  cancelled row does nothing.
* Each finished phase writes its outcome under that token and hands the next
  task a NEW token (`advance`), so a late duplicate of an earlier message can
  never start a second chain.
* A chain whose message was lost (a killed worker, a broker hiccup) is
  restarted under a fresh token by `nudge` (whoever polls the status) and by
  `reconcile` (main-worker start). Celery does not redeliver a killed task.
* Every claim counts as an attempt; only a finished phase resets the count.
  A phase whose task keeps getting killed (out of memory, the hard time
  limit) is claimed again by each restart, and the claim past `max_attempts`
  ends the row instead of running it, so a restart loop cannot hold the
  owner's live slot or the worker forever.

Every write a phase makes checks the token (`Guard`), so a cancelled row, or a
chain a reconcile replaced, stops writing at the next check.

Paid calls are reserved on the row BEFORE they are made (`grant`), and only
what went unused is given back (`refund`). A task killed mid-phase gives
nothing back, so its retry works from what is left and can never spend a
second budget.

Pool-free: everything goes through `connection_or_direct`, so the same code
runs in the API and in the worker.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Mapping, get_args
from uuid import UUID, uuid4

from app.database import connection_or_direct

logger = logging.getLogger(__name__)

# The tables a chain may run on. Every statement here is built from one of
# these names, never from a string a caller made up.
ChainTable = Literal["mw_job_searches", "mw_agent_tasks"]

_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")
_INTERVAL = re.compile(r"[1-9][0-9]* (second|minute|hour)s?")


class PhaseFailed(Exception):
    """The row cannot go on; the message is shown to the person."""


@dataclass
class PhaseOutcome:
    status: str
    progress: dict = field(default_factory=dict)
    cursor: dict | None = None
    countdown: int = 0
    # The next phase, for an owner whose phase is its own column
    # (`ChainSpec.phase_column`). None keeps the current one.
    phase: str | None = None


PhaseFn = Callable[[dict, Any, "Guard"], Awaitable[PhaseOutcome]]


@dataclass(frozen=True, kw_only=True, eq=False)
class ChainSpec:
    """One kind of row that runs as a chain, and what the engine may do to it.

    The table has the chain's columns: `status`, `dispatch_token`,
    `lease_until`, `attempts`, `progress` and `phase_cursor` (jsonb), `error`,
    `started_at`, `completed_at`, `updated_at`, `deleted_at`; plus
    `phase_column` and the `budget_columns` when the spec names them.

    Every name and value that ends up inside SQL (the table, statuses, the
    columns, the intervals) is checked here, once, when the spec is built.
    """

    table: ChainTable
    # Statuses a chain is still running in. Anything else is terminal.
    live: tuple[str, ...]
    # (from, to): the first claim moves a fresh row from `from` to `to`.
    start: tuple[str, str]
    # Phase name -> the phase. The name is the row's status, or its
    # `phase_column` when the spec has one.
    phases: Mapping[str, PhaseFn]
    # dispatch(row_id, token, *, countdown=0): queue the task for this token.
    dispatch: Callable[..., Awaitable[None]]
    # ending(row, message): the outcome for a row that cannot go on.
    ending: Callable[[dict, str], Awaitable[PhaseOutcome]]
    # on_terminal(conn, row_id): runs on advance's connection once the row ends.
    on_terminal: Callable[[Any, UUID], Awaitable[None]] | None = None
    phase_column: str | None = None
    # The paid-call counters `grant` and `refund` may touch, and nothing else.
    budget_columns: frozenset[str] = frozenset()
    # "job search" in logs; "search" in what the person reads.
    name: str
    noun: str
    # Under the task's soft time limit, with room to write the outcome.
    phase_seconds: float
    # Longer than the task's hard time limit: a lease never runs out while its
    # task can still be running, so a restart cannot start a second copy.
    lease_interval: str
    max_attempts: int
    retry_countdown: int
    # A live row with no lease that has not moved in this long lost its task.
    idle_interval: str
    # A live row that has not moved in this long is ended by reconcile.
    stale_interval: str

    def __post_init__(self) -> None:
        if self.table not in get_args(ChainTable):
            raise ValueError(f"not a chain table: {self.table!r}")
        statuses = (*self.live, *self.start)
        if not self.live or any(not _NAME.fullmatch(s) for s in statuses):
            raise ValueError(f"bad chain statuses: {statuses!r}")
        columns = (*self.budget_columns, *([self.phase_column] if self.phase_column else []))
        if any(not _NAME.fullmatch(c) for c in columns):
            raise ValueError(f"bad chain column: {columns!r}")
        for interval in (self.lease_interval, self.idle_interval, self.stale_interval):
            if not _INTERVAL.fullmatch(interval):
                raise ValueError(f"bad chain interval: {interval!r}")

    @property
    def live_sql(self) -> str:
        return ", ".join(f"'{status}'" for status in self.live)


# ── the token and the lease ─────────────────────────────────────────────────

async def claim(spec: ChainSpec, row_id: UUID, token: UUID) -> dict | None:
    """Take the lease for this token, counting an attempt. None when the token
    is not current, the row is not live, or another task holds the lease."""
    old, new = spec.start
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""UPDATE {spec.table}
                SET lease_until = NOW() + INTERVAL '{spec.lease_interval}',
                    attempts = attempts + 1,
                    status = CASE WHEN status = '{old}' THEN '{new}' ELSE status END,
                    started_at = COALESCE(started_at, NOW()),
                    updated_at = NOW()
                WHERE id = $1 AND dispatch_token = $2 AND deleted_at IS NULL
                  AND status IN ({spec.live_sql})
                  AND (lease_until IS NULL OR lease_until < NOW())
                RETURNING *""",
            row_id, token,
        )
    return dict(row) if row else None


async def advance(spec: ChainSpec, row_id: UUID, token: UUID, outcome: PhaseOutcome, *,
                  retry: bool = False, error: str | None = None) -> tuple[bool, UUID | None]:
    """Write the phase's outcome if this chain still owns the row.

    Returns (written, token for the next task). `written` is False when the
    chain was retired (cancelled, deleted, or replaced by a restart); the next
    token is None when the row is finished.
    """
    terminal = outcome.status not in spec.live
    next_token = None if terminal else uuid4()
    args: list[Any] = [
        row_id, token, outcome.status, next_token, retry,
        json.dumps(outcome.progress or {}),
        json.dumps(outcome.cursor) if outcome.cursor is not None else None,
        error, terminal,
    ]
    phase_sql = ""
    if spec.phase_column:
        column = spec.phase_column
        phase_sql = f"\n                   {column} = COALESCE($10::text, {column}),"
        args.append(outcome.phase)
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""UPDATE {spec.table}
               SET status = $3, dispatch_token = $4, lease_until = NULL,
                   attempts = CASE WHEN $5 THEN attempts ELSE 0 END,
                   progress = progress || $6::jsonb,
                   phase_cursor = COALESCE($7::jsonb, phase_cursor),
                   error = CASE WHEN $8::text IS NULL THEN error ELSE $8 END,
                   completed_at = CASE WHEN $9 THEN NOW() ELSE completed_at END,{phase_sql}
                   updated_at = NOW()
               WHERE id = $1 AND dispatch_token = $2
               RETURNING id""",
            *args,
        )
        if row is not None and terminal and spec.on_terminal is not None:
            await spec.on_terminal(conn, row_id)
    if row is None:
        return False, None
    return True, next_token


# ── one task ─────────────────────────────────────────────────────────────────

async def run_phase(spec: ChainSpec, row_id: UUID, token: UUID, *, deps: Any = None) -> None:
    """Claim, run the row's phase under `phase_seconds`, write the outcome and
    dispatch the next task. `deps` is handed to the phase as it is."""
    row = await claim(spec, row_id, token)
    if row is None:
        return
    guard = Guard(spec, row_id, token)
    step = row[spec.phase_column] if spec.phase_column else row["status"]
    phase = spec.phases.get(step)
    error = None
    retry = False
    if int(row["attempts"]) > spec.max_attempts:
        # Earlier claims of this phase never finished: their task was killed.
        message = f"A step kept stopping before it finished, so the {spec.noun} stopped."
        outcome = await spec.ending(row, message)
        error = message
    elif phase is None:
        outcome = await spec.ending(row, f"Unknown step {step!r}.")
        error = outcome.progress["note"]
    else:
        try:
            outcome = await asyncio.wait_for(phase(row, deps, guard), spec.phase_seconds)
        except PhaseFailed as exc:
            outcome = await spec.ending(row, str(exc))
            error = str(exc)
        except Exception as exc:  # TimeoutError included
            logger.warning("%s phase failed %s=%s phase=%s attempt=%s",
                           spec.name, spec.noun, row_id, step, row["attempts"], exc_info=True)
            if int(row["attempts"]) >= spec.max_attempts:
                message = f"A step kept failing, so the {spec.noun} stopped."
                outcome = await spec.ending(row, message)
                error = f"{message} ({type(exc).__name__})"
            else:
                outcome = PhaseOutcome(
                    status=row["status"], countdown=spec.retry_countdown,
                    progress={"note": "Hit a snag; trying that step again shortly…"},
                )
                retry = True
    _written, next_token = await advance(spec, row_id, token, outcome, retry=retry, error=error)
    if next_token is None:
        return
    try:
        await spec.dispatch(row_id, next_token, countdown=outcome.countdown)
    except Exception:
        # The row stays live with no lease; nudge/reconcile restart it.
        logger.exception("%s next phase dispatch failed %s=%s", spec.name, spec.noun, row_id)


# ── recovery ─────────────────────────────────────────────────────────────────

async def _restart(spec: ChainSpec, row_id: UUID) -> bool:
    """Give an idle live row a new token and dispatch it. True if restarted."""
    token = uuid4()
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            f"""UPDATE {spec.table} SET dispatch_token = $2, updated_at = NOW()
                WHERE id = $1 AND deleted_at IS NULL AND status IN ({spec.live_sql})
                  AND (lease_until IS NULL OR lease_until < NOW())
                  AND updated_at < NOW() - INTERVAL '{spec.idle_interval}'
                RETURNING id""",
            row_id, token,
        )
    if row is None:
        return False
    try:
        await spec.dispatch(row_id, token)
    except Exception:
        logger.exception("%s restart dispatch failed %s=%s", spec.name, spec.noun, row_id)
        return False
    logger.info("%s restarted %s=%s", spec.name, spec.noun, row_id)
    return True


async def nudge(spec: ChainSpec, row_id: UUID) -> bool:
    """Restart this row's chain if it has stalled. Cheap when it hasn't."""
    try:
        return await _restart(spec, row_id)
    except Exception:
        logger.warning("%s nudge failed %s=%s", spec.name, spec.noun, row_id, exc_info=True)
        return False


async def reconcile(spec: ChainSpec) -> dict:
    """Main-worker start: end rows dead for `stale_interval`, restart idle ones."""
    ended = restarted = 0
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"""SELECT * FROM {spec.table}
                WHERE deleted_at IS NULL AND status IN ({spec.live_sql})
                  AND (lease_until IS NULL OR lease_until < NOW())
                  AND updated_at < NOW() - INTERVAL '{spec.idle_interval}'
                ORDER BY updated_at LIMIT 200""",
        )
        stale_ids = {
            row["id"] for row in await conn.fetch(
                f"""SELECT id FROM {spec.table}
                    WHERE deleted_at IS NULL AND status IN ({spec.live_sql})
                      AND updated_at < NOW() - INTERVAL '{spec.stale_interval}'"""
            )
        }
    for row in rows:
        record = dict(row)
        if record["id"] in stale_ids:
            outcome = await spec.ending(record, f"the {spec.noun} stopped making progress.")
            if record["dispatch_token"] is not None:
                written, _ = await advance(spec, record["id"], record["dispatch_token"], outcome,
                                           error="Stopped: no progress.")
                ended += int(written)
            continue
        if await _restart(spec, record["id"]):
            restarted += 1
    return {"ended": ended, "restarted": restarted}


# ── inside a phase ───────────────────────────────────────────────────────────

async def grant(spec: ChainSpec, row_id: UUID, column: str, want: int, limit: int) -> int:
    """Reserve up to `want` calls against the row's lifetime `limit`; the
    number granted (0 when spent)."""
    assert column in spec.budget_columns, column
    if want <= 0:
        return 0
    async with connection_or_direct() as conn:
        granted = await conn.fetchval(
            f"""WITH cur AS (SELECT id, {column} AS before FROM {spec.table} WHERE id = $1 FOR UPDATE)
                UPDATE {spec.table} s
                SET {column} = cur.before + GREATEST(LEAST($2, $3 - cur.before), 0)
                FROM cur WHERE s.id = cur.id
                RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)""",
            row_id, want, limit,
        )
    return int(granted or 0)


async def refund(spec: ChainSpec, row_id: UUID, column: str, unused: int) -> None:
    """Give back the part of a grant that went unused."""
    assert column in spec.budget_columns, column
    if unused <= 0:
        return
    async with connection_or_direct() as conn:
        await conn.execute(
            f"UPDATE {spec.table} SET {column} = GREATEST({column} - $2, 0) WHERE id = $1",
            row_id, unused,
        )


@dataclass
class Budget:
    """Calls this phase was granted; `exhausted` once one was refused."""

    left: int
    used: int = 0
    exhausted: bool = False

    def take(self) -> bool:
        if self.left <= 0:
            self.exhausted = True
            return False
        self.left -= 1
        self.used += 1
        return True


@dataclass
class Guard:
    """What a phase writes through: is this chain still the row's, and
    progress notes that land only while it is."""

    spec: ChainSpec
    row_id: UUID
    token: UUID

    async def current(self) -> bool:
        async with connection_or_direct() as conn:
            return bool(await conn.fetchval(
                f"SELECT 1 FROM {self.spec.table} WHERE id = $1 AND dispatch_token = $2",
                self.row_id, self.token,
            ))

    async def note(self, text: str, **counts: Any) -> None:
        progress = {"note": text[:200], **counts}
        async with connection_or_direct() as conn:
            await conn.execute(
                f"""UPDATE {self.spec.table} SET progress = progress || $3::jsonb, updated_at = NOW()
                   WHERE id = $1 AND dispatch_token = $2""",
                self.row_id, self.token, json.dumps(progress),
            )
