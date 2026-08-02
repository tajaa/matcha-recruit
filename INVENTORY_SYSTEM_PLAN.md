# Inventory system via @huume in /work channels

## Context

We want an inventory system usable from the event-management channels: "@huume we gifted some
Cherry Farms cookies to Elizabeth our manager" auto-deducts stock; "@huume we ran out of salads
again" records a stockout, runs deterministic pattern math over the item's depletion history,
suggests an order amount, and stages a pending order the manager approves by replying **confirm**
in-channel. Confirmed product decisions: items **auto-create on first mention** (fuzzy-match
first), orders are **internal records** (queued → ordered → received; receiving restocks), and v1
ships a **full /work Inventory page** (items, ledger, order queue).

Architecture reality: the `@huume` channel surface is NOT the Huume thread agent — it's the EMS
one-shot dispatch in `server/app/werk/routes/channels_ws.py`, routed by the pure regex classifier
`server/app/matcha/services/ems/intent.py` (biased to LOG; unmatched text becomes an EMS event).
Inventory becomes a new intent + a new `services/inventory/` package, mirroring how SCHEDULE was
added: request handler shaped like `_bg_schedule_request` (`channels_ws.py:381`), confirm-by-reply
shaped like `_bg_schedule_reply` (`channels_ws.py:453`), clarify loop shaped like EMS
(`event_intake.py`).

Verified facts pinned to:
- `"inventory": False` **already exists** in `DEFAULT_COMPANY_FEATURES`
  (`server/app/core/feature_flags.py:340`) inside the "no require_feature gate anywhere — parity
  no-op" comment block (:336-341); `client/src/data/featureCatalog.ts:54` lists it. We make it
  real, not add it.
- Current leaf of the ems alembic chain is `ems02` → new migration rev `inventory01`,
  `down_revision="ems02"` (repo tolerates multiple heads with a docstring note, precedent
  `ems01_event_management.py:46`; re-point if something lands on `ems02` first).
- **No pg_trgm** (deliberately avoided on RDS — `zzzzcappe25` docstring). Fuzzy match = Python
  `difflib.get_close_matches` (precedent `core/routes/admin/_shared.py:672`, cutoff 0.72).
- `parse_confirm_reply(text) -> Literal["confirm","cancel","other"]` (pure, anchored
  start-to-end) at `services/scheduling/schedule_chat_rules.py:368` — reuse directly.
  `ScheduleVerdict` (:35, `kind: Literal["proceed","refuse"], reason`) is the verdict shape to copy.
- `check_rate_limit(ip, action, limit, window)` at `core/services/redis_cache.py:120` (raises
  HTTPException over limit — callers catch and skip silently, `channels_ws.py:416-419`).
- `mean` / `coefficient_of_variation` at `services/pilots/analysis_packs/base.py:139,144` — pure
  stdlib, safe import.
- Pill plumbing: `_insert_system_message(conn, channel_id_str, content)` (`channels_ws.py:139`),
  `_system_message_payload(channel_id_str, sys_row)` (:115), `broadcast_system_message(channel_id,
  message)` (:1730). EMS question convention: `question_text(confirmation, question)` /
  `extract_question(pill_content)` (`event_intake.py:332,339`) — shape-copy, don't import (the
  suffix strings are EMS's wire format).
- `werk/CLAUDE.md` documents the werk→matcha.services import edge count (9 files / 44 imports,
  recounted 2026-08-01) and requires it stay accurate — our new lazy imports in `channels_ws.py`
  must bump that count in the doc.
- Frontend name `InventoryPanel.tsx` is taken (thread-mode CSV panel) → page is `InventoryHub.tsx`.

## Key design decisions

1. **Unstated quantity** ("some cookies"): record immediately as `quantity=1,
   quantity_estimated=true` (auto-deduct is the explicit requirement) AND arm an EMS-style
   clarify question on the pill ("How many? Reply with a number."). A numeric reply amends the
   flagged movement in place (`amended_by/amended_at`, only while `quantity_estimated`) — the one
   sanctioned edit on an otherwise append-only ledger. `clarify_rounds` capped at 2.
2. **`current_quantity NUMERIC NULL`** = unknown (auto-created items start NULL). Deduction
   against NULL stays NULL; `stockout` force-sets 0; `adjust` establishes a baseline.
