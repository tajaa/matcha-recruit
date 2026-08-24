# Inventory Waste, Shrinkage & Closed-Loop Predictive Par (`inventory_waste`)

## Context

Food/inventory waste and shrinkage runs 4–10% of revenue for perishable-stock
operators. Matcha Ops already has the substrate — append-only ledger, POS sales
depletion, physical audits with unit+dollar variance, a deterministic forecast
engine — but **cannot name a single dollar of waste**, and its par levels are dead
constants.

Five concrete defects, each verified in the code:

1. **No `waste` kind.** `inventory_movements.kind` CHECK is
   `('out','in','stockout','adjust','sale')` (`sales01_sales_intake.py:110-113`).
   Spoilage, trim, comps, breakage and theft are all indistinguishable `out` rows.
2. **No perishability.** `shelf_life_days` has **zero hits repo-wide**.
   `reorder.py:10` hardcodes `DEFAULT_COVER_DAYS = 14`, so the system orders 14
   days of cover for lettuce that dies in 5. That constant is the over-ordering bug.
3. **Recipe/BOM is built but unreachable.** `inventory_sales_mappings.kind` already
   allows `'recipe'`, `inventory_sales_mapping_lines.quantity_per_sale` already
   carries per-component quantities, `sales_mappings.upsert_mapping` already
   validates it, `sales_commit` already aggregates across components, and
   `SalesMappingsPanel.tsx:28` hardcodes `kind: 'direct'`. **A 70-line frontend file
   is the only thing standing between you and theoretical usage.**
4. **Audit variance is computed then thrown away.** `variance_rollup`
   (`expected.py:46`) returns `biggest_over[:5]`/`biggest_short[:5]`; only
   `variance_units`/`variance_value` persist (`audits.py:145-151`). No per-item
   trend exists.
5. **Par is an open loop.** `calculate_replenishment` computes
   `target_quantity = lead_demand + safety_demand` (`forecast.py:142-146`) on every
   run — that *is* the textbook par formula — and discards it.
   `inventory_items.low_stock_threshold` has exactly **two writers**, both
   human-typed (`routes/inventory.py:90` create, `:160-162` patch), and exactly
   **one SQL reader** (`matcha_ops_admin.py:89-90`, a count on an internal admin
   screen). **Nothing alerts on it. No task, no email, no pill, no notification.**
   `reorder.suggest_order` does not read it either — the two reorder brains are
   fully disjoint.

**Outcome:** a manager sees "waste was 6.2% of revenue last week, $4,180 — 61%
spoilage, concentrated in produce; these 5 items bleed every week; your lettuce par
is 2.3× what your shelf life supports", and the par retunes itself within
guardrails instead of sitting where someone typed it in March.

**Decisions taken (user, this session):** all four waste levers **plus** the
closed-loop predictive par; new `inventory_waste` flag; generic shrinkage
vocabulary with food-tuned defaults; all four agentic scopes; **Gemini fleet, not
OpenAI** (repo has zero OpenAI surface — no dep, no key, no client factory, no
pricing rows — and no OpenAI model named "Luna" exists to wire to).

**Standing invariant:** deterministic math is the source of truth. Every dollar and
every par number is computed in Python/SQL. The model narrates, ranks and proposes;
it never does arithmetic and never writes unconfirmed. Same contract
`forecast_ai.py` and `huume/inventory_skill.py` already hold.

**Branch:** currently on `main`, clean tree. Ask before branching (per your global
rule) — do not create one unprompted.

---

## Two pre-existing bugs this work must not step on

**A. `amend_movement_quantity` sign map** — `movements.py:224`:
```python
sign = -1 if old["kind"] == "out" else 1
```
A `waste` movement amended through the clarify path (`_bg_inventory_reply`,
`channels_ws.py:1069`) would get `sign = +1` and **add** stock. Fix as part of
Phase 1:
```python
_NEGATIVE_KINDS = frozenset({"out", "waste"})
sign = -1 if old["kind"] in _NEGATIVE_KINDS else 1
```

**B. `forecast_ai._coerce_adjustments` emits the wrong source** —
`forecast_ai.py:57` hardcodes `"source": "manual"`, while the DDL
(`invforecast01:76`) and `services/inventory/CLAUDE.md` both say AI suggestions
must store as `'ai_accepted'`. Pre-existing, out of scope, **but the par loop
inherits it** — an AI-driven multiplier that moves a par would be journaled as a
human decision. Fix it in Phase 4 with an explicit note, or leave it and record the
discrepancy; do not let it pass unremarked.

---

## Phase 1 — Waste becomes a first-class ledger fact

### Migration `invwaste01` (`down_revision = "pos01"` — inventory-chain head)

Repo has ~49 branched heads; `pos01` is the inventory branch tip
(`pos01_square_inventory_sales.py`, `down_revision = "invforecast01"`).

```sql
-- Widen kind. Copy sales01:107-113's drop-and-re-add.
ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_kind_check;
ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_kind_check
  CHECK (kind IN ('out','in','stockout','adjust','sale','waste'));

ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS waste_reason VARCHAR(30);
ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_waste_reason_check
  CHECK (waste_reason IS NULL OR (kind='waste' AND waste_reason IN (
    'spoilage','expired','prep_error','overproduction',
    'breakage','contamination','theft','comp','recall','unknown')));
CREATE INDEX IF NOT EXISTS idx_inventory_movements_waste
  ON inventory_movements (company_id, created_at DESC) WHERE kind='waste';

ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS category VARCHAR(60);
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS shelf_life_days INT
  CHECK (shelf_life_days IS NULL OR shelf_life_days BETWEEN 1 AND 3650);
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS yield_pct NUMERIC
  CHECK (yield_pct IS NULL OR (yield_pct > 0 AND yield_pct <= 1));
```

`yield_pct` is the trim/prep loss factor (whole romaine ≈ 0.75 usable). Without it
theoretical usage systematically under-reads and every item falsely looks
over-portioned.

`downgrade()` reverts the CHECK to the 5-kind list and drops the three columns +
the `waste_reason` constraint and index.

**Mirror in `server/app/database/bootstrap/inventory.py` — two places, both
required:** the inline DDL at **`:159`** and the explicit re-add at **`:174-177`**.
Bootstrap/Alembic drift is a silent 500 on any fresh DB.

### Feature flag

