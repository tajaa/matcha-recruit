# Inventory system via @huume in /work channels — EXECUTION SPEC

This doc is written to be followed mechanically, in order, by a model with no
prior context on this codebase beyond what's quoted here. Every edit to an
existing file quotes the exact surrounding lines it anchors to (verified this
session — line numbers are real, not guessed). Every new file is a complete
code block, not a signature list. Do the steps in order; each one compiles
and its own tests pass before moving to the next.

## Context

Goal: usable from `/work` channels via `@huume`. "@huume we gifted some
Cherry Farms cookies to Elizabeth our manager" auto-deducts stock. "@huume we
ran out of salads again" records a stockout, computes a suggested reorder
amount from deterministic history math, stages a pending order, and the
manager approves it by replying **confirm** in-channel. Items **auto-create
on first mention** (fuzzy-match existing names first). Orders are **internal
records only** (no vendor integration): `queued` → `ordered` → `received`
(receiving restocks the item) + `cancelled`. v1 ships a full `/work`
Inventory page (items, ledger, order queue) in addition to the channel flow.

The `@huume` surface in channels is NOT the Huume thread agent (that requires
an `mw_threads` row) — it's the EMS one-shot dispatch in
`server/app/werk/routes/channels_ws.py`, routed by the pure regex classifier
`server/app/matcha/services/ems/intent.py` (biased to LOG by default;
unmatched text becomes an EMS event so nothing is silently dropped).
Inventory is a new intent + a new `services/inventory/` package, built by
copying the SCHEDULE intent's shape end to end: request handler copies
`_bg_schedule_request`, confirm-by-reply copies `_bg_schedule_reply`, and the
clarify-question mechanics copy EMS's `question_text`/`extract_question`.

## Verified anchors (do not re-derive — read once, use throughout)

All line numbers below were read from the actual files this session.