3. **Order lifecycle**: `queued` (staged) → `ordered` (confirm-reply or page approve) →
   `received` (page action writes the restock `in` movement) + `cancelled`. Partial unique index
   = one queued order per item; repeat stockouts re-point the confirm pill at the existing order.
4. **Injury-adjacent safety** (bias-to-LOG is a product invariant): (a) narrow `^`-anchored verb
   patterns — bare "gave"/"used" never match; (b) deterministic OSHA-keyword check
   (`event_intake.fallback_classification(content)["urgency"] == "osha"`) before inventory
   handling — on hit ALSO fire `_bg_ems_intake` (dual-write); (c) non-actionable/failed Gemini
   extraction falls back to `_bg_ems_intake` wholesale; `inventory` off but `ems` on → delegate
   to EMS intake.
5. **Grounded-pilots corpus wiring skipped** — ops stock data, not compliance/legal evidence;
   one-line justification in the service CLAUDE.md (root CLAUDE.md Code Modification Rule
   addressed explicitly).

## Steps (build order; each compiles/tests alone)

### 1. Migration + bootstrap (authored, NOT run)

`server/alembic/versions/inventory01_channel_inventory.py` — `revision = "inventory01"`,
`down_revision = "ems02"`, docstring noting multi-head tolerance. Set-based SQL only; real
`downgrade()` = 3 DROPs in FK order (orders → movements → items). Mirror file
`server/app/database/bootstrap/inventory.py` with `async def create_inventory(conn)` (pattern:
`bootstrap/ems.py:create_ems`), wired into `bootstrap/__init__.py` after `create_ems`.

```sql
CREATE TABLE inventory_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    normalized_name VARCHAR(200) NOT NULL,
    unit VARCHAR(50),
    current_quantity NUMERIC,            -- NULL = unknown
    low_stock_threshold NUMERIC,
    auto_created BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uniq_inventory_items_name
    ON inventory_items (company_id, normalized_name) WHERE archived_at IS NULL;

CREATE TABLE inventory_movements (        -- append-only ledger
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
    source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
    recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('out','in','stockout','adjust')),
    quantity NUMERIC,                     -- magnitude; NULL for stockout
    quantity_delta NUMERIC,               -- signed effect applied; NULL when count unknown
    quantity_estimated BOOLEAN NOT NULL DEFAULT FALSE,
    note TEXT,                            -- "gifted to Elizabeth (manager)"
    narrative TEXT NOT NULL,              -- original message, mention-stripped
    clarify_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
    clarify_rounds SMALLINT NOT NULL DEFAULT 0,
    amended_by UUID REFERENCES users(id) ON DELETE SET NULL,
    amended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uniq_inventory_movements_message   -- WS replay dedupe, per-item
    ON inventory_movements (source_message_id, item_id) WHERE source_message_id IS NOT NULL;
CREATE UNIQUE INDEX uniq_inventory_movements_clarify   -- atomic reply-claim
    ON inventory_movements (clarify_message_id) WHERE clarify_message_id IS NOT NULL;
CREATE INDEX idx_inventory_movements_company ON inventory_movements (company_id, created_at DESC);
CREATE INDEX idx_inventory_movements_item ON inventory_movements (item_id, created_at DESC);

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
    suggestion JSONB,                     -- math audit: daily_rate, intervals, cover_days,
                                          -- confidence, n_samples
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
);
CREATE UNIQUE INDEX uniq_inventory_orders_confirm
    ON inventory_orders (confirm_message_id) WHERE confirm_message_id IS NOT NULL;
CREATE UNIQUE INDEX uniq_inventory_orders_open        -- one pending order per item
    ON inventory_orders (item_id) WHERE status = 'queued';
CREATE INDEX idx_inventory_orders_company ON inventory_orders (company_id, status, created_at DESC);
```

### 2. Feature flag

`server/app/core/feature_flags.py`: move `"inventory": False` out of the no-op comment block
(:336-341) into a real entry with a spec comment (channel-driven inventory via @huume; gates
`/inventory` router + /work Inventory page; NOT bundled). Add to `FEATURE_REQUIRES` (~:740):
`"inventory": ("matcha_work",)` — same reasoning comment as `ems`/`huume`.

### 3. Pure service modules + tests (no DB, no Gemini)

New package `server/app/matcha/services/inventory/` (`__init__.py` empty, absolute imports):

