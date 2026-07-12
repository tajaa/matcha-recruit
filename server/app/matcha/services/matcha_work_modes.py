"""Thread-mode registry for Matcha Work.

Single source of truth for the per-thread grounding modes (the "node system").
Each mode is a boolean column on mw_threads that, when on, injects a
mode-specific grounded context into every AI turn for that thread.

Adding a mode now means:
  1. Alembic migration adding the `<key>_mode` boolean to mw_threads
     (+ the conditional ALTER in database.py:init_db for fresh bootstraps)
  2. A context builder (services/matcha_work_mode_contexts.py or
     services/matcha_work_node.py)
  3. A ThreadMode entry below — including `required_feature` if the mode reads
     a paid subsystem, which both 403s the toggle route and hides the button
  4. A THREAD_MODE_TOGGLES row (client/src/components/matcha-work/constants.ts,
     with the matching `feature`) + the `<key>_mode` field on the thread types
     (types/matcha-work.ts)

Everything else — the toggle endpoint, the document-service setter, the
thread-select column lists, the response models, and the messaging dispatch
loop (including its feature re-check) — is driven by this registry.

Compliance and payer keep bespoke dispatch blocks in messaging.py
(reasoning-chain status events + conditional RAG for compliance; the
prompt-swap + payer-policy RAG path for payer) and are marked
custom_dispatch=True so the generic loop skips them.
"""

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
from uuid import UUID

ContextBuilder = Callable[[UUID], Awaitable[str]]


@dataclass(frozen=True)
class ThreadMode:
    key: str                 # URL segment + frontend key, e.g. "node"
    column: str              # mw_threads boolean column, e.g. "node_mode"
    label: str
    status_loading: str      # SSE status emitted while the builder runs
    status_unavailable: str  # SSE status when the builder fails (turn continues)
    # Lazy thunk so importing the registry stays cheap — builders pull in
    # compliance/DB machinery that route modules shouldn't pay for at import.
    build_context: Optional[ContextBuilder] = None
    # True → messaging.py dispatches this mode in a hand-written block
    # (compliance, payer); the generic loop skips it.
    custom_dispatch: bool = False
    # Paid feature flag the mode's data lives behind. The mode injects records
    # from a subsystem the company may not have bought, so the toggle route
    # gates on this (403) and the frontend hides the button. None → ungated
    # (node/compliance/payer predate the registry and stay open).
    required_feature: Optional[str] = None


async def _node_context(company_id: UUID) -> str:
    from app.matcha.services.matcha_work_node import build_node_context
    return await build_node_context(company_id)


async def _benefits_context(company_id: UUID) -> str:
    from app.matcha.services.matcha_work_mode_contexts import build_benefits_context
    return await build_benefits_context(company_id)


async def _legal_context(company_id: UUID) -> str:
    from app.matcha.services.matcha_work_mode_contexts import build_legal_context
    return await build_legal_context(company_id)


async def _risk_context(company_id: UUID) -> str:
    from app.matcha.services.matcha_work_mode_contexts import build_risk_context
    return await build_risk_context(company_id)


async def _training_context(company_id: UUID) -> str:
    from app.matcha.services.matcha_work_mode_contexts import build_training_context
    return await build_training_context(company_id)


THREAD_MODES: tuple[ThreadMode, ...] = (
    ThreadMode(
        key="node",
        column="node_mode",
        label="Node",
        status_loading="Loading internal company data...",
        status_unavailable="Internal data unavailable — continuing without it...",
        build_context=_node_context,
    ),
    ThreadMode(
        key="compliance",
        column="compliance_mode",
        label="Compliance",
        status_loading="Loading compliance data for your locations...",
        status_unavailable="Compliance data unavailable — continuing without it...",
        custom_dispatch=True,
    ),
    ThreadMode(
        key="payer",
        column="payer_mode",
        label="Payer",
        status_loading="Searching payer coverage data...",
        status_unavailable="Payer data unavailable — continuing without it...",
        custom_dispatch=True,
    ),
    ThreadMode(
        key="benefits",
        column="benefits_mode",
        label="Benefits",
        status_loading="Loading benefits roster & eligibility data...",
        status_unavailable="Benefits data unavailable — continuing without it...",
        build_context=_benefits_context,
        required_feature="benefits_admin",
    ),
    ThreadMode(
        key="legal",
        column="legal_mode",
        label="Legal",
        status_loading="Loading legal matters & evidence summary...",
        status_unavailable="Legal data unavailable — continuing without it...",
        build_context=_legal_context,
        required_feature="legal_defense",
    ),
    ThreadMode(
        key="risk",
        column="risk_mode",
        label="Risk",
        status_loading="Loading risk index & coverage data...",
        status_unavailable="Risk data unavailable — continuing without it...",
        build_context=_risk_context,
        # The builder reads risk_index (risk_profile) + limit_adequacy; the
        # portal flag is the one that owns the composite index it leads with.
        required_feature="risk_profile",
    ),
    ThreadMode(
        key="training",
        column="training_mode",
        label="Training",
        status_loading="Loading training & credential data...",
        status_unavailable="Training data unavailable — continuing without it...",
        build_context=_training_context,
        required_feature="training",
    ),
)

MODES_BY_KEY: dict[str, ThreadMode] = {m.key: m for m in THREAD_MODES}

# Column helpers for SQL assembly. Registry-defined identifiers only — never
# interpolate user input into these (mode keys from requests must be resolved
# through MODES_BY_KEY first).
MODE_COLUMNS: tuple[str, ...] = tuple(m.column for m in THREAD_MODES)
MODE_COLUMNS_SQL: str = ", ".join(MODE_COLUMNS)