**`server/app/matcha/services/ems/intent.py`** (208 lines total):
- `LOG = "log"` / `ASK` / `HELP` / `LINK` / `SCHEDULE` at lines 26-30.
- `strip_mention()` at lines 149-171 (bounded 5-iteration greeting-strip loop, then mention-prefix strip).
- `classify_intent()` at lines 174-207. Body order: HELP loop (188-190) → LINK loop (192-194) → SCHEDULE loop (196-198) → RECALL loop (200-202) → interrogative check (204-205) → `return LOG` (207).
- `_RECALL_PATTERNS` includes `r"^(?:did|have|has) (?:we|you|anyone|any ?one|somebody|someone)\b"` at line 77 — this is why "did we run out of cups?" must classify ASK, not INVENTORY (INVENTORY's own patterns start `^(?:we|i)`, never `^did`).
- Compiled tuples `_HELP_RE`...`_SCHEDULE_RE` at lines 143-146.

**`server/app/matcha/services/scheduling/schedule_chat_rules.py`**:
- `ALLOWED_ROLES = frozenset({"client", "admin"})` at line 22.
- `ScheduleVerdict` dataclass at lines 34-41 — copy this shape verbatim.
- `evaluate_schedule_proposal()` at lines 44-67.
- `_CONFIRM_RE` / `_CANCEL_RE` / `_THUMBS_UP` at lines 353-365; `parse_confirm_reply()` at lines 368-383 — **import this directly**, don't reimplement.

**`server/app/matcha/services/ems/event_intake.py`**:
- `_QUESTION_MARKER = "\n\U0001F914 "` (line 322), `_QUESTION_SUFFIX = " — just reply to this message."` (line 325), `question_text()` (332-336), `extract_question()` (339-354) — shape-copy into inventory's `pills.py` with inventory's OWN marker/suffix constants (not imports — these are EMS's wire format).
- `fallback_classification(content)` (423-429) — returns a dict with `.get("urgency")`; used for the deterministic OSHA dual-write check.
- `classify_event()` (432-488) — template for `extraction.py`'s Gemini call shape: build prompt → `_get_client().aio.models.generate_content(model=FLASH_LITE_MODEL, contents=prompt, config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json", max_output_tokens=800))` → parse → except-wrapped, never raises, no conn held across the call.

**`server/app/werk/routes/channels_ws.py`**:
- `_system_message_payload(channel_id_str, sys_row)` (115-136) — the 17-key WS broadcast shape.
- `_insert_system_message(conn, channel_id_str, content)` (139-149).
- `_ems_row_allowed(row)` (152-161), `_ems_company_gate(conn, channel_id_str)` (164-179), `_ems_flag_enabled(conn, company_id)` (182-192) — the flag/gate pattern to mirror for `inventory`.
- `_schedule_company_features(conn, company_id)` (~370-378) — returns merged features dict or `{}`; flag-agnostic, **reuse directly, no inventory-specific copy needed**.
- `_bg_schedule_request()` (381-450) — template for `_bg_inventory_request`. Rate-limit idiom at 416-419: `try: await check_rate_limit(str(company_id), "ems_schedule", 20, 3600) / except HTTPException: return`.
- `_bg_schedule_reply()` (453-630) — template for `_bg_inventory_reply`. Claim SQL at 503-514 (`UPDATE ... SET confirm_message_id = NULL, updated_at = NOW() WHERE confirm_message_id = $1 AND status IN (...) AND created_at > NOW() - INTERVAL '7 days' RETURNING ...`). Replier re-verdict + re-arm-on-refusal at 526-539. `return claim_happened` in the except block at 628-630 (so a mid-flight exception after the claim still reports `True` to the dispatcher).
- `_ems_dispatch_decision()` (960-970) — **unchanged, do not touch**.
- `_bg_ems_dispatch()` (973-1027) — reply-chain probes at 1005-1015 (`_bg_ems_clarify` then `_bg_schedule_reply`); mention-fork lazy import + branch at 1016-1027.

**`server/app/core/feature_flags.py`**:
- Line 340: `"inventory": False,` sits inside a no-op comment block spanning lines 336-341 (shared with `"interview_prep"`, comment: "No require_feature(...) gate anywhere...").
- `FEATURE_REQUIRES` dict at lines 740-744: `{"huume": ("matcha_work",), "werk_lite": ("matcha_work",), "ems": ("matcha_work",)}`.

**`server/app/core/services/redis_cache.py`**: `check_rate_limit(ip, action, limit, window)` at line 120 — raises `HTTPException(429, ...)` over budget.

**`server/app/matcha/services/pilots/analysis_packs/base.py`**: `mean(values)` (line 139, returns `Optional[float]`, `None` on empty) and `coefficient_of_variation(values)` (line 144, `None`-propagating) — both must be None-guarded by callers.

**`server/app/database/bootstrap/ems.py`** — mirror-file template: raw `CREATE TABLE IF NOT EXISTS`/`CREATE [UNIQUE] INDEX IF NOT EXISTS` statements, one `await conn.execute("""...""")` per statement, no ORM.

**`server/app/database/bootstrap/__init__.py`**: `from app.database.bootstrap.ems import create_ems` at line 29, `await create_ems(conn)` at line 67 (last call in `init_db()`).

**`server/alembic/versions/ems01_event_management.py`**: lines 46-48 are the "multi-head, confirm your down_revision" docstring precedent to copy. Confirmed this session: **`ems02` is currently a real leaf** (no other migration's `down_revision` points to it) — `inventory01`'s `down_revision = "ems02"` is safe as of now, but re-check before applying if time has passed.

**`server/app/matcha/routes/__init__.py`**: `from .ems import router as ems_router` (line 46); mount at lines 150-151:
```python
matcha_router.include_router(ems_router, prefix="/ems", tags=["ems"],
                             dependencies=[Depends(require_feature("ems"))])
```

**Huume bridge** (`server/app/matcha/services/huume/`):
- `tools.py`: `LOOKUP_TOPICS` tuple at line 26, `SHOW_RECORD_TYPES = ("incident", "er_case", "employee", "credential", "discipline", "ems_event")` at line 35.
- `onboarding_skill.py`: topic→feature map has `"events": "ems"` at line 128; the `if topic == "events":` branch (lines 376-418) is the model to copy — fetches counts by status + a capped `LIMIT 21` row set, truncation note, returns `{"topic": ..., ...}`.
- `record_view.py`: module docstring (lines 1-20) states the exact recipe: "one `_model_<type>` + one `_build_<type>_view` + one `RECORD_REQUIRED_FEATURE` entry + one `SHOW_RECORD_TYPES` entry". `RECORD_REQUIRED_FEATURE` dict at line 33 (currently 6 entries ending `"ems_event": "ems"`). `_MODEL_BATCH_BUILDERS` dict at ~309-315, `_VIEW_BUILDERS` dict at ~769-775. **A parity test enforces identical key sets across `SHOW_RECORD_TYPES`, `RECORD_REQUIRED_FEATURE`, `_MODEL_BATCH_BUILDERS`, `_VIEW_BUILDERS`** — adding `"inventory_item"` to only 3 of the 4 breaks it.

**Frontend** (`client/src/`):
- `work/routes/WorkRouteTree.tsx`: the ems `FeatureGate` block (verified verbatim):
```tsx
<Route
  element={
    <FeatureGate feature="ems" label="Events">
      <Outlet />
    </FeatureGate>
  }
>
  <Route path="events" element={<EventsHub />} />
  <Route path="events/:eventId" element={<EventsHub />} />
  <Route path="protocol" element={<ProtocolPage />} />
</Route>
```
- `work/components/shell/WorkSidebar.tsx`: `showEvents` at line 36 (`canReviewEvents(me?.user?.role) && hasFeature('ems')`), full Events entry at lines 222-243.
- **CORRECTION to the original draft of this plan: `work/components/shell/WerkLiteSidebar.tsx` line 34 has the SAME `showEvents` pattern** — werk-lite companies have channels too, so the inventory sidebar entry must be added to **both** sidebar files, not just `WorkSidebar.tsx`.
- `work/api/events.ts`: confirmed pattern — `import { api } from '../../api/client'` then exported TS interfaces + thin async wrapper functions. `inventory.ts` copies this shape.
- `client/src/data/featureCatalog.ts` line 54: `inventory: 'Inventory',` — **this is a label map (string → display name), not a description object.** The step-9 task is "confirm the label reads correctly", not "reword a description field" (correction from the original draft).

## Key design decisions

1. **Unstated quantity** ("some cookies"): record immediately as `quantity=1,
   quantity_estimated=true` (auto-deduct is required) AND arm an EMS-style
   clarify question on the pill ("How many? Reply with a number."). A numeric
   reply amends the flagged movement in place (`amended_by`/`amended_at`,
   only while `quantity_estimated`) — the one sanctioned edit on an otherwise
   append-only ledger. `clarify_rounds` capped at 2.
2. **`current_quantity NUMERIC NULL`** = unknown (auto-created items start
   NULL). Deduction against NULL stays NULL. `stockout` force-sets 0.
   `adjust` establishes a baseline.
3. **Order lifecycle**: `queued` (staged) → `ordered` (confirm-reply or page
   approve) → `received` (page action writes the restock `in` movement) +
   `cancelled`. A partial unique index enforces one queued order per item;
   a repeat stockout re-points the confirm pill at the existing order.
4. **Injury-adjacent safety** (bias-to-LOG is a product invariant carried
   over from EMS): (a) narrow `^`-anchored verb patterns — bare
   "gave"/"used" never match; (b) deterministic OSHA-keyword check
   (`fallback_classification(content).get("urgency") == "osha"`) runs before
   inventory handling — on a hit, ALSO fire `_bg_ems_intake` (dual-write);
   (c) non-actionable/failed Gemini extraction falls back to `_bg_ems_intake`
   wholesale; `inventory` off but `ems` on → delegate to EMS intake entirely.
5. **Grounded-pilots corpus wiring is deliberately skipped** — this is ops
   stock data, not compliance/legal evidence. One-line justification goes in
   the service's own `CLAUDE.md` (Step 10) addressing the root CLAUDE.md's
   "new analytics engine ships wired into grounded pilots" rule head-on.

---

## Step 1 — Migration + bootstrap mirror (author only, do NOT run)

### 1a. `server/alembic/versions/inventory01_channel_inventory.py` (new file, full contents)

```python
"""Inventory tracking via @huume channel intake — inventory_items,
inventory_movements (append-only ledger), inventory_orders.

Backs the `inventory` feature flag. Mirrors the ems01/ems02 migrations'
shape: set-based SQL only, no ORM. See server/app/matcha/services/inventory/
CLAUDE.md for the full feature spec once it lands (Step 10 of the build).

NOTE: the alembic history on this branch has multiple leaves; down_revision
is set to `ems02`, a verified leaf at authoring time (no other migration's
down_revision points to it as of 2026-08-02). Confirm the correct head for
your environment before `alembic upgrade` if time has passed.

Revision ID: inventory01
Revises: ems02
Create Date: 2026-08-02
"""

from alembic import op

revision = "inventory01"
down_revision = "ems02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE inventory_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            unit VARCHAR(50),
            current_quantity NUMERIC,
            low_stock_threshold NUMERIC,
            auto_created BOOLEAN NOT NULL DEFAULT FALSE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_items_name
        ON inventory_items (company_id, normalized_name) WHERE archived_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE inventory_movements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('out','in','stockout','adjust')),
            quantity NUMERIC,
            quantity_delta NUMERIC,
            quantity_estimated BOOLEAN NOT NULL DEFAULT FALSE,
            note TEXT,
            narrative TEXT NOT NULL,
            clarify_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            clarify_rounds SMALLINT NOT NULL DEFAULT 0,
            amended_by UUID REFERENCES users(id) ON DELETE SET NULL,
            amended_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_movements_message
        ON inventory_movements (source_message_id, item_id) WHERE source_message_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_movements_clarify
        ON inventory_movements (clarify_message_id) WHERE clarify_message_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX idx_inventory_movements_company ON inventory_movements (company_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_inventory_movements_item ON inventory_movements (item_id, created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE inventory_orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','ordered','received','cancelled')),
            suggested_quantity NUMERIC,
            quantity NUMERIC,
            suggestion JSONB,
            confirm_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            ordered_at TIMESTAMPTZ,
            received_by UUID REFERENCES users(id) ON DELETE SET NULL,
            received_at TIMESTAMPTZ,
            received_quantity NUMERIC,
            receipt_movement_id UUID REFERENCES inventory_movements(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_orders_confirm
        ON inventory_orders (confirm_message_id) WHERE confirm_message_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_orders_open
        ON inventory_orders (item_id) WHERE status = 'queued'
        """
    )
    op.execute(
        "CREATE INDEX idx_inventory_orders_company ON inventory_orders (company_id, status, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS inventory_orders")
    op.execute("DROP TABLE IF EXISTS inventory_movements")
    op.execute("DROP TABLE IF EXISTS inventory_items")
```

### 1b. `server/app/database/bootstrap/inventory.py` (new file, full contents)

```python
"""bootstrap.inventory — inventory_items + inventory_movements +
inventory_orders (mirrors alembic/versions/inventory01_channel_inventory.py).

Reference-only for a fresh DB bootstrap; schema changes always go through
Alembic (see server/CLAUDE.md's migration-authoring rules).
"""


async def create_inventory(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            unit VARCHAR(50),
            current_quantity NUMERIC,
            low_stock_threshold NUMERIC,
            auto_created BOOLEAN NOT NULL DEFAULT FALSE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_items_name
        ON inventory_items (company_id, normalized_name) WHERE archived_at IS NULL
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('out','in','stockout','adjust')),
            quantity NUMERIC,
            quantity_delta NUMERIC,
            quantity_estimated BOOLEAN NOT NULL DEFAULT FALSE,
            note TEXT,
            narrative TEXT NOT NULL,
            clarify_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            clarify_rounds SMALLINT NOT NULL DEFAULT 0,
            amended_by UUID REFERENCES users(id) ON DELETE SET NULL,
            amended_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_movements_message
        ON inventory_movements (source_message_id, item_id) WHERE source_message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_movements_clarify
        ON inventory_movements (clarify_message_id) WHERE clarify_message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_company
        ON inventory_movements (company_id, created_at DESC)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_item
        ON inventory_movements (item_id, created_at DESC)
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','ordered','received','cancelled')),
            suggested_quantity NUMERIC,
            quantity NUMERIC,
            suggestion JSONB,
            confirm_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            ordered_at TIMESTAMPTZ,
            received_by UUID REFERENCES users(id) ON DELETE SET NULL,
            received_at TIMESTAMPTZ,
            received_quantity NUMERIC,
            receipt_movement_id UUID REFERENCES inventory_movements(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_orders_confirm
        ON inventory_orders (confirm_message_id) WHERE confirm_message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_orders_open
        ON inventory_orders (item_id) WHERE status = 'queued'
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_orders_company
        ON inventory_orders (company_id, status, created_at DESC)
    """)
```

### 1c. Wire into `server/app/database/bootstrap/__init__.py`

Quote of current lines 29 and 67:
```python
from app.database.bootstrap.ems import create_ems
```
```python
        await create_ems(conn)
```

Change to:
```python
from app.database.bootstrap.ems import create_ems
from app.database.bootstrap.inventory import create_inventory
```
```python
        await create_ems(conn)
        await create_inventory(conn)
```

**Done when**: `python3 -m py_compile server/app/database/bootstrap/inventory.py server/alembic/versions/inventory01_channel_inventory.py server/app/database/bootstrap/__init__.py` is clean (the post-edit hook does this automatically per file).

---

## Step 2 — Feature flag

### 2a. `server/app/core/feature_flags.py` — move `inventory` out of the no-op block

Current (lines 336-341):
```python
    # No require_feature(...) gate anywhere — kept for parity with the admin
    # toggle grid / featureCatalog.ts, which already list them; toggling
    # either is currently a no-op read-side.
    "interview_prep": False,
    "inventory": False,
}
```

Change to:
```python
    # No require_feature(...) gate anywhere — kept for parity with the admin
    # toggle grid / featureCatalog.ts, which already list them; toggling
    # either is currently a no-op read-side.
    "interview_prep": False,
}
```

Then find `DEFAULT_COMPANY_FEATURES`'s dict close a few lines below (the `}` that ends the whole dict — same one, since `"inventory"` was its last real entry) and add a NEW real entry immediately before that closing `}`, with its own spec comment:

```python
    # Channel-driven inventory tracking via @huume ("we gifted some cookies",
    # "we ran out of salads") — auto-created items, append-only movement
    # ledger, internal order queue with in-channel confirm. Gates the
    # /inventory router + the /work Inventory page. See
    # services/inventory/CLAUDE.md for the full spec. NOT bundled.
    "inventory": False,
```

(Net effect: `"inventory": False` moves from the no-op comment block down to its own real entry with a real comment, same dict, same default value.)

### 2b. `FEATURE_REQUIRES` — add the `matcha_work` prerequisite

Current (lines 740-744):
```python
FEATURE_REQUIRES: dict[str, tuple[str, ...]] = {
    "huume": ("matcha_work",),
    "werk_lite": ("matcha_work",),
    "ems": ("matcha_work",),
}
```

Change to:
```python
FEATURE_REQUIRES: dict[str, tuple[str, ...]] = {
    "huume": ("matcha_work",),
    "werk_lite": ("matcha_work",),
    "ems": ("matcha_work",),
    "inventory": ("matcha_work",),
}
```

**Done when**: `py_compile` clean; `grep -n '"inventory"' server/app/core/feature_flags.py` shows exactly 2 hits (the DEFAULT entry + the FEATURE_REQUIRES entry).

---

## Step 3 — Pure service modules + tests (no DB, no Gemini)

New package: create `server/app/matcha/services/inventory/__init__.py` (empty file).

### 3a. `server/app/matcha/services/inventory/matching.py` (full contents)

```python
"""Fuzzy item-name matching for auto-created inventory items. Pure,
stdlib-only — no pg_trgm (deliberately avoided on RDS, see the zzzzcappe25
migration docstring), so fuzzy match is Python's difflib."""

import difflib
import re

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, naive
    de-pluralize (trailing 's', not 'ss'/'us') so "Cookies!" and "cookie"
    both normalize toward the same key."""
    text = (name or "").strip().lower()
    text = _PUNCT_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    if text.endswith("s") and not text.endswith("ss") and len(text) > 3:
        text = text[:-1]
    return text


def best_match(name: str, existing: list[dict]) -> dict | None:
    """existing: list of {id, name, normalized_name}. Returns the matched
    row dict, or None. Order: exact normalized match -> substring
    containment (either direction, guarded to avoid 1-2 char false
    positives) -> difflib fuzzy (cutoff 0.75, same cutoff family as
    core/routes/admin/_shared.py's 0.72)."""
    if not existing:
        return None
    target = normalize_name(name)
    if not target:
        return None

    for row in existing:
        if row["normalized_name"] == target:
            return row

    for row in existing:
        other = row["normalized_name"]
        if len(target) >= 4 and len(other) >= 4:
            if target in other or other in target:
                return row

    by_norm = {row["normalized_name"]: row for row in existing}
    matches = difflib.get_close_matches(target, list(by_norm.keys()), n=1, cutoff=0.75)
    if matches:
        return by_norm[matches[0]]
    return None
```

### 3b. `server/app/matcha/services/inventory/reorder.py` (full contents)

```python
"""Deterministic reorder-quantity suggestion from movement history. No
Gemini, no DB — pure over an already-fetched movement list, chronological
(oldest first)."""

import math
from datetime import datetime

from app.matcha.services.pilots.analysis_packs.base import coefficient_of_variation, mean

DEFAULT_COVER_DAYS = 14
LOOKBACK_DAYS = 90


def suggest_order(movements: list[dict], now: datetime) -> dict | None:
    """movements: chronological dicts with keys {kind, quantity,
    quantity_delta, created_at}. Returns None when history is too thin to
    say anything useful (fewer than 2 'out' movements AND no prior 'in'
    receipt) — never guesses from nothing.

    daily_rate: sum of 'out' quantity magnitudes within LOOKBACK_DAYS,
    divided by the number of days actually observed (oldest-in-window to
    now, floored at 1 to avoid a same-day divide-by-zero).

    suggested_quantity: ceil(daily_rate * DEFAULT_COVER_DAYS) when a rate
    exists; else falls back to the most recent 'in' receipt quantity; else
    None (caller must still stage the order — with no history to price it
    from — but the pill says so explicitly).
    """
    cutoff = now.timestamp() - LOOKBACK_DAYS * 86400
    in_window = [m for m in movements if m["created_at"].timestamp() >= cutoff]

    outs = [m for m in in_window if m["kind"] == "out" and m["quantity"] is not None]
    stockouts = [m for m in in_window if m["kind"] == "stockout"]
    receipts = [m for m in in_window if m["kind"] == "in" and m["quantity"] is not None]

    n_out = len(outs)
    if n_out < 2 and not receipts:
        return None

    daily_rate = None
    if outs:
        earliest = min(m["created_at"] for m in outs)
        observed_days = max(1.0, (now - earliest).total_seconds() / 86400)
        daily_rate = sum(float(m["quantity"]) for m in outs) / observed_days

    stockout_intervals = []
    sorted_stockouts = sorted(stockouts, key=lambda m: m["created_at"])
    for prev, curr in zip(sorted_stockouts, sorted_stockouts[1:]):
        stockout_intervals.append((curr["created_at"] - prev["created_at"]).total_seconds() / 86400)
    avg_stockout_interval = mean(stockout_intervals) if stockout_intervals else None

    if daily_rate is not None and daily_rate > 0:
        suggested_quantity = math.ceil(daily_rate * DEFAULT_COVER_DAYS)
    elif receipts:
        last_receipt = max(receipts, key=lambda m: m["created_at"])
        suggested_quantity = float(last_receipt["quantity"])
    else:
        suggested_quantity = None

    cv = coefficient_of_variation(stockout_intervals) if len(stockout_intervals) >= 2 else None
    n_samples = n_out + len(stockouts)
    if n_samples >= 8 and (cv is None or cv < 0.5):
        confidence = "high"
    elif n_samples >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "suggested_quantity": suggested_quantity,
        "daily_rate": daily_rate,
        "avg_stockout_interval_days": avg_stockout_interval,
        "cover_days": DEFAULT_COVER_DAYS,
        "confidence": confidence,
        "n_samples": n_samples,
    }
```

### 3c. `server/app/matcha/services/inventory/rules.py` (full contents)

```python
"""Pure, DB-free authz + reply-parsing rules for the @huume inventory flow.
InventoryVerdict mirrors schedule_chat_rules.ScheduleVerdict exactly —
same two-stage pattern (role -> flag -> stage-specific check)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

APPROVE_ROLES = frozenset({"client", "admin"})

_INVENTORY_OFF_MESSAGE = "Inventory tracking isn't turned on for this workspace."
_APPROVE_ONLY_MESSAGE = (
    "Only a manager can approve or cancel an order — an admin can do that "
    "from the Inventory page or by replying here."
)


@dataclass(frozen=True)
class InventoryVerdict:
    kind: Literal["proceed", "refuse"]
    reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


def evaluate_inventory_action(
    *, role: Optional[str], features: dict, stage: Literal["movement", "approve_order"],
) -> InventoryVerdict:
    """movement: any channel member (any role) may record a deduction/
    receipt/stockout, as long as `inventory` is enabled. approve_order:
    role must be client/admin, same pair as scheduling's ALLOWED_ROLES."""
    if not features.get("inventory"):
        return InventoryVerdict("refuse", _INVENTORY_OFF_MESSAGE)
    if stage == "approve_order" and role not in APPROVE_ROLES:
        return InventoryVerdict("refuse", _APPROVE_ONLY_MESSAGE)
    return InventoryVerdict("proceed")


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "a dozen": 12, "dozen": 12, "a couple": 2,
    "couple": 2, "a few": 3, "few": 3,
}
_NUMERIC_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_quantity_reply(text: str) -> Optional[Decimal]:
    """First bare number in the reply ("12", "about 12", "12 boxes"), or a
    recognized small number word ("a dozen" -> 12). None when nothing
    parses (e.g. "yes", ""). Numeric check runs first — a reply containing
    both a digit and a number word ("a dozen, so like 12") should read the
    explicit digit."""
    t = (text or "").strip().lower()
    if not t:
        return None
    m = _NUMERIC_RE.search(t)
    if m:
        try:
            return Decimal(m.group(1))
        except InvalidOperation:
            return None
    for phrase, value in sorted(_NUMBER_WORDS.items(), key=lambda kv: -len(kv[0])):
        if phrase in t:
            return Decimal(value)
    return None
```

`parse_confirm_reply` is NOT redefined here — import it directly in `channels_ws.py` from `app.matcha.services.scheduling.schedule_chat_rules`.

### 3d. `server/app/matcha/services/inventory/pills.py` (full contents)

```python
"""Channel system-message ("pill") builders for the inventory flow. Every
builder returns a str whose FIRST CHARACTER is the 📦 stock emoji — never
🚨 (systemContent.tsx's isUrgentSystemContent sniffs char 0 for urgent-red;
📦 must never collide with that). Own question-marker wire format, NOT
EMS's — event_intake._QUESTION_MARKER/_QUESTION_SUFFIX are that module's
own round-trip format and must not be reused across features."""

_QUESTION_MARKER = "\n\U00002753 "  # "\n❓ "
_QUESTION_SUFFIX = " Reply to this message to answer."


def movement_pill(item_name: str, qty, remaining, note: str | None, estimated: bool) -> str:
    qty_str = f"~{qty}" if estimated else str(qty)
    base = f"\U0001F4E6 Deducted {qty_str} × {item_name}"
    if note:
        base += f" — {note}"
    if remaining is None:
        base += ". Count unknown — set it on the Inventory page."
    else:
        base += f". {remaining} left."
    return base


def quantity_question(pill: str) -> str:
    return f"{pill}{_QUESTION_MARKER}How many?{_QUESTION_SUFFIX}"


def extract_question(pill_content: str) -> str:
    idx = pill_content.find(_QUESTION_MARKER)
    if idx == -1:
        return pill_content
    question = pill_content[idx + len(_QUESTION_MARKER):]
    if question.endswith(_QUESTION_SUFFIX):
        return question[: -len(_QUESTION_SUFFIX)]
    return question


def stockout_pill(item_name: str, suggestion: dict | None, order_qty) -> str:
    base = f"\U0001F4E6 {item_name} marked out of stock."
    if suggestion and suggestion.get("avg_stockout_interval_days"):
        days = round(suggestion["avg_stockout_interval_days"])
        base += f" You've run out ~every {days} days;"
    if order_qty is not None:
        base += f" suggest ordering {order_qty}."
    else:
        base += " not enough history yet to suggest an amount — set one on the Inventory page."
    base += " Reply **confirm** to queue it, a number to change the amount, or **cancel**."
    return base


def receipt_pill(item_name: str, qty, new_count) -> str:
    base = f"\U0001F4E6 Received {qty} × {item_name}."
    if new_count is not None:
        base += f" {new_count} in stock now."
    return base


def order_confirmed_pill(item_name: str, qty) -> str:
    return f"\U0001F4E6 Order queued: {qty} × {item_name}. Approved and marked ordered."


def order_cancelled_pill(item_name: str) -> str:
    return f"\U0001F4E6 Order for {item_name} cancelled."


def rearm_pill() -> str:
    return "\U0001F4E6 Didn't catch that — reply **confirm**, a number, or **cancel**."
```

### 3e. Tests — `server/tests/inventory/` (new package: `__init__.py` empty + 4 files)

`server/tests/inventory/test_matching.py`:
```python
from app.matcha.services.inventory.matching import best_match, normalize_name


def _row(name):
    return {"id": name, "name": name, "normalized_name": normalize_name(name)}


def test_normalize_case_and_punctuation():
    assert normalize_name("Cherry Farms Cookies!") == normalize_name("cherry farms cookies")


def test_normalize_pluralize():
    assert normalize_name("salads") == normalize_name("salad")


def test_exact_match():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("cherry farms cookies", existing)["name"] == "Cherry Farms Cookies"


def test_containment_match():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("cookies", existing)["name"] == "Cherry Farms Cookies"


def test_typo_fuzzy_match():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("cheery farms cookies", existing)["name"] == "Cherry Farms Cookies"


def test_no_match_returns_none():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("napkins", existing) is None


def test_empty_existing_returns_none():
    assert best_match("anything", []) is None
```

`server/tests/inventory/test_reorder.py`:
```python
from datetime import datetime, timedelta, timezone

from app.matcha.services.inventory.reorder import DEFAULT_COVER_DAYS, suggest_order

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _out(days_ago, qty):
    return {"kind": "out", "quantity": qty, "quantity_delta": -qty,
            "created_at": NOW - timedelta(days=days_ago)}


def _stockout(days_ago):
    return {"kind": "stockout", "quantity": None, "quantity_delta": None,
            "created_at": NOW - timedelta(days=days_ago)}


def _receipt(days_ago, qty):
    return {"kind": "in", "quantity": qty, "quantity_delta": qty,
            "created_at": NOW - timedelta(days=days_ago)}


def test_steady_consumption_rate_times_cover_days():
    movements = [_out(d, 2) for d in range(1, 11)]  # 2/day over ~10 days
    result = suggest_order(movements, NOW)
    assert result is not None
    assert result["suggested_quantity"] == round(2 * DEFAULT_COVER_DAYS)


def test_thin_history_returns_none():
    movements = [_out(1, 1)]
    assert suggest_order(movements, NOW) is None


def test_stockout_interval_average():
    movements = [_stockout(30), _stockout(21), _stockout(12), _out(5, 3), _out(3, 3)]
    result = suggest_order(movements, NOW)
    assert result["avg_stockout_interval_days"] == 9.0


def test_fallback_to_last_receipt_when_no_rate():
    movements = [_receipt(60, 24)]
    result = suggest_order(movements, NOW)
    assert result["suggested_quantity"] == 24.0


def test_null_quantity_movements_excluded():
    movements = [_out(1, 2), _out(2, 2), {"kind": "out", "quantity": None,
                 "quantity_delta": None, "created_at": NOW - timedelta(days=3)}]
    result = suggest_order(movements, NOW)
    assert result is not None  # the two valid outs still count


def test_confidence_tiers():
    many = [_out(d, 1) for d in range(1, 9)]
    assert suggest_order(many, NOW)["confidence"] in ("high", "medium")
    few = [_out(1, 1), _out(2, 1)]
    assert suggest_order(few, NOW)["confidence"] == "low"
```

`server/tests/inventory/test_rules.py`:
```python
from decimal import Decimal

from app.matcha.services.inventory.rules import evaluate_inventory_action, parse_quantity_reply

FEATURES_ON = {"inventory": True}
FEATURES_OFF = {"inventory": False}


def test_employee_can_record_movement():
    v = evaluate_inventory_action(role="employee", features=FEATURES_ON, stage="movement")
    assert v.ok


def test_employee_cannot_approve_order():
    v = evaluate_inventory_action(role="employee", features=FEATURES_ON, stage="approve_order")
    assert not v.ok


def test_client_can_approve_order():
    v = evaluate_inventory_action(role="client", features=FEATURES_ON, stage="approve_order")
    assert v.ok


def test_admin_can_approve_order():
    v = evaluate_inventory_action(role="admin", features=FEATURES_ON, stage="approve_order")
    assert v.ok


def test_flag_off_refuses_both_stages():
    assert not evaluate_inventory_action(role="admin", features=FEATURES_OFF, stage="movement").ok
    assert not evaluate_inventory_action(role="admin", features=FEATURES_OFF, stage="approve_order").ok


def test_parse_quantity_reply_table():
    assert parse_quantity_reply("12") == Decimal("12")
    assert parse_quantity_reply("about 12") == Decimal("12")
    assert parse_quantity_reply("a dozen") == Decimal(12)
    assert parse_quantity_reply("12 boxes") == Decimal("12")
    assert parse_quantity_reply("yes") is None
    assert parse_quantity_reply("") is None
```

`server/tests/inventory/test_pills.py`:
```python
from app.matcha.services.inventory.pills import (
    extract_question, movement_pill, order_cancelled_pill, order_confirmed_pill,
    quantity_question, rearm_pill, receipt_pill, stockout_pill,
)

_ALL_BUILDERS = [
    movement_pill("Cookies", 1, 12, "gifted to Elizabeth", False),
    quantity_question(movement_pill("Cookies", 1, None, None, True)),
    stockout_pill("Salads", {"avg_stockout_interval_days": 9}, 42),
    receipt_pill("Cookies", 24, 30),
    order_confirmed_pill("Salads", 42),
    order_cancelled_pill("Salads"),
    rearm_pill(),
]


def test_every_pill_starts_with_box_emoji():
    for pill in _ALL_BUILDERS:
        assert pill.startswith("\U0001F4E6"), pill


def test_never_urgent_emoji():
    for pill in _ALL_BUILDERS:
        assert not pill.startswith("\U0001F6A8"), pill


def test_extract_question_round_trip():
    base = movement_pill("Cookies", 1, None, None, True)
    q = quantity_question(base)
    assert extract_question(q) == "How many?"


def test_unknown_count_phrasing():
    pill = movement_pill("Cookies", 1, None, "gifted", True)
    assert "count unknown" in pill.lower()
```

**Done when**: `cd server && python3 -m pytest tests/inventory/ -v` — all pass.

---

## Step 4 — Intent routing

### 4a. `server/app/matcha/services/ems/intent.py` — exact diff

Current lines 26-30:
```python
LOG = "log"
ASK = "ask"
HELP = "help"
LINK = "link"
SCHEDULE = "schedule"
```

Change to:
```python
LOG = "log"
ASK = "ask"
HELP = "help"
LINK = "link"
SCHEDULE = "schedule"
INVENTORY = "inventory"
```

After the `_SCHEDULE_PATTERNS`/`_SCHEDULE_RE` block (current lines 129-146), insert a new block (do not remove anything):

```python
# The inventory ask — deduct/receive/stockout/order stock. Bias-to-LOG
# stands here too: patterns deliberately exclude bare "gave"/"used" so
# "we gave John a written warning" and "someone used the slicer and got
# hurt" still LOG.
_INVENTORY_PATTERNS = (
    # OUT — gifted/comped/donated/wasted stock, explicitly, not a bare verb.
    r"^(?:we|i)(?:'ve| have| just|'ve just| have just)? "
    r"(?:gifted|gave away|comped|donated|handed out|used up|went through|"
    r"threw (?:out|away)|tossed|wasted)\b",
    # STOCKOUT / LOW — "we ran out of salads again", "we're low on cups".
    r"^(?:we|i)(?:'re|'ve| are| have| am)?\s*(?:completely |all |totally |almost )?"
    r"(?:ran out of|run out of|out of|used the last of|have no more|"
    r"running low on|low on)\b",
    # RECEIPT — "we received the produce order", "we restocked napkins".
    r"^(?:we|i)(?: just)? (?:received|restocked|got in|"
    r"got (?:a|the|our) (?:delivery|shipment|order)(?: of)?)\b",
    # ORDER REQUEST — tense-exact like SCHEDULE's \bneed\b (never "needed").
    r"^(?:we|i)(?:'ll| will)? need to (?:order|re-?order|re-?stock|buy)\b",
)
_INVENTORY_RE = tuple(re.compile(p, re.IGNORECASE) for p in _INVENTORY_PATTERNS)
```

Then in `classify_intent()`, current lines 196-200:
```python
    for pattern in _SCHEDULE_RE:
        if pattern.search(text):
            return SCHEDULE

    for pattern in _RECALL_RE:
```

Change to:
```python
    for pattern in _SCHEDULE_RE:
        if pattern.search(text):
            return SCHEDULE

    for pattern in _INVENTORY_RE:
        if pattern.search(text):
            return INVENTORY

    for pattern in _RECALL_RE:
```

Finally, update the `classify_intent` docstring (current lines 175-183) by appending one sentence after the existing SCHEDULE-ordering sentence: `"INVENTORY is checked after SCHEDULE and before RECALL for the same reason — its own verb set (gifted/ran out/received/need to order) doesn't overlap SCHEDULE's shift vocabulary or RECALL's show/list/tell set."`

### 4b. `server/tests/ems/test_intent_inventory.py` (new file, full contents — model is `test_intent_schedule.py`, not read verbatim here but the shape below is standard pytest-parametrize matching repo convention)

```python
import pytest

from app.matcha.services.ems.intent import ASK, INVENTORY, LOG, classify_intent

INVENTORY_POSITIVES = [
    "@huume we gifted some Cherry Farms cookies to Elizabeth our manager",
    "@huume we ran out of salads again",
    "@huume we're low on cups",
    "@huume we used up the last coffee filters",
    "@huume we received the produce delivery",
    "@huume we need to reorder napkins",
    "hey @huume we ran out of salads",
]

LOG_NEGATIVES = [
    "@huume we gave John a written warning",
    "@huume someone used the slicer and got hurt",
    "@huume we needed more staff last night and someone got hurt",
    "@huume customer threw a chair",
    "@huume the walk-in ran all night",
]

ASK_NEGATIVES = [
    "@huume did we run out of cups?",
    "@huume how many cookies do we have?",
    "@huume what did we order last week",
]


@pytest.mark.parametrize("text", INVENTORY_POSITIVES)
def test_inventory_positive(text):
    assert classify_intent(text) == INVENTORY


@pytest.mark.parametrize("text", LOG_NEGATIVES)
def test_log_negative_bias_to_log(text):
    assert classify_intent(text) == LOG


@pytest.mark.parametrize("text", ASK_NEGATIVES)
def test_ask_negative(text):
    assert classify_intent(text) == ASK
```

Non-regression: also run the existing `server/tests/ems/test_ems_intent.py` (or whatever the existing SCHEDULE/LINK/HELP test file is actually named — `grep -rl "SCHEDULE" server/tests/ems/`) and confirm it still passes unmodified after this edit.

**Done when**: `cd server && python3 -m pytest tests/ems/test_intent_inventory.py tests/ems/ -v` — all pass, including every pre-existing EMS intent test.

---

## Step 5 — Extraction (Gemini) + DB services

### 5a. `server/app/matcha/services/inventory/extraction.py` (full contents)

```python
"""One-shot Gemini extraction for an inventory-classified channel message.
Mirrors services/ems/event_intake.py:classify_event's call shape exactly:
never raises, takes no conn, returns the uncategorized/non-actionable
fallback shape on any failure so the caller can delegate to EMS intake."""

import json
import logging
import re
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

FLASH_LITE_MODEL = "gemini-3.1-flash-lite"

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


_PROMPT_TEMPLATE = """You extract structured inventory data from a short channel message.

Known existing items (reuse an exact name below when the message clearly refers to one of them; otherwise propose a short, title-case new item name):
{item_names}

Message: "{content}"

Return ONLY JSON matching this shape:
{{
  "actionable": true or false,
  "kind": "movement" | "stockout" | "receipt" | "order_request",
  "lines": [
    {{"item_name": "...", "quantity": number or null, "unit": "..." or null, "direction": "out" or "in"}}
  ],
  "recipient_note": "..." or null
}}

Rules:
- "actionable": false when the message does not name any identifiable stock item, or is not really about inventory (a misclassification) — the caller falls back to plain event logging in that case.
- "kind": "movement" for an ordinary deduction/use ("we gifted some cookies"), "stockout" for a "ran out of" / "out of" report, "receipt" for goods coming IN ("we received the produce delivery"), "order_request" for an explicit "we need to reorder X".
- "quantity" is null when the message doesn't state a number ("some cookies") — never guess a number.
- "recipient_note" captures a short human-readable aside like "gifted to Elizabeth (manager)" — null if there isn't one.
- Every "direction" is "out" for movement/stockout, "in" for receipt. order_request lines have direction "out" (they represent what's being replenished).
"""


def _build_prompt(content: str, item_names: list[str]) -> str:
    names = ", ".join(item_names) if item_names else "(none yet)"
    return _PROMPT_TEMPLATE.format(item_names=names, content=content)


_FALLBACK_RESULT = {
    "actionable": False,
    "kind": "movement",
    "lines": [],
    "recipient_note": None,
}

_NUMERIC_RE = re.compile(r"(\d+(?:\.\d+)?)")


def fallback_extraction(content: str) -> dict:
    """Deterministic, zero-Gemini fallback: single line, first number found
    (or None), actionable only when we found a number worth acting on.
    Documentation-over-precision — caller still falls back to EMS intake
    when actionable is False, so an unparseable message is never lost."""
    result = dict(_FALLBACK_RESULT)
    m = _NUMERIC_RE.search(content)
    if m:
        result["actionable"] = False  # no item name isolated deterministically; still hand to EMS
    return result


def _parse_model_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


async def extract_inventory(content: str, item_names: list[str]) -> dict:
    """Never raises. Returns the fallback shape (actionable=False) on any
    Gemini failure or malformed response — caller falls back to
    _bg_ems_intake wholesale in that case, same as EMS's own outage rule."""
    try:
        prompt = _build_prompt(content, item_names)
        resp = await _get_client().aio.models.generate_content(
            model=FLASH_LITE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2, response_mime_type="application/json", max_output_tokens=500,
            ),
        )
        parsed = _parse_model_json(resp.text)
        return {**_FALLBACK_RESULT, **parsed}
    except Exception:
        logger.warning("inventory: extraction failed, falling back", exc_info=True)
        return fallback_extraction(content)
```

### 5b. `server/app/matcha/services/inventory/movements.py` (full contents)

```python
"""DB service for inventory items + the append-only movement ledger."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.matcha.services.inventory.matching import best_match, normalize_name


async def list_item_names(conn, company_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, name, normalized_name FROM inventory_items "
        "WHERE company_id = $1 AND archived_at IS NULL",
        company_id,
    )
    return [dict(r) for r in rows]


async def find_or_create_item(conn, company_id: UUID, raw_name: str, *, created_by: Optional[UUID]) -> dict:
    existing = await list_item_names(conn, company_id)
    match = best_match(raw_name, existing)
    if match is not None:
        row = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1", match["id"])
        return dict(row)

    normalized = normalize_name(raw_name)
    await conn.execute(
        """
        INSERT INTO inventory_items (company_id, name, normalized_name, auto_created, created_by)
        VALUES ($1, $2, $3, TRUE, $4)
        ON CONFLICT (company_id, normalized_name) WHERE archived_at IS NULL DO NOTHING
        """,
        company_id, raw_name.strip(), normalized, created_by,
    )
    row = await conn.fetchrow(
        "SELECT * FROM inventory_items WHERE company_id = $1 AND normalized_name = $2 AND archived_at IS NULL",
        company_id, normalized,
    )
    return dict(row)


async def record_movements(
    conn, *, company_id: UUID, channel_id: Optional[UUID], source_message_id: Optional[UUID],
    recorded_by: Optional[UUID], kind: str, lines: list[dict], narrative: str, note: Optional[str],
) -> list[dict]:
    """lines: [{item_id, quantity (Decimal|None), estimated (bool)}]. kind
    applies to every line in this call (movement handler calls this once
    per kind: 'out'/'in'; stockout handler calls it separately with
    kind='stockout'). Returns inserted rows only — a WS replay that hits
    the ON CONFLICT DO NOTHING contributes nothing to the return list."""
    inserted = []
    for line in lines:
        quantity = line.get("quantity")
        estimated = bool(line.get("estimated", False))
        delta = None
        if kind == "out" and quantity is not None:
            delta = -abs(float(quantity))
        elif kind == "in" and quantity is not None:
            delta = abs(float(quantity))

        row = await conn.fetchrow(
            """
            INSERT INTO inventory_movements (
                company_id, item_id, channel_id, source_message_id, recorded_by,
                kind, quantity, quantity_delta, quantity_estimated, note, narrative
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (source_message_id, item_id) WHERE source_message_id IS NOT NULL DO NOTHING
            RETURNING *
            """,
            company_id, line["item_id"], channel_id, source_message_id, recorded_by,
            kind, quantity, delta, estimated, note, narrative,
        )
        if row is None:
            continue
        inserted.append(dict(row))

        if kind == "stockout":
            await conn.execute(
                "UPDATE inventory_items SET current_quantity = 0, updated_at = NOW() WHERE id = $1",
                line["item_id"],
            )
        elif delta is not None:
            await conn.execute(
                """
                UPDATE inventory_items SET current_quantity = CASE
                    WHEN current_quantity IS NULL THEN NULL
                    ELSE GREATEST(current_quantity + $2, 0)
                END, updated_at = NOW() WHERE id = $1
                """,
                line["item_id"], delta,
            )
    return inserted


async def amend_movement_quantity(conn, *, movement_id: UUID, quantity, user_id: UUID) -> Optional[dict]:
    """Only amends WHILE quantity_estimated=TRUE — the one sanctioned edit
    on an otherwise append-only ledger. Recomputes delta vs the old value
    and applies the diff to the item's running count."""
    old = await conn.fetchrow(
        "SELECT * FROM inventory_movements WHERE id = $1 AND quantity_estimated = TRUE", movement_id,
    )
    if old is None:
        return None
    old_qty = float(old["quantity"] or 0)
    new_qty = float(quantity)
    sign = -1 if old["kind"] == "out" else 1
    diff = sign * (new_qty - old_qty)

    row = await conn.fetchrow(
        """
        UPDATE inventory_movements
        SET quantity = $2, quantity_delta = $3, quantity_estimated = FALSE,
            amended_by = $4, amended_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        movement_id, new_qty, sign * new_qty, user_id,
    )
    await conn.execute(
        """
        UPDATE inventory_items SET current_quantity = CASE
            WHEN current_quantity IS NULL THEN NULL
            ELSE GREATEST(current_quantity + $2, 0)
        END, updated_at = NOW() WHERE id = $1
        """,
        old["item_id"], diff,
    )
    return dict(row)


async def adjust_item_count(conn, *, item_id: UUID, company_id: UUID, quantity, user_id: UUID) -> dict:
    """The ONLY set-count path — never write inventory_items.current_quantity
    directly from a route handler."""
    old = await conn.fetchrow(
        "SELECT current_quantity FROM inventory_items WHERE id = $1 AND company_id = $2",
        item_id, company_id,
    )
    old_qty = old["current_quantity"]
    new_qty = float(quantity)
    delta = None if old_qty is None else new_qty - float(old_qty)

    await conn.execute(
        "UPDATE inventory_items SET current_quantity = $2, updated_at = NOW() WHERE id = $1",
        item_id, new_qty,
    )
    row = await conn.fetchrow(
        """
        INSERT INTO inventory_movements (
            company_id, item_id, recorded_by, kind, quantity, quantity_delta, narrative
        ) VALUES ($1, $2, $3, 'adjust', $4, $5, 'Manual count adjustment')
        RETURNING *
        """,
        company_id, item_id, user_id, new_qty, delta,
    )
    return dict(row)
```

### 5c. `server/app/matcha/services/inventory/orders.py` (full contents)

```python
"""DB service for the inventory order queue."""

from typing import Optional
from uuid import UUID

from app.matcha.services.inventory import movements as movements_service


async def stage_order(
    conn, *, company_id: UUID, item_id: UUID, channel_id: Optional[UUID],
    source_message_id: Optional[UUID], created_by: Optional[UUID], suggestion: Optional[dict],
) -> dict:
    """A repeat stockout re-points the confirm pill at the SAME queued
    order (partial unique index uniq_inventory_orders_open enforces one
    queued order per item) rather than erroring or duplicating."""
    suggested_quantity = suggestion.get("suggested_quantity") if suggestion else None
    row = await conn.fetchrow(
        """
        INSERT INTO inventory_orders (
            company_id, item_id, channel_id, source_message_id, created_by,
            suggested_quantity, quantity, suggestion
        ) VALUES ($1, $2, $3, $4, $5, $6, $6, $7)
        ON CONFLICT (item_id) WHERE status = 'queued'
        DO UPDATE SET suggestion = EXCLUDED.suggestion,
                      suggested_quantity = EXCLUDED.suggested_quantity,
                      quantity = EXCLUDED.quantity,
                      updated_at = NOW()
        RETURNING *
        """,
        company_id, item_id, channel_id, source_message_id, created_by,
        suggested_quantity, suggestion,
    )
    return dict(row)


async def approve_order(conn, *, order_id: UUID, company_id: UUID, user_id: UUID, quantity=None) -> dict:
    row = await conn.fetchrow(
        """
        UPDATE inventory_orders
        SET status = 'ordered', quantity = COALESCE($3, quantity),
            approved_by = $2, approved_at = NOW(), ordered_at = NOW(),
            confirm_message_id = NULL, updated_at = NOW()
        WHERE id = $1 AND company_id = $4 AND status = 'queued'
        RETURNING *
        """,
        order_id, user_id, quantity, company_id,
    )
    return dict(row) if row else None


async def cancel_order(conn, *, order_id: UUID, company_id: UUID, user_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        UPDATE inventory_orders
        SET status = 'cancelled', confirm_message_id = NULL, updated_at = NOW()
        WHERE id = $1 AND company_id = $3 AND status IN ('queued', 'ordered')
        RETURNING *
        """,
        order_id, user_id, company_id,
    )
    return dict(row) if row else None


async def mark_received(conn, *, order_id: UUID, company_id: UUID, user_id: UUID, quantity=None) -> dict:
    order = await conn.fetchrow(
        "SELECT * FROM inventory_orders WHERE id = $1 AND company_id = $2 AND status IN ('queued', 'ordered')",
        order_id, company_id,
    )
    if order is None:
        return None
    received_qty = float(quantity) if quantity is not None else float(order["quantity"] or 0)

    [movement] = await movements_service.record_movements(
        conn, company_id=company_id, channel_id=order["channel_id"], source_message_id=None,
        recorded_by=user_id, kind="in", narrative="Order received", note=None,
        lines=[{"item_id": order["item_id"], "quantity": received_qty, "estimated": False}],
    )
    row = await conn.fetchrow(
        """
        UPDATE inventory_orders
        SET status = 'received', received_by = $2, received_at = NOW(),
            received_quantity = $3, receipt_movement_id = $4, updated_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        order_id, user_id, received_qty, movement["id"],
    )
    return dict(row)
```

**Done when**: `python3 -m py_compile` clean on all 3 new files (post-edit hook). No DB-backed automated test for these (per root CLAUDE.md, DB-mutating tests are manual/user-run) — manual verification happens in the end-to-end step.

---

## Step 6 — Models + REST router

### 6a. `server/app/matcha/models/inventory.py` (full contents)

```python
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

MovementKind = Literal["out", "in", "stockout", "adjust"]
OrderStatus = Literal["queued", "ordered", "received", "cancelled"]


class OrderOut(BaseModel):
    id: UUID
    item_id: UUID
    status: OrderStatus
    suggested_quantity: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    suggestion: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class InventoryItemOut(BaseModel):
    id: UUID
    name: str
    unit: Optional[str] = None
    current_quantity: Optional[Decimal] = None
    low_stock_threshold: Optional[Decimal] = None
    auto_created: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    open_order: Optional[OrderOut] = None


class InventoryItemCreate(BaseModel):
    name: str
    unit: Optional[str] = None
    current_quantity: Optional[Decimal] = None
    low_stock_threshold: Optional[Decimal] = None


class InventoryItemPatch(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    low_stock_threshold: Optional[Decimal] = None
    set_quantity: Optional[Decimal] = None
    archived: Optional[bool] = None


class MovementOut(BaseModel):
    id: UUID
    item_id: UUID
    kind: MovementKind
    quantity: Optional[Decimal] = None
    quantity_delta: Optional[Decimal] = None
    quantity_estimated: bool
    note: Optional[str] = None
    narrative: str
    created_at: datetime


class OrderCreate(BaseModel):
    item_id: UUID
    quantity: Optional[Decimal] = None


class OrderAction(BaseModel):
    quantity: Optional[Decimal] = None


class ItemListResponse(BaseModel):
    items: list[InventoryItemOut]


class MovementListResponse(BaseModel):
    movements: list[MovementOut]


class OrderListResponse(BaseModel):
    orders: list[OrderOut]
```

### 6b. `server/app/matcha/routes/inventory.py` (full contents)

```python
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.inventory import (
    InventoryItemCreate, InventoryItemOut, InventoryItemPatch, ItemListResponse,
    MovementListResponse, MovementOut, OrderAction, OrderCreate, OrderListResponse, OrderOut,
)
from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory import orders as orders_service
from app.matcha.services.inventory.matching import normalize_name
from app.matcha.services.inventory.reorder import suggest_order

router = APIRouter()


@router.get("/items", response_model=ItemListResponse)
async def list_items(include_archived: bool = False, company_id: UUID = Depends(get_client_company_id),
                      _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        clause = "" if include_archived else "AND archived_at IS NULL"
        rows = await conn.fetch(
            f"""
            SELECT it.*, o.id AS order_id, o.status AS order_status,
                   o.suggested_quantity AS order_suggested_quantity, o.quantity AS order_quantity,
                   o.suggestion AS order_suggestion, o.created_at AS order_created_at,
                   o.updated_at AS order_updated_at
            FROM inventory_items it
            LEFT JOIN inventory_orders o ON o.item_id = it.id AND o.status = 'queued'
            WHERE it.company_id = $1 {clause}
            ORDER BY it.name
            """,
            company_id,
        )
    items = []
    for r in rows:
        open_order = None
        if r["order_id"] is not None:
            open_order = OrderOut(
                id=r["order_id"], item_id=r["id"], status=r["order_status"],
                suggested_quantity=r["order_suggested_quantity"], quantity=r["order_quantity"],
                suggestion=r["order_suggestion"], created_at=r["order_created_at"],
                updated_at=r["order_updated_at"],
            )
        items.append(InventoryItemOut(**{**dict(r), "open_order": open_order}))
    return ItemListResponse(items=items)


@router.post("/items", response_model=InventoryItemOut, status_code=201)
async def create_item(body: InventoryItemCreate, company_id: UUID = Depends(get_client_company_id),
                       user=Depends(require_admin_or_client)):
    normalized = normalize_name(body.name)
    async with get_connection() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM inventory_items WHERE company_id = $1 AND normalized_name = $2 AND archived_at IS NULL",
            company_id, normalized,
        )
        if existing:
            raise HTTPException(409, "An item with this name already exists.")
        row = await conn.fetchrow(
            """
            INSERT INTO inventory_items (company_id, name, normalized_name, unit, current_quantity,
                                         low_stock_threshold, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
            """,
            company_id, body.name, normalized, body.unit, body.current_quantity,
            body.low_stock_threshold, user["id"],
        )
    return InventoryItemOut(**dict(row))


@router.get("/items/{item_id}", response_model=dict)
async def get_item(item_id: UUID, company_id: UUID = Depends(get_client_company_id),
                    _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        item = await conn.fetchrow(
            "SELECT * FROM inventory_items WHERE id = $1 AND company_id = $2", item_id, company_id,
        )
        if item is None:
            raise HTTPException(404, "Item not found.")
        movement_rows = await conn.fetch(
            "SELECT * FROM inventory_movements WHERE item_id = $1 ORDER BY created_at DESC LIMIT 50",
            item_id,
        )
    return {
        "item": InventoryItemOut(**dict(item)),
        "movements": [MovementOut(**dict(m)) for m in movement_rows],
    }


@router.patch("/items/{item_id}", response_model=InventoryItemOut)
async def patch_item(item_id: UUID, body: InventoryItemPatch,
                      company_id: UUID = Depends(get_client_company_id),
                      user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        item = await conn.fetchrow(
            "SELECT * FROM inventory_items WHERE id = $1 AND company_id = $2", item_id, company_id,
        )
        if item is None:
            raise HTTPException(404, "Item not found.")

        if body.set_quantity is not None:
            await movements_service.adjust_item_count(
                conn, item_id=item_id, company_id=company_id, quantity=body.set_quantity, user_id=user["id"],
            )

        fields, values = [], []
        if body.name is not None:
            fields.append("name = $%d" % (len(values) + 2)); values.append(body.name)
            fields.append("normalized_name = $%d" % (len(values) + 2)); values.append(normalize_name(body.name))
        if body.unit is not None:
            fields.append("unit = $%d" % (len(values) + 2)); values.append(body.unit)
        if body.low_stock_threshold is not None:
            fields.append("low_stock_threshold = $%d" % (len(values) + 2)); values.append(body.low_stock_threshold)
        if body.archived is not None:
            fields.append("archived_at = %s" % ("NOW()" if body.archived else "NULL"))

        if fields:
            await conn.execute(
                f"UPDATE inventory_items SET {', '.join(fields)}, updated_at = NOW() WHERE id = $1",
                item_id, *values,
            )
        row = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1", item_id)
    return InventoryItemOut(**dict(row))


@router.get("/movements", response_model=MovementListResponse)
async def list_movements(item_id: UUID = None, limit: int = Query(50, le=200), offset: int = 0,
                          company_id: UUID = Depends(get_client_company_id),
                          _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        if item_id:
            rows = await conn.fetch(
                "SELECT * FROM inventory_movements WHERE company_id = $1 AND item_id = $2 "
                "ORDER BY created_at DESC LIMIT $3 OFFSET $4",
                company_id, item_id, limit, offset,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM inventory_movements WHERE company_id = $1 "
                "ORDER BY created_at DESC LIMIT $2 OFFSET $3",
                company_id, limit, offset,
            )
    return MovementListResponse(movements=[MovementOut(**dict(r)) for r in rows])


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(status: str = None, company_id: UUID = Depends(get_client_company_id),
                       _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM inventory_orders WHERE company_id = $1 AND status = $2 ORDER BY created_at DESC",
                company_id, status,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM inventory_orders WHERE company_id = $1 ORDER BY created_at DESC", company_id,
            )
    return OrderListResponse(orders=[OrderOut(**dict(r)) for r in rows])


@router.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(body: OrderCreate, company_id: UUID = Depends(get_client_company_id),
                        user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        row = await orders_service.stage_order(
            conn, company_id=company_id, item_id=body.item_id, channel_id=None, source_message_id=None,
            created_by=user["id"], suggestion={"suggested_quantity": float(body.quantity)} if body.quantity else None,
        )
    return OrderOut(**row)


@router.post("/orders/{order_id}/approve", response_model=OrderOut)
async def approve_order_route(order_id: UUID, body: OrderAction,
                               company_id: UUID = Depends(get_client_company_id),
                               user=Depends(require_admin_or_client)):
    if user["role"] not in ("client", "admin"):
        raise HTTPException(403, "Only a manager can approve an order.")
    async with get_connection() as conn:
        row = await orders_service.approve_order(
            conn, order_id=order_id, company_id=company_id, user_id=user["id"], quantity=body.quantity,
        )
    if row is None:
        raise HTTPException(404, "No queued order found.")
    return OrderOut(**row)


@router.post("/orders/{order_id}/receive", response_model=OrderOut)
async def receive_order_route(order_id: UUID, body: OrderAction,
                               company_id: UUID = Depends(get_client_company_id),
                               user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        row = await orders_service.mark_received(
            conn, order_id=order_id, company_id=company_id, user_id=user["id"], quantity=body.quantity,
        )
    if row is None:
        raise HTTPException(404, "No open order found.")
    return OrderOut(**row)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order_route(order_id: UUID, company_id: UUID = Depends(get_client_company_id),
                              user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        row = await orders_service.cancel_order(conn, order_id=order_id, company_id=company_id, user_id=user["id"])
    if row is None:
        raise HTTPException(404, "No cancellable order found.")
    return OrderOut(**row)


@router.get("/suggestions", response_model=dict)
async def list_suggestions(company_id: UUID = Depends(get_client_company_id),
                            _=Depends(require_admin_or_client)):
    from datetime import datetime, timezone

    async with get_connection() as conn:
        items = await conn.fetch(
            "SELECT id, name FROM inventory_items WHERE company_id = $1 AND archived_at IS NULL", company_id,
        )
        out = {}
        for item in items:
            movement_rows = await conn.fetch(
                "SELECT kind, quantity, quantity_delta, created_at FROM inventory_movements "
                "WHERE item_id = $1 ORDER BY created_at ASC",
                item["id"],
            )
            suggestion = suggest_order([dict(m) for m in movement_rows], datetime.now(timezone.utc))
            if suggestion:
                out[str(item["id"])] = {"name": item["name"], **suggestion}
    return out
```

### 6c. Mount in `server/app/matcha/routes/__init__.py`

Quote of current line 46:
```python
from .ems import router as ems_router
```
Add immediately after:
```python
from .inventory import router as inventory_router
```

Quote of current lines 150-151:
```python
matcha_router.include_router(ems_router, prefix="/ems", tags=["ems"],
                             dependencies=[Depends(require_feature("ems"))])
```
Add immediately after:
```python
matcha_router.include_router(inventory_router, prefix="/inventory", tags=["inventory"],
                             dependencies=[Depends(require_feature("inventory"))])
```

**Done when**: `py_compile` clean on `models/inventory.py`, `routes/inventory.py`, `routes/__init__.py`.

---

## Step 7 — WS wiring (`server/app/werk/routes/channels_ws.py`)

### 7a. Generalize the EMS gate pair, add the inventory pair

Current lines 152-192 (`_ems_row_allowed`, `_ems_company_gate`, `_ems_flag_enabled`) stay EXACTLY as-is (do not rename — `_ems_row_allowed` already takes no flag param). Immediately after line 192 (after `_ems_flag_enabled`'s closing line, before `_ems_first_time_hint` at line 195), insert:

```python
def _inventory_row_allowed(row) -> bool:
    """Same shape as _ems_row_allowed, keyed on the `inventory` flag."""
    if not row or row["is_personal"]:
        return False
    from app.core.feature_flags import merge_company_features
    return bool(merge_company_features(row["enabled_features"], row["signup_source"]).get("inventory"))


async def _inventory_company_gate(conn, channel_id_str: str):
    row = await conn.fetchrow(
        """
        SELECT ch.company_id, comp.is_personal, comp.enabled_features, comp.signup_source
        FROM channels ch JOIN companies comp ON comp.id = ch.company_id
        WHERE ch.id = $1
        """,
        UUID(channel_id_str),
    )
    return row["company_id"] if _inventory_row_allowed(row) else None


async def _inventory_flag_enabled(conn, company_id) -> bool:
    row = await conn.fetchrow(
        "SELECT is_personal, enabled_features, signup_source FROM companies WHERE id = $1", company_id,
    )
    return _inventory_row_allowed(row)
```

(Note: this plan does NOT refactor `_ems_row_allowed` into a generic `_flag_row_allowed` helper — that would touch working EMS code for no functional gain. The inventory pair is a parallel copy with `"inventory"` hardcoded, same as `_ems_row_allowed` hardcodes `"ems"`.)

### 7b. `_bg_inventory_request` — insert after `_bg_schedule_request` (after line 450, before `_bg_schedule_reply` at line 453)

```python
async def _bg_inventory_request(
    channel_id_str: str, message_id_str: str, sender_user_id_str: str, content: str,
) -> None:
    """"@huume we gifted some cookies to Elizabeth" / "@huume we ran out of
    salads again" — INVENTORY-classified channel message. Same off-hot-path
    contract as _bg_schedule_request. Two connection blocks: the Gemini
    extraction call must not run with a pooled connection held."""
    try:
        from app.matcha.services.ems.event_intake import fallback_classification
        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.inventory import movements as movements_service
        from app.matcha.services.inventory import orders as orders_service
        from app.matcha.services.inventory import pills
        from app.matcha.services.inventory.extraction import extract_inventory
        from app.matcha.services.inventory.reorder import suggest_order
        from app.matcha.services.inventory.rules import evaluate_inventory_action

        sys_row = None
        stripped = strip_mention(content)

        async with get_connection() as conn:
            company_id = await _inventory_company_gate(conn, channel_id_str)
            if company_id is None:
                ems_company_id = await _ems_company_gate(conn, channel_id_str)
                if ems_company_id is not None:
                    async with get_connection() as _c2:
                        pass  # release before delegating, mirrors the two-block rule
                    await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
                return

            try:
                await check_rate_limit(str(company_id), "inventory_event", 30, 3600)
            except HTTPException:
                return

            if fallback_classification(content).get("urgency") == "osha":
                await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)

            features = await _schedule_company_features(conn, company_id)
            role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(sender_user_id_str))
            verdict = evaluate_inventory_action(role=role, features=features, stage="movement")
            if not verdict.ok:
                sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)

            if sys_row is None:
                item_rows = await movements_service.list_item_names(conn, company_id)

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
            return

        item_names = [r["name"] for r in item_rows]
        extracted = await extract_inventory(stripped, item_names)

        if not extracted.get("actionable"):
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
            return

        kind = extracted.get("kind", "movement")
        lines = extracted.get("lines") or []

        async with get_connection() as conn:
            if kind in ("movement", "receipt"):
                movement_kind = "in" if kind == "receipt" else "out"
                resolved_lines = []
                for line in lines:
                    item = await movements_service.find_or_create_item(
                        conn, company_id, line.get("item_name", ""), created_by=UUID(sender_user_id_str),
                    )
                    qty = line.get("quantity")
                    estimated = qty is None
                    resolved_lines.append({
                        "item_id": item["id"], "quantity": 1 if estimated else qty, "estimated": estimated,
                    })
                inserted = await movements_service.record_movements(
                    conn, company_id=company_id, channel_id=UUID(channel_id_str),
                    source_message_id=UUID(message_id_str), recorded_by=UUID(sender_user_id_str),
                    kind=movement_kind, lines=resolved_lines, narrative=stripped,
                    note=extracted.get("recipient_note"),
                )
                if not inserted:
                    return
                first = inserted[0]
                item_row = await conn.fetchrow("SELECT name, current_quantity FROM inventory_items WHERE id = $1",
                                                first["item_id"])
                pill_text = pills.movement_pill(
                    item_row["name"], first["quantity"], item_row["current_quantity"],
                    extracted.get("recipient_note"), first["quantity_estimated"],
                )
                single_unknown = len(inserted) == 1 and inserted[0]["quantity_estimated"]
                if single_unknown:
                    pill_text = pills.quantity_question(pill_text)
                sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                if single_unknown:
                    await conn.execute(
                        "UPDATE inventory_movements SET clarify_message_id = $1 WHERE id = $2",
                        sys_row["id"], inserted[0]["id"],
                    )

            else:  # stockout / order_request
                item_name = lines[0].get("item_name") if lines else stripped
                item = await movements_service.find_or_create_item(
                    conn, company_id, item_name, created_by=UUID(sender_user_id_str),
                )
                suggestion = None
                if kind == "stockout":
                    await movements_service.record_movements(
                        conn, company_id=company_id, channel_id=UUID(channel_id_str),
                        source_message_id=UUID(message_id_str), recorded_by=UUID(sender_user_id_str),
                        kind="stockout", lines=[{"item_id": item["id"], "quantity": None, "estimated": False}],
                        narrative=stripped, note=None,
                    )
                history_rows = await conn.fetch(
                    "SELECT kind, quantity, quantity_delta, created_at FROM inventory_movements "
                    "WHERE item_id = $1 ORDER BY created_at ASC",
                    item["id"],
                )
                from datetime import datetime, timezone
                suggestion = suggest_order([dict(r) for r in history_rows], datetime.now(timezone.utc))
                order_qty = suggestion.get("suggested_quantity") if suggestion else None

                order = await orders_service.stage_order(
                    conn, company_id=company_id, item_id=item["id"], channel_id=UUID(channel_id_str),
                    source_message_id=UUID(message_id_str), created_by=UUID(sender_user_id_str),
                    suggestion=suggestion,
                )
                pill_text = pills.stockout_pill(item["name"], suggestion, order_qty)
                sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                await conn.execute(
                    "UPDATE inventory_orders SET confirm_message_id = $1 WHERE id = $2",
                    sys_row["id"], order["id"],
                )

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
    except Exception:
        logger.exception("inventory chat request failed for message %s", message_id_str)
```

### 7c. `_bg_inventory_reply` — insert immediately after `_bg_inventory_request`, before `_bg_schedule_reply` (line 453)

```python
async def _bg_inventory_reply(
    channel_id_str: str, reply_to_id_str: str, sender_user_id_str: str, content: str,
) -> bool:
    """Fold a reply-to-an-inventory-pill into its order or clarify-armed
    movement. Same claim-then-act, exception-safe contract as
    _bg_schedule_reply — returns True iff a claim matched (order OR
    movement), so _bg_ems_dispatch knows whether to still try the mention
    fork. No Gemini call anywhere in this path."""
    claim_happened = False
    try:
        from app.matcha.services.ems.intent import strip_mention
        from app.matcha.services.inventory import movements as movements_service
        from app.matcha.services.inventory import orders as orders_service
        from app.matcha.services.inventory import pills
        from app.matcha.services.inventory.rules import evaluate_inventory_action, parse_quantity_reply
        from app.matcha.services.scheduling.schedule_chat_rules import parse_confirm_reply

        reply_uuid = UUID(reply_to_id_str)
        sender_uuid = UUID(sender_user_id_str)
        stripped = strip_mention(content)
        sys_row = None

        async with get_connection() as conn:
            claimed_order = await conn.fetchrow(
                """
                UPDATE inventory_orders SET confirm_message_id = NULL, updated_at = NOW()
                WHERE confirm_message_id = $1 AND status = 'queued'
                  AND created_at > NOW() - INTERVAL '7 days'
                RETURNING id, company_id, item_id, suggested_quantity, quantity, suggestion
                """,
                reply_uuid,
            )
            if claimed_order is not None:
                claim_happened = True
                item = await conn.fetchrow("SELECT name FROM inventory_items WHERE id = $1", claimed_order["item_id"])
                features = await _schedule_company_features(conn, claimed_order["company_id"])
                role = await conn.fetchval("SELECT role FROM users WHERE id = $1", sender_uuid)
                verdict = evaluate_inventory_action(role=role, features=features, stage="approve_order")
                if not verdict.ok:
                    await conn.execute(
                        "UPDATE inventory_orders SET confirm_message_id = $1 WHERE id = $2",
                        reply_uuid, claimed_order["id"],
                    )
                    sys_row = await _insert_system_message(conn, channel_id_str, verdict.reason)
                else:
                    action = parse_confirm_reply(stripped)
                    if action == "confirm":
                        row = await orders_service.approve_order(
                            conn, order_id=claimed_order["id"], company_id=claimed_order["company_id"],
                            user_id=sender_uuid, quantity=claimed_order["quantity"],
                        )
                        sys_row = await _insert_system_message(
                            conn, channel_id_str, pills.order_confirmed_pill(item["name"], row["quantity"]),
                        )
                    elif action == "cancel":
                        await orders_service.cancel_order(
                            conn, order_id=claimed_order["id"], company_id=claimed_order["company_id"], user_id=sender_uuid,
                        )
                        sys_row = await _insert_system_message(conn, channel_id_str, pills.order_cancelled_pill(item["name"]))
                    else:
                        new_qty = parse_quantity_reply(stripped)
                        if new_qty is not None:
                            await conn.execute(
                                "UPDATE inventory_orders SET quantity = $1 WHERE id = $2", new_qty, claimed_order["id"],
                            )
                            pill_text = pills.stockout_pill(item["name"], claimed_order["suggestion"], new_qty)
                        else:
                            pill_text = pills.rearm_pill()
                        sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                        await conn.execute(
                            "UPDATE inventory_orders SET confirm_message_id = $1 WHERE id = $2",
                            sys_row["id"], claimed_order["id"],
                        )

            else:
                claimed_movement = await conn.fetchrow(
                    """
                    UPDATE inventory_movements SET clarify_message_id = NULL
                    WHERE clarify_message_id = $1
                      AND created_at > NOW() - INTERVAL '7 days'
                    RETURNING id, company_id, item_id, clarify_rounds
                    """,
                    reply_uuid,
                )
                if claimed_movement is not None:
                    claim_happened = True
                    item = await conn.fetchrow("SELECT name, current_quantity FROM inventory_items WHERE id = $1",
                                                claimed_movement["item_id"])
                    qty = parse_quantity_reply(stripped)
                    if qty is not None:
                        await movements_service.amend_movement_quantity(
                            conn, movement_id=claimed_movement["id"], quantity=qty, user_id=sender_uuid,
                        )
                        new_item = await conn.fetchrow("SELECT current_quantity FROM inventory_items WHERE id = $1",
                                                        claimed_movement["item_id"])
                        sys_row = await _insert_system_message(
                            conn, channel_id_str,
                            pills.movement_pill(item["name"], qty, new_item["current_quantity"], None, False),
                        )
                    elif claimed_movement["clarify_rounds"] < 2:
                        await conn.execute(
                            "UPDATE inventory_movements SET clarify_rounds = clarify_rounds + 1 WHERE id = $1",
                            claimed_movement["id"],
                        )
                        pill_text = pills.quantity_question(pills.rearm_pill())
                        sys_row = await _insert_system_message(conn, channel_id_str, pill_text)
                        await conn.execute(
                            "UPDATE inventory_movements SET clarify_message_id = $1 WHERE id = $2",
                            sys_row["id"], claimed_movement["id"],
                        )
                    else:
                        sys_row = await _insert_system_message(
                            conn, channel_id_str,
                            f"\U0001F4E6 Couldn't pin down the count for {item['name']} — set it on the Inventory page.",
                        )

        if sys_row is not None:
            await broadcast_system_message(channel_id_str, _system_message_payload(channel_id_str, sys_row))
        return claim_happened
    except Exception:
        logger.exception("inventory chat reply failed for %s", reply_to_id_str)
        return claim_happened
```

### 7d. `_bg_ems_dispatch` diff — quote of current lines 1005-1027:

```python
    if reply_to_system_id_str is not None:
        claimed = await _bg_ems_clarify(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
        claimed = await _bg_schedule_reply(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
    if has_huume_mention:
        from app.matcha.services.ems.intent import LINK, LOG, SCHEDULE, classify_intent

        intent = classify_intent(content)
        if intent == LOG:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
        elif intent == LINK:
            await _bg_ems_link(channel_id_str, sender_user_id_str)
        elif intent == SCHEDULE:
            await _bg_schedule_request(channel_id_str, message_id_str, sender_user_id_str, content)
        else:
            await _bg_ems_ask(channel_id_str, sender_user_id_str, content, intent)
```

Change to:
```python
    if reply_to_system_id_str is not None:
        claimed = await _bg_ems_clarify(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
        claimed = await _bg_schedule_reply(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
        claimed = await _bg_inventory_reply(
            channel_id_str, reply_to_system_id_str, sender_user_id_str, content,
        )
        if claimed:
            return
    if has_huume_mention:
        from app.matcha.services.ems.intent import INVENTORY, LINK, LOG, SCHEDULE, classify_intent

        intent = classify_intent(content)
        if intent == LOG:
            await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
        elif intent == LINK:
            await _bg_ems_link(channel_id_str, sender_user_id_str)
        elif intent == SCHEDULE:
            await _bg_schedule_request(channel_id_str, message_id_str, sender_user_id_str, content)
        elif intent == INVENTORY:
            await _bg_inventory_request(channel_id_str, message_id_str, sender_user_id_str, content)
        else:
            await _bg_ems_ask(channel_id_str, sender_user_id_str, content, intent)
```

**Done when**: `python3 -m py_compile server/app/werk/routes/channels_ws.py` is clean. No automated test for this file's WS handlers (integration-only, DB+WS-backed) — verified in the manual end-to-end step.

### 7e. Update `server/app/werk/CLAUDE.md`'s import-count paragraph

The doc currently states "9 files / 44 import statements" reaching nine named things. Add `matcha.services.inventory.*` as a tenth reached target and bump the file/import counts by however many new lazy imports `channels_ws.py` gained in steps 7a-7d (count them: 7a adds 0 new imports (inline flag helpers, no imports), 7b/7c each add ~6 lazy imports inside their own function bodies, 7d adds 1 more inside the mention-fork lazy import block — recount exactly by grepping `from app.matcha.services.inventory` in the final file and update the sentence with the real number).

---

## Step 8 — Huume thread-agent bridge (cheap parts only)

### 8a. `server/app/matcha/services/huume/tools.py`

Quote of line 26 area (`LOOKUP_TOPICS` tuple) — add `"inventory"` as a new entry. Quote of line 35:
```python
SHOW_RECORD_TYPES = ("incident", "er_case", "employee", "credential", "discipline", "ems_event")
```
Change to:
```python
SHOW_RECORD_TYPES = ("incident", "er_case", "employee", "credential", "discipline", "ems_event", "inventory_item")
```
Update the `lookup_context`/`show_record` tool descriptions (the `types.Schema(..., enum=[...])` blocks near lines 98/115) to mention inventory in their free-text description strings — no schema shape change, just documentation text so the model knows the option exists.

### 8b. `server/app/matcha/services/huume/onboarding_skill.py`

Topic→feature map — quote of line 128 area:
```python
    "events": "ems",
```
Add a sibling entry:
```python
    "inventory": "inventory",
```

New topic branch — model is the `"events"` branch at lines 376-418. Insert a new `if topic == "inventory":` branch (anywhere among the other `if topic == ...:` blocks, e.g. right after the `"events"` block ends at line 418, before `if topic == "pto_leave":` at line 419):

```python
        if topic == "inventory":
            rows = await conn.fetch(
                """
                SELECT it.id, it.name, it.current_quantity, it.unit, o.status AS order_status
                FROM inventory_items it
                LEFT JOIN inventory_orders o ON o.item_id = it.id AND o.status = 'queued'
                WHERE it.company_id = $1 AND it.archived_at IS NULL
                ORDER BY it.name LIMIT 21
                """,
                company_id,
            )
            truncated = len(rows) > 20
            note = "Open a full item with show_record('inventory_item', ...)."
            if truncated:
                note += " More items exist than shown — narrow with query."
            return {
                "topic": "inventory",
                "items": [dict(r) for r in rows[:20]],
                "note": note,
            }
```

### 8c. `server/app/matcha/services/huume/record_view.py`

`RECORD_REQUIRED_FEATURE` (line 33) — add a sibling entry:
```python
    "inventory_item": "inventory",
```

New batch model builder (pattern: `_model_ems_events_batch` at line 263) — add near the other `_model_*_batch` functions:
```python
async def _model_inventory_items_batch(conn, company_id: UUID, rids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT it.id, it.name, it.current_quantity, it.unit, o.status AS order_status
        FROM inventory_items it LEFT JOIN inventory_orders o ON o.item_id = it.id AND o.status = 'queued'
        WHERE it.company_id = $1 AND it.id = ANY($2)
        """,
        company_id, rids,
    )
    return {r["id"]: dict(r) for r in rows}
```
Register it in `_MODEL_BATCH_BUILDERS` (~line 309):
```python
    "inventory_item": _model_inventory_items_batch,
```

New view builder (pattern: `_build_ems_event_view` at line 693) — add near the other `_build_*_view` functions:
```python
async def _build_inventory_item_view(conn, company_id: UUID, rid: UUID) -> Optional[dict[str, Any]]:
    item = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1 AND company_id = $2", rid, company_id)
    if item is None:
        return None
    movement_rows = await conn.fetch(
        "SELECT * FROM inventory_movements WHERE item_id = $1 ORDER BY created_at DESC LIMIT 10", rid,
    )
    order = await conn.fetchrow(
        "SELECT * FROM inventory_orders WHERE item_id = $1 AND status = 'queued'", rid,
    )
    return {
        "title": item["name"],
        "chips": [item["unit"] or "unit", f"{item['current_quantity']} in stock" if item["current_quantity"] is not None else "count unknown"],
        "meta": {"created_at": item["created_at"].isoformat()},
        "sections": [
            {"heading": "Recent movements", "rows": [
                {"kind": m["kind"], "quantity": str(m["quantity"]), "narrative": m["narrative"],
                 "created_at": m["created_at"].isoformat()} for m in movement_rows
            ]},
        ] + ([{"heading": "Open order", "rows": [{"quantity": str(order["quantity"]), "status": order["status"]}]}] if order else []),
        "link": f"/work/inventory/{item['id']}",
    }
```
Register it in `_VIEW_BUILDERS` (~line 769):
```python
    "inventory_item": _build_inventory_item_view,
```

**Done when**: `py_compile` clean on the 3 edited huume files; if a `test_record_type_parity`-style test exists (`grep -rn "SHOW_RECORD_TYPES.*RECORD_REQUIRED_FEATURE\|record.*parity" server/tests/`), run it and confirm it still passes with `inventory_item` present in all 4 collections.

---

## Step 9 — Frontend

### 9a. `client/src/work/api/inventory.ts` (full contents, pattern-matched to `work/api/events.ts`)

```ts
import { api } from '../../api/client'

export type MovementKind = 'out' | 'in' | 'stockout' | 'adjust'
export type OrderStatus = 'queued' | 'ordered' | 'received' | 'cancelled'

export interface InventoryOrder {
  id: string
  item_id: string
  status: OrderStatus
  suggested_quantity: number | null
  quantity: number | null
  suggestion: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface InventoryItem {
  id: string
  name: string
  unit: string | null
  current_quantity: number | null
  low_stock_threshold: number | null
  auto_created: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
  open_order: InventoryOrder | null
}

export interface InventoryMovement {
  id: string
  item_id: string
  kind: MovementKind
  quantity: number | null
  quantity_delta: number | null
  quantity_estimated: boolean
  note: string | null
  narrative: string
  created_at: string
}

export async function listItems(includeArchived = false) {
  return api.get<{ items: InventoryItem[] }>(`/inventory/items?include_archived=${includeArchived}`)
}

export async function createItem(body: { name: string; unit?: string; current_quantity?: number; low_stock_threshold?: number }) {
  return api.post<InventoryItem>('/inventory/items', body)
}

export async function getItem(itemId: string) {
  return api.get<{ item: InventoryItem; movements: InventoryMovement[] }>(`/inventory/items/${itemId}`)
}

export async function patchItem(itemId: string, body: Partial<{ name: string; unit: string; low_stock_threshold: number; set_quantity: number; archived: boolean }>) {
  return api.put<InventoryItem>(`/inventory/items/${itemId}`, body)
}

export async function listMovements(params: { itemId?: string; limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams()
  if (params.itemId) qs.set('item_id', params.itemId)
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.offset) qs.set('offset', String(params.offset))
  return api.get<{ movements: InventoryMovement[] }>(`/inventory/movements?${qs}`)
}

export async function listOrders(status?: OrderStatus) {
  const qs = status ? `?status=${status}` : ''
  return api.get<{ orders: InventoryOrder[] }>(`/inventory/orders${qs}`)
}

export async function createOrder(body: { item_id: string; quantity?: number }) {
  return api.post<InventoryOrder>('/inventory/orders', body)
}

export async function approveOrder(orderId: string, quantity?: number) {
  return api.post<InventoryOrder>(`/inventory/orders/${orderId}/approve`, { quantity })
}

export async function receiveOrder(orderId: string, quantity?: number) {
  return api.post<InventoryOrder>(`/inventory/orders/${orderId}/receive`, { quantity })
}

export async function cancelOrder(orderId: string) {
  return api.post<InventoryOrder>(`/inventory/orders/${orderId}/cancel`, {})
}

export async function listSuggestions() {
  return api.get<Record<string, { name: string; suggested_quantity: number | null; confidence: string }>>('/inventory/suggestions')
}
```

Note: check `api/client.ts`'s exact method signatures (`api.get<T>(path, opts?)` vs positional body args) before finalizing — the code above assumes `api.post<T>(path, body)` / `api.put<T>(path, body)` shape; adjust to match whatever the real client exports (confirmed pattern in root client CLAUDE.md: `api.get<T>`, `api.post`, `api.put`, `api.delete`).

### 9b. Component skeletons (JSX structure only — style to match neighboring `work/components/` files)

`client/src/work/components/inventory/ItemTable.tsx` — props `{ items: InventoryItem[] }`; a table with columns Name / Unit / Count / Threshold / Open Order badge; row click navigates to `inventory/:itemId`.

`client/src/work/components/inventory/ItemDetail.tsx` — props `{ itemId: string }`; fetches via `getItem`, renders item header + a movement ledger list + an "Adjust count" inline form (calls `patchItem(itemId, {set_quantity})`) + an "Archive" button.

`client/src/work/components/inventory/OrderQueue.tsx` — props `{ orders: InventoryOrder[] }`; per-row Approve/Receive/Cancel buttons wired to `approveOrder`/`receiveOrder`/`cancelOrder`; shows the suggestion basis line ("~X/day, ran out every ~N days") from `order.suggestion`.

### 9c. `client/src/work/pages/InventoryHub.tsx` (skeleton — model is `EventsHub.tsx`'s top-level shape: tab/list state + fetch-on-mount + render list or detail based on a route param)

```tsx
import { useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { listItems, listOrders, type InventoryItem, type InventoryOrder } from '../api/inventory'
import ItemTable from '../components/inventory/ItemTable'
import ItemDetail from '../components/inventory/ItemDetail'
import OrderQueue from '../components/inventory/OrderQueue'

export default function InventoryHub() {
  const { itemId } = useParams()
  const [items, setItems] = useState<InventoryItem[]>([])
  const [orders, setOrders] = useState<InventoryOrder[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([listItems(), listOrders('queued')])
      .then(([i, o]) => { setItems(i.items); setOrders(o.orders) })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return null
  if (itemId) return <ItemDetail itemId={itemId} />

  return (
    <div className="space-y-6">
      <OrderQueue orders={orders} />
      <ItemTable items={items} />
    </div>
  )
}
```

(Named `InventoryHub.tsx`, NOT `InventoryPanel.tsx` — that name is taken by the thread-mode CSV panel component.)

### 9d. `client/src/work/routes/WorkRouteTree.tsx` — insert a sibling FeatureGate block

Quote of the existing ems block (verified verbatim this session):
```tsx
          <Route
            element={
              <FeatureGate feature="ems" label="Events">
                <Outlet />
              </FeatureGate>
            }
          >
            <Route path="events" element={<EventsHub />} />
            <Route path="events/:eventId" element={<EventsHub />} />
            <Route path="protocol" element={<ProtocolPage />} />
          </Route>
```
Insert immediately after (still inside the same parent `<Route>` / `<Routes>` block this snippet lives in):
```tsx
          <Route
            element={
              <FeatureGate feature="inventory" label="Inventory">
                <Outlet />
              </FeatureGate>
            }
          >
            <Route path="inventory" element={<InventoryHub />} />
            <Route path="inventory/:itemId" element={<InventoryHub />} />
          </Route>
```
Add `import InventoryHub from '../pages/InventoryHub'` near the file's other page imports.

### 9e. Sidebar entries — BOTH `WorkSidebar.tsx` AND `WerkLiteSidebar.tsx`

`client/src/work/components/shell/WorkSidebar.tsx` — quote of line 36:
```tsx
  const showEvents = canReviewEvents(me?.user?.role) && hasFeature('ems')
```
Add immediately after:
```tsx
  const showInventory = hasFeature('inventory')
```
Then in the JSX near the Events entry (lines 222-243 region), add a sibling nav item:
```tsx
{showInventory && (
  <button onClick={() => navigate(`${base}/inventory`)}
          className={location.pathname.startsWith(`${base}/inventory`) ? /* active class, match Events' pattern */ '' : ''}>
    Inventory
  </button>
)}
```
(Match the exact className/structure of the surrounding Events button — read lines 222-243 in full before writing this, the snippet above is a structural placeholder.)

`client/src/work/components/shell/WerkLiteSidebar.tsx` — same pattern at its own line 34 (`showEvents`), add the identical `showInventory` const and nav entry.

### 9f. `client/src/data/featureCatalog.ts`

Line 54 (`inventory: 'Inventory',`) — this is already correct as a label map entry. No change needed; the original plan's "reword description" note was wrong (there is no description field here, just a label). Confirm the label reads fine as-is.

**Done when**: `cd client && npx tsc -p tsconfig.app.json --noEmit` is clean. (NOT bare `npx tsc --noEmit` — that checks nothing, see client/CLAUDE.md.)

---

## Step 10 — Docs

- `server/app/matcha/services/inventory/CLAUDE.md` (new file) — full feature spec: flag row content (copy the Step 2 comment), intake flow narrative (mirrors this doc's Context section), claim columns (`confirm_message_id` on orders, `clarify_message_id` on movements), invariants (bias-to-LOG fallback + EMS delegation, OSHA dual-write, append-only ledger + the single clarify-amendment exception, one-queued-order-per-item, NULL-count semantics), and an explicit sentence addressing the root CLAUDE.md's pilots-grounding rule: *"Inventory data is operational stock, not compliance/legal evidence — no grounded pilot (Legal/Broker/Handbook/HR/Analysis) cites it in v1. Revisit only if a future pilot's domain genuinely needs stock-on-hand facts."*
- Root `CLAUDE.md`: add an `inventory` row to the Feature Flags table (one-liner + `→ full spec:` pointer to the new CLAUDE.md above) + a Key Modules bullet + a subtree-docs table row pointing at the new file.
- `server/CLAUDE.md` symbol map: add an "Inventory (channel stock tracking)" section listing the intent constant, the two WS handlers, the service package, and the router — same format as the existing EMS symbol-map section.
- `server/app/werk/CLAUDE.md`: apply the exact edit described in Step 7e (recount the real import number, don't guess).

---

## Execution checklist (do in order; each step's "done when" gates the next)

1. Step 1 — migration + bootstrap. `python3 -m py_compile` on all 3 files.
2. Step 2 — feature flag. `grep -c '"inventory"' server/app/core/feature_flags.py` → 2.
3. Step 3 — pure modules + tests. `cd server && python3 -m pytest tests/inventory/ -v` → all green.
4. Step 4 — intent routing. `cd server && python3 -m pytest tests/ems/ -v` → all green (new + pre-existing).
5. Step 5 — extraction + DB services. `py_compile` clean; no automated test (DB/Gemini-backed).
6. Step 6 — models + router. `py_compile` clean.
7. Step 7 — WS wiring. `py_compile` clean on `channels_ws.py`; update `werk/CLAUDE.md`'s import count.
8. Step 8 — Huume bridge. `py_compile` clean; parity test (if present) green.
9. Step 9 — frontend. `cd client && npx tsc -p tsconfig.app.json --noEmit` → clean.
10. Step 10 — docs.
11. Manual end-to-end (user, on dev — NOT automated): enable `matcha_work` + `inventory` (+ `ems` for fallback coverage) on a test company. Post both product example messages in a channel. Verify: the 📦 pills appear, items auto-create, replying "confirm" on an order pill approves it, `/work/inventory` shows the ledger + order queue, replying a number to a "how many?" pill amends the movement. Test data uses RFC 2606 reserved domains only (`@example.com`/`*.test`/`*.invalid`) per root CLAUDE.md.

Scope ends at commit (+ push if on a `claude/...` cloud-session branch) — no build/deploy, no `alembic upgrade` against any database, per root CLAUDE.md's cloud-session and DB-safety rules. The user runs `./scripts/migrate-dev.sh` themselves.

## Risks / open questions (unchanged from prior draft, still open)

- Multiple alembic heads repo-wide; re-verify `ems02` is still a leaf immediately before applying `inventory01` if significant time has passed since this doc was written (2026-08-02).
- "low on" folded into the STOCKOUT regex pattern group (extractor's `kind` field distinguishes true stockout from low-but-not-empty; only `kind == "stockout"` zeroes the count) — drop the "low on"/"running low on" alternatives from `_INVENTORY_PATTERNS` if this proves too aggressive in practice (one-line regex edit in Step 4a).
- One clarify question per pill: v1 arms the clarify flow only when exactly one extracted line lacks a quantity. Multiple simultaneous unknowns are recorded as estimated with no clarify question (documented in Step 7b's movement branch).
- Item merge (near-duplicate items surviving fuzzy match) and unit conversion ("2 cases" vs "48 cookies") are out of scope for v1 — document as known limitations in the Step 10 CLAUDE.md.