**`matching.py`**
```python
def normalize_name(name: str) -> str
    # lower, strip punctuation, collapse whitespace, naive trailing-'s' de-pluralize
def best_match(name: str, existing: list[dict]) -> Optional[dict]
    # existing rows have keys id/name/normalized_name.
    # exact normalized -> substring containment (either direction, len>=4 guard)
    # -> difflib.get_close_matches(cutoff=0.75) over normalized names
```

**`reorder.py`** (imports `mean`, `coefficient_of_variation` from
`app.matcha.services.pilots.analysis_packs.base`)
```python
DEFAULT_COVER_DAYS = 14
LOOKBACK_DAYS = 90

def suggest_order(movements: list[dict], now: datetime) -> Optional[dict]
    # movements: chronological dicts {kind, quantity, quantity_delta, created_at}
    # daily_rate = sum('out' magnitudes in lookback) / observed_days
    # stockout_intervals = gaps between consecutive 'stockout' rows
    # suggested_quantity = ceil(daily_rate * DEFAULT_COVER_DAYS),
    #   fallback: last 'in' receipt qty, else None
    # confidence: 'high'|'medium'|'low' from n_samples + CV(stockout_intervals)
    # returns None when history too thin (<2 'out' movements AND no prior receipt)
    # -> {suggested_quantity, daily_rate, avg_stockout_interval_days,
    #     cover_days, confidence, n_samples}
```

**`rules.py`** (verdict dataclass copied from `schedule_chat_rules.ScheduleVerdict:35`)
```python
@dataclass(frozen=True)
class InventoryVerdict:
    kind: Literal["proceed", "refuse"]
    reason: Optional[str] = None
    @property
    def ok(self) -> bool: ...

def evaluate_inventory_action(*, role: Optional[str], features: dict,
                              stage: Literal["movement", "approve_order"]) -> InventoryVerdict
    # movement: any channel member with `inventory` in merged features
    # approve_order: role in {"admin", "client"} + `inventory`

def parse_quantity_reply(text: str) -> Optional[Decimal]
    # first bare number ("12", "about 12", "12 boxes") + small number words
    # ("a dozen"->12, "one"..."twenty"); None otherwise
# parse_confirm_reply: import from app.matcha.services.scheduling.schedule_chat_rules
```

**`pills.py`** — all builders return str; first char **📦 never 🚨** (`systemContent.tsx` sniffs
char 0 for urgent-red):
```python
_QUESTION_SUFFIX = " Reply to this message to answer."   # own wire format, not EMS's

def movement_pill(item_name, qty, remaining, note, estimated: bool) -> str
    # "📦 Deducted 1 × Cherry Farms Cookies — gifted to Elizabeth. 12 left."
    # remaining None -> "count unknown — set it on the Inventory page."
def quantity_question(pill: str) -> str          # appends "How many? ..." + suffix
def extract_question(pill_content: str) -> str   # mirror event_intake.py:339 shape
def stockout_pill(item_name, suggestion: Optional[dict], order_qty) -> str
    # "📦 Salads marked out of stock. You've run out ~every 9 days; suggest
    #  ordering 42. Reply **confirm** to queue it, a number to change the
    #  amount, or **cancel**."
def receipt_pill(item_name, qty, new_count) -> str
def order_confirmed_pill(item_name, qty) -> str
def order_cancelled_pill(item_name) -> str
def rearm_pill() -> str                          # unparseable reply to an order pill
```

**Tests** — new `server/tests/inventory/` (`__init__.py` + 4 files, pure, no DB, pattern
`tests/ems/`):
- `test_matching.py`: exact match; case/punctuation-insensitive ("cherry farms cookies!" ==
  "Cherry Farms Cookies"); plural/singular ("salads"→"salad"); containment ("cookies" matches
  "Cherry Farms Cookies"); difflib typo ("cheery farms cookies"); no-match returns None;
  empty-existing returns None.
- `test_reorder.py`: steady consumption → rate*14 rounded up; thin history (<2 outs, no receipt)
  → None; stockout-interval stats ("ran out again" cadence → avg_stockout_interval_days);
  fallback to last receipt qty when rate unknown; confidence tiers; NULL-quantity movements
  excluded from rate.
- `test_rules.py`: employee can record movement, cannot approve order; client/admin approve;
  missing `inventory` flag refuses both; `parse_quantity_reply` table ("12", "about 12",
  "a dozen", "12 boxes", "yes"→None, ""→None).
- `test_pills.py`: 📦 is char 0 on every builder; never 🚨; `extract_question(quantity_question(p))`
  round-trip; unknown-count phrasing.