- `server/app/core/feature_flags.py` — add `"inventory_waste": False` near `:378`;
  add `"inventory_waste": ("inventory",)` to `FEATURE_REQUIRES` near `:797`.
  Sibling pattern confirmed: `"inventory": ("matcha_ops",)`,
  `"sales_intake": ("inventory",)`.
  **Do not** require `sales_intake`/`inventory_forecasting` at flag level — waste
  capture and rollup work without POS data. Per-endpoint `require_all_features`
  adds those where genuinely needed, exactly as `/audit/sheet` is `sales_intake`-gated
  inside the `inventory` router.
- `client/src/data/featureCatalog.ts` — label near `:67`, requires near `:116`:
  ```ts
  inventory_waste: 'Ops — Inventory Waste & Shrinkage (waste log, variance, predictive par) — needs Inventory too',
  // …
  inventory_waste: ['inventory'],
  ```
- Use the `/add-feature-flag` skill so sidebar/gate/CLAUDE.md-row wiring is not
  hand-rolled.

### New package `server/app/matcha/services/inventory/waste/`

**`reasons.py`**
```python
WASTE_REASONS: tuple[str, ...] = (
    "spoilage", "expired", "prep_error", "overproduction",
    "breakage", "contamination", "theft", "comp", "recall", "unknown",
)
FOOD_DEFAULT_REASONS: tuple[str, ...] = ("spoilage", "expired", "prep_error", "overproduction")
UNEXPLAINED_REASONS: frozenset[str] = frozenset({"theft", "unknown"})
CHAT_FORBIDDEN_REASONS: frozenset[str] = frozenset({"theft"})

def label(reason: str) -> str: ...
def is_unexplained(reason: str | None) -> bool: ...
def coerce_chat_reason(reason: str | None) -> str: ...
    """theft → 'unknown'; unrecognised → 'unknown'; else passthrough."""
```

**`rollup.py`**
```python
async def waste_rollup(
    conn, *, company_id: UUID, location_id: Optional[UUID],
    start: date, end: date, group_by: Literal["reason", "category", "item"] = "reason",
) -> dict:
    """{'total_units': Decimal, 'total_value': Decimal|None,
        'unexplained_value': Decimal|None, 'groups': [{'key','label','units','value','pct'}],
        'revenue': Decimal|None, 'waste_pct_of_revenue': Decimal|None}"""

async def waste_revenue(conn, *, company_id, location_id, start, end) -> Optional[Decimal]:
    """SUM(sl.gross_sales) over inventory_sales_lines joined to
    inventory_sales_imports WHERE status='committed' AND business_date in range.
    None when sales_intake is off or no committed imports — the caller then
    reports absolute dollars and omits the percentage rather than inventing one."""
```

### Four wiring points a new kind touches

Missing any one makes waste silently vanish from a report.

**1. `movements.py:150-161` delta chain** — insert after the `in` branch (`:158`):
```python
        elif kind == "waste" and quantity is not None:
            delta = -abs(float(quantity))
```
`record_movements` gains `waste_reason` per `lines` element (element shape is today
`{item_id, quantity, estimated}`, docstring `:145`). Both INSERTs grow one column:
Branch A (`:163-176`, sales path) `$13 → $14`; **Branch B (`:177-190`) `$12 → $13`
— that is the branch the chat/waste path hits.** Refuse a non-null `waste_reason`
on any other kind (belt-and-braces with the CHECK). No change needed to the
post-insert item-count UPDATE (`:191-210`) — `waste` falls into the
`elif delta is not None` arm.

**2. `expected.py:19-30` bucket CTE** — add to the `buckets` SELECT:
```sql
SUM(CASE WHEN m.kind='waste' THEN ABS(COALESCE(m.quantity_delta,0)) ELSE 0 END) AS wasted,
```
and `COALESCE(k.wasted,0) AS wasted` to the final projection (`:31-34`).
Add `wasted: Decimal = Decimal("0")` to `AuditSheetRow`
(`models/inventory.py:184-192`) and to the `/audit/sheet` row builder.
**Without this the audit sheet's "since your last count" breakdown stops adding up.**

**3. `reorder.py:32` consumption filter** — stays `kind in ("out", "sale")`.
**Waste must not count as demand**, or you reorder what you throw away. Add the
comment saying so, and return a new `waste_in_window` key so the confirm pill can
read "14 suggested; 6 wasted last cycle". Note `suggest_order` has **four**
production callsites, not two — `routes/inventory.py:283`,
`channels_ws.py:1037`, `ems/channel_agent.py:318`, `huume/inventory_skill.py:154`
— all using the identical `[dict(r) for r in history_rows], datetime.now(timezone.utc)`
shape. A new return key is additive and safe for all four.

**4. `models/inventory.py:8`** —
`MovementKind = Literal["out","in","stockout","adjust","sale","waste"]`.
Add `waste_reason: Optional[str] = None` to `MovementOut` (`:57-67`).
Mirror in `client/src/work/api/inventory.ts:5`.

### Chat capture (`@huume`)

Nobody opens a form for a wilted lettuce.

**`extraction.py`:**
- `_VALID_KINDS` (`:78`) → add `"waste"`.
- `_FALLBACK_RESULT` (`:51-56`) → add `"waste_reason": None`. **Required** —
  `_coerce_result` (`:89-92`) merges `{**_FALLBACK_RESULT, **parsed}`, so a key
  absent from the fallback is not guaranteed present.