### 4. Intent routing

`services/ems/intent.py` — add after `SCHEDULE = "schedule"` (:30):
```python
INVENTORY = "inventory"

_INVENTORY_PATTERNS = (
    # OUT — deliberately NOT bare "gave"/"used": "we gave John a written
    # warning" and "someone used the slicer and got hurt" must LOG.
    r"^(?:we|i)(?:'ve| have| just|'ve just| have just)? "
    r"(?:gifted|gave away|comped|donated|handed out|used up|went through|"
    r"threw (?:out|away)|tossed|wasted)\b",
    # STOCKOUT / LOW — "we ran out of salads again", "we're low on cups"
    r"^(?:we|i)(?:'re|'ve| are| have| am)?\s*(?:completely |all |totally |almost )?"
    r"(?:ran out of|run out of|out of|used the last of|have no more|"
    r"running low on|low on)\b",
    # RECEIPT — "we received the produce order", "we restocked napkins"
    r"^(?:we|i)(?: just)? (?:received|restocked|got in|"
    r"got (?:a|the|our) (?:delivery|shipment|order)(?: of)?)\b",
    # ORDER REQUEST — tense-exact like SCHEDULE's \bneed\b
    r"^(?:we|i)(?:'ll| will)? need to (?:order|re-?order|re-?stock|buy)\b",
)
_INVENTORY_RE = tuple(re.compile(p, re.IGNORECASE) for p in _INVENTORY_PATTERNS)
```
In `classify_intent` (:174): insert the `_INVENTORY_RE` loop **after the `_SCHEDULE_RE` loop
(:196-198) and before the `_RECALL_RE` loop (:200)**; update the docstring's ordering-contract
sentence. Result order: HELP → LINK → SCHEDULE → INVENTORY → RECALL(ASK) → interrogative(ASK) →
LOG. "did we run out of cups?" hits `_RECALL_PATTERNS`' `^(?:did|have|has) (?:we|...)` (:77)
only because INVENTORY's `^(?:we|i)` doesn't match a `did`-lead — verify in tests.

**Tests** — new `server/tests/ems/test_intent_inventory.py` (model `test_intent_schedule.py`):
- INVENTORY positives: `"@huume we gifted some Cherry Farms cookies to Elizabeth our manager"`,
  `"@huume we ran out of salads again"`, `"we're low on cups"`, `"we used up the last coffee
  filters"` (via "used up"), `"we received the produce delivery"`, `"we need to reorder napkins"`,
  `"hey @huume we ran out of salads"` (greeting strip).
- LOG negatives (bias-to-LOG): `"we gave John a written warning"`, `"someone used the slicer and
  got hurt"`, `"we needed more staff last night and someone got hurt"`, `"customer threw a chair"`
  ("threw" without out/away), `"the walk-in ran all night"`.
- ASK negatives: `"did we run out of cups?"` → ASK, `"how many cookies do we have?"` → ASK,
  `"what did we order last week"` → ASK (recall).
- Non-regression: every existing SCHEDULE/LINK/HELP example in `test_ems_intent.py` still
  classifies the same (import + rerun a representative subset).

### 5. Extraction + DB services

**`services/inventory/extraction.py`** (mirror `event_intake.classify_event:432` — one JSON-mode
`GEMINI_FLASH_LITE` call, no conn held by caller):
```python
async def extract_inventory(content: str, item_names: list[str]) -> dict
    # prompt lists existing item names so the model reuses them; returns
    # {actionable: bool,
    #  kind: 'movement'|'stockout'|'receipt'|'order_request',
    #  lines: [{item_name: str, quantity: float|None, unit: str|None,
    #           direction: 'out'|'in'}],
    #  recipient_note: str|None}      # "gifted to Elizabeth (manager)"
def fallback_extraction(content: str) -> dict
    # deterministic: intent-verb kind + first-number regex; single line;
    # actionable=False when no item text can be isolated
    # (caller then falls back to _bg_ems_intake — documentation survives outage)
```

**`services/inventory/movements.py`**
```python
async def list_item_names(conn, company_id) -> list[dict]      # id/name/normalized_name, live only
async def find_or_create_item(conn, company_id, raw_name, *, created_by) -> dict
    # matching.best_match over list_item_names; miss ->
    # INSERT ... ON CONFLICT (company_id, normalized_name) WHERE archived_at IS NULL
    #   DO NOTHING; re-select (race belt)
async def record_movements(conn, *, company_id, channel_id, source_message_id,
                           recorded_by, kind, lines, narrative, note) -> list[dict]
    # transactional; per line: INSERT movement ON CONFLICT (source_message_id, item_id)
    # DO NOTHING (WS replay); then NULL-safe count update:
    #   UPDATE inventory_items SET current_quantity = CASE
    #     WHEN current_quantity IS NULL THEN NULL
    #     ELSE GREATEST(current_quantity + $delta, 0) END, updated_at = NOW()
    # kind='stockout' -> SET current_quantity = 0
    # returns inserted movement rows (skips replay-deduped ones)
async def amend_movement_quantity(conn, *, movement_id, quantity, user_id) -> Optional[dict]
    # only WHERE quantity_estimated; recompute delta vs old, apply diff to item count,
    # stamp amended_by/amended_at, clear quantity_estimated
async def adjust_item_count(conn, *, item_id, company_id, quantity, user_id) -> dict
    # writes kind='adjust' movement with delta = new - old (old NULL -> delta NULL),
    # sets the count; THE only set-count path (REST PATCH uses it)
```

**`services/inventory/orders.py`**
```python
async def stage_order(conn, *, company_id, item_id, channel_id, source_message_id,
                      created_by, suggestion: Optional[dict]) -> dict
    # INSERT ... ON CONFLICT ON CONSTRAINT-less: rely on uniq_inventory_orders_open via
    # INSERT ... ON CONFLICT (item_id) WHERE status='queued' DO UPDATE
    #   SET suggestion = EXCLUDED.suggestion, updated_at = NOW()
    # RETURNING * (repeat stockout re-points at the existing queued order)
async def approve_order(conn, *, order_id, company_id, user_id, quantity=None) -> dict
    # queued -> ordered; quantity override; stamps approved_by/at + ordered_at
async def cancel_order(conn, *, order_id, company_id, user_id) -> dict
async def mark_received(conn, *, order_id, company_id, user_id, quantity=None) -> dict
    # ordered|queued -> received; writes the 'in' movement via record_movements
    # (kind='in', no source_message_id) + links receipt_movement_id
# every function re-asserts rules.evaluate_inventory_action(stage="approve_order")
# for approve/cancel/receive; movement stage for the rest
```

### 6. Models + REST router

**`server/app/matcha/models/inventory.py`** (Pydantic v2):
```python
MovementKind = Literal["out", "in", "stockout", "adjust"]
OrderStatus = Literal["queued", "ordered", "received", "cancelled"]

class InventoryItemOut(BaseModel):        # + open_order: Optional[OrderOut], suggestion: Optional[dict]
class InventoryItemCreate(BaseModel):     # name, unit?, current_quantity?, low_stock_threshold?
class InventoryItemPatch(BaseModel):      # name?, unit?, low_stock_threshold?, set_quantity?, archived?
class MovementOut(BaseModel)
class OrderOut(BaseModel)
class OrderCreate(BaseModel)              # item_id, quantity?
class OrderAction(BaseModel)              # quantity: Optional[Decimal] (approve/receive override)
class ItemListResponse / MovementListResponse / OrderListResponse
```

**`server/app/matcha/routes/inventory.py`** — `router = APIRouter()`, every route
`Depends(require_admin_or_client)` + `get_client_company_id`, company-scoped SQL, no per-route
feature gate (mount-level):
```
GET    /items?include_archived=      list + open-order/suggestion LEFT JOIN
POST   /items                        manual create (normalized-name conflict -> 409)
GET    /items/{item_id}              detail + last 50 movements
PATCH  /items/{item_id}              rename/unit/threshold/archive; set_quantity ->
                                     movements.adjust_item_count (never a bare column write)
GET    /movements?item_id=&limit=&offset=
GET    /orders?status=
POST   /orders                       manual stage (orders.stage_order, no suggestion)
POST   /orders/{order_id}/approve    body OrderAction
POST   /orders/{order_id}/receive    body OrderAction
POST   /orders/{order_id}/cancel
GET    /suggestions                  reorder.suggest_order per active item, computed on read
```
Mount in `routes/__init__.py` beside ems (~:150):
```python
matcha_router.include_router(inventory_router, prefix="/inventory", tags=["inventory"],
                             dependencies=[Depends(require_feature("inventory"))])
```
Archive only — no delete/merge in v1.

### 7. WS wiring (`server/app/werk/routes/channels_ws.py`)