- Prompt template (`:20-43`, braces are doubled for `.format()`) — extend the
  `"kind"` union and add a rule line:
  > `"waste"` for stock destroyed or discarded rather than used or sold ("threw out
  > 3 lbs of spinach, went slimy", "dropped a tray of glasses"). Set `"waste_reason"`
  > to one of spoilage|expired|prep_error|overproduction|breakage|contamination|comp|recall|unknown.
  > Never report theft — if the message alleges theft, use "unknown".

**`channels_ws.py`** — branch map is `movement` L907-943, `receipt` L945-959,
`return` L961-1016, catch-all `else` L1018-1053. Insert `elif kind == "waste":`
**between L943 and L945**, modelled on the `movement` branch verbatim, with these
deltas:
- `movements_service.find_item(..., existing=item_rows)` — **match-only, never
  `find_or_create_item`**. Same rule as the `return` branch (`:973`): you do not
  mint a catalog row from "we threw out some stuff". Unmatched → steer pill.
- `record_movements(..., kind="waste", waste_reason=reasons.coerce_chat_reason(...))`.
- Add `from app.matcha.services.inventory import reasons` to the local import block
  at `:836-844`.
- Reuse the prefetched catalog `item_rows` from `:880`.

**New `pills.waste_pill(item_name, qty, remaining, reason, estimated) -> str`**,
modelled on `movement_pill` (`pills.py:12-21`), using `_fmt_qty` and `_safe_name`.
**First character must be `\U0001F4E6` (📦), never 🚨** — `systemContent.tsx`'s
`isUrgentSystemContent` sniffs char 0. When the reason was coerced from theft, the
pill says so and points at the Inventory page.

**`rules.py:31-41`** — widen `stage` from `Literal["movement","approve_order"]` to
include `"waste"`; `waste` follows the `movement` bar (any channel member, requires
the `inventory` feature) **plus** `features.get("inventory_waste")`.

### Provenance invariant, extended

`waste` is a first-hand observed loss, same class as `out`/`adjust`: free-form chat
is allowed with **no confirm step**, because it only ever *decrements* and therefore
cannot fabricate stock — the same reasoning that already permits free-form `out`
while refusing bare-assertion `in`. One deliberate exception:
**`waste_reason='theft'` is coerced to `'unknown'` on every chat path**
(`reasons.coerce_chat_reason`, enforced again in `_validate_inventory_movement`).
A personnel accusation must not be minted by an extraction model from a Slack-style
aside; the page and Huume-thread paths accept `theft` from an explicit human choice.
Document beside the existing `kind='in'` invariant in
`services/inventory/CLAUDE.md`.

### Phase 1 tests — `server/tests/inventory/test_waste_reasons.py`

Style matches `test_reorder.py` / `test_forecast.py`: plain pytest functions,
absolute imports, no fixtures, no DB.

| Test | Assertion |
|---|---|
| `test_reasons_match_db_check` | `WASTE_REASONS` == the tuple parsed out of `invwaste01`'s CHECK source text. Guards drift between Python and SQL. |
| `test_chat_reason_coerces_theft` | `coerce_chat_reason("theft") == "unknown"` |
| `test_chat_reason_coerces_unknown_garbage` | `coerce_chat_reason("shrinkage!!") == "unknown"` |
| `test_chat_reason_passthrough` | `coerce_chat_reason("spoilage") == "spoilage"` |
| `test_is_unexplained` | `theft`/`unknown` True; `spoilage` False; `None` False |

`test_movements.py` additions (pure-arg tests over the delta chain):
`test_waste_delta_is_negative`, `test_waste_reason_rejected_on_non_waste_kind`,
`test_amend_waste_uses_negative_sign` (pins bug A).

---

## Phase 2 — Theoretical vs actual (the shrinkage number)

### Recipe mapping UI — highest ROI change in the plan

`client/src/work/components/inventory/SalesMappingsPanel.tsx` is **70 lines**.
Current state: `mappings, soldName, itemId, quantity, saving`;
`save()` at `:22-35` posts `kind: 'direct'` with a one-element `components` array.
The render at `:63` **already** maps over `mapping.components` and joins them — the
read path handles recipes today.

Change: replace `itemId`/`quantity` with
`components: {item_id: string; quantity_per_sale: string; unit: string}[]`, add a
kind toggle (`direct | recipe | ignore`), add/remove component rows, and post
`kind` + the full array. Validation mirrors the server
(`sales_mappings.upsert_mapping`): `direct` needs exactly 1, `recipe` needs ≥1,
`ignore` needs 0. **No new endpoint** — `POST /inventory/sales/mappings` and
`SalesMappingUpsert` (`models/inventory.py:139-144`) already accept it.
UI imports: `import { Button, Select, useToast } from '../../../components/ui'`;
`const toast = useToast()` then `toast(msg, 'error' | 'success')`.

### `waste/usage.py`

```python
async def theoretical_usage(
    conn, *, company_id: UUID, location_id: Optional[UUID],
    item_ids: list[UUID], start: date, end: date,
) -> dict[UUID, Decimal]:
    """Reuse the 5-way join in forecast_store._forecast_inputs:189-202 verbatim
    (inventory_sales_lines → _imports → _mappings → _mapping_lines → items,
    si.status='committed' AND sl.status='mapped'), SUM(sl.quantity *
    ml.quantity_per_sale), then divide by items.yield_pct where set."""

async def actual_usage(
    conn, *, company_id: UUID, item_ids: list[UUID], start: date, end: date,
) -> dict[UUID, Decimal]:
    """Ledger-derived: ABS(quantity_delta) over kind IN ('sale','out','waste')."""

def usage_variance(
    theoretical: Optional[Decimal], actual: Optional[Decimal], unit_cost: Optional[Decimal],
) -> dict:
    """PURE. {'variance_units','variance_value','variance_pct','direction'}
    direction: 'over_use' | 'under_use' | 'even' | 'unknown'."""
```

Sustained `actual > theoretical` on a recipe item **with** matching waste rows is
spoilage; **without** them it is over-portioning. That distinction is the entire
portion-consistency feature and it needs no AI.

Lift the `DISTINCT ON (item_id) … kind='adjust'` baseline CTE out of
`expected.py:14-18` into a shared `waste/_baselines.py` helper rather than copying
it a third time.

### Persist per-line audit variance

```sql
CREATE TABLE IF NOT EXISTS inventory_audit_lines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES inventory_audit_runs(id) ON DELETE CASCADE,
  item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
  expected NUMERIC, counted NUMERIC NOT NULL, variance NUMERIC,
  unit_cost NUMERIC, variance_value NUMERIC,
  theoretical_usage NUMERIC, actual_usage NUMERIC, usage_variance NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_audit_lines_item
  ON inventory_audit_lines (item_id, created_at DESC);
```
The `item_id`-leading index is what makes "which item bleeds every week"
answerable — note `inventory_forecast_lines` lacks the equivalent and can only be
queried run-first.

`audits.commit_audit_lines` (`audits.py:27-30`) already computes everything needed:
`before` map at `:63-68`, `variance_lines` at `:69-73`, `variance_rollup` at `:74`.
Write the per-line row inside the **existing** per-line `async with
conn.transaction()` (`:92`), immediately after `adjust_item_count` (`:128`). Keep
the per-line-fails-alone shape — do not wrap the batch. The two
`inventory_audit_runs` rollup scalars stay for backward compatibility.

### Phase 2 tests — `server/tests/inventory/test_waste_usage.py`

| Test | Assertion |
|---|---|
| `test_usage_variance_over_use` | theoretical 100, actual 130, cost 2 → units 30, value 60, pct 0.3, `'over_use'` |
| `test_usage_variance_even` | equal → 0 / `'even'` |
| `test_usage_variance_no_cost` | `unit_cost=None` → `variance_value is None`, units still returned |
| `test_usage_variance_unknown` | either side `None` → `'unknown'`, all values `None` |
| `test_usage_variance_zero_theoretical` | theoretical 0, actual 5 → `variance_pct is None` (no divide-by-zero), units 5 |

---

## Phase 3 — Perishable-aware par, lots, expiry

### The forecast cap

`forecast.calculate_replenishment` (`forecast.py:107-117`) is pure — no DB, no
model. Add `shelf_life_days: Optional[int] = None`. Today `target_quantity` is
computed at `:142-146` and is a raw `Decimal` (**not** case-pack rounded — only
`suggested_quantity` goes through `_rounded_order_quantity`). Insert after `:146`:

```python
    shelf_cap = None
    shelf_life_capped = False
    if shelf_life_days:
        window = demand[lead_time_days:lead_time_days + shelf_life_days]
        shelf_cap = sum(window, Decimal("0")) or sum(demand[:shelf_life_days], Decimal("0"))
        if shelf_cap < target_quantity:
            target_quantity = shelf_cap
            shelf_life_capped = True
```

**Order matters: cap the target, then let `_rounded_order_quantity` apply case-pack**
— otherwise a case pack silently re-inflates past the cap. Return two new keys,
`shelf_cap` and `shelf_life_capped` (10 → 12 keys; `forecast_item` 13 → 15). Surface
in the UI when the minimum case pack alone exceeds shelf-life demand — that is a
supplier conversation, not a math error.

Second reorder brain: `reorder.suggest_order` gains an optional
`shelf_life_days` param and uses `min(DEFAULT_COVER_DAYS, shelf_life_days or
DEFAULT_COVER_DAYS)` as `cover_days`. Leave the two engines separate — reconciling
them is a real refactor — but record the duplication in
`services/inventory/CLAUDE.md`.

Thread the column: add `i.shelf_life_days` (and `i.low_stock_threshold`,
`i.par_source`, `i.category`) to `_forecast_inputs`'s items SELECT projection
(`forecast_store.py:165-182`). **No `GROUP BY` change needed** — `GROUP BY i.id, r.id`
at `:180` covers them by functional dependency on the PK.

### Lots

```sql
CREATE TABLE IF NOT EXISTS inventory_lots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
  location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
  received_movement_id UUID REFERENCES inventory_movements(id) ON DELETE SET NULL,
  lot_code VARCHAR(80), received_on DATE NOT NULL, expires_on DATE,
  quantity_received NUMERIC NOT NULL CHECK (quantity_received > 0),
  quantity_remaining NUMERIC NOT NULL CHECK (quantity_remaining >= 0),
  status VARCHAR(20) NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','depleted','discarded','expired')),
  unit_cost NUMERIC, created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inventory_lots_expiry
  ON inventory_lots (company_id, expires_on) WHERE status='open' AND expires_on IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_lots_receipt
  ON inventory_lots (received_movement_id, item_id) WHERE received_movement_id IS NOT NULL;
```

**Invariant — state it in the CLAUDE.md or a future reader will "fix" it and break
the ledger:** lots are an **advisory FEFO overlay, never a second source of truth**.
`inventory_items.current_quantity` stays authoritative. Lots answer "how old is
what's on the shelf" and attribute spoilage; they are permitted to drift, nothing
reconciles them, and nothing blocks on them.

**`waste/lots.py`**
```python
async def record_lot(conn, *, company_id, item_id, location_id, received_movement_id,
                     quantity, received_on: date, expires_on: Optional[date],
                     lot_code: Optional[str], unit_cost, created_by) -> Optional[dict]
    """Best-effort. Derives expires_on = received_on + shelf_life_days when the
    invoice carries no date and the item has a shelf life. Never raises into the
    caller's movement write."""

async def consume_fefo(conn, *, company_id, item_id, quantity) -> list[dict]
    """Decrement quantity_remaining earliest-expires_on first, NULLS LAST.
    Advisory; never touches inventory_items.current_quantity."""

async def expiring_lots(conn, *, company_id, location_id, within_days: int) -> list[dict]

def spoilage_risk_score(*, quantity_remaining: Decimal, days_to_expiry: Optional[int],
                        average_daily_demand: Decimal) -> dict
    """PURE, DETERMINISTIC. days_of_cover = qty / add (None when add == 0).
    at_risk_quantity = max(qty - add * days_to_expiry, 0).
    {'score': Decimal 0..1, 'days_of_cover', 'at_risk_quantity', 'basis'}
    The model RANKS and NARRATES these; it never computes them."""
```

Call `record_lot` from `orders.mark_received` (`orders.py:99`) and
`receipts.commit_receipt_lines` (`receipts.py:359`) — both already inside a
transaction with the `in` movement.

`POST /inventory/lots/{id}/discard` writes a `waste` movement with
`reason='expired'` **and** closes the lot in **one** transaction — the two must not
be separately failable.

---

## Phase 4 — Closed-loop predictive par

This is the piece that turns "intelligent order suggestion" into a par system that
actually tracks demand and shelf life instead of sitting where someone typed it.

### Schema

```sql
-- A human-typed par is sacred. Enrolment into auto is explicit.
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS par_source VARCHAR(10)
  NOT NULL DEFAULT 'manual' CHECK (par_source IN ('manual','auto'));

ALTER TABLE inventory_forecast_settings
  ADD COLUMN IF NOT EXISTS par_auto_apply BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventory_forecast_settings
  ADD COLUMN IF NOT EXISTS par_max_drift_pct NUMERIC NOT NULL DEFAULT 0.5
    CHECK (par_max_drift_pct > 0 AND par_max_drift_pct <= 5);

ALTER TABLE inventory_forecast_lines ADD COLUMN IF NOT EXISTS recommended_par NUMERIC;
ALTER TABLE inventory_forecast_lines ADD COLUMN IF NOT EXISTS par_basis VARCHAR(24);
ALTER TABLE inventory_forecast_lines ADD COLUMN IF NOT EXISTS current_par NUMERIC;
ALTER TABLE inventory_forecast_lines ADD COLUMN IF NOT EXISTS shelf_cap_quantity NUMERIC;
ALTER TABLE inventory_forecast_lines ADD COLUMN IF NOT EXISTS shelf_life_capped
  BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS inventory_par_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
  run_id UUID REFERENCES inventory_forecast_runs(id) ON DELETE SET NULL,
  previous_par NUMERIC, new_par NUMERIC NOT NULL,
  par_basis VARCHAR(24), drift_pct NUMERIC,
  source VARCHAR(10) NOT NULL CHECK (source IN ('auto','manual','huume')),
  reason VARCHAR(200),
  changed_by UUID REFERENCES users(id) ON DELETE SET NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inventory_par_history_item
  ON inventory_par_history (item_id, changed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_par_history_run_item
  ON inventory_par_history (run_id, item_id) WHERE run_id IS NOT NULL;
```

`uniq_inventory_par_history_run_item` makes auto-apply **idempotent per run** —
essential because the sweep retries (`task_acks_late=True`, `max_retries=3`).
Without the journal you cannot answer "why is my par 40 now" and cannot roll back
a bad sweep.

### `waste/par.py` — pure, no DB, no model

```python
PAR_BASIS = Literal["demand", "shelf_life", "structural_deficit", "no_demand", "insufficient"]

def recommend_par(
    *, lead_demand: Decimal, safety_demand: Decimal, daily_demand: list[Decimal],
    lead_time_days: int, shelf_life_days: Optional[int] = None, status: str = "ready",
) -> dict:
    """{'recommended_par': Decimal|None, 'par_basis': str, 'demand_par': Decimal,
        'shelf_cap': Decimal|None, 'structural_deficit': bool}

    demand_par = lead_demand + safety_demand  (forecast.py:142-146's target_quantity)
    shelf_cap  = sum(daily_demand[lead_time_days : lead_time_days+shelf_life_days])
                 falling back to sum(daily_demand[:shelf_life_days]) when that
                 window lands past the horizon.
    shelf_cap < demand_par            -> basis 'shelf_life',          par = shelf_cap
    shelf_cap < lead_demand           -> basis 'structural_deficit',  par = shelf_cap,
                                         structural_deficit=True
                                         (you cannot hold enough to cover lead time
                                          before it spoils — the fix is more frequent,
                                          smaller deliveries, not a bigger par)
    status != 'ready'                 -> par = None, basis 'no_demand'|'insufficient'
    """

def par_drift_pct(current_par: Optional[Decimal], recommended_par: Optional[Decimal]) -> Optional[Decimal]:
    """abs(new - old) / old. None when either is None or current_par == 0."""

def should_auto_apply(
    *, current_par: Optional[Decimal], recommended_par: Optional[Decimal],
    par_source: str, status: str, confidence: str, max_drift_pct: Decimal,
) -> tuple[bool, str]:
    """DETERMINISTIC gate, no model input. Guards in order:
       recommended_par is None      -> (False, 'no_recommendation')
       status != 'ready'            -> (False, 'status_not_ready')
       confidence == 'low'          -> (False, 'low_confidence')
       par_source != 'auto'         -> (False, 'manual_par_pinned')
       current_par is None          -> (True,  'first_par')
       drift > max_drift_pct        -> (False, 'drift_exceeds_bound')
       else                         -> (True,  'within_bound')"""

def par_exceeds_shelf_capacity(par: Decimal, shelf_cap: Optional[Decimal]) -> bool:
```

Rationale for the drift bound: a 15% par shift is routine seasonality; a 300% shift
is a data error — a bad sales import, a newly-built recipe mapping — and must not
silently retune the whole store. Out-of-bound items are **proposed**, never applied.

### `waste/par_store.py` — the only writer

```python
async def apply_par_recommendations(
    conn, *, company_id: UUID, run_id: UUID, user_id: Optional[UUID],
    mode: Literal["auto", "manual", "huume"],
    item_ids: Optional[list[UUID]] = None,
) -> dict:
    """{'considered': int, 'applied': int,
        'skipped': [{'item_id','reason'}], 'proposed': [{'item_id','current_par',
        'recommended_par','par_basis','drift_pct','reason'}]}

    Reads inventory_forecast_lines JOIN inventory_items for the run, plus
    forecast settings for par_max_drift_pct.
    mode='auto'  : full should_auto_apply gate.
    mode='manual'/'huume' with explicit item_ids: the manager is overriding, so
      guards 4 (manual_par_pinned) and 6 (drift bound) are skipped — guards 1-3
      still hold, and par_exceeds_shelf_capacity still warns.
    Per item, inside `async with conn.transaction()` (per-line-fails-alone, same
    shape as commit_audit_lines:92 / commit_receipt_lines):
      UPDATE inventory_items SET low_stock_threshold=$2, par_source=$3,
             updated_at=NOW() WHERE id=$1 AND company_id=$4
      INSERT INTO inventory_par_history (...) ON CONFLICT (run_id, item_id)
             WHERE run_id IS NOT NULL DO NOTHING

async def enroll_items_in_auto_par(conn, *, company_id, item_ids, enrolled: bool) -> int
    """Sets par_source. Note PATCH /inventory/items/{id} cannot null
    low_stock_threshold (routes/inventory.py:160-162 guards on `is not None`), so
    un-enrolling flips par_source rather than clearing the number."""

async def par_history(conn, *, company_id, item_id, limit: int = 50) -> list[dict]
```

### Where the loop closes

1. **`build_preview` (`forecast_store.py:215-267`)** calls `recommend_par(...)` per
   item and adds `recommended_par`, `par_basis`, `current_par`, `shelf_cap_quantity`,
   `shelf_life_capped`, `structural_deficit` to the line dict at `:247-259`.
   Everything not in the exclusion set `{"item_id","name","unit","location_id","unit_cost"}`
   lands in the `calculation` JSONB automatically (`:324-327`) — free audit trail.
2. **`create_run` (`:270-347`)** persists them: the INSERT at `:328-346` grows from
   17 columns / `$1..$17` to 22 / `$1..$22`. The write loop is already inside
   `async with conn.transaction():` opened at **`:287`** — that transaction is the
   natural boundary. **`create_run` writes recommendations only; it never touches
   `inventory_items`.** Recommendation ≠ application.
3. **`POST /inventory/forecast/runs/{run_id}/apply-par`** — explicit apply, body
   `{item_ids?: UUID[], mode: 'manual'}`. **Declare it after `/runs/latest` (`:185`)**
   — that route is declared before `/runs/{run_id}` (`:198`) and order is
   load-bearing; a new `/runs/{...}` path added above it would shadow.
4. **Worker `inventory_par_sweep`** — build a run, then `apply_par_recommendations(mode="auto")`.
5. **Huume staged `waste_par_change`** — see below.

### The "predictive" claim, honestly earned

An accepted AI demand multiplier already lands in `inventory_forecast_overrides`
and already flows `forecast_daily_demand` → `calculate_replenishment` →
`recommend_par`. **So an accepted AI forecast adjustment moves the par with zero
new AI surface.** That chain is the predictive par; everything else here is
guardrails around it. (This is where bug B bites: `_coerce_adjustments` stamps
`source='manual'`, so an AI-driven par move would be journaled as a human decision.
Fix it here.)

`waste/par_ai.py:propose_par_exceptions(...)` mirrors
`forecast_ai.propose_forecast_adjustments`'s contract **verbatim** — same
`genai_env_client()`, `model=GEMINI_FLASH`, `types.GenerateContentConfig(
temperature=0.2, response_mime_type="application/json")`, `asyncio.wait_for(...,
timeout=60)`, bare `except Exception` → `logger.warning`, never raises, returns
`{"available": bool, "model": ..., ...}`. Scope: **only** items where the
deterministic recommendation is suppressed (`status != 'ready'`) but a real signal
exists (repeated stockouts, repeated waste). Output is a bounded multiplier, capped
count, clamped range, and it lands **only** through the staged `waste_par_change`
path — never a direct write.

Rate limiting lives in the route, not the service — copy
`routes/inventory_forecast.py:151-153`'s three-key pattern with new keys
`inventory_par_ai_burst` (5/60), `inventory_par_ai` (40/3600),
`inventory_par_ai_company` (120/3600).
`check_rate_limit(ip: str, action: str, limit: int, window: int) -> None`
(`core/services/redis_cache.py:131`, raises `HTTPException(429)`).

### Phase 4 tests — `server/tests/inventory/test_waste_par.py`

Pure functions, no DB, `Decimal` throughout (matches `test_forecast.py`).

| Test | Setup → assertion |
|---|---|
| `test_par_equals_lead_plus_safety_without_shelf_life` | lead 20, safety 10, no shelf life → par 30, basis `'demand'`, `shelf_cap is None` |
| `test_shelf_life_caps_par` | lead 20, safety 10, demand 2/day, shelf_life 5, lead_time 2 → shelf_cap 10 → par 10, basis `'shelf_life'` |
| `test_shelf_cap_below_lead_demand_is_structural_deficit` | lead_demand 20, shelf_cap 8 → basis `'structural_deficit'`, `structural_deficit is True`, par 8 |
| `test_shelf_window_past_horizon_falls_back` | `lead_time_days` beyond `len(daily_demand)` → falls back to `demand[:shelf_life_days]`, no IndexError |
| `test_no_demand_status_yields_no_par` | `status='no_demand'` → `recommended_par is None`, basis `'no_demand'` |
| `test_insufficient_history_yields_no_par` | `status='insufficient_history'` → `None`, basis `'insufficient'` |
| `test_drift_pct_basic` | current 10, recommended 13 → `Decimal('0.3')` |
| `test_drift_pct_none_when_current_zero` | current 0 → `None` (no divide-by-zero) |
| `test_auto_apply_blocks_manual_pinned_par` | `par_source='manual'` → `(False, 'manual_par_pinned')` |
| `test_auto_apply_blocks_low_confidence` | `confidence='low'` → `(False, 'low_confidence')` |
| `test_auto_apply_blocks_excess_drift` | current 10, rec 40, max 0.5 → `(False, 'drift_exceeds_bound')` |
| `test_auto_apply_allows_within_bound` | current 10, rec 13, max 0.5, `par_source='auto'`, ready, medium → `(True, 'within_bound')` |
| `test_auto_apply_first_par_when_none` | `current_par=None`, `par_source='auto'` → `(True, 'first_par')` |
| `test_auto_apply_blocks_not_ready` | `status='count_required'` → `(False, 'status_not_ready')` |

`test_forecast.py` additions:
`test_shelf_life_caps_target_quantity`,
`test_case_pack_cannot_re_inflate_past_shelf_cap`,
`test_shelf_life_capped_flag_false_when_uncapped`.

---

## Phase 5 — Workers

**`server/app/workers/tasks/inventory_expiry_sweep.py`** — copy
`schedule_daily_digest.py` + `services/scheduling/daily_digest.py` wholesale; it is
already the exact shape (per-location, tz-aware via `ZoneInfo(l.timezone)`,
claim → send → release-on-transient-failure).

- Gate: `scheduler_enabled(conn, "inventory_expiry_sweep", default=False)` —
  **fail-closed**, per `workers/utils.py:65`'s docstring rule for anything that
  sends or spends.
- Feature gate in **Python via `merge_company_features(...)`**, not raw SQL on
  `enabled_features` — `inventory` is tier-overlaid, so the SQL form misses tenants.
  (`pos_sales_sync.py:41` is the reference for both halves.)
- Dedupe table:
  ```sql
  CREATE TABLE IF NOT EXISTS inventory_waste_alert_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
    alert_date DATE NOT NULL,
    alert_kind VARCHAR(30) NOT NULL CHECK (alert_kind IN ('expiring','waste_spike','par_applied')),
    recipient_email VARCHAR(255), channel_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );
  CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_waste_alert_deliveries
    ON inventory_waste_alert_deliveries
       (company_id, location_id, alert_date, alert_kind, recipient_email)
    NULLS NOT DISTINCT;
  ```
- Delivery: in-channel via
  `services/huume_code/chat.py:post_as_huume(company_id, channel_id, content)` to
  the channel bound to that store (`channels.location_id`); email fallback via
  `get_email_service().send_email(...)` when no channel is bound. Pill text from
  `pills.py`, leading 📦.

**`inventory_waste_digest`** (weekly waste % of revenue + top bleeders) and
**`inventory_par_sweep`** follow the identical shape. `inventory_par_sweep`
additionally reports what it changed — a par system that retunes silently is one
nobody trusts.

**Register each in all three places** or it never fires:
1. `server/app/workers/celery_app.py:62-72` — module path in `include=[...]`
2. `server/app/workers/celery_app.py:154-202` —
   `("<task_key>", "app.workers.tasks.<module>", "<callable>")` in `_SCHEDULED_TASKS`
   (dispatch is `@worker_ready` at `:205`; no celery-beat — hourly container restart
   re-fires it, so any cadence longer than that is the task's own `last_run_at` job)
3. Migration seed, copying `sales01:143-151`:
```sql
INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
VALUES ('inventory_expiry_sweep', 'Inventory expiry sweep',
        'Nudge stores about lots expiring soon', FALSE, 200)
ON CONFLICT (task_key) DO NOTHING
```
with matching `DELETE FROM scheduler_settings WHERE task_key=...` in `downgrade()`.

---

## Phase 6 — The agentic layer

Model ids come from `core/services/model_catalog.py` (`GEMINI_FLASH =
"gemini-3.7-flash"`, `GEMINI_FLASH_LITE`) — **never re-literaled**;
`tests/test_model_catalog.py` enforces that.

**1. Waste analyst (read-only, grounded)** — `waste/agent.py`, copying
`services/ems/channel_agent.py:answer_channel_question`'s bounded tool-calling loop
and `channel_grounding.run_topic_lookup`'s dispatch registry. Tools all read-only,
all returning deterministic rollups: `waste_by_reason`, `usage_variance_for_item`,
`expiring_soon`, `par_history_for_item`, `item_history`. **Citation gate: every
dollar and every par number in the answer must trace to a tool result.** The model
composes sentences; `rollup.py` and `par.py` compute.

**2. Predictive spoilage risk** — `waste/par_ai.py` + the existing
`forecast_ai.py`, contracts as specified in Phase 4.

**3. Staged fix proposals** — new `services/huume/waste_skill.py` following
`inventory_skill.py`'s shape. Registration touches **seven** points:

| File:line | Change |
|---|---|
| `huume/actions.py:112-128` `_HUUME_ACTION_REQUIRED_FEATURE` | `"waste_movement": "inventory_waste"`, `"waste_par_change": "inventory_waste"`, `"waste_recipe_correction": "inventory_waste"` |
| `huume/actions.py:172-175` `_INVENTORY_ACTIONS` frozenset | add the three new types |
| `huume/actions.py:176` `_INVENTORY_MOVEMENT_KINDS` | `frozenset({"out","stockout","adjust","waste"})` |
| `huume/actions.py:338-345` validate dispatch if-chain | add three `if action_type == …: return _validate_…` |
| `huume/actions.py:627+` | new `_validate_waste_movement` (enforces the reason vocabulary; `theft` allowed here — explicit human choice, unlike chat), `_validate_waste_par_change` (clamps to `par_exceeds_shelf_capacity`), `_validate_waste_recipe_correction` |
| `huume/agent.py:417` | field whitelists for the new action types |
| `huume/tools.py:687` region | Gemini `types.Schema` tool declarations |
| `huume/inventory_skill.py:60-72` executor dispatch | `if atype == "waste_par_change": …` → `par_store.apply_par_recommendations(mode="huume", item_ids=[…])` |

All confirm-first. `waste_recipe_correction` writes through
`sales_mappings.upsert_mapping` — **the same writer the page calls** — so a
chat-originated and a page-originated mapping are indistinguishable rows.

**4. Chat capture** — Phase 1.

### Grounded-pilots corpus

`services/inventory/CLAUDE.md:33` records a deliberate decision to skip pilot corpus
wiring, and names the exact condition for revisiting: *"a food-safety or
loss-prevention angle"*. **This feature is that angle.** Wire waste + variance
records into Analysis Pilot's corpus in the same PR as Phase 2, per the root
CLAUDE.md rule, and rewrite that paragraph rather than leaving it contradicting the
code.

---

## Routes

**Extend `routes/inventory.py`:** `InventoryItemPatch` (`models/inventory.py:48-54`)
and `InventoryItemCreate` (`:39-45`) gain `category`, `shelf_life_days`, `yield_pct`,
`par_source`; the dynamic UPDATE at `routes/inventory.py:127-172` gains the matching
`if body.X is not None` blocks.

**New `routes/inventory_waste.py`** (use the `/new-router` skill), mounted in
`routes/__init__.py` beside the existing block at `:164-169`:
```python
matcha_router.include_router(
    inventory_waste_router, prefix="/inventory/waste", tags=["inventory-waste"],
    dependencies=[Depends(require_all_features("matcha_ops", "inventory", "inventory_waste"))],
)
```

| Method | Path | Extra gate |
|---|---|---|
| POST | `/inventory/waste` | — |
| GET | `/inventory/waste/rollup?start&end&location_id&group_by` | — |
| GET | `/inventory/waste/variance?start&end&location_id` | `sales_intake` |
| GET | `/inventory/waste/lots?item_id&expiring_within_days` | — |
| POST | `/inventory/waste/lots/{lot_id}/discard` | — |
| GET | `/inventory/waste/par/history?item_id` | — |
| POST | `/inventory/waste/par/enroll` | — |
| POST | `/inventory/waste/ask` | rate-limited |

Plus on the forecast router (**after `:185`**):
`POST /inventory/forecast/runs/{run_id}/apply-par`, `POST /inventory/forecast/par-ai`.

Conventions: `require_admin_or_client` + `get_client_company_id`; never trust a
client-supplied `company_id`; location ownership uses the verbatim idiom
`… AND is_active IS NOT FALSE AND is_company_wide=FALSE`. Note the forecast router
has **no `response_model=` on any route** — it returns bare dicts; match that.

---

## Frontend

`api` helper is `import { api } from '../../api/client'` with
`api.get/post/patch/delete<T>(path, body)`.

- **`components/inventory/SalesMappingsPanel.tsx`** — recipe mode (Phase 2). 70
  lines today; the read path at `:63` already renders multi-component.
- **New `pages/InventoryWaste.tsx`** — waste % of revenue headline, by-reason and
  by-category breakdown, bleeders table, theoretical-vs-actual, expiring-soon, par
  drift list, agent ask box. **Load the `dataviz` skill before writing any chart
  code here.**
- **New `components/inventory/ParPanel.tsx`** — per item: current par, recommended
  par, basis badge (`demand` / `shelf-life capped` / `structural deficit`), drift %,
  auto-enrol toggle, and the `inventory_par_history` timeline. The basis badge is
  what stops "the number changed and nobody knows why".
- `components/inventory/ItemDetail.tsx` — category / shelf-life / yield / par-source
  fields + lot list. Existing `stockColor()` at `:180`.
- `pages/InventoryAudit.tsx` — per-line usage variance beside count variance.
- `pages/InventoryForecast.tsx` — `shelf_life_capped` badge; add the five par fields
  to the `ForecastLine` type (`api/inventory.ts:511-532`).
- `api/inventory.ts` — `MovementKind` union at `:5` gains `'waste'`; new functions
  matching existing style; `patchItem`'s body type (`:104-115`) gains the new fields.
- `components/inventory/ItemTable.tsx` — the `:59` amber "Review stock" cell now
  means something, since par is maintained. Consider a par-source dot.
- **Register the route in all three trees** — `ops/routes/OpsRoutes.tsx:44-55`,
  `work/routes/WorkRouteTree.tsx:69-72`, `work/routes/WerkLiteRoutes.tsx:91-94` —
  under `<FeatureGate feature="inventory_waste">`, and add sidebar entries to
  `ops/components/OpsSidebar.tsx` (Operations group), `work/components/shell/WorkSidebar.tsx:277`,
  and `WorkSidebar/CollapsedRail.tsx:97`. Missing a tree is the classic regression.

---

## Verification

**Unit tests** — `server/tests/inventory/`, one file per service module (matches the
existing 14). New: `test_waste_reasons.py`, `test_waste_usage.py`,
`test_waste_par.py`, `test_waste_rollup.py`, `test_waste_lots.py`. Extend
`test_forecast.py`, `test_movements.py`, `test_reorder.py`. Style: plain pytest
functions, absolute imports, `Decimal`, no fixtures, no DB, no Gemini.
```bash
cd server && ./venv/bin/python -m pytest tests/inventory/ -q
```

**Migration** — commit before applying anywhere (dev included; same revision id with
different bytes is silent drift). Rehearse:
```bash
cd server && MIGRATE_REHEARSAL=1 DATABASE_URL=<dev> ./venv/bin/python -m alembic upgrade heads
```
Elapsed time is the signal. Then `./scripts/migrate-dev.sh`. **Prod needs explicit
approval** — `./scripts/migrate-prod.sh`, never a hand-run `alembic upgrade`. All
DDL here is set-based (`ALTER`/`CREATE`), no row loops.

**Typecheck** — `cd client && npx tsc -p tsconfig.app.json --noEmit`.
The bare `npx tsc --noEmit` checks **nothing** (root tsconfig is `files: []` +
project refs → always exits 0).

**End-to-end on dev** (`./scripts/dev-remote.sh`; frontend already on `:5174` — do
**not** clean up with `pkill -f "vite --port"`, that regex matches the real
dev-remote process; track your own PID):

1. Enable `inventory_waste` + `sales_intake` + `inventory_forecasting`. Set an item
   `shelf_life_days=5`, `category='produce'`, `yield_pct=0.75`, `unit_cost=3.20`.
2. Build a **recipe** mapping (one menu item → 3 ingredients) in the new panel.
   Assert `inventory_sales_mapping_lines` has 3 rows and mapping `kind='recipe'`.
3. Commit a sales import → assert one aggregated `sale` movement per component.
4. Channel: `@huume tossed 3 lbs of romaine, went slimy` → assert a `waste`
   movement, `waste_reason='spoilage'`, 📦 pill, and **no new catalog row** if the
   name was unmatched.
5. `@huume someone stole a case of steaks` → assert `waste_reason='unknown'` and a
   pill steering to the page.
6. Reply a number to a quantity-clarify waste pill → assert `current_quantity`
   went **down**, not up (pins bug A).
7. Run an audit → assert `inventory_audit_lines` rows carry theoretical + actual.
8. Run a forecast → assert `shelf_life_capped=true`, `par_basis='shelf_life'`, and
   `recommended_par` < the uncapped `lead_demand + safety_demand`.
9. `POST /inventory/forecast/runs/{id}/apply-par` on an item with
   `par_source='manual'` and no `item_ids` → assert **skipped**, reason
   `manual_par_pinned`, `low_stock_threshold` unchanged.
10. Enrol the item (`par_source='auto'`), re-apply → assert `low_stock_threshold`
    updated **and** one `inventory_par_history` row. Re-run the same apply → assert
    still exactly one history row (idempotency via `uniq_inventory_par_history_run_item`).
11. `GET /inventory/waste/rollup` → assert `waste_pct_of_revenue` non-zero and the
    dollar total matches hand arithmetic over the seeded rows.
12. Ask the analyst a question → assert every dollar in the answer appears in a tool
    result.

**Workers** — leave all three `scheduler_settings` rows disabled. Test by invoking
each task function directly against dev. Do not enable in prod as part of this work.

**Test data** — RFC 2606 reserved domains only (`@example.com`, `*.test`).

---

## Sequencing

| Phase | Ships | Why here |
|---|---|---|
| 1 | waste kind + reasons + chat capture + rollup (+ bug A) | Everything downstream needs history; start it accruing day one |
| 2 | recipe UI + theoretical-vs-actual + per-line audit + pilot corpus | Backend already done; unlocks the shrinkage number |
| 3 | shelf life + lots + forecast cap | Stops over-ordering at source |
| 4 | closed-loop predictive par (+ bug B) | Needs Phase 3's shelf-life cap to bound the par |
| 5 | workers (expiry / digest / par sweep) | Needs 1–4's outputs to have anything to say |
| 6 | agentic layer | Needs 1–5's deterministic numbers as grounding |

Phases 1–4 each deliver standalone value. Phase 6 is narration and proposal over
numbers that are already correct without it.

---

## Note on the model choice

Targeting the existing Gemini fleet, per your answer. Recording why, since it came
up: there is no OpenAI model named "Luna" in any catalog I can verify, and this repo
has no OpenAI surface at all — no dependency, no `OPENAI_API_KEY`, no client
factory, no rows in `model_pricing.MODEL_PRICING` or `ai_usage.PRICING`. Adding a
second provider is a real project: your own `ai-vertex-baa-cutover` finding is that
~44 call sites construct `genai.Client(...)` directly, so there is no provider seam
to slot into today. If you want a specific OpenAI model later, give me the real id
and it becomes its own PR ahead of this one — not a parameter inside it.