- Generalize the gate pair (:152-192): `_ems_row_allowed(row)` → `_flag_row_allowed(row, flag)`
  with `_ems_row_allowed` kept as a wrapper; add
  `_inventory_company_gate(conn, channel_id_str) -> Optional[UUID]` and
  `_inventory_flag_enabled(conn, company_id) -> bool` beside the EMS pair.
- ```python
  async def _bg_inventory_request(channel_id_str: str, message_id_str: str,
                                  sender_user_id_str: str, content: str) -> None
  ```
  Same off-hot-path / top-level-except / two-connection-block contract as
  `_bg_schedule_request` (:381-450):
  1. conn block 1: `_inventory_company_gate`; None → if `_ems_company_gate` passes, delegate
     `_bg_ems_intake` and return, else return.
  2. `check_rate_limit(str(company_id), "inventory_event", 30, 3600)` — over limit: silent
     return (mirror :416-419).
  3. Deterministic OSHA check: `fallback_classification(content)["urgency"] == "osha"` → also
     spawn `_bg_ems_intake` (dual-write) and continue.
  4. `evaluate_inventory_action(role, features, stage="movement")`; refusal → verdict pill.
  5. Fetch `list_item_names`, release conn; `extract_inventory` with **no conn held**.
  6. `actionable=False` → `await _bg_ems_intake(...)`, return.
  7. conn block 2: kind `movement`/`receipt` → `record_movements`; exactly one line with
     `quantity=None` → qty=1 estimated + arm `clarify_message_id` on the pill row (multiple
     unknowns: all estimated, pill points at the page, no clarify). Kind `stockout` /
     `order_request` → stockout movement (stockout only) → fetch item history →
     `reorder.suggest_order` → `orders.stage_order` → pill via `stockout_pill` → stamp
     `confirm_message_id = sys_row["id"]`.
  8. `_insert_system_message` + `broadcast_system_message` after the conn releases.
- ```python
  async def _bg_inventory_reply(channel_id_str: str, reply_to_id_str: str,
                                sender_user_id_str: str, content: str) -> bool
  ```
  Claim chain, exception-safe like `_bg_schedule_reply` (:453-629):
  (a) order-confirm claim:
  ```sql
  UPDATE inventory_orders SET confirm_message_id = NULL, updated_at = NOW()
  WHERE confirm_message_id = $1 AND status = 'queued'
    AND created_at > NOW() - INTERVAL '7 days'
  RETURNING id, company_id, item_id, suggested_quantity, quantity, suggestion
  ```
  Then re-assert verdict on the REPLIER (refusal → re-arm on the ORIGINAL pill id, mirror
  :531-539); `parse_confirm_reply(strip_mention(content))`: `confirm` → `approve_order` +
  confirmed pill; `cancel` → `cancel_order`; else `parse_quantity_reply` → update `quantity` +
  fresh pill re-armed; else `rearm_pill` + re-arm. No Gemini anywhere in this path.
  (b) claim miss → movement clarify claim on `inventory_movements.clarify_message_id` (same
  UPDATE...RETURNING shape); numeric reply → `amend_movement_quantity` + updated-count pill;
  non-numeric → re-ask once (`clarify_rounds < 2`) else final "set it on the Inventory page"
  pill. Returns True iff either claim matched.
- `_bg_ems_dispatch` (:973): reply chain gains a third probe after `_bg_schedule_reply`
  (:1011-1015) → `claimed = await _bg_inventory_reply(...)`; mention fork (:1017-1027) adds
  `INVENTORY` to the lazy import and `elif intent == INVENTORY: await _bg_inventory_request(...)`.
  `_ems_dispatch_decision` (:960) unchanged — spawn/reply decision is intent-agnostic.

### 8. Huume thread-agent bridge (cheap parts only)

- `services/huume/tools.py`: `"inventory"` added to `LOOKUP_TOPICS`; `"inventory_item"` added to
  `SHOW_RECORD_TYPES`; mention both in the lookup/show tool descriptions.
- `services/huume/onboarding_skill.py`: topic→feature map entry `"inventory": "inventory"`
  (:128) + `if topic == "inventory":` branch (model: `"events"` branch :376) — items with
  counts + open orders, capped ~20 rows.
- `services/huume/record_view.py`: `RECORD_REQUIRED_FEATURE["inventory_item"] = "inventory"`;
  `_model_inventory_items_batch` + `_build_inventory_item_view` (item + last 10 movements + open
  order → the normalized `{title, chips, meta, sections, link}` shape) added to **both** builder
  dicts — the record-type parity test enforces key-set equality.
- NO staged chat actions (no approve-order Huume tool) in v1.

### 9. Frontend

- `client/src/work/api/inventory.ts` — typed wrappers over the Step-6 endpoints (model
  `work/api/events.ts`): `listItems`, `createItem`, `getItem`, `patchItem`, `listMovements`,
  `listOrders`, `createOrder`, `approveOrder`, `receiveOrder`, `cancelOrder`, `listSuggestions`.
- `client/src/work/components/inventory/ItemTable.tsx` (name/count/unit/threshold/open-order
  badge), `ItemDetail.tsx` (movement ledger + adjust-count form + archive), `OrderQueue.tsx`
  (approve/receive/cancel + suggestion basis line "~X/day, ran out every ~N days").
- `client/src/work/pages/InventoryHub.tsx` (model `EventsHub.tsx`; NOT "InventoryPanel" — taken).
- `WorkRouteTree.tsx`: sibling block to the ems FeatureGate (:46-55):
  `<FeatureGate feature="inventory" label="Inventory"><Outlet/></FeatureGate>` wrapping routes
  `inventory` and `inventory/:itemId` — one tree serves /work + /werk.
- `WorkSidebar.tsx`: `const showInventory = canReviewEvents(me?.user?.role) &&
  hasFeature('inventory')`; entry beside Events (~:222), `navigate(\`${base}/inventory\`)`.
- `featureCatalog.ts:54`: reword the `inventory` description to the live meaning.
- Pills: zero client work — 📦 renders via the existing `message_type='system'` branch in
  `MessageList.tsx`; only 🚨 first char goes urgent-red.

### 10. Docs

- `server/app/matcha/services/inventory/CLAUDE.md` — full feature spec: flag row content, intake
  flow, claim columns, invariants (bias-to-LOG fallback + EMS delegation, OSHA dual-write,
  append-only ledger + the single clarify-amendment exception, one-queued-order-per-item,
  NULL-count semantics), pilots-corpus skip justification.
- Root `CLAUDE.md`: `inventory` flag-table row (one-liner + `→ full spec:` pointer) + Key
  Modules bullet + subtree-docs table row.
- `server/CLAUDE.md` symbol map: "Inventory (channel stock tracking)" section (intent, WS
  handlers, service package, router).
- `server/app/werk/CLAUDE.md`: bump the werk→matcha.services edge inventory (new lazy imports of
  `matcha.services.inventory.*` from `channels_ws.py`) — the doc requires exact counts stay
  accurate.

## Verification

- Pure tests: `cd server && python3 -m pytest tests/inventory/ tests/ems/ -v` — matching,
  reorder math, rules/reply parsing, pills, intent positives/negatives + SCHEDULE/LINK/HELP
  non-regression, dispatch decision unchanged.
- `python3 -m py_compile` runs via the post-edit hook on every backend edit; frontend:
  `cd client && npx tsc -p tsconfig.app.json --noEmit` (bare `npx tsc --noEmit` checks nothing).
- Migration authored + committed only — the user runs `./scripts/migrate-dev.sh` /
  `migrate-prod.sh` themselves (never run alembic against a live DB without approval; rehearsal
  via `MIGRATE_REHEARSAL=1` is theirs to fire).
- Manual end-to-end (user, on dev): enable `matcha_work`+`inventory` (+`ems` for fallback) on a
  test company; post the two product example messages in a channel; verify the 📦 pills, the
  auto-created items, reply "confirm" on the order pill; check /work Inventory page ledger +
  order queue; reply a number to a "how many?" pill. Test data uses RFC 2606 domains only.
- Scope ends at commit + push to `claude/huume-inventory-system-hsh7m1` (cloud session: no
  build/deploy, no PR unless asked).

## Risks / open questions

- Multiple alembic heads repo-wide; re-point `down_revision` if something lands on `ems02` first.
- "low on" folded into the STOCKOUT pattern (extractor distinguishes `kind`; only a true stockout
  zeroes the count) — drop from the regex if too aggressive (one-line change).
- One clarify question per pill: v1 arms it only when exactly one line lacks quantity.
- Item merge (near-dupe items surviving fuzzy match) and unit conversion ("2 cases" vs "48
  cookies") deferred — documented v1 limitations in the service CLAUDE.md.
